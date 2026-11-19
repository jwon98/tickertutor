# Ticker Tutor

**Learn to analyze S&P 500 stocks yourself.** Ticker Tutor is a hands-on place for beginners to learn how stocks are analyzed. Look up any company in the S&P 500 or one of the four big US market indexes (S&P 500, Nasdaq-100, Dow Jones Industrial Average, Russell 2000), run the analyses people use most (moving averages, trend lines, MACD, RSI, momentum, volatility, Bollinger Bands, drawdowns, beta, performance vs the index, rolling returns, return distributions, volume) over any period you choose, and read what each number means, how it's calculated, how to interpret it, and what to watch out for. A deep-research agent team answers bigger questions in plain words and cites every number.

Deployed app: see `deploy_url` in [`submission.json`](submission.json). Path: **Deep Research**.

> Ticker Tutor is an educational project, not financial advice. It explains analyses and evidence. It doesn't recommend buying or selling anything, and past results don't guarantee future returns.

## Who it's for

Someone new to investing who keeps hearing "it's above its 200-day average," "RSI says it's oversold," or "it's a low-beta stock," and wants to understand what those mean, try them on real companies, and see whether any of them have actually mattered historically. Ticker Tutor teaches the analysis. It never tells anyone what to buy, doesn't rank stocks as good or bad, and doesn't do day-trading timing, options, shorting, crypto, or personal financial or tax advice.

## What's in the app

