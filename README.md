# Global Stock Research

A local Streamlit dashboard for worldwide stock research. It provides:

- company-name and ticker search across international exchanges;
- interactive candlestick or closing-price charts with volume;
- 200-day moving average overlay using buffered daily prices;
- annual revenue with year-over-year growth;
- quarterly revenue with quarter-over-quarter growth;
- annual and quarterly cost of revenue as a percentage of revenue;
- industry-based major cost drivers and monitoring variables for individual stocks;
- grouped valuation, profitability, growth, and financial-health metrics;
- prominent EV / Revenue valuation multiple;
- shareholder yield from dividends plus net buybacks;
- annual and quarterly ordinary share-count trends;
- original industry, country, and revenue-growth tailwinds and headwinds;
- structured upcoming events, evidence-based catalyst hypotheses, and source-linked
  reasons revenue might accelerate;
- direct links to current ticker and company discussions on X;
- company overview and profile information;
- an expanded company business description on the main stock screen;
- reported short interest, short percentage, and days to cover when available;
- CSV export of displayed price history.
- a global ETF market atlas with rapid previous/next chart navigation;
- a commodity ETF/ETP atlas spanning broad baskets, energy, precious and
  industrial metals, agriculture, and tanker freight;
- all 11 GICS sectors represented by global-sector ETF proxies;
- detailed, parent-sector-linked industry exposures where practical ETFs exist;
- the complete March 2023 GICS hierarchy: 11 sectors, 25 industry groups,
  74 industries, and 163 sub-industries, including rows without ETF proxies;
- broad developed, emerging, and frontier country-market ETF coverage;
- dedicated pan-Africa and Latin America regional ETF queues;
- 60 non-duplicative thematic ETF exposures across 25 theme families, including
  cybersecurity, AI, cloud, nuclear energy, quantum computing, digital consumer,
  transportation, environmental services, and other themes;
- five-year ETF charts with 200-day moving averages, returns, volatility, and drawdown.
- provider-reported ETF dividend/distribution yield in the chart overview.
- provider-reported top holdings for every ETF where Yahoo Finance supplies them.
- an ETF inflection scanner for possible early positive turns after material declines.
- a European stock scanner universe sourced from IEUR's official daily holdings;
- an early-breakout scanner inspired by CLMT on February 3, 2026, with prior-range
  and volume confirmation, held-breakout checks, annotated charts and a dated reference;
- one Income strategies table combining global infrastructure and a researched
  100-security NYSE/Nasdaq ADR universe, with separate qualification/yield methods,
  operating-exposure and venue research, company overviews, filters and CSV export;
- a short-only out-of-fashion strategy driven by declining Google Trends, Reddit,
  and news attention signals;
- a strict Richard Koch Star Principle strategy with source-linked market-leadership
  and niche-growth evidence;
- a curated IP-backed turnarounds strategy with cross-sector product-company
  research, an evaluation checklist, dated sources and stock-research handoffs;
- a semiconductor-equipment volatility pilot that finds concentrated unusual
  acceleration and connected quiet peers, with saved results, charts and CSV export.

## Requirements

**ITPM strategy** is available in the sidebar as a placeholder. No screening
rules or signals are configured; strategy details will be added later.

**Biotech strategy** is a sidebar placeholder for planned AI assessment of biotech
companies, with PFC filings and Substack noted as planned stock sources. Source
ingestion, assessment criteria and screening rules are not configured, and opening
this section makes no market-data or AI requests.

**Yellow Bricks strategy** is a sidebar placeholder for a strategy based on Yellow
Bricks. Details, screening rules and source integration are not configured; no
analysis, market-data or AI requests run in this section.

**Tax loss harvesting strategy** is a sidebar placeholder. Tax jurisdiction,
eligibility criteria and trading rules are not configured; no tax calculations,
screening, market-data or AI requests run in this section.

**Druckenmiller-like portfolio** is also a sidebar placeholder. Holdings, screening
rules, allocations and risk controls are not configured yet. It does not represent
Stanley Druckenmiller's actual holdings.

- Python 3.10 or newer
- Streamlit 1.60 or newer (installed by the requirements below; required for stateful chart tabs)
- Internet access while using the dashboard

## Install and run

Open PowerShell in this folder and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Streamlit opens the dashboard at `http://localhost:8501`.

The **Deploy** button belongs to Streamlit and starts a workflow to publish/host
the app online. It is not a refresh, save, or run control and is unnecessary for
local use. Merely seeing this button does not mean the app is deployed.

## Research workspace and stock chat

Individual stock research is organized into four sections:

- **Overview:** price/volume chart, price-data export and full company profile.
- **Financials:** rolling revenue comparison, annual/quarterly revenue, costs and valuation metrics.
- **Ownership:** insider purchases, shareholder returns and short interest.
- **Research:** catalysts, on-demand revenue outlook, business drivers, news sentiment
  and public-discussion links.

### On-demand revenue outlook from supplied excerpts

In **Individual stocks → Research → Revenue outlook**, supply up to four public
source excerpts (up to 6,000 characters each), with titles and publication dates.
Source URLs are optional reference links: the app **does not fetch them or search
the web**. The same panel is available for the selected stock in the **U-recovery
scanner**, including when that candidate's chart is unavailable. It is not offered
for the ETF scanner.

Choose a **6, 12 or 24 month** horizon (default 12), explicitly consent to the API
request and run the assessment. It uses the shared **AI assistant settings** key
and `OPENAI_REVENUE_MODEL` (default `gpt-4.1-mini`). Only the selected ticker/company,
assessment date/horizon and supplied source titles, dates and excerpts are sent.
Source URLs, other stocks, ordinary chat history, checklist/management notes and
portfolio information are not included. Do not paste private material or credentials.
OpenAI API charges and provider retention policies apply; requests use `store=false`.

The report distinguishes reported results from management expectations, cites
supplied source IDs, and evaluates leading indicators such as orders/backlog, RPO,
deposits, customer expansion, usage and production ramps where supported by the
excerpts. Five checks cover **demand, conversion timing, demand quality, ability
to deliver, and offsets/erosion**. Missing evidence remains **Insufficient evidence**.
The evidence balance describes the supplied indicators, not a growth forecast,
probability, valuation judgment or recommendation. Supportive indicators can coexist
with important unverified conversion/funding assumptions.

The app validates response structure, stock/horizon identity and source references;
it does **not** independently authenticate excerpts, verify AI factual interpretation
or establish that the sources are complete/current. Review source dates and missing
comparisons, cancellations, acquisitions, billing changes, capacity and cash needs.
Backlog growth or a clinical milestone alone does not guarantee future revenue.

There is **one request per explicit run**, no automatic retry or background research.
Changing inputs, navigating, refreshing market data or reopening a report does not
run a new assessment. Drafts and accepted reports are isolated per stock in the
browser session; they are not saved across server restarts or shared with other
browser sessions. Download the JSON report (including its source excerpts) to retain
it. Failed attempts retain any previous accepted report, which stays dated as the
previous assessment. These reports are not sent to ordinary stock chat and do not
activate the **Expected positive revenue growth** placeholder or alter scanner filters.

### Business-recovery filters

