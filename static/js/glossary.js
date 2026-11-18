// The glossary behind the Learn tab, and the "?" links that point to it from every other page.
import { el } from "./api.js";

// [id, term, definition], grouped. Each card on the Learn tab gets the element id `term-<id>`.
export const GLOSSARY = [
  ["Market basics", [
    ["stock", "Stock (share)", "A small piece of ownership in a company. If the company becomes more valuable, each share is worth more, and some companies also pay owners part of their profit as dividends. \"Stock\" and \"share\" mean nearly the same thing."],
    ["ticker", "Ticker symbol", "The short code a stock trades under, like AAPL for Apple or KO for Coca-Cola. Funds have them too: SPY is a fund that follows the S&P 500."],
    ["index", "Index", "A list of stocks plus a formula that combines their prices into one number, used to track a slice of the market. You can't buy an index directly, but you can buy a fund that follows it. The four big US indexes are described above."],
    ["index-fund", "Index fund and ETF", "A fund that holds the stocks in an index so its value follows the index, for a small yearly fee. An ETF (exchange-traded fund) trades during the day like a stock. Ticker Tutor follows the big indexes through four of them: SPY, QQQ, DIA, and IWM."],
    ["index-weighting", "Index weighting", "How much each company counts in an index. Most indexes weight by company value, so the biggest companies move the index most. The Dow weights by share price instead, so a $500 stock counts ten times as much as a $50 one."],
    ["sector", "Sector", "A group of companies in the same line of business. S&P uses 11 sectors under the GICS standard. Comparing a stock with its sector helps separate company news from industry trends."],
    ["sector-fund", "Sector fund", "A fund that holds only the S&P 500 companies in one sector, like XLK for technology or XLE for energy. Ticker Tutor uses the 11 SPDR sector funds to show how each sector is doing."],
    ["market-cap", "Company value (market cap)", "Share price times the number of shares. What the whole company is worth to the stock market today."],
    ["large-small-cap", "Large cap and small cap", "Shorthand for company size by market value. Large caps are roughly $10 billion and up, which covers most of the S&P 500. Small caps, like the companies in the Russell 2000, are usually under about $2 billion and tend to swing more."],
    ["trading-day", "Trading day and closing price", "US stock markets are open on weekdays except holidays, about 252 days a year (about 21 a month). The closing price is the last price of the day. Ticker Tutor uses daily closing prices, so a \"50-day\" average means 50 trading days, a bit over two months."],
    ["dividend", "Dividend", "Cash a company pays its shareholders, usually every three months, out of its profits. Not every company pays one. Fast-growing companies often keep the money to invest in the business instead."],
    ["stock-split", "Stock split", "When a company swaps each share for several cheaper ones, such as 4 for 1. The price drops to a quarter, you hold four times as many shares, and the value of what you own doesn't change. Charts here are adjusted so a split doesn't look like a crash."],
    ["bull-bear", "Bull market, bear market, correction", "Loose labels for big market moves. A correction is a drop of 10% or more from a recent high. A bear market is a drop of 20% or more. A bull market is a long stretch of rising prices."],
    ["diversification", "Diversification", "Spreading money across many stocks so no single company can hurt much. It's why an index fund usually swings less than most of the individual stocks inside it: one company's bad day is offset by others."],
  ]],
  ["Measuring returns", [
    ["total-return", "Total return (dividends included)", "The price change plus any dividends paid, as if each dividend was used to buy more shares. Every return in Ticker Tutor is a total return, so it can be a little higher than the price change you see quoted elsewhere."],
    ["adjusted-price", "Adjusted price", "Past prices adjusted for stock splits and dividends, so returns calculated from them include dividends and aren't thrown off by splits. Today's adjusted price equals the actual price."],
    ["ytd", "Year to date (YTD)", "From the last close of the previous year to now. A YTD return in March covers about ten weeks. In November it covers most of the year, so the same number means different things at different times."],
    ["annualized", "Per year (annualized)", "A multi-year return restated as the steady yearly rate that ends in the same place. +50% over 3 years is about +14.5% per year, because gains compound."],
    ["compounding", "Compounding", "Earning returns on past returns. $100 that grows 10% a year is $110 after one year and $121 after two, because the second year's 10% applies to $110. Over long periods this is most of the growth."],
    ["percentage-points", "Percentage points (pts)", "The plain difference between two percentages. If a stock returned 12% and the index 8%, the stock was ahead by 4 points. Ticker Tutor writes that as +4.0 pts."],
    ["excess-return", "Excess return", "A stock's return minus the S&P 500's over the same period. +5 pts means it beat the index by 5 percentage points. It separates what the stock did from what the whole market did that day or year."],
    ["beating-the-index", "Beating the index", "Doing better than the S&P 500 over the same period, dividends included. It's the usual yardstick because a low-cost index fund gets you the S&P 500's return with one purchase."],
  ]],
  ["Trend and momentum", [
    ["uptrend", "Uptrend and downtrend", "The general direction of a price over weeks or months, ignoring day-to-day wiggles. A common rule of thumb: above a rising 200-day average is an uptrend, below a falling one is a downtrend. A trend describes the past and can end without warning."],
    ["moving-average", "Moving average (50-day, 200-day)", "The average closing price over the last 50 or 200 trading days, recalculated every day. It smooths out daily noise. A price above its 200-day average is the most common definition of an uptrend."],
    ["ema", "Exponential moving average (EMA)", "A moving average that counts recent days more than older ones, so it reacts faster to new prices. MACD is built from two of them."],
    ["golden-cross", "Golden cross and death cross", "When the 50-day average rises above the 200-day average (golden) or falls below it (death). Popular in headlines. The Analyze tab shows how much it has mattered historically."],
    ["trend-line", "Trend line", "The straight line that best fits a price over a period (a regression line). Its slope gives a steady growth rate, and the distance from the line shows whether the price is above or below its own trend."],
    ["momentum", "Momentum", "How a stock did over roughly the past year, usually skipping the most recent month. Stocks that have done well have tended to keep doing a bit better for a while. It's one of the better-documented patterns in finance, and it can reverse sharply."],
    ["52-week-high", "52-week high", "The highest price in the past year. Being near it sounds expensive, but historically it has been more of a strength sign than a warning."],
    ["rsi", "RSI (relative strength index)", "A 0–100 score of recent ups vs downs, usually over 14 days. Above 70 is often called overbought, below 30 oversold. It was built for short-term trading."],
    ["overbought-oversold", "Overbought and oversold", "Trader shorthand for \"risen a lot, fast\" and \"fallen a lot, fast\", usually read from RSI above 70 or below 30. They describe recent speed. They don't mean the price is about to turn around."],
    ["macd", "MACD", "The gap between a 12-day and a 26-day average of the price (both weighting recent days more), plus a 9-day average of that gap called the signal line. The gap crossing above its signal line means short-term momentum is picking up. It reacts after turns, not before."],
    ["bollinger", "Bollinger Bands", "A 20-day moving average with bands two standard deviations above and below it. The bands widen when prices swing more and narrow when they calm down. A close outside the bands is unusual, but not a reliable signal by itself."],
    ["volume", "Trading volume", "How many shares changed hands in a day. Unusually heavy volume often comes with news like an earnings report. It shows how much interest there was, not which way the price will go."],
    ["signal", "Signal", "A yes-or-no rule based on data, like \"the price is above its 200-day average\" or \"RSI is below 30\". Ticker Tutor tests 15 popular ones against history to see whether stocks with the signal actually did better afterwards."],
  ]],
  ["Risk", [
    ["volatility", "Volatility", "How much the price swings, as a yearly percentage (the annualized standard deviation of daily returns). 20% volatility means a typical day moves about 1.3%. Higher volatility means a bumpier ride."],
    ["typical-daily-move", "Typical daily move", "The size of an ordinary day's change for a stock (one standard deviation of its daily returns). If a stock's typical day is 1.5%, a 6% drop is four times its normal move, which is rare. It's the yardstick for how unusual a big day was."],
    ["beta", "Beta", "How much a stock tends to move when the market moves. A beta of 1.3 means it has moved about 30% more than the S&P 500, in both directions. Below 1 means smaller moves than the market."],
    ["drawdown", "Drawdown", "The drop from a peak to a later low. The biggest drawdown shows the worst stretch someone holding the stock lived through, and how long getting back took."],
    ["vix", "VIX", "An index of how much traders expect the S&P 500 to swing over the next 30 days, as a yearly percentage, worked out from option prices. Often called the fear gauge. Below about 15 is calm and above about 25 is nervous. It measures expected size of moves, not direction."],
    ["treasury-yield", "10-year Treasury yield", "The yearly interest the US government pays to borrow for 10 years. It's the benchmark for what \"safe\" money earns. When it rises, stocks compete with a better safe alternative, which can weigh on prices."],
    ["market-breadth", "Market breadth", "How many stocks are taking part in a move. One common measure is the share of S&P 500 stocks above their 200-day average. If the index is rising while few stocks are, a handful of giants is doing the lifting."],
  ]],
  ["Company finances", [
    ["revenue", "Revenue", "Total sales: the money a company brings in from customers before any costs. Revenue growth compares it with the year before."],
    ["net-income", "Net income (earnings)", "Profit left after every cost, interest payment, and tax. \"Earnings\" usually means this. A company can grow revenue and still lose money."],
    ["eps", "Earnings per share (EPS)", "Net income divided by the number of shares. It's the E in P/E. Stocks often move on whether a quarter's EPS beat or missed what analysts expected."],
    ["profit-margin", "Profit margin", "Net income as a share of revenue. A 20% margin means the company keeps $20 of profit from every $100 of sales. Normal levels differ a lot by industry: grocers run thin margins, software companies wide ones."],
    ["operating-margin", "Operating margin", "Profit from the core business, before interest and taxes, as a share of revenue. It shows how well the main business makes money, apart from how it's financed."],
    ["free-cash-flow", "Free cash flow", "Cash from operations minus spending on equipment and buildings. Cash the company could use for dividends, buybacks, or paying down debt."],
    ["equity", "Shareholders' equity", "What would be left for owners if the company sold everything it has and paid everything it owes: assets minus debts. Also called book value."],
    ["debt-to-equity", "Debt to equity", "Long-term debt divided by shareholders' equity. Higher means more borrowing. What's normal varies a lot: utilities and banks carry more by design."],
    ["pe", "P/E ratio", "Share price divided by the last 12 months of earnings per share. Roughly, how many years of current profits you pay for. Compare it with the company's own history and its sector, not across very different businesses."],
    ["valuation", "Valuation", "How the price compares with what the business earns or owns, usually through ratios like P/E. A high valuation means buyers are paying up for expected growth. It says how much is expected, not whether the stock will rise or fall."],
    ["dividend-yield", "Dividend yield", "Yearly dividends per share divided by the price. A 3% yield pays about $3 a year for every $100 of stock. Companies can cut dividends."],
    ["buyback", "Buyback", "When a company uses its cash to buy its own shares. Fewer shares are left, so each one owns a slightly bigger slice of the company. It's another way of returning money to shareholders."],
    ["fiscal-year", "Fiscal year", "The 12 months a company uses for its books, which doesn't have to match the calendar. Apple's fiscal year ends in late September and Walmart's at the end of January, so \"fiscal 2025\" covers different months for each."],
    ["ttm", "Last 12 months (TTM)", "The four most recent quarters added together, also called trailing twelve months. It's more up to date than the last annual report because it rolls forward every quarter."],
    ["earnings-report", "Earnings report", "The results a company releases each quarter: revenue, profit, EPS, and often an outlook. Prices can jump or drop in the day or two after, which is what the earnings reaction numbers measure."],
    ["sec-filings", "SEC filings (10-K, 10-Q, 8-K)", "Reports public companies must file with the Securities and Exchange Commission. The 10-K is the audited annual report, including its Risk Factors. The 10-Q is the quarterly report. An 8-K announces a major event, like an acquisition or a new CEO."],
  ]],
  ["Words in the news", [
    ["big-move", "Big one-day move", "In Ticker Tutor, a day when a stock moved at least 5 percentage points more (or less) than the S&P 500. Measuring against the index filters out days when everything rose or fell together, so what's left is news about that company or its industry."],
    ["beat-miss", "Beat and miss", "Whether a company's quarterly results came in above (beat) or below (miss) what Wall Street analysts expected. Stocks react to the surprise, not the raw number, so a company can report record profit and still fall if more was expected."],
    ["guidance", "Guidance (outlook)", "A company's own forecast for the coming quarter or year, given alongside its earnings report. A weak outlook can sink a stock even after a strong quarter, because prices look forward."],
    ["priced-in", "Priced in", "Already reflected in the price. If everyone expects good news, buyers have usually paid for it in advance, so the stock may not rise when it arrives. It's why prices sometimes fall on good news and rise on bad."],
    ["analyst-rating", "Analyst upgrade, downgrade, price target", "Opinions from research analysts at banks and brokers. An upgrade or downgrade changes their rating, such as from \"hold\" to \"buy\". A price target is their guess at the price about a year out. They can move a stock for a day and are often wrong."],
    ["gap", "Gap up and gap down", "When a stock opens far above or below the previous day's close, usually because news came out while the market was closed. Earnings are mostly released after the close or before the open, which is why reactions show up as gaps."],
    ["merger", "Merger and acquisition (M&A)", "One company buying or combining with another. The company being bought usually jumps toward the offer price. The buyer often dips, since it's the one paying."],
    ["fed", "The Fed and interest rates", "The Federal Reserve sets short-term US interest rates. Higher rates make borrowing cost more and make safe savings pay more, which tends to weigh on stock prices. Lower rates do the opposite. Markets often move on hints about what the Fed will do next."],
    ["inflation", "Inflation (CPI)", "How fast prices for everyday things are rising, most often measured by the Consumer Price Index. High inflation pushes the Fed toward higher interest rates, so inflation reports can move the whole market."],
  ]],
  ["Statistics and testing", [
    ["average-median", "Average and median", "Two ways to say what's typical. The average adds everything up and divides. The median is the middle value when sorted. A few extreme values pull the average but barely move the median, so the median is often the fairer \"typical\"."],
    ["standard-deviation", "Standard deviation", "A measure of spread: how far values typically land from their average. For roughly bell-shaped data, about two-thirds fall within one standard deviation and about 95% within two."],
    ["distribution", "Distribution and bell curve", "A picture of how often each size of result happened, drawn as a histogram. Daily stock returns pile up near zero in a rough bell shape, but extreme days happen more often than a true bell curve predicts. Those are called fat tails."],
    ["skew-kurtosis", "Skewness and kurtosis", "Two numbers that describe a distribution's shape. Skewness says whether big moves lean to the downside (negative) or upside (positive). Excess kurtosis above zero means extreme days are more common than a bell curve would suggest."],
    ["percentile", "Percentile", "Where a value ranks against the rest. \"Higher than 90% of days\" means only one day in ten was higher. It turns a raw number into how unusual it is."],
    ["rolling-window", "Rolling window", "The same calculation repeated over a moving stretch of time. A rolling 1-year return computes the return for every 12-month window, one starting each day, which shows the range of outcomes and not just one."],
    ["regression", "Regression and R²", "A regression fits the best straight line through data. R² (0 to 1) is the share of the variation the line accounts for. Near 1 means the points hug the line."],
    ["correlation", "Correlation", "How consistently two things move together, from −1 (opposite) through 0 (unrelated) to 1 (in lockstep). Correlation isn't causation."],
    ["base-rate", "Base rate", "How often something happened across similar past cases. If 55% of stocks beat the index in the year after a big one-day drop, that's the base rate: a starting point before looking at any one company's story."],
    ["confidence-interval", "95% range (confidence interval)", "A range that reflects how uncertain an estimate is, given how much data there is and how noisy it is. If the range for a signal's extra return runs from −1 to +5 points, zero is inside it, so the signal can't be told apart from luck."],
    ["backtest", "Backtest", "Testing a rule on past data as if you'd followed it at the time. Useful for learning what has happened. It can't promise what will."],
    ["held-out", "Held-out period", "Recent data set aside and not looked at while a rule is being judged, then used as a final check. If an edge shows up in the older data but vanishes in the held-out years, it was probably luck or has stopped working."],
    ["survivorship-bias", "Survivorship bias", "Looking only at the winners that are still around. If a test leaves out companies that went bankrupt or were dropped from the index, results look better than what anyone actually lived through. Ticker Tutor rebuilds the index's past members to limit this."],
  ]],
];

