"""SEC EDGAR: official company filings (free, no key; the SEC asks for a contact
email in the User-Agent header, set SEC_USER_AGENT).

  companyfacts   every number a company has tagged in its 10-K/10-Q filings
                 (XBRL, roughly 2009 onward), each with the date it was filed
  submissions    the list of filings: 10-K, 10-Q, 8-K (with item codes)
  documents      the filing text itself, e.g. the Risk Factors section of a 10-K
"""

from __future__ import annotations

import difflib
import html as htmllib
import re
import threading
import time

from .. import config
from . import SourceError, get

_lock = threading.Lock()
_last = [0.0]


def _sec_get(url: str, expect: str = "json"):
    with _lock:  # stay well under the SEC's 10 requests/second
        wait = 0.12 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
    return get(url, headers={"User-Agent": config.SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}, expect=expect)


def cik10(cik: int | str) -> str:
    return str(int(cik)).zfill(10)


# --- Fundamentals (XBRL company facts) -------------------------------------------------------------

# Our metric → XBRL concepts to try, in order (companies switch tags over time;
# values are merged by period, preferring earlier concepts in the list).
CONCEPTS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "RevenuesNetOfInterestExpense",
                "SalesRevenueGoodsNet"],
    "net_income": ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "operating_income": ["OperatingIncomeLoss"],
    "gross_profit": ["GrossProfit"],
    "eps_diluted": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"],
    "assets": ["Assets"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "long_term_debt": ["LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "dividends_per_share": ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"],
    "shares_outstanding": ["EntityCommonStockSharesOutstanding"],   # dei
    "diluted_shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}
INSTANT = {"assets", "equity", "long_term_debt", "cash", "shares_outstanding"}


def companyfacts(cik: int | str) -> dict:
    return _sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10(cik)}.json")


def extract_facts(raw: dict) -> list[dict]:
    """Flatten company facts into rows for the metrics above:
    {metric, concept, start, end, value, fy, fp, form, filed, accn}."""
    facts = raw.get("facts") or {}
    rows: list[dict] = []
    for metric, concepts in CONCEPTS.items():
        seen: set[tuple] = set()
        for rank, concept in enumerate(concepts):
            node = (facts.get("us-gaap") or {}).get(concept) or (facts.get("dei") or {}).get(concept)
            if not node:
                continue
            for unit, entries in (node.get("units") or {}).items():
                if metric == "eps_diluted" or metric == "dividends_per_share":
                    if unit != "USD/shares":
                        continue
                elif metric in ("shares_outstanding", "diluted_shares"):
                    if unit != "shares":
                        continue
                elif unit != "USD":
                    continue
                for e in entries:
                    form = e.get("form", "")
                    if not form.startswith(("10-K", "10-Q", "20-F", "40-F")):
                        continue
                    key = (e.get("start"), e.get("end"), e.get("filed"), e.get("fp"))
                    if key in seen:   # an earlier (preferred) concept already covered this period
                        continue
                    seen.add(key)
                    rows.append({"metric": metric, "concept": concept, "rank": rank, "start": e.get("start"),
                                 "end": e.get("end"), "value": e.get("val"), "fy": e.get("fy"), "fp": e.get("fp"),
                                 "form": form, "filed": e.get("filed"), "accn": e.get("accn")})
    return rows


# --- Filings list ---------------------------------------------------------------------------------------

ITEM_NAMES = {
    "1.01": "Material agreement", "1.02": "Agreement terminated", "1.03": "Bankruptcy", "2.01": "Acquisition or sale completed",
    "2.02": "Earnings results", "2.03": "New debt", "2.05": "Restructuring costs", "2.06": "Impairment",
    "3.01": "Listing notice", "4.01": "Auditor change", "4.02": "Restatement warning", "5.01": "Change in control",
    "5.02": "Executive or director change", "5.03": "Bylaws change", "5.07": "Shareholder vote results",
    "7.01": "Investor presentation (Reg FD)", "8.01": "Other events", "9.01": "Financial exhibits",
}


def submissions(cik: int | str) -> dict:
    return _sec_get(f"https://data.sec.gov/submissions/CIK{cik10(cik)}.json")