The U-recovery stock scanner has six additional **optional AND filters**. They
do not change the technical U-pattern model or apply company fundamentals to ETFs.
Unselected filters do not fetch additional data. Each selected filter shows an
audit of passing, failing and unknown candidates; unknown/unreviewed never passes.
These are transparent research hypotheses, not backtested predictors of higher returns.

- **Improving profitability and cash generation:** operating margin AND free cash
  flow must improve. Shrinking negative free cash flow can qualify and is not
  described as positive cash generation. Compare the latest four quarters with
  the preceding four where complete comparable histories exist; otherwise label
  the comparison as a fiscal-year fallback. Revenue growth alone cannot pass.
  Quarterly endpoints older than 200 days or annual endpoints older than 550 days
  are Unknown. Flows are provider-reported discrete quarters/full fiscal years;
  reporting-currency changes, stub periods and filing availability are not
  independently verified. This is not a point-in-time backtest.
- **Sector-relative strength:** the stock must outperform its global-sector ETF
  over **both three and six calendar months**. Both legs use dividend/split-adjusted
  prices and matching observed dates; foreign stock returns are converted to USD
  using historical FX. No unadjusted-price or missing-FX fallback silently passes.
  The benchmark comes from the existing 11-sector ETF catalog and is shown by name
  and ticker. These are global, often US-heavy sector proxies, **not exact local
  sector or industry peers**. ETF fees and different market closing times remain
  limitations. Common latest observations must be no more than seven days old.
- **Market cap under $2B:** strictly positive equity capitalization **below
  USD 2,000,000,000**, not enterprise value or the unconverted local value.
  Yahoo's marketCap uses major currency units even where share prices use pence.
  FX is dated at or before the provider quote date (maximum five-day gap).
  Quote dates older than ten calendar days, unsupported currencies or missing
  capitalization produce Unknown. The quote date is not a verified share-count date.
- **Deleveraging turnaround:** both gross debt and net debt must decline versus
  the comparable prior-year balance sheet, and latest free cash flow must be
  positive. Repaying debt with existing cash alone cannot pass unchanged net debt.
  Falling debt/EBITDA alone is insufficient. This does **not** establish the source
  of repayment, debt maturity safety, covenant compliance, sustainable earnings,
  dilution or the impact of asset sales; review those separately. Generic corporate
  accounting screens are not suitable for banks, insurers and REITs.
- **Positive shareholder yield (>0%):** (cash dividends + buybacks - proceeds
  from share issuance) / current market capitalization must be **strictly above
  zero**. This reuses the shareholder-yield metric in individual-stock research.
  Use the latest four complete consecutive quarters, or a labeled full fiscal-year
  fallback. Missing flows are not assumed to be zero or replaced by older quarters.
  TTM endpoints older than 200 days and fiscal-year endpoints older than 550 days
  are unavailable. Missing/nonfinite values and unknown or mismatched cash-flow
  versus market-cap currencies cannot pass; this metric does not perform FX
  conversion. Pence quotes still use major-unit market capitalization.
  Results show the percentage and period, with components and source in recovery
  evidence. Debt repayment is **not** included, and cash issuance is not a complete
  measure of stock-based-compensation dilution. This is a current screen, not a
  point-in-time backtest.
- **Management & Incentives:** an explicitly **manual, source-backed favorable
  review**, not an automatically inferred CEO-change or stock-compensation signal.
  Use the dedicated Management & incentives workspace or a stock's evidence panel
  to record appointment details, mandate, old/new incentive metrics, time horizons,
  ownership/price hurdles and safeguards. Unresearched stocks stay Unreviewed.
  Favorable requires a review within 365 days, a dated CEO and incentive source,
  primary-source confirmation, structured evidence and your rationale. A stale
  favorable review becomes Needs evidence without deleting its saved judgment.
  There is no automatic web research batch or paid AI assessment.

Open **Financials > Recovery > Business recovery & management** on an individual
stock, or the corresponding panel below a scanner chart. **Load recovery evidence**
fetches only that stock's additional comparisons using the same 24-hour per-symbol
caches as screening. Metrics, dates, currencies, benchmark returns and sources are
available in the panel. Stock chat can explain loaded public recovery evidence;
manual management notes are **not** included in its context.

Management records persist locally in `data/management_evidence.sqlite3`, separate
from bookmarks and market caches. They are shared by browser sessions connected
to the local app and survive restarts. Back up this database with the app stopped.

A compact **stock chat** panel accompanies individual stocks, bookmarks and
selected scanner/strategy candidates, including ETFs. Conversations are separate
for each ticker (including its exchange suffix) and shared across views within
the same browser session. They are not stored on disk and do not survive a new
browser session or app restart. Clearing a conversation affects only that stock.

Configure the shared key under **AI assistant settings** in the sidebar, or set
`OPENAI_API_KEY` before starting the app. The same connection powers news summaries
and chat. `OPENAI_CHAT_MODEL` optionally overrides the chat model (default
`gpt-4.1-mini`); `OPENAI_NEWS_MODEL` still controls news summaries.
Do not paste API keys into chat. The password-field key is kept only in local
server session memory, not written into project files.

Questions are submitted explicitly; simply viewing, navigating or rerunning a page
does not generate a paid chat request. The assistant receives a bounded snapshot
of public company metadata, prices, annual/quarterly financials, the scanner's
rolling-growth comparison, available news excerpts, and the selected strategy's
evidence, together with your question and recent conversation for that ticker.
Market data retains the **24-hour cache**; chat messages are not globally cached.
Data needed for chat is loaded only when you submit a question, using those caches.

**Privacy and limitations:** your question and recent chat history are sent to
OpenAI alongside the public stock context. Do not enter private account details,
portfolio data or credentials. API usage is billed separately from ChatGPT/Copilot.
Requests use `store=false`, but provider retention policies still apply. The chat
does not browse the web or have live market access: it explains the supplied data
and financial concepts, identifies dates and missing evidence, and may make
mistakes. Responses are not verified conclusions or personalized investment advice.
API or provider failures are shown explicitly; resubmission is manual.

## Trade checklist

Choose **Trade checklist** under Research area for a reusable general pre-trade
review. The **Add checklist item** form is visible at the top of the page: enter a
title and click **Add item** to save a new unchecked point directly. Notes,
attribution and source link are optional. Existing review marks are preserved.
Check an item after reviewing it; **Start new review** clears the checkmarks
without deleting your principles. You can add, edit or remove items and optionally
record an attribution and source link. Editing an item unchecks it for review.
Removal requires confirmation; **Reload checklist** reads changes from another
browser session.

The first item is the requested reminder that crowded trades can be acceptable
when the thesis is sound and the trend supportive. Its attribution to Stanley
Druckenmiller is clearly labeled as a **user-supplied paraphrase, not a verified
quotation**. It is seeded once, so editing or deleting it is respected.

Items and review marks persist in `data/trade_checklist.sqlite3`, separately from
market caches, bookmarks and management reviews. They survive app restarts, are
shared by browsers using the local app and are excluded from source control.
Checklist notes are not sent to AI; the module does not fetch market data or
place trades. Source links open only when clicked. This is a reusable checklist,
not a per-stock trade journal or a guarantee of a successful trade.

## Other charts: S&P 500 market breadth

Choose **Other charts**, then **Load S&P 500 breadth**. This on-demand dashboard
compares the S&P 500 price index with a cumulative advance/decline line, and shows
the percentage of stocks above their 50- and 200-day moving averages. The latest
daily advancing/declining counts and index move are displayed together.