const BY_ID = new Map(GLOSSARY.flatMap(([, terms]) => terms.map(([id, term, text]) => [id, { term, text }])));

// Index cards on the Learn tab use these ids too (from the server's index list).
const INDEX_TERMS = { sp500: "S&P 500", nasdaq100: "Nasdaq-100", dow: "Dow Jones Industrial Average", russell2000: "Russell 2000" };

// Terms that help with each analysis on the Analyze tab.
export const ANALYSIS_TERMS = {
  moving_averages: ["moving-average", "golden-cross", "uptrend", "trading-day"],
  trendline: ["trend-line", "regression", "standard-deviation", "annualized"],
  macd: ["macd", "ema", "momentum", "signal"],
  rsi: ["rsi", "overbought-oversold", "momentum"],
  momentum: ["momentum", "excess-return", "percentile"],
  volatility: ["volatility", "typical-daily-move", "standard-deviation", "diversification"],
  bollinger: ["bollinger", "standard-deviation", "moving-average"],
  drawdown: ["drawdown", "bull-bear", "52-week-high"],
  beta: ["beta", "correlation", "regression"],
  relative: ["total-return", "excess-return", "beating-the-index", "sector-fund"],
  rolling_returns: ["rolling-window", "annualized", "average-median", "base-rate"],
  returns_distribution: ["distribution", "standard-deviation", "skew-kurtosis", "typical-daily-move"],
  volume: ["volume", "earnings-report", "gap"],
};

