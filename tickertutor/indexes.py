"""The big US stock market indexes, and the funds Ticker Tutor uses to follow them.

An index itself can't be bought and its official level leaves out dividends, so
Ticker Tutor uses the price of a large fund that tracks each one. Those funds'
adjusted prices include dividends, which makes their returns comparable with
the stocks' returns everywhere in the app.
"""

from __future__ import annotations

import re

INDEXES = [
    {
        "id": "sp500", "ticker": "SPY", "name": "S&P 500", "label": "S&P 500", "short": "500 large US companies",
        "fund": "SPDR S&P 500 ETF Trust (SPY)",
        "about": "About 500 of the largest US companies, chosen by a committee at S&P Dow Jones Indices. Bigger "
                 "companies count for more (it's weighted by company value). It covers roughly 80% of the value of "
                 "the US stock market, so when people say \"the market\" they usually mean this one.",
        "watch": "A handful of the largest companies make up a big share of it, so it can rise or fall with just a few names.",
        "started": "1957", "members": "About 500", "weighting": "By company value",
    },
    {
        "id": "nasdaq100", "ticker": "QQQ", "name": "Nasdaq-100", "label": "Nasdaq-100", "short": "100 largest Nasdaq companies",
        "fund": "Invesco QQQ Trust (QQQ)",
        "about": "The 100 largest companies listed on the Nasdaq stock exchange, leaving out banks and other financial "
                 "companies. It leans heavily toward technology. The \"Nasdaq\" on the evening news is usually the "
                 "Nasdaq Composite, which holds every stock on the exchange (several thousand) and moves very much like "
                 "the Nasdaq-100.",
        "watch": "With so much technology in it, it tends to swing more than the S&P 500 in both directions.",
        "started": "1985", "members": "About 100", "weighting": "By company value, with caps on the largest",
    },
    {
        "id": "dow", "ticker": "DIA", "name": "Dow Jones Industrial Average", "label": "Dow Jones", "short": "30 well-known US companies",
        "fund": "SPDR Dow Jones Industrial Average ETF Trust (DIA)",
        "about": "Thirty large, well-known US companies picked by a committee. Started in 1896, it's the oldest of "
                 "these. Unlike the others it's weighted by share price, not company size: a stock trading at $500 a "
                 "share moves the Dow more than one at $50, even if the $50 company is bigger.",
        "watch": "Thirty stocks and price weighting make it a narrow, somewhat quirky view of the market, even though "
                 "it's the number most often quoted on the news.",
        "started": "1896", "members": "30", "weighting": "By share price",
    },
    {
        "id": "russell2000", "ticker": "IWM", "name": "Russell 2000", "label": "Russell 2000", "short": "2,000 smaller US companies",
        "fund": "iShares Russell 2000 ETF (IWM)",
        "about": "About 2,000 smaller US companies (\"small caps\"), run by FTSE Russell. It's the standard way to see "
                 "how smaller companies are doing, which can differ a lot from the giants that dominate the S&P 500. "
                 "Ticker Tutor's stock list covers the S&P 500 only, so these smaller companies don't have their own pages here.",
        "watch": "Smaller companies tend to be more sensitive to the economy and interest rates, so it usually swings more.",
        "started": "1984", "members": "About 2,000", "weighting": "By company value",
    },
]

BY_TICKER = {i["ticker"]: i for i in INDEXES}
TICKERS = [i["ticker"] for i in INDEXES]

# Words people use for each index, for matching questions and searches.
ALIASES = {
    "SPY": ["s&p 500", "s&p500", "sp500", "s and p 500", "the s&p"],
    "QQQ": ["nasdaq-100", "nasdaq 100", "nasdaq100", "nasdaq composite", "the nasdaq", "nasdaq"],
    "DIA": ["dow jones industrial average", "dow jones", "the dow", "djia"],
    "IWM": ["russell 2000", "russell2000", "small caps", "small-cap index", "small cap index"],
}


def get(ticker: str | None) -> dict | None:
    return BY_TICKER.get((ticker or "").strip().upper())


def _has(text: str, phrase: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None


def find(text: str) -> list[dict]:
    """Indexes whose ticker, name, or common nickname appears in the text."""
    low = (text or "").lower()
    return [i for i in INDEXES
            if any(_has(low, w) for w in [i["name"].lower(), i["ticker"].lower(), *ALIASES.get(i["ticker"], [])])]