The universe is the **current IVV equity holdings**, including separate share
classes, not a historical constituent database. Historical results therefore have
survivorship/membership bias and are a reconstruction, not an official breadth
series. Stocks use Yahoo dividend/split-adjusted closes; `^GSPC` is the S&P 500
price index, not a total-return benchmark. These charts measure participation,
not the percentage of stocks outperforming the index.

Two years of daily prices provide moving-average warm-up; the chart shows up to
252 completed index sessions. Today's New York session is excluded even after
the close. Daily direction requires a valid price on two adjacent index sessions;
moving averages require 50/200 consecutive valid observations. Missing prices
are never filled or counted as declines. Each metric needs at least 95% coverage
of the requested universe, with denominators and a per-listing coverage audit
visible. Below that threshold, percentages and net advances are unavailable.
The cumulative A/D line restarts after an unavailable day rather than silently
bridging the gap. It starts from zero before the displayed window, and uses a
different axis from the index; compare direction, not their absolute heights.

Normal caching remains 24 hours and **Refresh data** bypasses it. The first load
may take a few minutes; no AI requests are involved. CSV export includes dates,
raw counts, coverage, percentages, index values and A/D segment identifiers.
Breadth divergences are research signals, not automatic trading recommendations.

## Bookmarks

Use **Bookmark stock** on an Individual stocks page, U-recovery scanner
candidate, or Star Principle candidate to save it, and **Remove bookmark** to remove it. International
listing suffixes are preserved, so different exchange listings remain distinct.
ETF scanner candidates can also be saved.

In the **ETF market atlas**, use **Bookmark ETF** above the selected fund's chart.
It uses the same saved list and becomes **Remove bookmark** after saving. The
control remains available when price history or fund metadata cannot be loaded;
classification entries without a mapped ETF cannot be bookmarked.

Choose **Bookmarks** under Research area to browse the saved list, step through
five-year charts with Previous/Next, or open the selected security in Individual
Stocks with the bookmark queue available there. A bookmark can still be removed
when its market data is unavailable.

Bookmarks are stored in `data/bookmarks.sqlite3`, independently of the market-data
cache. They survive browser refreshes and app restarts and are shared by browser
sessions connected to this local app. The database is excluded from source control;
back it up with the app stopped if you want to move your saved list.

## Worldwide ticker symbols

Search by company name, or enter the Yahoo Finance symbol directly. Listings outside
the US commonly need an exchange suffix:

| Market | Example |
| --- | --- |
| Germany | `BMW.DE` |
| Japan | `7203.T` |
| Australia | `BHP.AX` |
| India | `RELIANCE.NS` |
| United Kingdom | `SHEL.L` |

The same company may have listings in multiple currencies and markets. Select the
specific exchange you want to research.

## ETF market atlas

Choose **ETF market atlas** under **Research area** to browse market categories.
The sector view uses the standard 11-sector GICS structure. The country view groups
broad-market ETF proxies using the developed, emerging, and frontier convention used
by major index providers. Filters and previous/next buttons make it possible to step
through every chart in the current queue.

Charts request five years of prices, but provider history may be shorter. Period
return uses the available history; an unavailable 200-day average displays as N/A.
If fewer than two usable closing prices are returned, the atlas explains the
problem instead of calculating statistics. Refresh and ETF navigation remain
available so you can retry or choose another listing.

The **Industry exposures** view breaks the top-level GICS sectors into more focused
areas such as semiconductors, software, biotechnology, banks, insurance, retail,
transportation, metals and mining, and REITs. These ETFs are GICS-aligned investable
proxies rather than an exhaustive or exact replication of every formal GICS industry
or sub-industry. Detailed ETF availability is strongest in the US, which is shown in
the exposure-region field.

The **Full GICS hierarchy** view preserves every official March 2023 sub-industry.
ETF proxies are mapped only where a reasonably aligned active fund exists. Unmapped
rows remain visible as **no ETF proxy**, avoiding false precision from unrelated
thematic funds.

The **Country markets** view shows only countries with a mapped ETF. Countries
without one are omitted from its filters, selector, chart queue and Previous/Next
navigation; their classifications remain in the underlying catalog. A temporary
price-data error does not remove a mapped ETF. The full GICS hierarchy still
includes unmapped sub-industries.

The catalog covers developed, emerging, frontier, and standalone markets. Greece
remains in the emerging group until its announced May 2027 developed-market transition. Market
classification does not imply that a specific IBKR account can trade a local market
or ETF.

Bulgaria remains standalone until its announced May 2027 frontier-market transition.

The **Regional markets** view includes AFK for pan-Africa exposure and ILF, FLLA,
and FLN for Latin America. The Latin America funds include Mexico, so they are not
labeled as pure South America funds. Country ETFs for Brazil, Chile, Colombia, Peru,
Argentina, and South Africa remain available in the country view. Closed Egypt and
Nigeria ETFs are intentionally not mapped.

Country proxies favor broad-market exposure: the United States uses ITOT rather than
the large-cap-only SPY. FLN is labeled factor tilted and is an alternative rather than
a core Latin America proxy. EPU includes Peru and related global exposure, as reflected
in its fund name.

The **Thematic ETFs** view groups active, non-leveraged equity funds by theme and
subtheme. It uses one representative per subtheme rather than listing near-identical
issuer alternatives. Coverage spans 25 theme families and includes AI, robotics,
cloud and data centers, IoT, 5G, fintech, nuclear energy, critical materials, space,
digital health, consumer trends, emerging digital economies, quantum computing,
shipping, and environmental services. Thematic labels describe fund mandates rather
than guaranteed pure-play exposure.