def submissions_all(cik: int | str, since: str = "2014-01-01") -> dict:
    """Like submissions(), but also pulls the older filing pages back to `since`. The "recent" block
    holds the latest ~1,000 filings, which for big companies can be only a few years."""
    raw = submissions(cik)
    recent = (raw.get("filings") or {}).get("recent") or {}
    for f in (raw.get("filings") or {}).get("files") or []:
        if (f.get("filingTo") or "9999") < since or not f.get("name"):
            continue
        older = _sec_get(f"https://data.sec.gov/submissions/{f['name']}")
        n = len(older.get("form", []))
        for key in list(recent):
            if isinstance(recent[key], list):
                recent[key].extend(older.get(key) or [""] * n)
    return raw


def filings(raw: dict, forms: tuple[str, ...] = ("10-K", "10-Q", "8-K")) -> list[dict]:
    recent = (raw.get("filings") or {}).get("recent") or {}
    cik = int(raw.get("cik") or 0)
    out = []
    n = len(recent.get("form", []))
    for i in range(n):
        form = recent["form"][i]
        if form not in forms:
            continue
        accn = recent["accessionNumber"][i]
        doc = recent.get("primaryDocument", [""] * n)[i]
        items = [x.strip() for x in (recent.get("items", [""] * n)[i] or "").split(",") if x.strip()]
        out.append({
            "form": form, "filed": recent["filingDate"][i], "report_date": (recent.get("reportDate") or [""] * n)[i],
            "accession": accn, "items": items, "item_names": [ITEM_NAMES.get(x, f"Item {x}") for x in items],
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{doc}" if doc else
                   f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
        })
    return out


# --- Filing text: Risk Factors (10-K Item 1A) ----------------------------------------------------------------

def html_to_text(page: str) -> str:
    page = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", page)
    page = re.sub(r"<[^>]+>", " ", page)
    page = htmllib.unescape(page).replace("\xa0", " ")
    page = re.sub(r"[ \t]+", " ", page)
    return re.sub(r"\n\s*\n+", "\n", page).strip()


SECTIONS = {
    "risk_factors": (r"item\s*1a\.?\s*[\-–—:]?\s*risk\s*factors", r"item\s*1b\.?|item\s*1c\.?|item\s*2\.?\s*[\-–—:]?\s*properties"),
    "business": (r"item\s*1\.?\s*[\-–—:]?\s*business", r"item\s*1a\.?\s*[\-–—:]?\s*risk\s*factors"),
}


def section(text: str, name: str) -> str:
    """The longest span between the section's heading and the next one (skips the
    table of contents, where the same headings appear close together)."""
    start_re, end_re = SECTIONS[name]
    best = ""
    for m in re.finditer(start_re, text, re.I):
        rest = text[m.end():]
        e = re.search(end_re, rest, re.I)
        chunk = rest[: e.start()] if e else rest[:200_000]
        if len(chunk) > len(best):
            best = chunk
    return best.strip()


def paragraphs(text: str, min_len: int = 60) -> list[str]:
    return [p.strip() for p in text.split("\n") if len(p.strip()) >= min_len]


def risk_titles(text: str) -> list[str]:
    """Risk-factor headings: short-ish lines that read like a sentence-long title."""
    out = []
    for p in text.split("\n"):
        p = p.strip()
        if 40 <= len(p) <= 320 and p[-1:] in ".:" and not p.lower().startswith(("table of contents", "item")):
            out.append(p)
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", s.lower())


def compare_lists(new: list[str], old: list[str], threshold: float = 0.72) -> dict:
    """Which items are new, and which disappeared (fuzzy match, so small rewording
    doesn't count as a change)."""
    old_n = [_norm(x) for x in old]
    new_n = [_norm(x) for x in new]

    def matched(s: str, pool: list[str]) -> bool:
        if s in pool:
            return True
        close = difflib.get_close_matches(s, pool, n=1, cutoff=threshold)
        return bool(close)

    added = [new[i] for i, s in enumerate(new_n) if not matched(s, old_n)]
    removed = [old[i] for i, s in enumerate(old_n) if not matched(s, new_n)]
    return {"added": added, "removed": removed}


def filing_text(url: str) -> str:
    raw = _sec_get(url, expect="text")
    if not raw:
        raise SourceError("The filing document was empty.")
    return html_to_text(raw)