// The Learn term behind a number's label on the Analyze tab, so each stat can carry a "?".
const STAT_TERMS = [
  [/^R²/, "regression"], [/^Correlation/, "correlation"], [/^Beta/, "beta"], [/^RSI|Average RSI/, "rsi"],
  [/^MACD|Signal line|Histogram now/, "macd"], [/^%B|Band width|band/i, "bollinger"],
  [/Typical daily move/, "typical-daily-move"], [/^Volatility/, "volatility"], [/^Standard deviation/, "standard-deviation"],
  [/Skewness|kurtosis/, "skew-kurtosis"], [/beyond 3 standard deviations/, "distribution"],
  [/Biggest drop|Below its high|drops of 10%|Back to the old high/, "drawdown"],
  [/^Per year|Trend growth rate/, "annualized"], [/total return/, "total-return"], [/^Difference|^Gap vs/, "excess-return"],
  [/^Sector fund/, "sector-fund"], [/median/i, "average-median"], [/^Beat the S&P 500/, "beating-the-index"],
  [/^Higher than/, "percentile"], [/Windows ending/, "rolling-window"], [/daily volume|Heavy day|vs average/, "volume"],
  [/crossover/i, "golden-cross"], [/-day average/, "moving-average"], [/trend line|from the line|outside the band/, "trend-line"],
  [/-day change|positive momentum/, "momentum"],
];
export function statTerm(analysisId, label) {
  for (const [re, id] of STAT_TERMS) {
    if (!re.test(label)) continue;
    if (id === "golden-cross" && analysisId === "macd") return "macd";
    if (id === "moving-average" && analysisId === "volume") return "volume";
    return id;
  }
  return null;
}

export const termName = (id) => BY_ID.get(id)?.term || INDEX_TERMS[id] || id;
export const learnHref = (id) => `#/learn?term=${encodeURIComponent(id)}`;

// A small "?" that opens the term's card on the Learn tab. Hovering shows the short definition.
export function learnLink(id) {
  const t = BY_ID.get(id);
  if (!t && !INDEX_TERMS[id]) console.warn(`No Learn card for "${id}"`);
  const name = t?.term || INDEX_TERMS[id] || id;
  return el("a", { class: "qmark", href: learnHref(id), title: t ? `${t.term}: ${t.text}` : `What is the ${name}?`,
    "aria-label": `What is ${name}? Opens Learn`, onclick: (e) => e.stopPropagation() }, "?");
}

// A term written out as a link to its Learn card, for running text.
export function termLink(id, text) {
  return el("a", { class: "term-link", href: learnHref(id), onclick: (e) => e.stopPropagation() }, text || termName(id));
}

export const hasTerm = (id) => BY_ID.has(id) || id in INDEX_TERMS;
export const TERM_COUNT = BY_ID.size;