| Page | What it shows |
|---|---|
| **Home** (click "Ticker Tutor") | What Ticker Tutor is and who it's for in one screen: a search box for any company or index, a live chart of the S&P 500's past year with a tutor's handwritten notes on it (each note opens that analysis), and the three steps for using the app. |
| **How it works** | A five-step walkthrough with a place to start at each step, then every analysis you can run, and three things worth knowing about the data. |
| **Screener** | The four big indexes across the top (past-year return with a sparkline, plus 1 day, 1 month, and this year; each opens its index page), then every S&P 500 company with its key numbers, **grouped by sector** (the default: a treemap sized by company value and colored by return over a period you pick) or one by one in a sortable table. |
| **Analyze** | Starts with a search box and a few places to begin (the four indexes, this week's biggest movers, the largest companies), and shows nothing until you pick one. Then choose one of 13 analyses and a period (1 month to all history, or custom dates), adjust its settings, and get the chart(s), the key numbers, a plain-language readout, and an explanation: what it is, how it's calculated, how to read it, what to watch out for. Where a popular signal is involved, a "What history shows" panel gives its backtested track record across S&P 500 stocks. For an index, "performance" compares it with the other three indexes. |
| **Stock** | Price chart (starts on year to date with just the price; ranges from 1 month to all history or custom dates, with optional 50-day and 200-day averages and the S&P 500), finances from SEC filings, returns vs the S&P 500 and the stock's sector fund, links to every analysis for that stock, risk numbers, earnings reactions, and news. Each term has a **?** that opens its definition on Learn. |
| **Index** | The same layout for an index: chart, returns next to the other three indexes, every analysis, what the index is and what to keep in mind, risk numbers, and, for the S&P 500, its ten largest companies and their share of the index. |
| **In the news** | Big one-day moves grouped by day, each with the headlines from around that day that name the company (stories tagged with the ticker but about the market or a rival are left out), how many times the stock's typical day it was, and links to open it on Analyze or ask the research desk why. Next to it, the week's and month's biggest gains and losses. Also what has historically followed moves like these and sector momentum. Headlines are fetched fresh when the page opens. |
| **Research desk** | Ask a question; watch the Lead, parallel Researchers, Writer, and Verifier work live; get a short cited report that ends with analyses to try yourself. The example questions are researched ahead of time (see below), so they're ready in about ten seconds, and the other examples stay at the end of the conversation to try next. |
| **Learn** | A card for each market index, the sectors, a searchable glossary of 80 terms in groups, including the words that show up in headlines (every **?** across the app links to one, and the card is highlighted when you arrive), how signals are backtested, taxes and the one-year mark, what the data can't tell you, and where the data comes from. |

Each tab remembers what it was showing. Open AAPL from the Screener, look at something on Analyze, and the Screener tab takes you back to AAPL at the same scroll position. Clicking the tab you're already on returns to its start.

## Sample questions

Ask these on the **Research desk** (or `POST /chat`). Exact numbers depend on the date the database was built, so each sample lists what a correct answer contains and the table or endpoint that holds the evidence, with a query you can run to check it. Run a check query with `uv run python scripts/sql.py "<query>"`.

**1. "Walk me through Microsoft's (MSFT) trend over the past year using moving averages and RSI, and compare its volatility with the S&P 500's."**

- *Expected answer:* where MSFT closed relative to its 50- and 200-day averages and whether/when they crossed in the past year; its 14-day RSI now and how often it was above 70 or below 30; its annualized volatility over the year next to the S&P 500's and the typical daily move; one sentence on how to read each; the backtested track record of "above the 200-day average" (and the golden cross) across S&P 500 stocks; a note that none of this predicts the next move; and which analyses to run on the Analyze tab.
- *Sources:* daily prices in table `prices` through the analysis engine (`/api/analysis?ticker=MSFT&a=moving_averages&period=1y`, `a=rsi`, `a=volatility`), and `signal_cards` (`above_200d`, `golden_cross`). Tools: `run_analysis`, `get_signal_track_record`, `get_stock_snapshot`.
- *Check:* open `#/analyze?t=MSFT&a=moving_averages&p=1y` (then `a=rsi` and `a=volatility`), or `SELECT price, sma50, sma200, rsi14, vol_1y FROM snapshot WHERE ticker = 'MSFT'`

**2. "Does buying the dip work for S&P 500 stocks? What has happened after big one-day drops?"**

- *Expected answer:* the report card for "down 20%+ from its 52-week high" (verdict, how often those stocks beat the index over the next year vs the rest, the extra return and its 95% range, and whether it held in the recent held-out years) and for "RSI oversold"; the base rates after one-day drops of 5%+ vs the index and after earnings drops of 3%+ (average return vs the index afterwards, share that beat it, ranges). It should give the verdict the data supports (which may well be "did worse" or "no clear edge") and note survivorship and overlapping-window caveats.
- *Sources:* tables `signal_cards` (signal ids `big_dip`, `rsi_oversold`) and `events` (`one_day_drop`, `earnings_down`). Tools: `get_signal_track_record`, `get_recent_moves`, `query_database`.
- *Check:* `SELECT signal_id, verdict, hit_on, hit_off, diff, diff_lo, diff_hi, oos_diff FROM signal_cards WHERE universe = 'All' AND signal_id IN ('big_dip', 'rsi_oversold')` and `SELECT * FROM events WHERE event IN ('one_day_drop', 'earnings_down')`

**3. "Why is Nvidia down so much lately?"** (any covered company works, and blunt wording like "why is nvidia down so bad?" is fine)

- *Expected answer:* two halves. *The news:* the headlines and 8-K filings from around the days the price moved, with dates and links, or a plain statement that the news doesn't clearly explain it. *The numbers:* NVDA's return over the past day, week, and month next to the S&P 500 and its sector fund, how far it is below its 52-week high, and its biggest down days with how many times its typical daily move each one was and how rarely days that extreme have happened in its history. Then the base rate for what followed similar one-day drops across S&P 500 stocks, a note that headlines explain the past and not what comes next, and links to the In the news tab and to the daily-returns and drawdown analyses for NVDA. If NVDA happens to be up when you ask, a correct answer says so and describes the move it finds.
- *Sources:* table `prices` through `get_price_move` and `run_analysis` (`drawdown`, `returns_distribution`); tables `recent_moves`, `events`, and `filings`; Finnhub `/company-news` (live) or the `news` snapshot. Tools: `get_price_move`, `get_company_news`, `get_recent_moves`, `get_recent_filings`, `run_analysis`, `web_search`.
- *Check:* open `#/analyze?t=NVDA&a=returns_distribution&p=1y` and `#/analyze?t=NVDA&a=drawdown&p=1y`, or `SELECT date, adj_close FROM prices WHERE ticker = 'NVDA' ORDER BY date DESC LIMIT 30` and `SELECT date, kind, ret_1d, excess_1d FROM recent_moves WHERE ticker = 'NVDA'`

**Also try:** *"What were the biggest one-day moves among S&P 500 stocks recently, and what news was behind them?"*, *"How have the Nasdaq-100 and the Russell 2000 done against the S&P 500 over the past three years, and which swung more?"* (runs the analyses on the index funds), *"What should I buy?"* (Ticker Tutor doesn't pick stocks: the Lead asks one clarifying question that turns it into something to analyze, with suggested answers, and remembers your reply), *"Should I buy Bitcoin?"* (out of scope: says what Ticker Tutor covers instead), and a follow-up like *"How does that compare over five years?"* after sample 1.

### Same model, without Ticker Tutor

The same Gemini model, asked the same questions with no tools and no system prompt, for comparison. Regenerate with `uv run python scripts/baseline_compare.py` after building the real database (full transcripts, including every tool call, go to [`docs/baseline.md`](docs/baseline.md)).

<!-- baseline:start -->
_Generated by `scripts/baseline_compare.py` with `gemini-3.8-flash` on data as of 2026-11-17._

#### Sample 1: Walk me through Microsoft's (MSFT) trend over the past year using moving averages and RSI, and compare its volatility with the S&P 500's.

Research team: 2 researchers, 8 tool calls, 6 cited sources, 28 s. Same model without tools: no data access, no citations.

<details><summary><b>Ticker Tutor's answer</b></summary>

### In short
Over the past year, Microsoft (MSFT) has maintained a broader upward trend marked by a golden cross, but it is currently showing short-term softness below its 50-day average [1][2]. Its momentum sits in neutral territory, while its price swings have been over twice as volatile as the broader market [3][4][5]. 

### What the numbers show
* **Trend (Moving Averages):** MSFT closed at $506.24 on November 17, 2026. This sits 2.6% below its 50-day simple moving average ($519.61) but 14.7% above its 200-day simple moving average ($441.37) [1][2]. A moving average smooths out daily price noise to show the general direction of a trend over time. The 50-day average crossed above the 200-day average on August 28, 2026—a pattern known as a "golden cross" [1].
* **Momentum (RSI):** MSFT's 14-day Relative Strength Index (RSI) is at 42 (snapshot reading 41.86) [3][2]. RSI measures how fast and how far a stock has moved recently on a scale of 0 to 100, where readings above 70 suggest overbought conditions and below 30 suggest oversold conditions; 42 represents neutral momentum [3]. 
* **Volatility:** MSFT’s annualized volatility over the 1-year period was 34.0% (with a typical daily move of ±2.1%), compared to 13.8% (±0.9% daily) for the S&P 500 ETF (SPY) [4][5]. Volatility simply measures how wildly an asset's price fluctuates.
* **Market Risk (Beta & Correlation):** MSFT’s 1-year beta relative to the S&P 500 was 1.01, with a correlation of 0.41 and an R² of 16.7% [6]. Beta compares a stock’s sensitivity to broad market moves, where a beta of 1.0 moves in tandem with the index; here, the low R² indicates that roughly 83% of MSFT’s daily moves came from company-specific factors rather than the market [6].

### What history says
A golden cross is widely watched as a sign of positive long-term momentum [1]. However, across broad historical studies of S&P 500 stocks, technical patterns like moving average crossovers and RSI levels do not offer guaranteed outcomes or a clear statistical edge on their own, and false signals frequently occur. 

### What the data can't tell you
These technical indicators only summarize past price movements. They cannot account for upcoming earnings reports, unexpected regulatory shifts, or macroeconomic surprises, and no indicator can predict future stock prices.

### Try it yourself
To inspect these metrics directly, you can explore the following analyses over a 1-year window on Ticker Tutor:
* [Moving averages for MSFT](#/analyze?t=MSFT&a=moving_averages&p=1y)
* [RSI for MSFT](#/analyze?t=MSFT&a=rsi&p=1y)
* [Volatility for MSFT](#/analyze?t=MSFT&a=volatility&p=1y)
* [Beta & correlation for MSFT](#/analyze?t=MSFT&a=beta&p=1y)
* [Volatility for SPY](#/analyze?t=SPY&a=volatility&p=1y)

_Educational, not financial advice. Ticker Tutor explains analyses and evidence. It doesn't recommend buying or selling anything, and past results don't guarantee future returns._

**Sources**
1. Ticker Tutor analysis: Moving averages for MSFT, 2025-11-17 to 2026-11-17 — `run_analysis(MSFT, moving_averages, 2025-11-17..2026-11-17, Short average (days) 50, Long average (days) 200) on daily adjusted prices`
2. Ticker Tutor database: snapshot, as of 2026-11-17 — `get_stock_snapshot(MSFT)`
3. Ticker Tutor analysis: RSI for MSFT, 2025-11-17 to 2026-11-17 — `run_analysis(MSFT, rsi, 2025-11-17..2026-11-17, Look-back (days) 14, Overbought line 70, Oversold line 30) on daily adjusted prices`
4. Ticker Tutor analysis: Volatility for MSFT, 2025-11-17 to 2026-11-17 — `run_analysis(MSFT, volatility, 2025-11-17..2026-11-17, Rolling window (days) 21) on daily adjusted prices`
5. Ticker Tutor analysis: Volatility for SPY (S&P 500 fund), 2025-11-17 to 2026-11-17 — `run_analysis(SPY, volatility, 2025-11-17..2026-11-17, Rolling window (days) 21) on daily adjusted prices`
6. Ticker Tutor analysis: Beta & correlation for MSFT, 2025-11-17 to 2026-11-17 — `run_analysis(MSFT, beta, 2025-11-17..2026-11-17, Rolling window 126) on daily adjusted prices`

</details>

<details><summary><b>Same model, no tools, no system prompt</b></summary>

> Here is a technical and volatility breakdown of **Microsoft (MSFT)** over the past year (mid-2023 to mid-2024), focusing on moving averages, RSI, and its comparative volatility to the broader market (S&P 500).
>
> ---
>
> ### 1. Trend Analysis via Moving Averages (50-Day and 200-Day SMA)
>
> Over the past year, MSFT has operated primarily in a **strong, sustained macro uptrend**, driven largely by the AI boom and consistent enterprise cloud earnings, though it has experienced periodic consolidation phases.
>
> *   **The 200-Day Simple Moving Average (SMA) – Macro Baseline:** 
>     *   MSFT has traded predominantly **above its 200-day SMA** for the vast majority of the past 12 months. This confirms that the long-term institutional trend has remained firmly bullish.
>     *   Whenever the stock experienced broader market sell-offs (such as in late summer/early autumn 2023), the 200-day SMA acted as a dynamic, foundational support level from which buyers repeatedly stepped in.
> *   **The 50-Day SMA – Medium-Term Momentum:**
>     *   The 50-day SMA remained sloping upward, spending almost the entire year stacked *above* the 200-day SMA (a sustained "Golden Cross" environment). 
>     *   During strong impulse moves (e.g., late 2023 through early 2024), the 50-day average acted as short-term support during routine pullbacks.
>     *   **Recent Shift / Consolidation:** In recent months, MSFT has repeatedly tested and oscillated around its 50-day moving average. A flattening 50-day SMA indicates that the steep, aggressive rally has transitioned into a broader horizontal consolidation or range-bound regime as the market digests elevated valuations.
>
> ---
>
> ### 2. Momentum and Overbought/Oversold Cycles via RSI (14-Day)
>
> The 14-day Relative Strength Index (RSI) highlights how MSFT’s momentum has ebbed and flowed across distinct market phases:
>
> *   **Bullish Regime Characteristics (RSI 40–80):**
>     *   During the primary trend advances over the past year, MSFT exhibited textbook bull-market RSI behavior: dips routinely found support around the **40–45 zone** rather than dropping fully into oversold territory (below 30).
>     *   The stock periodically pushed into **overbought conditions (RSI > 70)** following major catalysts (such as earnings beats, OpenAI-related product announcements, and Copilot integration milestones).
> *   **Bearish Divergences and Cooling Off:**
>     *   At various interim peaks (notably early 2024), the RSI began printing **lower highs while price action printed higher highs** (a classic bearish divergence). This signaled that the upward velocity was slowing down, which correctly foreshadowed multi-week pauses and pullbacks back to the 50-day SMA.
> *   **Current State:** 
>     *   The RSI has spent recent stretches hovering near the neutral **50 level**, reflecting market indecision and a balance between aggressive accumulation and profit-taking.
>
> ---
>
> ### 3. Volatility Comparison: MSFT vs. S&P 500 (SPY)
>
> To compare MSFT’s volatility to the broader market, we look at **Beta**, **Realized (Historical) Volatility**, and response to macro drawdowns:
>
> | Metric | Microsoft (MSFT) | S&P 500 (SPX/SPY) | Interpretation |
> | :--- | :--- | :--- | :--- |
> | **Beta (1-Year)** | ~1.15 to 1.25 | 1.00 (Benchmark) | MSFT moves in the same direction as the market, but with roughly **15% to 25% higher amplitude**. |
> | **Annualized Volatility** | ~20% – 24% | ~12% – 14% | MSFT exhibits wider daily percentage price swings than the diversified index. |
> | **Drawdown Depth** | Moderate (~8%–12%) | Mild to Moderate (~5%–10%) | Corrections in MSFT tend to be slightly deeper, but recovery times have historically been faster over this period. |
>
> #### Key Takeaways on Volatility:
> 1.  **Lower Volatility than Big Tech Peers:** While MSFT is more volatile than the S&P 500 due to single-stock idiosyncratic risk, it remains one of the **least volatile mega-cap tech equities**. Its massive recurring revenue base (SaaS, Azure, Windows enterprise contracts) gives it a lower annualized volatility profile compared to high-beta peers like Nvidia (NVDA), Tesla (TSLA), or Meta (META).
> 2.  **Market-Driving Influence:** Because Microsoft represents roughly 6.5% to 7% of the S&P 500's total weighting, it has a circular relationship with index volatility: spikes in MSFT’s volatility often transmit directly into the S&P 500's volatility (VIX).
> 3.  **Earnings Volatility Imbalance:** Most of MSFT’s excess volatility relative to the index is clustered around its quarterly earnings prints, where guidance on Azure growth or AI capital expenditures can produce instantaneous 3% to 5% intraday gaps.
>
> ---
>
> ### Summary
> *   **Moving Averages:** Bullish macro trend confirmed by price holding above a rising 200-day SMA, though a flattening 50-day SMA indicates medium-term range-bound digestion.
> *   **RSI:** Reflects an overall healthy bull regime (support near 40, periodic excursions above 70), currently neutralizing near 50 as momentum levels off.
> *   **Volatility:** Exhibits higher baseline volatility than the S&P 500 (Beta ~1.2), yet operates with significantly more stability and shallower drawdowns than most of its mega-cap tech and semiconductor counterparts.

</details>

#### Sample 2: Does buying the dip work for S&P 500 stocks? What has happened after big one-day drops?

Research team: 2 researchers, 7 tool calls, 7 cited sources, 29 s. Same model without tools: no data access, no citations.

<details><summary><b>Ticker Tutor's answer</b></summary>

### In short
Historically, the S&P 500 index (SPY) has eventually recovered from large pullbacks, but the time it takes can vary from a couple of weeks to well over a year. While individual stocks often rebound after sharp single-day plunges, simply buying every stock that has fallen significantly from its highs has shown no clear performance edge over the broader market.

### What the numbers show
* **Broad market index drawdowns**: Over the 5-year period through November 17, 2026, SPY's largest drawdown was a 24.5% decline between January and October 2022, which took 427 days from its trough to climb back to its previous high [1]. Over the trailing 1-year period, its biggest drawdown was a milder 8.9% drop that recovered in just 15 days [2]. *A drawdown measures how far an asset has fallen from its highest peak before making a new high.*
* **Extreme daily swings**: SPY’s daily returns over 5 years featured an average daily gain of +0.05%, but showed "fat tails" with an excess kurtosis of 8.74 and 13 moves exceeding 3 standard deviations—far higher than the roughly 3 expected by a standard bell curve [3]. Over the trailing 1 year, it had 3 such extreme days [4]. *Excess kurtosis reveals whether an investment experiences unusually large, extreme daily swings more frequently than a normal statistical distribution predicts.*

### What history says
* **Single-day drops**: Looking at 11,120 historical cases where an individual S&P 500 stock plunged 5% or more in a single day relative to the index, the average excess return over the following 12 months was +12.05% (with a range of 1.95% to 20.83%) [5], [6]. However, only 51.5% of those stocks outperformed the index, meaning roughly half still lagged [5].
* **Deep pullbacks offer no clear edge**: Backtesting a "big dip" strategy—buying S&P 500 stocks that sit 20% or more below their highs—showed a 40.2% win rate of beating the index over the following 12 months, compared to 40.8% when the signal was off [7]. This resulted in an excess return difference of -0.4% and an official verdict of **no clear edge** [7].

### What the data can't tell you
Historical recovery patterns describe broad averages across thousands of past events; they cannot predict when a current dip will end or whether a specific stock will ever recover. Additionally, the data does not provide very short-term post-drop base rates (such as 1-day or 1-week rebounds), nor can it forecast future economic conditions.

### Try it yourself
To study these patterns on the Analyze page, explore:
* [Drawdowns for SPY](#/analyze?t=SPY&a=drawdown&p=5y) over 1-year and 5-year periods.
* [Return distribution for SPY](#/analyze?t=SPY&a=returns_distribution&p=5y) over 1-year and 5-year periods.

_Educational, not financial advice. Ticker Tutor explains analyses and evidence. It doesn't recommend buying or selling anything, and past results don't guarantee future returns._

**Sources**
1. Ticker Tutor analysis: Drawdowns for SPY (S&P 500 fund), 2021-11-18 to 2026-11-17 — `run_analysis(SPY, drawdown, 2021-11-18..2026-11-17) on daily adjusted prices`
2. Ticker Tutor analysis: Drawdowns for SPY (S&P 500 fund), 2025-11-17 to 2026-11-17 — `run_analysis(SPY, drawdown, 2025-11-17..2026-11-17) on daily adjusted prices`
3. Ticker Tutor analysis: Return distribution for SPY (S&P 500 fund), 2021-11-18 to 2026-11-17 — `run_analysis(SPY, returns_distribution, 2021-11-18..2026-11-17, Return length 1) on daily adjusted prices`
4. Ticker Tutor analysis: Return distribution for SPY (S&P 500 fund), 2025-11-17 to 2026-11-17 — `run_analysis(SPY, returns_distribution, 2025-11-17..2026-11-17, Return length 1) on daily adjusted prices`
5. Ticker Tutor database: SQL query, as of 2026-11-17 — `SELECT * FROM events WHERE event IN ('one_day_drop', 'one_day_jump') ORDER BY event, horizon;`
6. Ticker Tutor database: recent_moves + events + earnings (event study), as of 2026-11-17 — `get_recent_moves(all)`
7. Ticker Tutor database: signal_cards (backtest), as of 2026-11-17 — `get_signal_track_record(big_dip, sector=All)`

</details>

<details><summary><b>Same model, no tools, no system prompt</b></summary>

> The short answer is **yes, historically, "buying the dip" on the broader S&P 500 index has been a highly profitable strategy**, especially over medium-to-long-term horizons. However, for **individual stocks**, buying the dip is much riskier, as individual companies can go bankrupt or take decades to recover.
>
> Here is a breakdown of what historically happens after big one-day drops, the data behind it, and the crucial caveats.
>
> ---
>
> ### 1. What happens after big one-day drops in the S&P 500?
>
> Historically, when the S&P 500 experiences a severe one-day drop (e.g., -3% to -5% or more), the market exhibits two strong tendencies:
> 1. **Short-term volatility (The "Aftershock"):** Over the next 1 to 5 days, the market is extremely volatile. Big down days are frequently followed by other big down days, but also by massive "relief rallies."
> 2. **Medium-to-Long-term outperformance:** Over 1-year, 3-year, and 5-year periods, forward returns following major drops are significantly higher than the market’s historical average.
>
> #### The Historical Numbers
> According to historical data analyzing S&P 500 drops of **3% or more in a single day** (going back to the 1950s):
> * **1 Month Later:** Positive roughly **55–60%** of the time. (A coin flip, because the market may still be in freefall).
> * **1 Year Later:** Positive roughly **70–75%** of the time, with an average return often exceeding **15% to 20%** (compared to the normal annual average of ~10%).
> * **3 Years Later:** Positive over **80%** of the time, with annualized returns often beating the baseline market return.
> * **5 Years Later:** Positive nearly **90%** of the time.
>
> #### What about the *worst* single days in history?
> Consider the most famous market crashes:
> * **Black Monday (Oct 19, 1987):** The S&P dropped **20.5%** in one day. 
>   * *1 year later:* Up **+23%** from the bottom.
>   * *2 years later:* Fully recovered and hit new all-time highs.
> * **Lehman Brothers Collapse (Oct–Nov 2008):** Multiple 5% to 9% daily drops.
>   * *1 year later:* Buying on the worst days yielded mixed results immediately, but buying in late 2008 yielded massive gains over the next 5 years (over +100%).
> * **COVID Crash (March 16, 2020):** S&P dropped **12%** in one day.
>   * *1 year later:* Up over **+55%**.
>
> ---
>
> ### 2. S&P 500 Index vs. Individual S&P 500 Stocks
>
> There is a massive distinction between buying the dip on the **index** versus buying the dip on **individual components**:
>
> * **The S&P 500 Index is "self-cleansing":** If a company fails, it drops out of the index and is replaced by a winning company. Because of this, the S&P 500 has a 100% historical recovery rate from every crash it has ever had.
> * **Individual Stocks do not always recover:** A study by J.P. Morgan found that roughly **40% of all stocks in the Russell 3000 suffered a "catastrophic decline"** (a 70%+ drop from peak that they never recovered from) between 1980 and 2020. 
>   * *Example:* Buying the dip on Apple or Microsoft in 2022 worked brilliantly. Buying the dip on Enron, WorldCom, Lehman Brothers, or even Intel (which is still down ~60% from its 2000 highs) destroyed wealth.
>
> ---
>
> ### 3. The Catch: The "Falling Knife" Problem
>
> While buying the dip works over time, it comes with psychological and mathematical traps:
>
> 1. **A dip is often not the bottom:** In sustained bear markets (like the 2000 Dot-com bust or the 2008 Financial Crisis), buying a 4% single-day drop in the first few months of the crash meant you still had to endure an additional 30% to 40% loss before the true bottom was reached.
> 2. **Cash Drag:** If an investor sits in 100% cash *waiting* for a 3% or 5% drop to "buy the dip," they usually underperform. The market often rallies 15% before dropping 4%. In financial terms: **"Time in the market beats timing the market."**
>
> ---
>
> ### Summary: How to actually use this data
>
> * **For the S&P 500 (VOO, SPY):** Yes, buying after sharp one-day drops has historically been an excellent trade, provided your time horizon is **at least 1 to 3 years**.
> * **Don't wait for dips with all your money:** A better strategy is **DCA (Dollar-Cost Averaging)**, where you invest automatically every month, but keep a small reserve of opportunistic cash to buy extra shares when the market has a rare, panic-induced single-day collapse.
> * **Be cautious with individual stocks:** Ensure a single-day drop in a specific stock is due to market-wide panic, rather than a fundamental collapse in that company's business model.

</details>

#### Sample 3: Why is Nvidia down so much lately?

Research team: 2 researchers, 10 tool calls, 10 cited sources, 57 s. Same model without tools: no data access, no citations.

<details><summary><b>Ticker Tutor's answer</b></summary>

### In short
Nvidia (NVDA) has fallen 35.0% from its October 6, 2026 high to $155.46 as of November 17, 2026 [1]. The decline was initially sparked by tech-wide scrutiny over artificial intelligence spending and macro uncertainty, followed by leadership turmoil after CEO Jensen Huang acknowledged a personal matter and faced an outside legal investigation alongside an executive change [2][3].

### What's in the news
The [In the news](#/news) tab tracks major corporate events and headlines linked to large price swings. For Nvidia, three specific dates drove the bulk of the recent pullback:

* **October 22, 2026:** Shares fell 4.4% amid broader semiconductor weakness as investors questioned elevated AI infrastructure capital spending following peer earnings reports [1][4].
* **November 5, 2026:** NVDA dropped 9.3% during a broader market pullback driven by election-related policy uncertainty and a 4.4% slide in the S&P 500 [1][5].
* **November 10, 2026:** The stock plunged 5.5% following reports of an internal memo from CEO Jensen Huang acknowledging a personal matter, alongside news of an outside legal investigation [1][3]. On November 12, Nvidia filed Form 8-K reporting an executive or director change [2]. 

Shares stayed under pressure around its November 17 earnings report as Federal Reserve rate-hike concerns and upcoming AI IPOs weighed on tech valuations [6][7][8].

### The move in numbers
Comparing a stock "vs the S&P 500" shows whether it outperformed or lagged the broader market, while a "typical daily move" refers to its normal daily volatility (measured by standard deviation) [1][9].

* **Recent returns:** NVDA is down 0.4% over 1 day (+0.6% vs S&P 500), down 8.0% over 1 week (-5.6% vs S&P 500), and down 28.4% over 1 month (-23.9% vs S&P 500 and -12.2% vs its sector fund) [1].
* **Distance from peak:** At 35.0% below its 52-week peak, NVDA’s one-year maximum drawdown reached -35.0%, compared to the S&P 500’s -8.9% drawdown over the same period [1][10].
* **Biggest drop days:** The 9.3% drop on November 5 was 3.9 times its typical daily move on 2.5x normal trading volume [1]. The 5.5% drop on November 10 was 2.3 times its typical move on 3.5x normal volume [1].

### How unusual is this?
A drawdown of 35.0% is relatively rare for Nvidia, occurring just 15.3% of the time in its history since January 2016 [1][10]. Similarly, single-day plunges like the 9.3% drop on November 5 have happened only 13 times across 2,734 trading days [1]. Across 251 daily returns over the past year, NVDA saw three moves exceeding 3 standard deviations and recorded four separate drops of 10% or more [10][9]. 

### What the data can't tell you
News and historical distributions explain what already occurred, but past trading patterns and leadership changes cannot predict future stock performance. 

### Try it yourself
To explore these metrics, check out [Drawdowns for NVDA](#/analyze?t=NVDA&a=drawdown&p=1y) (1-year), [Return distribution for NVDA](#/analyze?t=NVDA&a=returns_distribution&p=1y) (1-year), or [NVDA vs the S&P 500](#/analyze?t=NVDA&a=relative&p=3m) (3-month).

_Educational, not financial advice. Ticker Tutor explains analyses and evidence. It doesn't recommend buying or selling anything, and past results don't guarantee future returns._

**Sources**
1. Ticker Tutor price-move summary for NVDA, 2026-10-06 to 2026-11-17 — `get_price_move(NVDA, days=30) on daily adjusted prices`
2. [NVDA 8-K filed 2026-11-12 (Executive or director change; Financial exhibits)](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000082/nvda-20261111.htm)
3. [cnn.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHMjsiOLL33gr3LZjhLyKbkjzAI-XBgFvZi-WHBSOxAG89Avw0s7mKDgLDhD1ADW98WENX2_oacj9LJHSUbmEqDkb8VKddZO8DvFXt7-PcWxj4wrhgbYZPnKkY_CDov2YkL8FD9q5vwaQeV_gznP45F7cetof1xRdk43rVG9Q==)
4. [heygotrade.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEWwqYhutsTlnTwGpb1FILp233TcGPAvYszBrNUToMk86Umb1Ba6_OJwGxgBbLRS2hoodOw1IRAtrY9LOsd9IL3eJuI91P0DCAJz840OQzSPaogwuTcjHbXej4CL28FsDmU74_WjJytjY5mW5fgvgbn-p3h40T_sg54_eOVa5mqUgtYZBfk)
5. [vantagemarkets.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEjERTngoAXUgUw_1Nw4T6n_--Y_obobjzC0V5lLpUoNldkNjmdoPPL52PFJtfxzjzamA9xtO_-P-yPwJLxp-SXtDoahmRx_iMrChsXohzDAxXkPzgKETGW-kGF_xKfBWEWxsbpVVM9GtjO1JICmSmp52ndlzwJ2wbLNz75VWamNTWv85AGReyZSbo4I1uQ-mONCxkOEk97n1eTqvFz)
6. [Yahoo: Stock Market Today: Dow Ends In Red On Rate 'Shock' Fears; Nvidia Sinks As Anthropic IPO Looms](https://finnhub.io/api/news?id=376af3ccc406b1c2d77058d5ec111788d87a926c4c05754a70a798ff8bf06076)
7. [NVDA 8-K filed 2026-11-17 (Earnings results; Financial exhibits)](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000088/nvda-20261117.htm)
8. [CNBC: Why Anthropic's hot IPO is bringing out sellers — plus, a silver lining of the down market](https://www.cnbc.com/investingclub/2026/11/18/why-anthropics-hot-ipo-is-bringing-out-sellers-plus-a-down-market-silver-lining.html)
9. Ticker Tutor analysis: Return distribution for NVDA, 2025-11-17 to 2026-11-17 — `run_analysis(NVDA, returns_distribution, 2025-11-17..2026-11-17, Return length 1) on daily adjusted prices`
10. Ticker Tutor analysis: Drawdowns for NVDA, 2025-11-17 to 2026-11-17 — `run_analysis(NVDA, drawdown, 2025-11-17..2026-11-17) on daily adjusted prices`

</details>

<details><summary><b>Same model, no tools, no system prompt</b></summary>

> Nvidia’s recent stock decline is not due to a single catastrophic event, but rather a combination of **high expectations, broader macroeconomic shifts, regulatory concerns, and market mechanics**. 
>
> Here are the primary reasons Nvidia (NVDA) has been down recently:
>
> ---
>
> ### 1. The "Priced for Perfection" Problem (Post-Earnings Hangover)
> Nvidia recently reported record-breaking earnings, beating Wall Street’s revenue and profit estimates. However, the stock still dropped. Why?
> * **Whisper Numbers:** Nvidia didn’t just need to beat the official estimates; it needed to beat the *unofficial*, ultra-optimistic "whisper numbers" traded among hedge funds. 
> * **Slowing Growth Rates:** While Nvidia is still growing at an incredible pace, the *rate* of that growth is mathematically starting to decelerate compared to the explosive triple-digit surges seen in 2023.
> * **Margins:** Nvidia reported a slight dip in gross margins, raising fears that profitability may have peaked for this cycle.
>
> ### 2. Doubts Around "AI ROI" (Return on Investment)
> There is a growing debate on Wall Street about whether Nvidia’s biggest customers—Microsoft, Alphabet, Meta, and Amazon—are spending too much money on AI infrastructure without seeing enough revenue in return.
> * These Big Tech companies account for roughly **40% of Nvidia’s revenue**. 
> * Investors are beginning to worry that if these tech giants don't start showing significant profits from their AI products soon, they will eventually cut back on their massive capital expenditures (CapEx) for Nvidia’s chips.
>
> ### 3. Rumors and Delays Around the "Blackwell" Chip
> Nvidia's next-generation AI chip, called **Blackwell**, is expected to be its next massive growth driver. However:
> * Reports surfaced indicating engineering/design flaws that could cause a **two-to-three-month delay** in high-volume shipments.
> * While CEO Jensen Huang reassured investors that Blackwell would ship billions of dollars worth of chips later this year, the initial news created uncertainty, and markets hate uncertainty.
>
> ### 4. Sector Rotation (The "Great Rotation")
> Money is moving out of Big Tech and into other areas of the market:
> * With the Federal Reserve signaling **interest rate cuts**, investors have started pulling profits out of expensive mega-cap tech stocks (which carried the market for 18 months) and rotating into beaten-down, rate-sensitive sectors like small caps (Russell 2000), real estate, utilities, and value stocks.
> * Nvidia, being one of the biggest winners of 2023–2024, became an easy target for investors looking to "take profits off the table."
>
> ### 5. Regulatory and Geopolitical Headwinds
> * **Antitrust Scrutiny:** Reports emerged that the U.S. Department of Justice (DOJ) is escalating its antitrust investigation into Nvidia regarding whether it makes it difficult for customers to switch to other chipmakers or penalizes buyers who don't exclusively use its AI chips. (Nvidia has denied receiving a formal subpoena, but regulatory pressure remains an overhang).
> * **China Export Restrictions:** The U.S. government continues to tighten export controls on advanced semiconductors to China, cutting Nvidia off from a historically massive market.
>
> ### 6. Extreme Volatility and "Crowded Trade" Dynamics
> Because Nvidia is held by nearly every major index fund, hedge fund, and retail investor, it has become a very "crowded trade." 
> * When the market dips, algorithmic selling and margin calls can trigger automated sell-offs.
> * Nvidia is also one of the most actively traded stocks in the **options market**. When option dealers have to adjust their hedges during a downturn, it can artificially accelerate the downward momentum.
>
> ---
>
> ### Summary: Is the AI boom over?
> Most analysts say **no**. Demand for Nvidia's current-gen chips (H100 and H200) remains higher than supply, and demand for Blackwell is reportedly staggering. 
>
> Rather than a collapse in Nvidia’s underlying business, this drop represents a **healthy market correction**. After gaining several trillion dollars in market value over just two years, the stock is catching its breath as the market resets its expectations.

</details>
<!-- baseline:end -->

## How the research desk works (Deep Research)

```
              your question
                   │
             ┌─────▼─────┐   too vague? → one clarifying question (with suggested answers),
             │   Lead    │                 remembered for your reply
             │  (plan)   │   out of scope? → says what Ticker Tutor covers
             └─────┬─────┘
       ┌───────────┼────────────┐        in parallel, each with a fresh context:
 ┌─────▼────┐ ┌────▼─────┐ ┌────▼────┐   only its brief and its own toolset
 │ Market   │ │Fundament-│ │  News   │
 │researcher│ │als resea-│ │research-│
 │          │ │  rcher   │ │   er    │
 └─────┬────┘ └────┬─────┘ └────┬────┘
       └───────────┼────────────┘
             ┌─────▼─────┐   gaps or conflicts? → sends new Researchers
             │Lead review│   (up to 3 rounds, within a time budget)
             └─────┬─────┘
             ┌─────▼─────┐
             │  Writer   │   short beginner-friendly report, every number cited [n]
             └─────┬─────┘
             ┌─────▼─────┐
             │ Verifier  │   checks numbers and citations against the tool results;
             └───────────┘   issues → one revision by the Writer
```

- **Lead** (structured JSON): decides *clarify / research / out of scope* (a request to pick stocks gets a clarifying question that turns it into an analysis, while "why is it down?" about a named company always goes to research, with one Researcher on the news and one on the size of the move), restates the question so it stands alone (using earlier turns), notes parts the data can't answer ("will it go up next month?"), and writes 1–5 specific briefs, each for one Researcher role. After each round it reviews the findings and either says "enough" or lists the gaps and writes new briefs.
- **Researchers** (Gemini function calling, up to 6 tool steps each): run in parallel threads, each starting from nothing but its brief. Three roles with different tools:
  - *Market data:* `run_analysis` (any of the 13 analyses, any period and settings, exactly as the Analyze page runs them), `get_price_move` (how big a recent move is next to the S&P 500 and the sector, the biggest days, and how unusual they are for that stock), `get_stock_snapshot`, `get_signal_track_record`, `compare_stocks`, `screen_stocks`, `query_database` (read-only SQL over the database), `find_ticker`
  - *Fundamentals:* `get_fundamentals`, `get_annual_report_risks` (pulls the latest 10-K from SEC EDGAR, extracts Item 1A, and compares its risk headings with the previous year's), `get_stock_snapshot`, `query_database`, `find_ticker`
  - *News:* `get_company_news`, `get_market_news`, `get_recent_moves` (with historical base rates), `get_price_move` (to find which days to look for news around), `get_recent_filings` (8-K item codes), `web_search` (Google Search grounding), `find_ticker`
  
  Each returns findings as JSON with the source ids its claims rest on, plus gaps and anything the data can't answer.
- **Writer and Verifier:** the Writer explains each number in plain words and ends with analyses the reader can run themselves; it never recommends buying, selling, or holding. The Verifier flags unsupported numbers, wrong citations, and any sentence that recommends.
- **Citations:** every tool result registers its sources (a database table and query as of the build date, an SEC filing URL, a news article URL) and hands back ids like `S3`. The Writer may only cite those ids. Unknown ids are dropped, the rest become numbered links with a Sources list.
- **Limits:** at most 3 rounds, 5 Researchers per round, 6 tool steps per Researcher, and a 200-second research budget (writing and verification come after), so answers finish well inside the 5-minute grading window. Hitting a limit is reported, not hidden.
- **`/chat`** returns `{"response", "session_id", "tool_calls"}`. Every tool call carries an `agent` field: `lead`, `researcher:market#1`, `researcher:news#3`, `writer`, `verifier`. `/chat/stream` sends the same as server-sent events while the team works, which is what the live board on the Research desk shows.

```bash
curl -s -X POST "$URL/chat" -H 'Content-Type: application/json' \
  -d '{"message": "How volatile has Microsoft (MSFT) been compared with the S&P 500 over the last three years?"}' | jq '.tool_calls[] | {agent, name}'
```

## The data

| Source | What Ticker Tutor uses | Access |
|---|---|---|
| Wikipedia: [List of S&P 500 companies](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies) and [Historical components of the S&P 500](https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500) | Current members, GICS sectors, date added, CIK, and the table of index additions/removals (which moved to the second page), used to rebuild who was in the index each month | MediaWiki API, no key |
| [Alpaca Market Data](https://docs.alpaca.markets/docs/historical-stock-data-1) (default), [Tiingo](https://www.tiingo.com/documentation/end-of-day), or [Stooq](https://stooq.com/) | Daily close and split/dividend-adjusted close for every member (current and former), the four index funds (SPY, QQQ, DIA, IWM), and the 11 SPDR sector funds | Free key (Alpaca, Tiingo) or none (Stooq) |
| [SEC EDGAR XBRL company facts](https://www.sec.gov/edgar/sec-api-documentation) | Revenue, net and operating income, EPS, equity, long-term debt, cash flow, capex, dividends per share, shares outstanding, each with the date it was filed | Free, no key (contact email in the User-Agent) |
| [SEC EDGAR submissions](https://www.sec.gov/edgar/sec-api-documentation) and filing documents | 10-K / 10-Q / 8-K lists with 8-K item codes (2.02 = earnings release), and the Risk Factors text of 10-Ks (live) | Free, no key |
| [Finnhub](https://finnhub.io/docs/api/company-news) (or [GDELT](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) without a key) | Company and market headlines: a snapshot at build time and live lookups by the agents | Free key / none |
| [FRED](https://fred.stlouisfed.org/docs/api/fred/) | VIX and the 10-year Treasury yield (optional) | Free key |

**Why an agent needs tools for this:** the model doesn't know this week's prices, what a stock's RSI or beta was over a specific window, a company's latest filed numbers, or how a signal has performed for S&P 500 stocks month by month. Those come from Ticker Tutor's analysis engine, computed tables, and live sources.

### The analyses

`tickertutor/analysis.py` runs each analysis on daily adjusted prices for the dates you pick, for any S&P 500 stock or any of the four index funds. Indicators are computed on the full history first, so a 200-day average is already valid on the first day of a short period. The Analyze page and the agents' `run_analysis` tool use the same code.

| Group | Analyses (default settings) |
|---|---|
| Trend | Moving averages (50/200-day, golden/death cross markers) · Trend line (least-squares fit of log price: growth rate per year, R², ±2σ band) · MACD (12, 26, 9) |
| Momentum | RSI (14-day, 70/30 lines) · Momentum / rate of change (126-day, vs the S&P 500) |
| Volatility & risk | Volatility (rolling 21-day, annualized, vs the S&P 500) · Bollinger Bands (20-day, ±2σ, %B) · Drawdowns (underwater chart, recovery) · Beta & correlation (daily-return scatter with best-fit line, rolling beta, behavior on big market days) |
| Returns | Performance vs the S&P 500 and the sector fund · Rolling returns (1 month to 3 years) · Return distribution (daily/weekly/monthly histogram vs the bell curve, skewness, kurtosis, 3σ moves) |
| Trading activity | Volume (with its rolling average and the heaviest days) |

**The indexes** (`tickertutor/indexes.py`) are followed through the funds that track them, because an index can't be bought and its quoted level leaves out dividends: SPY (S&P 500), QQQ (Nasdaq-100), DIA (Dow Jones Industrial Average), and IWM (Russell 2000). Comparisons with the S&P 500 are dropped when the subject is SPY itself, beta on SPY explains that it's 1 by definition, and "performance" for an index compares it with the other three.

### How the database is built

`scripts/build_data.py` runs on your machine (the deployed app only reads the result):

1. **Download** (cached in `data/cache/`, so an interrupted build resumes): members and index changes → point-in-time membership intervals; prices for current and former members, the four index funds, and the sector funds; SEC company facts and filing lists; headlines; FRED.
2. **Compute**, all point-in-time:
   - **Indicators** per stock and day: 50/200-day averages, golden cross, RSI(14), 12-1 momentum, distance from the 52-week high, volatility, beta, return vs its sector fund.
   - **Fundamentals as known at the time:** each fiscal year's values as first reported, usable only after their filing date; trailing-twelve-month figures from 10-K + 10-Q year-to-date values; P/E vs its own 5-year median.
   - **A monthly panel** of every stock *that was in the index that month*, with its signals and its next-12-month return minus SPY's (dividends included).
   - **Report cards:** for each signal, every month compare stocks with it on vs off (needs 5+ on each side), then average across months. 95% ranges come from a moving-block bootstrap (12-month blocks, 2,000 resamples), because overlapping 1-year windows aren't independent. The most recent third of months is held out. Verdicts: *held up* (range excludes zero, effect ≥ 1 point a year, same sign in the held-out years), *mixed* (didn't hold out of sample), *no clear edge*, *did worse*, *too little data* (< 24 months).
   - **Snapshot per stock:** latest price, returns over standard periods, indicator readings, valuation, and risk numbers.
   - **Event base rates:** one-day moves of ±5% vs the index and 3%+ earnings reactions (8-K item 2.02 dates), with cluster-bootstrap ranges by month.
3. **Write** `data/tickertutor.duckdb` (tables: `companies`, `prices`, `snapshot`, `panel`, `fundamentals`, `signal_cards`, `sectors`, `events`, `recent_moves`, `earnings`, `filings`, `news`, `membership`, `index_changes`, `meta`).

The database is committed to the repo (under GitHub's 100 MB limit) so the deployed app has it. If a build is larger, upload it to Cloud Storage with `--upload gs://BUCKET/tickertutor.duckdb` and set `DATA_GCS_URI`. The app downloads it at startup and falls back to the committed copy.

### What the data can't tell you

- **The future.** Every number describes the past; the app and the agents say so.
- **Survivorship.** Former members are included where the price provider still has their history, but delisted or acquired companies are often missing from free data, which flatters results somewhat. A reused ticker can also point at a different company's prices.
- **History length.** Alpaca's free history starts in 2016, so backtests cover roughly 2017–2025 (about 100 months, with the last third held out). Tiingo goes back further, but its free plan's request limits make a full download take hours (it resumes from the cache).
- **XBRL coverage** starts around 2009–2011 and companies tag items differently; missing figures show as unknown rather than guessed.
- **Many signals.** Testing 15 signals invites a lucky one, which is why held-out years and ranges are shown, not just averages.

## Run it locally

Requires [uv](https://docs.astral.sh/uv/) and, for the research desk, the gcloud CLI set up as in the course's GCP guide.

```bash
uv sync
cp .env.example .env                 # fill in keys (see below)
gcloud auth application-default login
uv run app.py                        # http://localhost:8080
uv run pytest                        # offline tests: mocked APIs, synthetic data, a scripted stand-in for Gemini
```

The repo ships with a database. Until you build real data it's a **synthetic demo** (real tickers, simulated numbers), and every page shows a yellow banner saying so.

**UI work without Gemini or keys:** `uv run python scripts/dev_server.py` runs the app at http://127.0.0.1:8000 with a scripted stand-in for the model that plays every agent role and calls the real tools.

### Load the real data

1. **Get free keys** (5 minutes):
   - **Alpaca** (prices): sign up at [alpaca.markets](https://alpaca.markets/), open the *Paper Trading* dashboard, generate an API key and secret → `ALPACA_API_KEY`, `ALPACA_API_SECRET`.
   - **Finnhub** (news): [finnhub.io/register](https://finnhub.io/register) → `FINNHUB_API_KEY`.
   - **SEC EDGAR and Wikipedia:** no key, but both refuse requests without a contact email. Set `SEC_USER_AGENT` to a name and your email (for example `Ticker Tutor class project you@school.edu`); the same email is sent to every data source.
   - Save the file as exactly `.env`. Windows Notepad tends to save `.env.txt` with the ending hidden; the build stops and tells you if that happened.
   - *Optional:* **FRED** (VIX, 10-year yield) at [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) → `FRED_API_KEY`. **Tiingo** for longer price history → `TIINGO_API_KEY` and `PRICE_PROVIDER=tiingo`.
2. **Smoke test** with 20 companies (a minute or two): `uv run python scripts/build_data.py --limit 20 --out data/test.duckdb`
3. **Full build** (roughly 30–60 minutes, mostly SEC downloads; the SEC allows 10 requests a second): `uv run python scripts/build_data.py`
4. Restart the app, then regenerate the comparison: `uv run python scripts/baseline_compare.py`
5. Commit `data/tickertutor.duckdb` and push; the deploy picks it up.

A database built before the index funds were added shows "Rerun the data build to add this index" on the index cards until you rebuild.

### Keeping prices current

Prices are daily closes, not live quotes. A day's prices count as final at 6 pm New York time, so "current" means through the last weekday that has passed that point (on a Saturday, that's Friday).

**On your computer the app updates itself.** When it starts, and every half hour while it's open, it compares the data's date with the last finished trading day. If the data is behind and your price keys are in `.env`, it runs the daily update in the background, and the corner of the page says "Updating prices…" until the new date appears. Pages keep working on the old data in the meantime. Nothing happens on weekends or market holidays beyond one small check.

The same update by hand:

```bash
uv run python scripts/build_data.py --refresh
```

What the daily update does: downloads prices, market context (FRED), and headlines again, then recomputes everything. It reuses index membership, SEC financials, and filing lists saved by the last full build for up to a week, so those can lag by a few days. The first update after a full build made with an older version of this code has nothing saved to reuse, so it takes as long as a full build. After that, expect a few minutes. If an update fails, the reason is in `data/cache/refresh.log` and the app keeps the data it had. Set `AUTO_REFRESH=0` in `.env` to turn this off.

The update rewrites `data/tickertutor.duckdb`, so git will show it as changed. Commit and push it when you want the deployed app to ship with newer data (or use the bucket below so no commit is needed).

### Example answers, ready ahead of time

A full research answer takes one to three minutes, and the six example questions on the Research desk are the same for everyone. So the app researches each example once per data day and saves the result in `data/research_examples.json`: every step the team took and the final answer. Clicking an example replays those steps over about ten to fourteen seconds (the clarifying "What should I buy?" stays quick), then adds the answer to the conversation like any other, so follow-ups work. The answer's footer says it was researched ahead of time and on which day's data. Anything else you ask is researched live.

When answers are prepared (with real data only, never the synthetic demo data):

- **On your computer:** when the app starts, and again after each daily price update. With real Gemini this takes a few minutes in the background.
- **Deployed:** the app uses the `research_examples.json` you committed, as long as it matches the database's date and the `GEMINI_MODEL`. If it doesn't, the first visitor's page sends one background request that stays open while the missing answers are prepared. On Cloud Run an open request is what keeps the CPU running. Someone who clicks an example while it's being prepared follows that same run instead of starting another.

So when you commit a refreshed `data/tickertutor.duckdb`, commit `data/research_examples.json` with it (open the app locally first and give it a few minutes to prepare them). Set `PRELOAD_EXAMPLES=0` to turn this off.

## Deploy (Cloud Run, continuous deploy from GitHub)

Follow the course guide *Deploying to Cloud Run from GitHub* with this repo. Run these once in your class project.

**1. Enable services**

```bash
PROJECT_ID=$(gcloud config get-value project)
gcloud services enable run.googleapis.com cloudbuild.googleapis.com developerconnect.googleapis.com \
  secretmanager.googleapis.com aiplatform.googleapis.com storage.googleapis.com
```

**2. Give the Cloud Run service account the roles it needs**

```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
SA=$PROJECT_NUMBER-compute@developer.gserviceaccount.com
for ROLE in roles/aiplatform.user roles/secretmanager.secretAccessor roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$SA --role=$ROLE --condition=None
done
```

**3. Store keys in Secret Manager.** The deployed app only needs news keys for live headlines (prices and filings are in the database). The SEC contact string is used for live 10-K risk-factor lookups.

```bash
printf '%s' 'PASTE_FINNHUB_KEY' | gcloud secrets create FINNHUB_API_KEY --data-file=-
printf '%s' 'Ticker Tutor class project you@columbia.edu' | gcloud secrets create SEC_USER_AGENT --data-file=-
```

**4. Create the service** (course guide steps 3–7): Connect repository → Developer Connect → this repo, branch `main`, **buildpack** with entrypoint

```
uvicorn app:app --host 0.0.0.0 --port $PORT
```

Require authentication with **Identity-Aware Proxy**, principal `columbia.edu`. Name the service `tickertutor`.

**5. Set memory, timeout, environment variables, and secrets.** Research answers can take a few minutes, so raise the request timeout; DuckDB and pandas want more than the default memory. Use the region you picked in step 4.

```bash
gcloud run services update tickertutor --region=us-east1 --memory=2Gi --cpu=2 --timeout=600 \
  --set-env-vars=GEMINI_MODEL=gemini-3.8-flash,GOOGLE_CLOUD_LOCATION=global,GOOGLE_CLOUD_PROJECT=$PROJECT_ID \
  --set-secrets=FINNHUB_API_KEY=FINNHUB_API_KEY:latest,SEC_USER_AGENT=SEC_USER_AGENT:latest
```

Later pushes to `main` redeploy automatically and keep these settings. Put the service URL in `submission.json` as `deploy_url`.

### Keeping the deployed app current

The deployed app can't update itself the way your computer does: Cloud Run pauses instances between requests and throws away their disk. So the deployed app shows whatever database it was given, which is the one committed to the repo unless you set up a bucket. With a bucket, the app loads the newest upload when it starts and checks for a newer one every ten minutes.

**Step 1. Create a bucket, upload, and point the app at it:**

```bash
gcloud storage buckets create gs://$PROJECT_ID-tickertutor --location=us-east1
uv run python scripts/build_data.py --upload gs://$PROJECT_ID-tickertutor/tickertutor.duckdb
gcloud storage buckets add-iam-policy-binding gs://$PROJECT_ID-tickertutor --member=serviceAccount:$SA --role=roles/storage.objectViewer
gcloud run services update tickertutor --region=us-east1 --update-env-vars=DATA_GCS_URI=gs://$PROJECT_ID-tickertutor/tickertutor.duckdb
```

**Step 2. Choose how the bucket gets fresh data.**

*Option A, from your computer (simplest).* Add this line to `.env`, and every automatic update on your computer also uploads the result. The deployed app picks it up within ten minutes. The catch is that it only happens on days you open the app locally.

```
REFRESH_UPLOAD_URI=gs://YOUR_PROJECT_ID-tickertutor/tickertutor.duckdb
```

Or upload by hand any time: `uv run python scripts/build_data.py --refresh --upload gs://$PROJECT_ID-tickertutor/tickertutor.duckdb`

*Option B, a scheduled job in the cloud (fully automatic).* A Cloud Run job runs the same daily update every weekday evening and uploads the result. These commands follow Google's documentation but have not been run against a real project yet, so treat the first run as a test and check its log.

```bash
# The job needs the price keys too (the deployed app itself never did).
printf '%s' 'PASTE_ALPACA_KEY' | gcloud secrets create ALPACA_API_KEY --data-file=-
printf '%s' 'PASTE_ALPACA_SECRET' | gcloud secrets create ALPACA_API_SECRET --data-file=-
gcloud storage buckets add-iam-policy-binding gs://$PROJECT_ID-tickertutor --member=serviceAccount:$SA --role=roles/storage.objectAdmin

# Reuse the image Cloud Build already made for the service.
IMAGE=$(gcloud run services describe tickertutor --region=us-east1 --format='value(spec.template.spec.containers[0].image)')
gcloud run jobs create tickertutor-refresh --region=us-east1 --image=$IMAGE --memory=4Gi --cpu=2 --task-timeout=3600 --max-retries=1 \
  --command=/cnb/lifecycle/launcher \
  --args=python,scripts/build_data.py,--refresh,--upload,gs://$PROJECT_ID-tickertutor/tickertutor.duckdb \
  --set-env-vars=PRICE_PROVIDER=alpaca,CACHE_DIR=/tmp/cache \
  --set-secrets=ALPACA_API_KEY=ALPACA_API_KEY:latest,ALPACA_API_SECRET=ALPACA_API_SECRET:latest,FINNHUB_API_KEY=FINNHUB_API_KEY:latest,SEC_USER_AGENT=SEC_USER_AGENT:latest

gcloud run jobs execute tickertutor-refresh --region=us-east1 --wait      # try it once and read the log

# Then every weekday at 6:30 pm New York time.
gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$SA --role=roles/run.invoker --condition=None
gcloud scheduler jobs create http tickertutor-refresh-daily --location=us-east1 \
  --schedule="30 18 * * 1-5" --time-zone="America/New_York" --http-method=POST \
  --uri="https://us-east1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/tickertutor-refresh:run" \
  --oauth-service-account-email=$SA
```

The job starts with an empty cache each time, so it first fetches the saved build inputs that sit next to the database in the bucket (uploaded with every `--upload`) and reuses them for up to a week. If Wikipedia or the SEC refuses requests from the cloud when the weekly re-download comes around, the job keeps using the saved inputs and says so in its log. Upload from your computer once (Option A's command) before the first scheduled run so those inputs exist.

### Troubleshooting

- **Build stops with `en.wikipedia.org refused the request (HTTP 403)`:** Wikipedia blocks requests without a contact email in the User-Agent. Put your email in `SEC_USER_AGENT` in `.env`. If it still fails, open [the page](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies) in your browser, save it (Ctrl+S, "Webpage, HTML only") into the project folder, and add `--wiki-html "List of S&P 500 companies - Wikipedia.html"` to the build command. Do the same for [the index-changes page](https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500) with `--wiki-changes-html`.
- **Step 1 of the build says `0 index changes on record` or `0 former members`:** the backtests then cover only today's members. The build reads the changes from Wikipedia's "Historical components of the S&P 500" page and saves both pages to `data/cache/wikipedia_sp500*.html`. If the count is still 0, that page's layout has changed again, so open the saved file to see the table.

- **First build fails with `developerconnect.gitRepositoryLinks.fetchReadToken` denied:** wait a minute, then Cloud Build → History → Rebuild.
- **Research answers stop at about 5 minutes or the page shows a connection error:** the request timeout is still the default; rerun step 5.
- **Answers say the Gemini model isn't available:** set `GEMINI_MODEL` to the model the course uses.
- **The yellow "Demo data" banner is showing:** the committed database is still the synthetic one; build real data and push it.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model on Vertex AI |
| `GOOGLE_CLOUD_LOCATION` | `global` | Vertex AI location |
| `GOOGLE_CLOUD_PROJECT` | auto-detected | GCP project |
| `GEMINI_THINKING` / `GEMINI_TOOL_THINKING` | `low` / `minimal` | Thinking levels for planning vs tool loops |
| `FINNHUB_API_KEY` | none (GDELT fallback) | Live and snapshot news |
| `SEC_USER_AGENT` | generic | Contact string the SEC requires |
| `PRICE_PROVIDER` | `alpaca` | `alpaca`, `tiingo`, or `stooq` (builds and the daily update) |
| `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `TIINGO_API_KEY`, `FRED_API_KEY` | none | Build-time data keys |
| `TICKERTUTOR_DB` | `data/tickertutor.duckdb` | Database path |
| `DATA_GCS_URI` | none | Load the database from Cloud Storage at startup, and switch to a newer upload within ten minutes |
| `AUTO_REFRESH` | on locally, off on Cloud Run | `0` stops the app from updating prices by itself. `1` forces it on |
| `REFRESH_UPLOAD_URI` | none | After each automatic update, also upload the database to this `gs://` address |
| `PRELOAD_EXAMPLES` | on with real data | `0` stops the app from researching the example questions ahead of time. `1` turns it on even with the demo data |
| `PRELOAD_WAIT_SECONDS` | `540` | How long the page's background request waits while example answers are prepared (keep it under the Cloud Run timeout) |
| `MAX_ROUNDS`, `MAX_RESEARCHERS`, `MAX_RESEARCHER_STEPS`, `TIME_BUDGET_SECONDS` | 3, 5, 6, 200 | Research team limits |
| `CHAT_RATE_PER_HOUR` | 40 | Questions per visitor per hour |

## API

| Endpoint | Returns |
|---|---|
| `POST /chat` `{"message", "session_id"?}` | `{"response", "session_id", "tool_calls": [{"agent", "name", "args", "result"}]}` |
| `POST /chat/stream` | The same, as server-sent events: `plan`, `round`, `researcher_start`, `tool_call`, `researcher_done`, `review`, `writing`, `verified`, `done` |
| `GET /api/meta` | Data date, provider, coverage, whether it's synthetic |
| `GET /api/analysis?ticker=KO&a=rsi&period=1y` (or `start`/`end`, plus settings like `window=21`) | One analysis: chart series, summary numbers, readout, explanation, and related backtest evidence |
| `GET /api/analyses` | The list of analyses with their settings and explanations |
| `GET /api/indexes` | The four big indexes: recent returns, volatility, distance from the 52-week high, and a one-year sparkline |
| `GET /api/indexes/{ticker}` | One index's page: description, snapshot, returns next to the other indexes, risk, and (S&P 500) largest companies |
| `GET /api/overview`, `/api/stocks`, `/api/tickers` (index funds first, then companies), `/api/stocks/{ticker}`, `/api/stocks/{ticker}/prices?range=1m\|3m\|6m\|ytd\|1y\|3y\|5y\|max` (or `start`/`end`), `/api/suggestions`, `/api/news` | Page data |
| `GET /api/news/live` | Fresh headlines for each recent big move that name the company (cached 30 minutes; the page falls back to the saved ones) |
| `GET /api/research/examples` | The Research desk's example questions and whether each answer is ready |
| `POST /api/research/preload` | Prepare any example answers that aren't ready, and wait while that runs (the page sends this when it opens) |
| `GET /api/data-status` | The data's date, the last finished trading day, and whether an update is running |

## Project layout

```
app.py                      FastAPI app: pages' API, /chat, /chat/stream
tickertutor/agents.py       Lead, Researchers, Writer, Verifier; sessions; citations
tickertutor/tools.py        The 15 research tools, their declarations, and the source registry
tickertutor/views.py        Queries behind each page
tickertutor/analysis.py     The 13 analyses: settings, periods, chart series, summaries, readouts, explanations
tickertutor/sectors.py      Plain-language descriptions of the 11 GICS sectors
tickertutor/indexes.py      The four big indexes, the funds that track them, and their descriptions
tickertutor/data.py         DuckDB access, safe read-only SQL, ticker checks, the one-year date rule
tickertutor/refresh.py      Keeps prices current: the daily background update and switching to a newer database
tickertutor/preload.py      Researches the example questions ahead of time and replays them at a readable pace
tickertutor/stats.py        Report cards: monthly on/off comparison, block bootstrap, verdicts
tickertutor/indicators.py   Moving averages, RSI, momentum, drawdowns, holding odds
tickertutor/sources/        Wikipedia, prices (Alpaca/Tiingo/Stooq), SEC EDGAR, news, FRED clients
tickertutor/build/          fetch.py (download), compute.py (everything above), demo.py (synthetic data)
scripts/                    build_data.py, baseline_compare.py, dev_server.py, sql.py
static/                     index.html, css/app.css, js/ (no build step; js/pages/ has one file per page, js/glossary.js holds the
                            Learn terms and the "?" links), fonts/ (three open-license typefaces served by the app, so nothing
                            loads from another site)
tests/                      offline tests, including the full build against mocked APIs and a browser smoke test
```

## How this meets the assignment

- **Data the model doesn't know, through tools:** prices as of the build date, analyses computed on them for any window, point-in-time backtests computed here, SEC filings, live news. Fifteen tools, including read-only SQL, the same analysis engine the Analyze page uses, and one that measures how big and how unusual a recent move is.
- **Combines evidence and admits limits:** answers join price history, signal track records, filings, and news with citations; the Lead flags what the data can't answer, the Writer must include it, and the Verifier checks numbers against tool results.
- **Deep Research:** four agent shapes (Lead planner/reviewer, three Researcher roles with separate toolsets, Writer, Verifier); Researchers fan out in parallel with fresh contexts; the Lead goes back for more on gaps up to a round cap; vague questions get a clarifying question; citations point to the exact table/query, filing, or article.
- **Frontend:** the home page says what it explores, who it's for, and how to use it on the first screen, and How it works walks through it step by step; the big indexes, by-sector, and individual views; an Analyze tab where a beginner picks a stock or index, an analysis, a period, and settings, and gets the chart with an explanation of how to read it; "?" links from every number to its definition; a live view of the agent team.

## Disclaimer

Ticker Tutor is an educational project. It is not a registered investment adviser and nothing in it is a recommendation to buy or sell any security. Track records describe the past and don't guarantee future results. Tax notes are general US information, not tax advice.
