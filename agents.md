# Project guide for agents and contributors

## Project description

Global Stock Research is a local Python and Streamlit dashboard for researching
stocks and ETFs worldwide. It combines company search, price and volume charts,
financial statements, valuation and ownership metrics, ETF catalogs, market
breadth, and strategy-specific scanners. Optional OpenAI-powered features provide
stock chat, news summaries, and assessments of user-supplied revenue evidence.
It is a research tool, not investment advice or an automated trading system.

See [README.md](README.md) for detailed features, data limitations, strategy rules,
and privacy behavior. Several strategies are explicitly placeholders; do not
describe them as implemented scanners.

## Requirements

- Python 3.10 or newer.
- Dependencies from [requirements.txt](requirements.txt), including Streamlit 1.60
  or newer, yfinance, Plotly, pandas, and pytrends.
- Internet access for market data and optional AI requests.

## Install and run on Windows

Open PowerShell in the project directory:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open `http://localhost:8501` if the browser does not open automatically.
Stop the server with Ctrl+C. Using the virtual environment's interpreter directly
avoids PowerShell activation-policy issues.

Market-data research does not require an OpenAI key. For optional AI features,
enter a key in the app's **AI assistant settings**, or set `OPENAI_API_KEY` in the
environment before starting Streamlit. Never put a real key in source files or
documentation. Optional model overrides are `OPENAI_CHAT_MODEL`,
`OPENAI_NEWS_MODEL`, and `OPENAI_REVENUE_MODEL`; their defaults are `gpt-4.1-mini`.
AI requests may incur provider charges. Preserve the existing consent controls
and data-sharing boundaries documented in the README.

## Project structure

- [app.py](app.py): Streamlit entry point and top-level page orchestration.
- [stock_data.py](stock_data.py): market-data access, normalization, financial
  metrics, and shared research calculations.
- [scanner_loading.py](scanner_loading.py): shared caching and scanner loading.
- Files ending in `_ui.py`: focused Streamlit interfaces for their associated
  research or strategy modules.
- [stock_chat.py](stock_chat.py), [news_sentiment.py](news_sentiment.py),
  [revenue_outlook.py](revenue_outlook.py), and
  [openai_transport.py](openai_transport.py): optional AI features and transport.
- [data/](data/): versioned CSV reference catalogs and ignored local SQLite
  databases for bookmarks, management evidence, checklists, and saved pilot data.
- [tests/](tests/): unittest-based calculation, data-access, and UI tests.

## Run tests

From the project directory, after installing dependencies:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

For a focused test file:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_stock_data.py -v
```

## Contribution guidelines

- Reuse existing data helpers, cache controls, and UI patterns. Keep calculations
  testable independently of Streamlit rendering.
- Preserve explicit unavailable-data states, source dates, and provider
  limitations; do not replace missing evidence with invented values.
- Do not add automatic paid AI calls, background scans, or trading actions.
- Add or update relevant tests for behavior changes and update the README when
  features or run instructions change.
- Never commit API keys, environment files, Streamlit secrets, local databases,
  virtual environments, or generated caches. Keep CSV reference catalogs tracked.