The healthtech mapping uses **HEAL**, not the former **EDOC** ticker. Global X
[changed the fund and benchmark on April 1, 2025](https://www.globalxetfs.com/articles/why-healthtech-why-heal),
broadening its mandate beyond telemedicine. HEAL's provider history includes the
pre-change fund; charts and chat context disclose that it is not five years of the
current strategy. Saved atlas selections move from EDOC to HEAL; existing personal
bookmarks are not rewritten.

Every mapped ETF has a **Holdings** view. Yahoo generally provides the largest
positions rather than the complete portfolio, so the dashboard labels these as top
holdings and notes that weights can lag the issuer's own daily disclosure.

The catalogue favors established US-listed ETF proxies so one comparable instrument
can represent each market. A proxy may differ materially from its local market because
of index construction, fees, currency effects, foreign ownership limits, and fund
availability. IBKR access is not guaranteed: it depends on the user's residence,
trading permissions, exchange access, and product eligibility.

Taxonomy references:

- GICS Methodology 2023: <https://www.msci.com/documents/1296102/11185224/GICS+Methodology+2023.pdf>
- MSCI market classification: <https://www.msci.com/indexes/index-resources/market-classification>
- IBKR products and exchanges: <https://www.interactivebrokers.com/en/trading/products-exchanges.php#/>

## Early breakout strategy

Choose **Early breakout strategy** under **Research area** to screen for the early
consolidation-breakout phase illustrated by **CLMT on February 3, 2026**, rather
than its later February 13 momentum surge. It is separate from the U-recovery
scanner; it does not change U-shape qualification or add a CLMT-only exception.

Use **Run breakout scan** for the current Russell 2000, S&P 500 or European holdings,
or enter up to 50 **Custom tickers** (including exchange suffixes). These are the
existing holdings-based universes, not complete global exchange lists. Historical
membership is not reconstructed and this is not a point-in-time backtest.
The page does not download anything merely when opened. Prices load with up to
four concurrent workers and the existing 24-hour failure-aware cache; missing
coverage is shown separately from a stock that does not qualify.

### Price-only rules

Using dividend/split-adjusted daily OHLC and provider-reported volume:

1. The event close is at least **1% above the highest intraday high of the preceding
   60 trading observations**, excluding the event.
2. That prior range's depth `(highest high - lowest low) / highest high` is **at most
   30%**. This is a bounded consolidation heuristic, not a fitted reference image.
3. Event-day closing return is **at least 3%**.
4. Volume is **at least 1.5 times the prior 20-session mean**, excluding the event;
   at least 15 of those sessions must have positive volume.
5. **Close > MA50 > MA200**, and MA50 exceeds its value 20 sessions earlier.
6. The close is **at most 25% above MA50**, and in the **upper 30%** of that day's
   high-low range. This limits some already extended spikes.

After the newest qualifying event, every subsequent **close** must hold at or above
the original breakout level, and the latest close must remain above MA50. An intraday
retest alone does not invalidate it. A breach remains a **Failed breakout** until a
new qualifying event; it is not resurrected merely because price later bounces.
The local default filters retain events **at most 5 trading sessions ago** and a latest
close **0-10% above the original level**. Age 0 means the latest completed bar.
Age can be changed from 1 to 20 sessions, and maximum extension from 0% to 30%,
without fetching prices again.

At least **221 valid daily observations** are required; missing/nonfinite/impossible
OHLC, duplicate dates, unavailable recent volume and prices older than seven calendar
days are marked unavailable. To avoid intraday confirmation, current-date bars are
conservatively excluded using the prior UTC calendar date, even when a local market
has already closed. Signals depend on the event's closing data and are not assumed
tradable at an earlier price. Provider adjustments and volume definitions can change.

### Reference, results and controls

The dated CLMT reference records a **23.41** prior high, **23.99** breakout close,
approximately **+5.54%** daily return and **1.66x** prior average volume on February 3.
The historical reference chart is loaded only on request and ends at that event,
without using the later rally to calculate the signal. The reference is not inserted
into current results or evidence of future returns.

Current matches have an on-demand adjusted chart with the original level and event
marked, a bookmark action and **Open in Individual Stocks** preserving the filtered
candidate queue. The existing Individual Stocks chart can use a different (non-auto-
dividend-adjusted) price basis, so its levels may differ. The audit includes failed
and unavailable cases, and matching results can be exported as CSV.
Results and loaded charts are browser-session snapshots, not disk-persisted research.
Changing the universe does not silently relabel old results. **Refresh data** clears
the shared provider cache; use **Run breakout scan** again to update the snapshot.

The rules are transparent initial research heuristics, not optimized thresholds,
a trading recommendation or a backtested profitability claim. No fundamental/borrow
checks, liquidity guarantee, automatic trade or paid AI call is performed.
Model version: `early-breakout-v1`.

## U-recovery scanner

Choose **U-recovery scanner** under **Research area** to rank incomplete U-shaped
recoveries across current S&P 500 stocks, Russell 2000 stocks, European stocks,
or the ETF atlas.
Stock constituents come from the official IVV, IWM, and IEUR holdings feeds. Stock
candidates can be opened in the full **Individual stocks** research view. The
filtered candidate queue and previous/next controls remain available there.

**Chart shape** has two independent checkboxes:

- **Strict U-shape matches** (on by default): all existing technical rules pass.
- **Near misses** (off by default): one or two strict rules fail, including bounded
  base/trend deviations or a completed intermediate cycle before the final low.
  Strict matches are not duplicated in this group.

Either group can be selected alone. Both combine the groups (OR), after which all
selected fundamental/business filters still apply (AND). Neither selection means
no scan is requested. Both groups use the same 24-hour cached price scan. The
table, selected-chart explanation and chat evidence identify the group and missed
rules. A strict match is not a claim of a literally perfect U, and the 16-point
technical score is not a probability of investment success.

The scanner also keeps a separate **Reference patterns** library. **TWST (Twist
Bioscience)** is retained as a completed/advanced U-recovery example using a dated
September 24, 2026 snapshot: a January 2021 closing peak of $207.97, May 2023 low
of $11.49 and reference close of $184.03, or approximately 87.8% recovery through
the full peak-to-low range. It illustrates the long decline, multi-year base and
powerful right side, but is intentionally not inserted into candidate results:
it had already exceeded the peak selected by the five-year model and is beyond
the scanner's 75% maximum for an incomplete recovery. Reference measurements are
fixed and dated; opening TWST in Individual Stocks loads current market data.

### News sentiment: business impact

Stock candidates have a **News sentiment: business impact** panel below the chart.
It also appears in the **News sentiment** tab in Individual stocks. Enter your
OpenAI API key in the password field under **AI assistant settings** in the sidebar,
then choose **Load news and summarize**. The key stays in server memory for your
browser session and is not written to disk. Do not paste keys into chat or source code.
Alternatively, supply `OPENAI_API_KEY` through the environment before starting
Streamlit. The default model is `gpt-4.1-mini`; `OPENAI_NEWS_MODEL` overrides it.
No additional Python dependency is needed.

Enable **Automatically summarize the selected company** to load a summary as you
navigate stock candidates. This analyzes only the selected company, not the full
universe. News and successful assessments use the existing 24-hour in-memory
cache; restarting the server or clearing caches can incur a new API charge.
Failures are shown explicitly and require an explicit retry.

Yahoo Finance's combined news/press-release feed supplies up to 20 distinct,
source-linked headlines and available excerpts from the past 30 days. The app
sends only the ticker, company name and public news text to OpenAI, not portfolio
data. API usage is billed separately from ChatGPT/Copilot subscriptions.
Requests set `store=false`; OpenAI's retention policies still apply.

The summary evaluates **reported business developments**, not how investors
received them: operating results, contracts, products, financing, competition,
and legal/regulatory outcomes. Labels are Positive, Negative, Mixed, Neutral,
or Insufficient information. Unrelated stories are marked Not relevant.
Reaction-only stories and missing evidence are not treated as Neutral.
The model is instructed to weigh materiality, negation, company roles and repeated
coverage rather than counting headlines. Summaries cite article IDs linked to the
original sources, and each article has an explanation and confidence label.

This is an AI assessment of headlines/excerpts, **not a full-article review or
verified factual conclusion**. Press releases may be promotional, headlines can
omit context, global coverage varies, and no-news results are not positive evidence.
News does not change the technical U-recovery rules or add a sentiment filter.
ETF candidates are excluded because a fund's news is not a company-level assessment.

The **Commodity ETFs** atlas contains 26 exchange-traded products covering
broad commodity baskets, energy, precious and industrial metals, agriculture, and freight.
They automatically participate in the ETF U-recovery scan. Commodity structures
vary: some are ETFs, physical trusts, commodity pools, or exchange-traded notes.
Futures-based products can be materially affected by roll yield and may not track
spot commodity prices over long periods.

**Commodity ETFs → Freight → Tanker freight futures** includes **BWET
(Breakwave Tanker Shipping ETF)**. It holds tanker freight futures, not shipping-company
equities like BOAT or direct crude oil exposure. The chart and research context include
an [issuer-linked explanation](https://amplifyetfs.com/bwet/) of the exposure and
futures/volatility caveats. BOAT remains under **Thematic ETFs → Transportation → Global shipping**.

The European universe uses the official daily holdings CSV for the iShares Core
MSCI Europe ETF (IEUR), which tracks the MSCI Europe IMI Index. Local listing
symbols are mapped to Yahoo Finance suffixes for supported European exchanges.
This is a broad-liquidity proxy, not a guarantee that a security is currently
tradable for a particular IBKR account; permissions and restrictions must still
be checked in IBKR before trading.

At least 500 usable daily closing prices are required for either group.
A strict candidate must have declined at least 15% from a five-year peak, have a
low-zone base spanning at least 120 trading days with at least 50 observations in
the bottom 20% of its peak-to-trough range, and remain at least 10% below the old
peak. Its low must be at least 60 trading days old. It must have recovered 5–75%
of the lost range, formed a recent low no more than 3% below the prior low,
produced a non-negative one-year return, kept its 20-day return at least -10% and
its 60-day return at least -3%, and moved above a rising 50-day average. A
recent early reversal can qualify despite a negative one-year return when its
low is at most 180 trading days old and its
60-day return is at least 8%. It must still satisfy the general base, higher-low,
and rising 50-day-average rules. Mild short-term pullbacks are allowed. A chart
is rejected if it previously recovered
at least 75% of the lost peak-to-trough range and subsequently surrendered at
least 25 percentage points of that recovery. This removes failed late recoveries
and repeated major cycles such as VRDN. A chart is also rejected when it had
already completed an earlier decline of at least 25% and then spent at least 120
trading days recovering into the peak used for the current pattern. This excludes
multi-cycle charts such as OMC. These are technical screens, not proof that a
durable bottom has formed.

An earlier substantial recovery **between the selected peak and the final low**
is classified as a **near miss**, not a strict U-shaped base. The detector follows
the running low from the selected peak: an intermediate drop of at least **25%**
must subsequently recover at least **75%** of that peak-to-intermediate-trough range,
at least **120 trading observations after the intermediate trough**, before the
final low. This identifies multi-cycle paths like SM without a ticker-specific
exception. It counts as **one missed strict rule**, not a score penalty.

Near misses may miss **one or two** strict rules in total. An intermediate cycle
can therefore coexist with at most one bounded base/trend miss. All relaxed
bounds must still hold: low age >=45 trading days, base span >=90, low-zone
observations >=40, 20-day return >=-15%, 60-day return >=-8%, recent low at most
8% below the preceding low, 50-day-average slope >=-2% over 20 sessions, and
price at least 97% of its 50-day average. The non-negative one-year return /
recent-reversal exception, meaningful decline, 5–75% recovery, 10% distance below
peak and both failed-cycle exclusions are **not** relaxed. Missing/invalid or
insufficient history is not classified as a near miss.
These bounded tolerances are explicit research heuristics, not optimized or
backtested predictors. The model version is `u-recovery-v10-intermediate-cycles`;
other numeric thresholds and scoring are unchanged. The pre-selected-peak and
post-final-low failed-cycle exclusions remain hard guards for both groups.
The reference-pattern library is unchanged, and this is not a pixel/template match
or a requirement for a perfectly smooth curve.
Pattern tests use dividend/split-adjusted closing prices; display charts use the
provider's OHLC prices without automatic dividend adjustment. Peak prices and
derived measurements can therefore differ from a visual reading of the chart.

The revenue-growth result view is independent of calendar-year boundaries. At each
reported quarter end, it sums that quarter and the preceding three quarters, then
compares that rolling twelve-month revenue with the equivalent four-quarter window
one year earlier. SEC filing history is merged with Yahoo's latest quarters for US
companies; latest fiscal-year growth is used only when rolling history is
unavailable.

SEC revenue tags are selected by their most recent reported period, not their
number of historical records. Comparative facts are identified by actual start/end
dates rather than the filing's fiscal-year label. Fiscal week-end and Yahoo
calendar-end dates within seven days are treated as the same quarter, with Yahoo's
recent value taking precedence. Rolling growth requires eight consecutive
quarters; missing periods are never treated as adjacent quarters, and an older
rolling growth observation is not substituted for an unavailable latest one.
The Annual revenue chart remains a fiscal-year comparison and can legitimately
have a different sign from the scanner's rolling comparison.
The Individual Stocks **Revenue** screen now shows **Revenue growth used by the
scanner** above its annual and quarterly charts, including the current and prior
four-quarter totals, comparison dates and growth rate. Its rolling revenue chart
plots the latest three quarter-end totals and their year-over-year growth rates:
the same three observations used for the acceleration criterion. Exact period-end
dates and an expandable data table distinguish this from completed fiscal years.
The chart and summary share the scanner's per-symbol 24-hour cache and calculation.
Revenue charts render when their tabs open, rather than initializing inside hidden
nested tabs. Annual and Quarterly views remain available. Fiscal-year fallback
and unavailable data are explicitly labeled, with no fabricated rolling chart.

Cost of revenue preserves the provider's signed values, including negative credits
or reversals. Gross-profit reconciliation uses those reported signs rather than
converting all costs to positive expenses.

The accelerating-growth selector requires the latest rolling growth rate to be
positive and the latest three quarter-end rolling growth rates to increase
consecutively. It does not use sequential-quarter growth or Yahoo's summary growth
field.

Stock scanner criteria are selectable with checkboxes and combine using **AND**:
the U-recovery pattern is required, while positive rolling revenue growth,
accelerating growth, six-month open-market insider purchases, and high short
interest can be added independently, along with provider-reported EV / Revenue
below 10. High short interest means at least 10% of float using the
provider-reported value.

**Positive net buybacks (>0)** is an independent checkbox under **Additional stock
criteria**. It requires actual cash repurchase spending to exceed cash proceeds
from share issuance. It first uses the negative of reported `Net Common Stock
Issuance`; otherwise both signed repurchase outflows and issuance inflows must be
reported. Missing issuance is never assumed to be zero. Announced authorizations,
insider purchases and dividends do not qualify by themselves, and no market-cap
or dividend data is required.

The latest four complete consecutive quarters are used if the period ends within
200 days. Otherwise the latest fiscal year may be used if it ends within 550 days,
explicitly labeled **Fiscal year** rather than TTM. Valid zero/negative net buybacks
fail; incomplete, nonfinite, inconsistent, stale or future-period data is Unknown.
The audit, results table, selected-candidate metrics and chat evidence identify the
amount, reporting currency, period and source. Unknown reporting currency is labeled
**Unreported**, never inferred from the trading currency.

Buyback and shareholder-yield calculations share the same 24-hour raw cash-flow
cache but qualify independently. Shareholder yield includes dividends and requires
compatible market capitalization; missing dividend data can make its comparison
period differ from the standalone buyback period. Cash net buybacks do not prove
that outstanding shares fell: noncash stock compensation and other dilution can
still increase share count. The filter combines with other stock criteria using
**AND**, is absent for ETFs, and does not change technical U-shape rules.

**Limit public float (%)** is an optional stock-only filter. Its adjustable maximum
defaults to **25%** (a screening preference, not a validated volatility threshold).
It includes `floatShares / sharesOutstanding <= maximum / 100`, using Yahoo Finance
company metadata. Both share counts must be finite and strictly positive, and float
cannot exceed shares outstanding. Missing or inconsistent values are **Unknown**,
never zero, and do not pass. No ownership-percentage proxy or clipped ratio is used.
The results table and selected candidate show both float percentage and the absolute
floating-share count; the float audit also shows the denominator and exclusion reasons.
Low float percentage can still mean many tradable shares. Volume, spreads, dilution
and share-class/ADR bases matter; these provider share bases and observation dates
are not independently verified. The chart date is not a float date.

**Positive trailing P/E (>0)** independently requires a finite provider `trailingPE`
strictly above zero, with no upper limit. Zero, negative, missing and invalid values
do not pass; `forwardPE` is not substituted. The ratio is shown in the results table
and selected-candidate metrics. A positive P/E is not proof of sustainable profits
or an inexpensive valuation.

These filters apply to Russell 2000, S&P 500 and European stock universes, not ETFs,
and combine with other selected criteria using **AND**. They share the existing
24-hour company-metadata cache with short-interest and EV / Revenue filters; no
extra screening fetch occurs when they are off. They do not change U-shape scores,
expand the stock universe or forecast volatility.

**Expected positive revenue growth (placeholder)** appears alongside the historical
revenue criteria for all stock universes. It is disabled and unchecked for now:
no forecast data, growth horizon or screening rule has been configured, and it
does not affect candidate inclusion or ranking. It is not offered for ETFs.

For S&P 500 and Russell 2000 stocks, **Require open-market insider buys** limits U-recovery
candidates to companies with at least one Yahoo-reported "Purchase at price"
transaction during the preceding six months. Grants, stock awards, option
exercises, gifts, and sales are excluded. The **Insider buys** tab in Individual
Stocks shows the qualifying transactions, purchased shares, reported value, and
latest purchase date. Provider coverage can be delayed or incomplete.

The Individual Stocks **Catalysts** tab shows a **Why revenue might accelerate**
section only when a recent company-named source describes a concrete event. Strict
rules cover major contracts or awards, positive late-stage clinical/regulatory
milestones, completed acquisitions, opened production capacity, and actual
commercial launches. Planned, expected, preparatory, failed, and unrelated events
are excluded. Every reason includes its dated source and monitoring conditions.

## Focused strategies

### Combined income research

Choose **Income strategies** under **Research area** for one candidate table
combining infrastructure and ADR income. **Income strategy** can show both,
Infrastructure only, or ADRs only. Existing browser sessions on either old page
are redirected to this workspace with their strategy selected.

Each Yahoo listing appears once. Overlapping listings retain **both** assessments
and yields; different share classes and ordinary-share/ADR listings of the same
issuer are intentionally not merged. **Included via** explains why a row appears.
A stock that fails infrastructure rules can still appear through its ADR result,
without being labeled an infrastructure pass.

**Infrastructure forward yield (%)** and **ADR TTM yield (%)** are separate columns
with their own price dates. There is no blended yield, unified qualification score
or implied apples-to-apples ranking. The default is **Company** order with **All**
eligible listings shown. Choose **Infrastructure forward yield** or **ADR TTM yield**
to sort numerically by that method (missing values last), then optionally cap the
display at 25, 50 or 100 rows. Export uses the same filtered, sorted combined table.

Infrastructure region and **Show excluded / unavailable infrastructure** affect
only that strategy. ADR country and **Minimum ADR TTM yield (%)** affect only the
ADR strategy. In the combined view, matching either selected strategy is enough;
an ADR-only filter does not silently remove an otherwise valid infrastructure row.
The assessment audit retains failed, unavailable and unverified-venue records
without substituting zero yields. A provider/catalog failure on one side does
not hide usable results on the other.

The shared candidate selector includes Previous/Next navigation, source details,
bookmarks, stock chat, a toggleable five-year chart and **Open in Individual Stocks**
with the current combined queue. Chart failures do not erase income evidence.
**Refresh data** retains the shared anytime-refresh behavior and 24-hour normal cache.

**ADR dividend yield** uses the same 100 ADR/ADS securities from the September 11,
2026 research screen, persisted in `data/adr_catalog.csv`. It fetches Yahoo Finance daily prices and
cash dividend histories through the existing 24-hour cache, rather than reusing the
original snapshot's yields. To recreate the old top-50 list, select **ADRs**,
sort by **ADR TTM yield**, and set **Maximum income results** to 50.

Trailing yield is the sum of recorded USD cash dividends with ex-dates in
`(price date minus one calendar year, price date]`, divided by that day's Close.
Today's New York calendar day is excluded to avoid incomplete daily bars. Each
row shows its price date, dividend-window start, cash amount, ex-date count and
fetch timestamp. Provider split-adjusted cash amounts and Close are used without
dividend-adjusting the price. This is not a forward annualized yield.

Missing or incomplete histories, missing dividends, non-USD quotes, unsupported
exchanges and quotes older than seven calendar days are reported separately as
unavailable, not silently ranked at 0%. A complete provider history with no
recorded payouts produces 0%. When some data is unavailable, the top-50 ranking is
only among available securities. Provider omissions remain possible.

Use **Refresh data** at the top of the page, or **Refresh all cached data** in the
sidebar, to force a reload anytime. **Retry unavailable ADRs** retries failed
entries without invalidating successful per-security requests. Filtering and
candidate navigation reuse the cached scan. Results can be exported to CSV, and
candidates support bookmarks, an optional five-year chart, and **Open in Individual
Stocks** with the ranked, filtered queue. Display tickers `PBR.A` and `AKO.B` map to
Yahoo symbols `PBR-A` and `AKO-B` for charts, bookmarks and research.

The catalog is fixed and non-exhaustive; current ADR legal status and broker access
are not automatically reverified. PBR and PBR.A represent different share classes
of one company. Dated research notes, company overviews and original source links
are retained separately from live data. Special and irregular dividends are
included, so high yields are not forecasts or evidence of sustainability.
Provider cash figures may reflect foreign withholding and depositary deductions:
they are neither uniformly gross yields nor personal after-tax estimates.

**Infrastructure Income** starts with a source-linked catalog of airports, regulated
water networks, transmission grids, toll roads, pipelines, and communications
infrastructure whose assets have monopoly or oligopoly characteristics. It then
requires provider-reported forward dividend yield above 4%, payout or cash-flow
coverage of at most 80%, and a price at least 5% below its five-year high. The
five-year high is a cycle proxy rather than a literal lifetime high.

**Income view > Infrastructure research coverage** shows every researched company before
financial filtering, without loading market data. **Show excluded / unavailable
infrastructure** exposes the financial rejection reason. Missing provider
metrics are distinguished from failed numeric thresholds. Data-load failures remain
in the scan denominator and are listed separately; scans show completion progress.

The expanded research includes JSE-listed African operators, London-listed Helios
Towers and Airtel Africa, and US-listed VEON with Kazakhstan exposure. London/US
listing location is not the same as operating geography. Diversified infrastructure
operators can include competitive businesses; inclusion is not a pure-play claim.
Research-region labels are not formal MSCI or FTSE market classifications.

Venue access was cross-checked against the official IBKR exchange master:
<https://www.interactivebrokers.com/webrest/exchanges/>. Its stock-venue inventory
covered 41 jurisdictions at review, but this is **not** a completed issuer-by-issuer
review of every listed security in all 41 jurisdictions. The catalog remains
source-researched, not a guaranteed exhaustive or automatically synchronized IBKR
contract universe. Exact account/entity, residency, stock/ADR permissions and
liquidity must be checked before trading.

Warsaw and Bucharest are present in that stock-venue inventory and remain in the
screen. Cash-equity venues for Chile, Greece, Turkey, Qatar and Thailand were not
found; their existing candidates remain visible in Research coverage but are not
financially screened. Indian cash equities are explicitly marked restricted: the
presence of NSE does not grant general foreign-retail access.

The coverage view also records African/frontier research gaps, including KazTransOil,
KEGOC, Kazakhtelecom, Safaricom, Kenya Power, Sonatel and other local-market candidates.
Many local African exchanges and Kazakhstan's venues were absent from the published
IBKR stock list; no suitable accessible foreign line was verified. That is an access
or data limitation, **not** evidence that the company failed the income filters.
Quoted symbols, access and corporate actions can change after the review date.

**Fashion Shorts** is a short-only research screen that intentionally ignores
reported revenue. Its selectable catalog includes AEO, AKA, ANF, BKE, BOOT, BRIA,
BURL, CAL, CATO, CRI, CTRN, CURV, DBGI, DLTH, DXLG, GAP, GCO, JEM, JILL, LE,
LULU, LVLU, MYSZ, REF, RENT, ROST, SFIX, SHOE, TJX, TLYS, URBN, VSXY and ZUMZ,
alongside the existing US and European companies. These additions use the US-listed
selection group; this is not a claim about company domicile. Catalog membership
does not verify current listing status, market-data coverage or shortability.
Tracked company/brand terms are attention proxies, particularly for multi-brand
holdings, rather than a complete measure of demand across every owned brand.
The footwear/accessories catalog also includes BIRK, CROX, DBI, DECK, FMFC,
FOSL, NKE, ONON, RCKY, SHOO, VRA, WEYS and WWW without duplicating existing entries.
Google Trends needs no API key. Uncached requests are serialized across sessions
in the app process and spaced at least ten seconds apart, including cookie,
payload and time-series requests. HTTP 429 responses receive at most two retries
with 30/60-second backoff. Server `Retry-After` instructions are respected;
delays over 60 seconds trigger a cooldown instead of blocking the scan indefinitely.
Persistent rate limiting pauses further requests for at least five minutes.
Cached navigation adds no requests; a fresh comparison can take several minutes.
Pacing reduces request pressure but cannot guarantee that Google will allow access.
After a cooldown, use **Refresh data** to retry cached unavailable results.
Victoria's Secret uses VSXY instead of VSCO following its
[June 2, 2026 ticker change](https://finance.yahoo.com/markets/stocks/articles/victoria-secret-co-change-ticker-123000438.html).
Shoe Station Group uses SHOE following its
[June 12, 2026 name and ticker change](https://investors.shoecarnival.com/news/news-details/2026/Shoe-Carnival-Inc--Announces-Name-Change-to-Shoe-Station-Group-and-Ticker-Symbol-Change-to-SHOE/default.aspx).
Reformation (REF) is a recent IPO; insufficient daily price history will prevent
it from passing the 200-session technical filter until enough history is available.

For up to five selected brands it compares the latest four weeks
with the preceding four weeks in Google Trends, and the latest 30-day mention rate
with the preceding 60-day monthly rate for Reddit and Google News. A company enters
the short-research queue only when at least two available sources independently
decline beyond the displayed thresholds. Google requires prior-period interest of
at least 10 and a decline of at least 20%. Reddit and Google News require a prior
monthly pace of at least three mentions and a decline of at least 25%. These
minimums prevent tiny baselines from becoming short signals. A qualifying company
must also be in a chart downtrend: its latest daily close must be below its 200-day
moving average and its 50-day moving average must be below its 200-day moving
average. Missing or insufficient price history fails the screen visibly rather than
being treated as a downtrend. Reddit uses its official API and requires
`REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` environment variables; the app reports
Reddit as unavailable when they are not configured. Attention decline and a chart
downtrend do not establish weak sales, overvaluation, borrow availability, or a
profitable short. Short selling can produce unlimited losses and may involve borrow
fees, recalls, and squeezes. Every scanned company that passes both chart-downtrend
rules can be browsed with wraparound previous/next controls, even when it does not
pass the separate attention screen. Stocks that fail either chart rule are excluded
from the browser and Individual Stocks handoff queue. Full short-screen qualification
remains visible in the results table.

**Star Principle** follows Richard Koch's strict definition. A company is included
only when linked evidence supports both leadership in a defined niche and growth
of at least 10% annually in that same niche. Missing or ambiguous evidence is not
replaced with financial proxies.

**Volatility Strategy** runs a small, price-only semiconductor-equipment pilot:

- Ten US-listed stocks: AMAT, LRCX, ASML, ACLS (wafer fabrication);
  KLAC, ONTO, NVMI (process control); TER, COHU, FORM (test and interfaces).
  These are curated economic buckets, not interchangeable companies or the entire sector.
- Two years of Yahoo dividend/split-adjusted daily prices. SOXX is a broad
  semiconductor benchmark, not an equipment-only fund or a stock candidate.
  Today's New York session is excluded; missing prices are never forward-filled.
- Acceleration is the change in daily stock-minus-SOXX log returns. Its z-score
  uses only the preceding 60 sessions. A stock is unusual if any absolute z-score
  reaches 2 during the latest five completed sessions.
- **Price information (5d)** labels each stock Positive (up), Negative (down), or
  Neutral (flat), based on the sign of its actual adjusted five-session return,
  not acceleration or performance relative to SOXX. Unavailable analysis data
  remains Unavailable. Pocket tables and historical breadth split unusual stocks
  into up/down/flat counts; stock CSV exports include the label. These are price
  direction labels, not verified news sentiment or information-theory measures.
  Screening, leader direction versus SOXX, and rankings are unchanged.
- A pocket is active with at least 80% coverage, two unusual stocks, 30% unusual
  breadth and an 80th-percentile historical breadth reading. The percentile uses
  midranks against up to 252 earlier windows, excluding windows overlapping the
  current five sessions, with at least 60 historical observations.
- Directional leaders must also move at least one pre-window normal five-session
  relative-return scale; two leaders and two-thirds directional agreement are required.
  A research lead must be in that active sub-pocket, have no unusual acceleration,
  remain within one normal move scale, and have moved less than half as far as the
  leaders' median in their direction. Gaps rank research attention, not expected profit.
- Pocket and stock tables, an acceleration heatmap, relative-response paths,
  historical breadth, source links and an Individual Stocks handoff show the evidence.
  No matching pocket or quiet peer is a valid result; thresholds are not relaxed to
  manufacture a shortlist.

Use **Run / refresh sector analysis** to download and save a snapshot in
`data/volatility-pilot.sqlite3`. The saved results reopen without network requests
and survive app restarts. A refresh needs at least 80% usable stock coverage before
replacing the snapshot. Errors are visible and failed refreshes retain the previous
snapshot. Retrieval and price dates, stale-data warnings and unavailable stocks are
shown. This explicit snapshot is separate from Streamlit's 24-hour cache:
**Refresh all cached data** does not update it. No AI calls are made by the pilot.

This is a descriptive research screen, not evidence of inefficient pricing, a
valuation model, verified common-news analysis or a backtested trading edge.
Unit benchmark exposure is not beta-neutral; equipment businesses have different
end-market mixes. Current membership, adjusted-data revisions, noisy differentiation,
benchmark overlap, correlated stocks and repeated testing limit interpretation.
No automatic buys, sells, target returns, position sizes or trading-cost assumptions
are supplied.

The Star Principle screen includes a selected-company five-year price/volume
chart with the 200-day moving average, company metrics, previous/next navigation,
bookmarks, news summaries, and an **Open in Individual Stocks** handoff preserving
the filtered Star candidate queue. These controls are available for near misses
and unreviewed stocks too; chart shape does not determine Star qualification.

**Reviewed shortlist** contains the source-researched records. **US and European
stock universe** loads the listing-level union of the existing S&P 500, Russell
2000 and IEUR stock universes, deduplicating identical ticker symbols. It is not
all stocks available through IBKR and does not confirm account-specific trading
permissions. A stock without a research record is **Unreviewed**, not rejected.
Loading the universe only loads coverage; it does not perform or imply thousands
of company evaluations. Region and evidence-status filters control the queue.

The expansion uses manually researched shortlists, not automatic paid AI batches.
Each assessment includes its sources, scope, evidence date and limitations.
The September 6, 2026 batch adds ASM International, Besi, Dassault Systemes,
Halma, Arista, Cadence, Synopsys, FICO, Verisk and Fortinet to the nine earlier
near-miss reviews. None was promoted without both strict criteria being verified.
Inconsistent forecast figures and vendor-list ordering are not accepted as proof.
Forecast market CAGR must be identified as a forecast rather than realized annual
growth. An evidence-qualified star is not a recommendation or a valuation judgment.

## IP-backed turnarounds

Choose **IP-backed turnarounds** under **Research area** for the researched
product-company strategy: valuable technology and product capabilities surviving
a business setback, with a credible route to recovery. The Sonos-like archetype
is not restricted to consumer hardware or existing royalty collectors. Confirmed
revenue/profit recovery and an exact U-shape are not prerequisites.

The curated **2026-09-25** research snapshot contains:

- **SSYS, GN.CO and OLED:** core research candidates, not low-risk endorsements;
- **KLIC:** a more-confirmed recovery comparison;
- **PACB:** a separate high-risk watchlist case.

Filter by research category and sector, select a company, and review its technology,
catalysts, financial evidence, risks, next verification steps and dated primary
sources. Pending transactions are described as of the research date: notably, GN's
Hearing business/IP leave with its proposed disposal, and Stratasys's proposed
Markforged acquisition consumes cash and adds integration risk.

The evaluation checklist covers commercial usefulness, repairability, funding
runway/dilution, catalysts, valuation and entry/invalidation conditions. It is a set
of reference prompts, not saved checkmarks or a scored review; the existing **Trade
checklist** remains the place for saved personal checklist notes.

**Open in Individual Stocks** carries the selected ticker and filtered shortlist
into the existing research queue for current charts, financials and short interest.
The existing bookmark action is also available. This curated page makes no
market-data or AI requests; external source links open only when clicked.

This is not automated discovery, patent appraisal, a buy list, or a change to the
U-recovery scanner. It does not infer patent value from counts or assign a guaranteed
asset-value floor. **Refresh data** clears market-data caches, but does not re-research
the shortlist, update its evidence date or turn dated financial figures into live data.

## Short-interest limitations

Short-interest publication is not standardized worldwide. Some exchanges do not
publish security-level short positions, use different reporting thresholds, or
report with a delay. The dashboard displays values only when Yahoo Finance returns
them and clearly identifies securities with no available data. Treat all figures as
research data rather than real-time trading data.

## Tests

```powershell
python -m unittest discover -s tests -v
```

## Data caching

All external market, company, statement, holdings, scanner, catalyst, and insider
data is cached for 24 hours. The app does not refresh data in the background: a
missing or expired entry is fetched only when the user opens a view that needs it.
Each distinct ticker, period, interval, universe, or filter-data request has its own
cache entry. Streamlit reruns the interface when controls change, but those reruns
reuse matching cache entries rather than fetching them again.

The **U-recovery scanner** keeps automatic checkbox updates, but loads optional
revenue, buyback, insider, company-metric and business-recovery data using at most
**four concurrent candidate workers**, rather than a serial download loop. Each
stage displays processed/total progress and an elapsed-time/cache summary. Counts
refer to cache entries, including nested raw-data and calculated-assessment entries,
not a count of HTTP requests or unique companies. Completed results retain the
original candidate order, filter thresholds and AND semantics.

Raw income, cash-flow and balance statements are shared between revenue, buybacks,
shareholder yield, share counts and financial-recovery assessments. Share counts
continue to use balance-sheet data. SEC quarterly revenue has its own shared cache.
Checkboxes reuse complete per-symbol assessments; changing an earlier filter only
loads data for newly exposed candidates. The technical scan's universe key uses
sorted unique tickers, so a holdings-order change alone does not trigger a new scan.

Scanner market-data errors are cached as **unavailable**, not as successful empty
results or zero values. Ordinary reruns do not repeatedly retry a failed request;
**Refresh data** explicitly clears both successes and failures for a retry.
Failures otherwise expire with the same 24-hour cache lifetime. Manual management
reviews are still read from their local store, not frozen in the market-data cache.
These caches remain in memory, not on disk: restarting the server clears them.
An initial/expired scan, a previously unused filter or a newly selected company's
chart can still require downloads. Provider latency/rate limits and optional news
summaries are not eliminated by caching; the progress display distinguishes filter
loading from later company research. No background preload or paid AI batch is run.

**Refresh data** is visible next to the heading on Individual stocks, ETF market
atlas, Other charts, U-recovery scanner, Early breakout strategy, Bookmarks, Income strategies, IP-backed turnarounds, Fashion shorts and
Star principle. It works even when results are empty or
provider data is unavailable. **Refresh all cached data** remains under
**Data & cache** in the sidebar. Both actions bypass the cache **anytime**; the
normal automatic expiry remains 24 hours.

These controls clear the app's shared data caches (including per-symbol and
aggregate scan entries), not just the selected ticker. The active page fetches
the data it needs immediately; other pages fetch on their next use. Connected
browser sessions share these caches. Large scans can take several minutes and
repeated refreshes may encounter provider rate limits. A refresh requests new data;
it cannot make the provider publish a newer observation. The UI reports the
manual request time separately from source/price/evidence dates.

Refresh does **not** redo source-based Star leadership/niche-growth research,
change assessment statuses or dates, add researched companies, or update the
fixed strategy catalogs. Nor does it erase bookmarks, saved management reviews,
filters, API keys or chat history. Placeholders have no live data to refresh;
the manual management editor already provides **Reload saved evidence**.

To avoid unexpected API charges, a manual refresh pauses automatic news summaries
in the initiating browser session and clears its loaded-summary selections.
Use **Load news and summarize** to request a new analysis, or explicitly re-enable
automatic summaries. Other connected browser sessions keep their own news settings.
