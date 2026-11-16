from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
from datetime import datetime, timezone
import math
import os
from typing import TypeVar

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from workspace_ui import apply_workspace_style, render_workspace_brand

from adr_dividend import ADR_RESEARCH_AS_OF, adr_catalog, get_adr_dividend
from etf_catalog import ETF_ENTRY_REPLACEMENTS, ETF_RESEARCH_NOTES, etf_catalog, filter_etfs
from bookmarks import BookmarkError, add_bookmark, list_bookmarks, remove_bookmark
from breakout_strategy import (
    BREAKOUT_MODEL_VERSION,
    BREAKOUT_UNIVERSES,
    analyze_early_breakout,
    completed_breakout_date,
    get_breakout_history,
)
from market_breadth import BREADTH_MODEL_VERSION, BreadthSnapshot, get_market_breadth
from scanner_loading import (
    BatchResult,
    CacheActivity,
    LoadProgress,
    cache_market_data,
    load_symbol_batch,
    track_cache_activity,
)
from infrastructure_research import (
    IBKR_EXCHANGE_SOURCE,
    INFRASTRUCTURE_RESEARCH_GAPS,
    RESEARCH_AS_OF,
    infrastructure_listing_details,
)
from news_sentiment import (
    DEFAULT_NEWS_MODEL,
    NEWS_ANALYSIS_VERSION,
    analyze_company_news,
    get_company_news,
)
from recovery_market import (
    assess_sector_strength,
    assess_small_cap,
    get_recovery_prices,
    quote_currency,
    sector_benchmark,
)
from strategy_catalog import (
    FASHION_COMPANIES,
    INFRASTRUCTURE_COMPANIES,
    build_star_research_universe,
    star_principle_catalog,
)
from stock_data import (
    StockDataError,
    U_RECOVERY_MODEL_VERSION,
    U_SHAPE_NEAR_MISS,
    U_SHAPE_STRICT,
    analyze_fashion_downtrend,
    analyze_infrastructure_income,
    compact_number,
    company_screening_metrics,
    format_value,
    generate_revenue_acceleration_reasons,
    generate_stock_catalysts,
    generate_stock_drivers,
    get_business_context,
    get_cashflow_history,
    get_company_info,
    get_company_developments,
    get_etf_holdings,
    get_european_holdings,
    get_financial_history,
    get_google_trends_signal,
    get_etf_inflection_scan,
    get_inflection_scan,
    get_price_history,
    get_news_volume_signal,
    get_net_buybacks,
    get_reddit_mention_signal,
    get_recent_insider_buys,
    get_revenue_growth_scan,
    get_russell_2000_holdings,
    get_share_count_history,
    get_shareholder_yield,
    get_sec_quarterly_revenue,
    get_statement_history,
    get_sp500_holdings,
    get_stock_catalyst_data,
    key_metric_sections,
    search_stocks,
    short_interest_rows,
    summarize_insider_buys,
    summarize_fashion_signals,
    summarize_price_history,
    x_discussion_links,
)


PERIODS = {
    "1 month": "1mo",
    "3 months": "3mo",
    "6 months": "6mo",
    "Year to date": "ytd",
    "1 year": "1y",
    "5 years": "5y",
    "Maximum": "max",
}
CACHE_TTL_SECONDS = 24 * 60 * 60
REVENUE_MODEL_VERSION = "rolling-four-quarter-v6-chart"
RECOVERY_MODEL_VERSION = "business-recovery-v1"
U_SHAPE_REFERENCE_PATTERNS = (
    {
        "Symbol": "TWST",
        "Company": "Twist Bioscience",
        "Stage": "Completed / advanced recovery",
        "AsOf": "2026-09-24",
        "PriorPeak": 207.97,
        "PriorPeakDate": "2021-01-20",
        "Low": 11.49,
        "LowDate": "2023-05-02",
        "ReferenceClose": 184.03,
        "RecoveryProgress": 0.8782,
        "Reason": (
            "Long decline, multi-year base and powerful right side. It is a reference "
            "for the completed/advanced form, not an incomplete-recovery candidate."
        ),
    },
)
RECOVERY_CRITERIA = {
    "small_cap": ("Market cap under $2B (USD)", "SmallCapStatus", "SmallCapReason", "Pass"),
    "profitability": ("Improving profitability and cash generation", "ProfitabilityStatus", "ProfitabilityReason", "Pass"),
    "sector": ("Stronger than its sector (3 and 6 months)", "SectorStrengthStatus", "SectorStrengthReason", "Pass"),
    "deleveraging": ("Deleveraging turnaround", "DeleveragingStatus", "DeleveragingReason", "Pass"),
    "shareholder_yield": ("Positive shareholder yield (>0%)", "ShareholderYieldStatus", "ShareholderYieldReason", "Pass"),
    "management": ("Management & Incentives: favorable reviewed evidence", "ManagementStatus", "ManagementReason", "Favorable"),
}


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_recovery_prices(symbol: str) -> pd.DataFrame:
    return get_recovery_prices(symbol)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_financial_recovery(symbol: str, model_version: str) -> dict:
    from recovery_financials import get_financial_recovery

    if model_version != RECOVERY_MODEL_VERSION:
        raise ValueError("Unsupported business-recovery model version.")
    try:
        return get_financial_recovery(
            symbol, info=cached_info(symbol), statement_loader=cached_statement_history,
        )
    except StockDataError as exc:
        return {"ProfitabilityStatus": "Unknown", "ProfitabilityReason": str(exc),
                "DeleveragingStatus": "Unknown", "DeleveragingReason": str(exc)}


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_market_recovery(symbol: str, criterion: str, model_version: str) -> dict:
    if model_version != RECOVERY_MODEL_VERSION or criterion not in ("small_cap", "sector"):
        raise ValueError("Unsupported market-recovery assessment.")
    _, status, reason, _ = RECOVERY_CRITERIA[criterion]
    try:
        info = cached_info(symbol)
        if info.get("quoteType") and info["quoteType"] != "EQUITY":
            return {status: "Not applicable", reason: "This company-equity filter is not applicable to funds."}
        currency, _ = quote_currency(info.get("currency"))
        fx = cached_recovery_prices(f"{currency}USD=X") if currency != "USD" else None
        if criterion == "small_cap":
            return assess_small_cap(symbol, info, fx)
        _, benchmark, _ = sector_benchmark(info)
        return assess_sector_strength(
            symbol, info, cached_recovery_prices(symbol), cached_recovery_prices(benchmark), fx,
        )
    except StockDataError as exc:
        return {status: "Unknown", reason: str(exc)}


def load_recovery_signals(symbol: str, criteria: tuple[str, ...]) -> dict:
    result = {}
    financial_loaded = False
    for criterion in criteria:
        if criterion not in RECOVERY_CRITERIA:
            raise ValueError(f"Unknown recovery criterion: {criterion}")
        if criterion == "management":
            from management_evidence import ManagementEvidenceError, get_management_evidence

            try:
                result.update(get_management_evidence(symbol))
            except ManagementEvidenceError as exc:
                result.update({"ManagementStatus": "Unknown", "ManagementReason": str(exc)})
        elif criterion == "shareholder_yield":
            result.update(cached_shareholder_recovery(symbol, RECOVERY_MODEL_VERSION))
        elif criterion in ("profitability", "deleveraging"):
            if not financial_loaded:
                result.update(cached_financial_recovery(symbol, RECOVERY_MODEL_VERSION))
                financial_loaded = True
        else:
            result.update(cached_market_recovery(symbol, criterion, RECOVERY_MODEL_VERSION))
    return result


def render_recovery_research(symbol: str, company_name: str, evidence: dict | None = None) -> None:
    from management_evidence_ui import render_management_evidence
    from recovery_ui import render_recovery_evidence

    with st.expander("Business recovery & management", expanded=False):
        signals_tab, management_tab = st.tabs(["Recovery evidence", "Management & Incentives"])
        with signals_tab:
            st.caption(
                "Optional research screens, not proven predictors of returns. "
                "Load this stock's evidence on demand; external data is cached for 24 hours."
            )
            key = f"recovery_loaded_{symbol}"
            if st.button("Load recovery evidence", key=f"load_recovery_{symbol}"):
                st.session_state[key] = True
            public = dict(evidence or {})
            if st.session_state.get(key):
                with st.spinner("Loading size, sector and financial comparisons..."):
                    public.update(load_recovery_signals(
                        symbol, ("small_cap", "sector", "profitability", "deleveraging", "shareholder_yield"),
                    ))
            render_recovery_evidence(public)
        with management_tab:
            render_management_evidence(symbol, company_name)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_search(query: str) -> list[dict[str, str]]:
    return search_stocks(query)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
    return get_price_history(symbol, period, interval)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_info(symbol: str) -> dict:
    return get_company_info(symbol)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_adr_dividend(symbol: str, as_of: str) -> dict:
    return get_adr_dividend(symbol, as_of)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_adr_scan(symbols: tuple[str, ...], as_of: str) -> tuple[list[dict], list[dict]]:
    if not symbols:
        raise ValueError("An ADR universe is required.")
    rows_by_symbol = {}
    errors_by_symbol = {}
    with ThreadPoolExecutor(max_workers=min(4, len(symbols))) as executor:
        futures = {
            executor.submit(cached_adr_dividend, symbol, as_of): symbol
            for symbol in symbols
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                rows_by_symbol[symbol] = {"Symbol": symbol, **future.result()}
            except StockDataError as exc:
                errors_by_symbol[symbol] = {"Symbol": symbol, "Error": str(exc)}
    return (
        [rows_by_symbol[symbol] for symbol in symbols if symbol in rows_by_symbol],
        [errors_by_symbol[symbol] for symbol in symbols if symbol in errors_by_symbol],
    )


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_etf_holdings(symbol: str) -> pd.DataFrame:
    return get_etf_holdings(symbol)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_business_context(
    industry_key: str | None,
    sector: str | None,
    country: str | None,
) -> dict:
    return get_business_context(industry_key, sector, country)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_inflection_scan(
    symbols: tuple[str, ...],
    model_version: str,
) -> pd.DataFrame:
    if model_version != U_RECOVERY_MODEL_VERSION:
        raise ValueError("Unsupported U-recovery scanner model version.")
    return get_etf_inflection_scan(list(symbols), include_near_misses=True)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_russell_holdings() -> pd.DataFrame:
    return get_russell_2000_holdings()


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_sp500_holdings() -> pd.DataFrame:
    return get_sp500_holdings()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_market_breadth(symbols: tuple[str, ...], model_version: str) -> BreadthSnapshot:
    if model_version != BREADTH_MODEL_VERSION:
        raise ValueError("Unsupported market-breadth model version.")
    return get_market_breadth(symbols)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_european_holdings() -> pd.DataFrame:
    return get_european_holdings()


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_stock_inflection_scan(
    symbols: tuple[str, ...],
    model_version: str,
) -> pd.DataFrame:
    if model_version != U_RECOVERY_MODEL_VERSION:
        raise ValueError("Unsupported U-recovery scanner model version.")
    return get_inflection_scan(list(symbols), include_near_misses=True)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_stock_revenue_growth(symbol: str, model_version: str) -> dict:
    if model_version != REVENUE_MODEL_VERSION:
        raise ValueError("Unsupported revenue model version.")
    return get_revenue_growth_scan(
        [symbol], sec_loader=cached_sec_quarterly_revenue,
        financial_loader=cached_financial_history,
    ).iloc[0].to_dict()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_revenue_growth_scan(
    symbols: tuple[str, ...],
    model_version: str,
) -> pd.DataFrame:
    if model_version != REVENUE_MODEL_VERSION:
        raise ValueError("Unsupported revenue model version.")
    batch = load_symbol_batch(
        sorted(set(symbols)), lambda symbol: cached_stock_revenue_growth(symbol, model_version),
    )
    if batch.errors:
        raise StockDataError("Revenue data unavailable for " + ", ".join(batch.errors) + ". Use Refresh data to retry.")
    return pd.DataFrame(list(batch.values.values()))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_catalyst_data(symbol: str) -> dict:
    return get_stock_catalyst_data(symbol)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_company_developments(symbol: str) -> pd.DataFrame:
    return get_company_developments(symbol)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_insider_buys(symbol: str) -> pd.DataFrame:
    return get_recent_insider_buys(symbol, months=6)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_statement_history(symbol: str, statement: str, frequency: str) -> pd.DataFrame:
    return get_statement_history(symbol, statement, frequency)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_sec_quarterly_revenue(symbol: str) -> pd.DataFrame:
    return get_sec_quarterly_revenue(symbol)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_financial_history(symbol: str, frequency: str) -> pd.DataFrame:
    return get_financial_history(symbol, frequency, statement_loader=cached_statement_history)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_share_count_history(symbol: str, frequency: str) -> pd.DataFrame:
    return get_share_count_history(symbol, frequency, statement_loader=cached_statement_history)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_cashflow_history(symbol: str, frequency: str) -> pd.DataFrame:
    return get_cashflow_history(symbol, frequency, statement_loader=cached_statement_history)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_shareholder_yield(
    symbol: str,
    market_cap: float | int | None,
    model_version: str = "shareholder-yield-v3",
) -> dict | None:
    if model_version != "shareholder-yield-v3":
        raise ValueError("Unsupported shareholder-yield model version.")
    return get_shareholder_yield(symbol, market_cap, cashflow_loader=cached_cashflow_history)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_net_buyback_assessment(symbol: str) -> dict:
    result = {
        "BuybackStatus": "Unknown", "BuybackCurrency": "Unreported",
        "NetBuybacks": None, "BuybackPeriod": None, "BuybackPeriodBasis": None,
        "BuybackPeriodEnd": None,
        "BuybackSourceURL": f"https://finance.yahoo.com/quote/{symbol}/cash-flow/",
        "BuybackMethod": "Repurchase spending minus cash proceeds from share issuance; dividends excluded.",
    }
    try:
        info = cached_info(symbol)
    except StockDataError:
        info = {}
    if info.get("quoteType") and info["quoteType"] != "EQUITY":
        return {**result, "BuybackStatus": "Not applicable",
                "BuybackReason": "Company share repurchases are not a fund-distribution measure."}
    currency = info.get("financialCurrency")
    if isinstance(currency, str) and currency.strip():
        result["BuybackCurrency"] = currency.strip().upper()
    try:
        data = get_net_buybacks(symbol, cashflow_loader=cached_cashflow_history)
        if data is None:
            raise StockDataError(
                "No complete, current cash-flow period with net share issuance. "
                "TTM needs four consecutive quarters ending within 200 days; "
                "the fiscal-year fallback must end within 550 days. Missing issuance is not zero."
            )
        value = data["NetBuybacks"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise StockDataError("A finite net-buyback value is unavailable.")
        result.update({
            "NetBuybacks": value, "BuybackPeriod": data["Period"],
            "BuybackPeriodBasis": data["PeriodBasis"], "BuybackPeriodEnd": data["PeriodEnd"],
            "BuybackMethod": data["NetBuybackMethod"],
            "BuybackStatus": "Pass" if value > 0 else "Fail",
            "BuybackReason": (
                f"{value:,.2f} in {data['Period']}; requires net buybacks strictly above 0. "
                + ("Reporting currency unavailable; the sign comparison needs no FX conversion."
                   if result["BuybackCurrency"] == "Unreported" else f"Reporting currency: {result['BuybackCurrency']}.")
            ),
        })
    except StockDataError as exc:
        result["BuybackReason"] = str(exc)
    return result


def shareholder_yield_inputs(info: dict) -> tuple[float, str]:
    currency, _ = quote_currency(info.get("currency"))
    financial_currency = str(info.get("financialCurrency") or "").strip().upper()
    if not financial_currency or financial_currency != currency:
        raise StockDataError(
            f"Shareholder yield needs comparable currencies: cash flows are in "
            f"{financial_currency or 'an unknown currency'}, market cap is in {currency}. "
            "Cross-currency conversion is not available for this metric."
        )
    market_cap = pd.to_numeric(info.get("marketCap"), errors="coerce")
    if isinstance(info.get("marketCap"), bool) or pd.isna(market_cap) or not math.isfinite(market_cap) or market_cap <= 0:
        raise StockDataError("Shareholder yield requires a finite, positive market capitalization.")
    return float(market_cap), currency


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_shareholder_recovery(symbol: str, model_version: str) -> dict:
    if model_version != RECOVERY_MODEL_VERSION:
        raise ValueError("Unsupported shareholder-recovery model version.")
    result = {
        "ShareholderYieldStatus": "Unknown",
        "ShareholderYieldSourceURL": f"https://finance.yahoo.com/quote/{symbol}/cash-flow/",
        "ShareholderYieldMethod": "(Cash dividends + net buybacks) / current market cap; issuance reduces net buybacks. Debt repayment is not included.",
    }
    try:
        info = cached_info(symbol)
        if info.get("quoteType") and info["quoteType"] != "EQUITY":
            return {**result, "ShareholderYieldStatus": "Not applicable",
                    "ShareholderYieldReason": "Company shareholder yield is not a fund-distribution yield."}
        market_cap, currency = shareholder_yield_inputs(info)
        data = cached_shareholder_yield(symbol, market_cap)
        if data is None:
            raise StockDataError(
                "No complete, current cash-flow period with dividends and net share issuance. "
                "TTM needs four consecutive quarters ending within 200 days; "
                "the fiscal-year fallback must end within 550 days."
            )
        value = pd.to_numeric(data.get("ShareholderYield"), errors="coerce")
        if isinstance(data.get("ShareholderYield"), bool) or pd.isna(value) or not math.isfinite(value):
            raise StockDataError("A finite shareholder-yield value is unavailable.")
        result.update({
            "ShareholderYield": float(value), "ShareholderYieldPeriod": data["Period"],
            "ShareholderYieldBasis": data["PeriodBasis"], "ShareholderYieldPeriodEnd": data["PeriodEnd"],
            "ShareholderYieldDividends": data["Dividends"], "ShareholderYieldNetBuybacks": data["NetBuybacks"],
            "ShareholderYieldTotalReturned": data["TotalReturned"],
            "ShareholderYieldMarketCap": market_cap, "ShareholderYieldCurrency": currency,
            "ShareholderYieldStatus": "Pass" if value > 0 else "Fail",
            "ShareholderYieldReason": f"{value:.2%} for {data['Period']}; requires strictly above 0%.",
        })
    except StockDataError as exc:
        result["ShareholderYieldReason"] = str(exc)
    return result


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_google_trends_signal(search_term: str) -> dict:
    try:
        return get_google_trends_signal(search_term)
    except StockDataError as exc:
        return {"Available": False, "Reason": str(exc)}


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_news_volume_signal(search_term: str) -> dict:
    try:
        return get_news_volume_signal(search_term)
    except StockDataError as exc:
        return {"Available": False, "Reason": str(exc)}


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_reddit_mention_signal(search_term: str) -> dict:
    try:
        return get_reddit_mention_signal(search_term)
    except StockDataError as exc:
        return {"Available": False, "Reason": str(exc)}


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_company_news(symbol: str) -> dict:
    return get_company_news(symbol)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_news_assessment(
    symbol: str, company_name: str, news: dict, model: str,
    version: str, _api_key: str,
) -> dict:
    if version != NEWS_ANALYSIS_VERSION:
        raise ValueError("Unsupported news analysis version.")
    return {
        "analysis": analyze_company_news(
            symbol, company_name, news["articles"], _api_key, model,
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def openai_key() -> str:
    return (
        st.session_state.get("openai_session_key", "")
        or os.environ.get("OPENAI_API_KEY", "")
    ).strip()


def remember_openai_key() -> None:
    st.session_state["openai_session_key"] = st.session_state.get("news_openai_key", "").strip()


def render_ai_settings() -> None:
    if "openai_session_key" not in st.session_state:
        st.session_state["openai_session_key"] = st.session_state.get("news_openai_key", "").strip()
    if "news_openai_key" not in st.session_state:
        st.session_state["news_openai_key"] = st.session_state.get("openai_session_key", "")
    st.text_input(
        "OpenAI API key", type="password", key="news_openai_key",
        on_change=remember_openai_key,
        help="Shared by stock chat, news and on-demand revenue outlook. Stored only in this browser session's server memory.",
    )
    if os.environ.get("OPENAI_API_KEY", "").strip():
        st.caption("A key is configured through OPENAI_API_KEY.")
    st.caption(
        "Chat sends your question, this stock's recent chat history and public stock data "
        "to OpenAI. Revenue outlook sends only the selected company and the public excerpts "
        "you supply when you explicitly run an assessment. Do not enter private account information. API usage is billed "
        "separately; requests use store=false. Provider retention policies still apply."
    )


def load_stock_chat_context(
    symbol: str, company_name: str, info: dict, history: pd.DataFrame,
    evidence: dict | None = None,
) -> dict:
    from stock_chat import MARKET_EVIDENCE_FIELDS, RECOVERY_FINANCIAL_FIELDS, build_stock_context

    research_view = {**(evidence or {}), **ETF_RESEARCH_NOTES.get(symbol, {})}
    sections = {"research_view": research_view, "data_cache_hours": CACHE_TTL_SECONDS // 3600}
    recovery = dict(evidence or {})
    if st.session_state.get(f"recovery_loaded_{symbol}"):
        recovery.update(load_recovery_signals(
            symbol, ("small_cap", "sector", "profitability", "deleveraging", "shareholder_yield"),
        ))
    for label, fields in (("recovery_financials", RECOVERY_FINANCIAL_FIELDS),
                          ("recovery_market", MARKET_EVIDENCE_FIELDS)):
        values = {key: value for key, value in recovery.items() if key in fields}
        if values:
            sections[label] = values
    unavailable = []
    if not info:
        try:
            info = cached_info(symbol)
        except StockDataError:
            unavailable.append("company_info: provider data unavailable")
    if history.empty:
        try:
            history = cached_history(symbol, "5y", "1d")
        except StockDataError:
            unavailable.append("price_history: provider data unavailable")
    for label, loader in (
        ("annual_financials", lambda: cached_financial_history(symbol, "annual")),
        ("quarterly_financials", lambda: cached_financial_history(symbol, "quarterly")),
        ("rolling_growth", lambda: cached_stock_revenue_growth(symbol, REVENUE_MODEL_VERSION)),
        ("news", lambda: cached_company_news(symbol)),
    ):
        try:
            result = loader()
        except StockDataError:
            unavailable.append(f"{label}: provider data unavailable")
        else:
            sections[label] = result.tail(10).to_dict("records") if isinstance(result, pd.DataFrame) else result
    sections["unavailable"] = unavailable
    return build_stock_context(symbol, company_name, info, history, sections)


@st.fragment
def render_revenue_outlook_research(symbol: str, company_name: str) -> None:
    from revenue_outlook import DEFAULT_OUTLOOK_MODEL
    from revenue_outlook_ui import render_revenue_outlook

    render_revenue_outlook(
        symbol, company_name, openai_key(),
        os.environ.get("OPENAI_REVENUE_MODEL", DEFAULT_OUTLOOK_MODEL).strip(),
    )


@st.fragment
def render_stock_assistant(
    symbol: str, company_name: str, info: dict, history: pd.DataFrame,
    evidence: dict | None = None,
) -> None:
    from stock_chat_ui import render_stock_chat

    render_stock_chat(
        symbol, company_name,
        lambda: load_stock_chat_context(symbol, company_name, info, history, evidence),
        openai_key(),
        os.environ.get("OPENAI_CHAT_MODEL", DEFAULT_NEWS_MODEL).strip(),
    )


def render_chart_and_assistant(
    symbol: str, company_name: str, info: dict, history: pd.DataFrame,
    evidence: dict | None = None, chart_type: str = "Line",
) -> None:
    fund_research = ETF_RESEARCH_NOTES.get(symbol)
    if fund_research:
        st.info(
            f"{fund_research['ResearchNotes']} "
            f"[Issuer explanation]({fund_research['ResearchSource']})"
        )
    chart, assistant = st.columns([2.2, 1], gap="large")
    with chart:
        st.plotly_chart(
            price_chart(history, symbol, chart_type), width="stretch",
            config={"displaylogo": False},
        )
    with assistant:
        render_stock_assistant(symbol, company_name, info, history, evidence)


def step_strategy_candidate(
    symbols: list[str], selection_key: str, direction: int,
) -> None:
    current = st.session_state.get(selection_key)
    index = symbols.index(current) if current in symbols else 0
    st.session_state[selection_key] = symbols[(index + direction) % len(symbols)]


def render_strategy_candidate_research(
    results: pd.DataFrame,
    key: str,
    queue_label: str,
    *,
    browse: bool = False,
) -> None:
    if results.empty:
        st.info("There are no candidates to research with the current filters.")
        return
    by_symbol = results.set_index("Symbol").to_dict("index")
    symbols = list(by_symbol)
    selection_key = f"{key}_research_symbol"
    if st.session_state.get(selection_key) not in symbols:
        st.session_state[selection_key] = symbols[0]
    st.divider()
    symbol = st.selectbox(
        "Research a company", symbols, key=selection_key,
        format_func=lambda value: f"{value} - {by_symbol[value]['Name']}",
    )
    if browse:
        previous, position, following = st.columns([1, 2, 1])
        previous.button(
            "←",
            key=f"{key}_previous_research",
            help="Previous candidate",
            width="stretch",
            on_click=step_strategy_candidate,
            args=(symbols, selection_key, -1),
            disabled=len(symbols) == 1,
        )
        position.markdown(
            f"<p style='text-align:center'>{symbols.index(symbol) + 1} / "
            f"{len(symbols)}</p>",
            unsafe_allow_html=True,
        )
        following.button(
            "→",
            key=f"{key}_next_research",
            help="Next candidate",
            width="stretch",
            on_click=step_strategy_candidate,
            args=(symbols, selection_key, 1),
            disabled=len(symbols) == 1,
        )
    selected = by_symbol[symbol]
    st.subheader(f"{selected['Name']} ({symbol})")
    actions = st.columns([1, 1, 2])
    with actions[0]:
        render_bookmark_button(symbol, selected["Name"])
    with actions[1]:
        st.button(
            "Open in Individual Stocks", type="primary", key=f"{key}_open_research",
            on_click=open_stock_research, args=(symbol, symbols, queue_label),
        )
    try:
        history = cached_history(symbol, "5y", "1d")
    except StockDataError as exc:
        st.warning(f"Price chart unavailable. {exc}")
        render_stock_assistant(symbol, selected["Name"], {}, pd.DataFrame(), selected)
        return
    try:
        info = cached_info(symbol)
    except StockDataError as exc:
        info = {}
        st.warning(f"Company metadata unavailable. {exc}")
    render_chart_and_assistant(symbol, selected["Name"], info, history, selected)


def render_company_news(symbol: str, company_name: str) -> None:
    st.subheader("News sentiment: business impact")
    st.caption(
        "Good or bad for the business, not investor reception or share-price reaction. "
        "Reviews up to 20 source-linked headlines/excerpts from the past 30 days, "
        "not full articles. Coverage can be sparse, especially outside the US."
    )
    with st.expander("OpenAI setup and automatic summaries"):
        st.caption(
            "Only the company name, ticker and public news excerpts are sent to OpenAI. "
            "API usage is billed separately from this chat. No portfolio or financial "
            "account data is sent. API storage is disabled (store=false); provider "
            "retention policies still apply."
        )
        if not st.session_state.get("workspace_ai_settings"):
            render_ai_settings()
        else:
            st.caption("Configure the shared API key under AI assistant settings in the sidebar.")
        api_key = openai_key()
        model = os.environ.get("OPENAI_NEWS_MODEL", DEFAULT_NEWS_MODEL).strip()
        st.caption(f"Model: {model}. Override using OPENAI_NEWS_MODEL before starting the app.")
        automatic = st.checkbox(
            "Automatically summarize the selected company", key="news_auto_summary",
            help="One company at a time, not the entire scanner. Cached for 24 hours.",
        )
    if not api_key:
        st.info("Configure an OpenAI API key in AI assistant settings, or set OPENAI_API_KEY locally.")
    requested = st.button(
        "Load news and summarize", key=f"news_load_{symbol}", disabled=not api_key,
    )
    request_key = (symbol, company_name, model, NEWS_ANALYSIS_VERSION)
    loaded_requests = st.session_state.setdefault("news_loaded_requests", set())
    loaded = request_key in loaded_requests
    if not api_key or not (automatic or requested or loaded):
        return
    # Failed requests require an explicit retry, rather than billing on every rerun.
    failures = st.session_state.setdefault("news_failures", {})
    if requested:
        failures.pop(request_key, None)
    if request_key in failures:
        st.warning(failures[request_key])
        st.caption("Use Load news and summarize to retry.")
        return
    try:
        with st.spinner("Loading news and analysis from the 24-hour cache (fetches only if missing or expired)..."):
            news = cached_company_news(symbol)
            if not news["articles"]:
                st.info("No recent source-linked news was returned. This is not neutral or positive evidence.")
                return
            result = cached_news_assessment(
                symbol, company_name, news, model, NEWS_ANALYSIS_VERSION, api_key,
            )
    except StockDataError as exc:
        failures[request_key] = str(exc)
        st.warning(str(exc))
        return
    loaded_requests.add(request_key)
    assessment = result["analysis"]
    st.metric("Overall reported business impact", assessment["overall"])
    st.write(assessment["summary"])
    st.caption(assessment["limitations"])
    st.caption(
        f"News fetched: {news['fetched_at']} | Summary generated: {result['generated_at']} | "
        f"{model} | AI assessment, not verified fact or investment advice."
    )
    by_id = {article["id"]: article for article in news["articles"]}
    for source_id in assessment["source_ids"]:
        source = by_id[source_id]
        st.link_button(f"[{source_id}] {source['title']}", source["url"])
    with st.expander(f"Article assessments and sources ({len(by_id)})"):
        rows = []
        for item in assessment["articles"]:
            source = by_id[item["id"]]
            rows.append({
                "ID": item["id"], "Date": source["date"][:10],
                "Publisher": source["provider"], "Headline": source["title"],
                "Business impact": item["impact"], "Explanation": item["reason"],
                "Confidence": item["confidence"],
                "Input available": "Headline + excerpt" if source["excerpt"] else "Headline only",
                "Source": source["url"],
            })
        st.dataframe(
            pd.DataFrame(rows), hide_index=True, width="stretch",
            column_config={"Source": st.column_config.LinkColumn("Source")},
        )


def render_etf_holdings(symbol: str) -> None:
    try:
        holdings = cached_etf_holdings(symbol)
    except StockDataError as exc:
        st.warning(str(exc))
        return
    if holdings.empty:
        st.info("The data provider does not currently publish holdings for this ETF.")
        return

    holdings_display = holdings.copy()
    holdings_display["Weight"] = holdings_display["Weight"].map(
        lambda value: f"{value:.2%}"
    )
    st.dataframe(holdings_display, hide_index=True, width="stretch")
    st.caption(
        "Top holdings reported by Yahoo Finance; this may not be the fund's "
        "complete portfolio and weights can lag issuer disclosures."
    )


def render_insider_buys(buys: pd.DataFrame, currency: str) -> None:
    if buys.empty:
        st.info("No open-market insider purchases were reported in the past six months.")
        return
    summary = summarize_insider_buys(buys)
    metrics = st.columns(4)
    metrics[0].metric("Open-market purchases", summary["InsiderBuyCount"])
    metrics[1].metric(
        "Shares purchased",
        f"{summary['InsiderBuyShares']:,.0f}",
    )
    metrics[2].metric(
        "Reported value",
        compact_number(summary["InsiderBuyValue"], currency),
    )
    metrics[3].metric(
        "Latest purchase",
        summary["LatestInsiderBuy"].strftime("%Y-%m-%d"),
    )
    display = buys.copy()
    display["Date"] = display["Date"].dt.strftime("%Y-%m-%d")
    display["Shares"] = display["Shares"].map(
        lambda value: f"{value:,.0f}" if pd.notna(value) else "N/A"
    )
    display["Value"] = display["Value"].map(
        lambda value: compact_number(value, currency)
        if pd.notna(value)
        else "N/A"
    )
    st.dataframe(
        display.loc[
            :,
            ["Date", "Insider", "Position", "Shares", "Value", "Details"],
        ],
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "Includes only transactions described by Yahoo Finance as purchases at a "
        "reported price. Stock awards, option exercises, gifts, and sales are excluded."
    )


def load_financials(symbol: str, frequency: str) -> pd.DataFrame:
    financials = cached_financial_history(symbol, frequency)
    expected_columns = {
        "Period",
        "Revenue",
        "Growth",
        "CostOfRevenue",
        "CostOfRevenuePercent",
    }
    missing_columns = expected_columns.difference(financials.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise StockDataError(
            f"{frequency.title()} financial data is missing columns: {missing}."
        )
    return financials


def interval_for_period(period: str) -> str:
    return "1d"


def price_chart(history: pd.DataFrame, symbol: str, chart_type: str) -> go.Figure:
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.75, 0.25],
    )
    if chart_type == "Candlestick":
        figure.add_trace(
            go.Candlestick(
                x=history.index,
                open=history["Open"],
                high=history["High"],
                low=history["Low"],
                close=history["Close"],
                name=symbol,
            ),
            row=1,
            col=1,
        )
    else:
        figure.add_trace(
            go.Scatter(
                x=history.index,
                y=history["Close"],
                mode="lines",
                name="Close",
                line={"width": 2.5, "color": "#60a5fa"},
            ),
            row=1,
            col=1,
        )
    figure.add_trace(
        go.Bar(x=history.index, y=history["Volume"], name="Volume", marker_color="#64748b"),
        row=2,
        col=1,
    )
    if "MA200" in history and history["MA200"].notna().any():
        figure.add_trace(
            go.Scatter(
                x=history.index,
                y=history["MA200"],
                mode="lines",
                name="200-day MA",
                line={"color": "#f59e0b", "width": 2},
                hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )
    figure.update_layout(
        height=520,
        margin={"l": 10, "r": 10, "t": 55, "b": 10},
        title=f"{symbol} price and volume",
        xaxis_rangeslider_visible=False,
        legend={"orientation": "h", "y": 1.02, "x": 0},
        hovermode="x unified",
    )
    figure.update_yaxes(title_text="Price", row=1, col=1)
    figure.update_yaxes(title_text="Volume", row=2, col=1)
    return figure


def revenue_chart(
    revenue: pd.DataFrame,
    currency: str,
    frequency: str,
    growth_label: str,
) -> go.Figure:
    revenue_label = "Rolling four-quarter revenue" if frequency == "rolling" else "Revenue"
    periods = revenue["Period"].map(
        lambda period: format_financial_period(period, frequency)
    )
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Bar(
            x=periods,
            y=revenue["Revenue"],
            name=revenue_label,
            marker_color="#2563eb",
            hovertemplate=f"%{{x}}<br>{currency} %{{y:,.0f}}<extra></extra>",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=periods,
            y=revenue["Growth"],
            name=growth_label,
            mode="lines+markers",
            connectgaps=False,
            line={"color": "#f97316", "width": 3},
            hovertemplate="%{x}<br>%{y:.2%}<extra></extra>",
        ),
        secondary_y=True,
    )
    figure.update_layout(
        height=500,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        legend_orientation="h",
        hovermode="x unified",
        xaxis={"type": "category"},
    )
    figure.update_yaxes(title_text=f"{revenue_label} ({currency})", secondary_y=False)
    figure.update_yaxes(title_text=growth_label, tickformat=".0%", secondary_y=True)
    if frequency == "rolling":
        figure.update_xaxes(title_text="Four-quarter period ending")
        figure.add_hline(y=0, line_dash="dot", line_color="#94a3b8", secondary_y=True)
    return figure


def render_scanner_revenue_comparison(symbol: str, currency: str) -> None:
    st.subheader("Revenue growth used by the scanner")
    try:
        with st.spinner("Loading the scanner's 24-hour cached revenue comparison..."):
            summary = cached_stock_revenue_growth(symbol, REVENUE_MODEL_VERSION)
    except StockDataError as exc:
        st.warning(str(exc))
        return
    if summary["RevenueGrowth"] is None or pd.isna(summary["RevenueGrowth"]):
        st.info("Scanner revenue growth is unavailable. This is not positive growth.")
        return
    st.caption(summary["RevenuePeriod"])
    rolling = summary["RevenueBasis"] == "Rolling four quarters"
    metrics = st.columns(3 if rolling else 2)
    metrics[0].metric(
        "Latest rolling four-quarter revenue" if rolling else "Latest fiscal-year revenue",
        compact_number(summary["TotalRevenue"], currency),
    )
    metrics[1].metric("Scanner year-over-year growth", f"{summary['RevenueGrowth']:.2%}")
    if rolling:
        metrics[2].metric(
            f"Prior four quarters ended {summary['PriorRollingPeriod']}",
            compact_number(summary["PriorRollingRevenue"], currency),
        )
        st.caption(
            "Compares the latest four quarters with the four quarters one year earlier. "
            "This can be positive even when the last completed fiscal year's growth "
            "below is negative. It is not quarter-over-quarter growth."
        )
    else:
        st.warning(
            "Fiscal-year fallback: a complete rolling comparison is unavailable. "
            "The scanner uses the fiscal-year growth shown here instead, not a rolling rate."
        )
    st.caption(
        f"Positive-growth criterion: {'passes' if summary['RevenueGrowth'] > 0 else 'does not pass'}. "
        f"Recent rolling growth trend: {summary['RevenueGrowthTrend']}"
        if rolling else
        f"Positive-growth criterion: {'passes' if summary['RevenueGrowth'] > 0 else 'does not pass'}."
    )
    if rolling:
        st.caption(
            f"Accelerating-growth criterion: {'passes' if summary['RevenueAccelerating'] else 'does not pass'}. "
            "Requires three increasing rolling year-over-year growth rates, with the latest positive. "
            "The chart shows those three quarter-ends, not three completed fiscal years."
        )
        trend = pd.DataFrame(summary["RevenueGrowthHistory"])
        if trend.empty:
            st.warning("The rolling revenue chart is unavailable. Use Refresh data to retry.")
        else:
            trend = trend.rename(columns={"RollingRevenue": "Revenue", "RevenueGrowth": "Growth"})
            st.plotly_chart(
                revenue_chart(trend, currency, "rolling", "Rolling revenue YoY growth"),
                key=f"rolling_revenue_chart_{symbol}",
                width="stretch",
                config={"displaylogo": False},
            )
            with st.expander("Rolling revenue chart data"):
                st.dataframe(
                    trend.rename(columns={
                        "Period": "Four-quarter period ending", "Revenue": "Rolling revenue",
                        "Growth": "YoY growth",
                    }),
                    column_config={
                        "Four-quarter period ending": st.column_config.DateColumn(format="YYYY-MM-DD"),
                        "Rolling revenue": st.column_config.NumberColumn(format="localized", help=currency),
                        "YoY growth": st.column_config.NumberColumn(format="percent"),
                    },
                    hide_index=True,
                    width="stretch",
                )


def render_revenue_history(
    revenue: pd.DataFrame,
    currency: str,
    frequency: str,
    growth_label: str,
) -> None:
    if revenue.empty:
        st.info("Revenue history is not available for this security.")
        return

    latest = revenue.iloc[-1]
    latest_period = format_financial_period(latest["Period"], frequency)
    metrics = st.columns(2)
    metrics[0].metric(
        f"Latest revenue ({latest_period})",
        compact_number(latest["Revenue"], currency),
    )
    metrics[1].metric(
        growth_label,
        f"{latest['Growth']:.2%}" if pd.notna(latest["Growth"]) else "N/A",
    )
    st.plotly_chart(
        revenue_chart(revenue, currency, frequency, growth_label),
        width="stretch",
        config={"displaylogo": False},
    )

    display = revenue.sort_values("Period", ascending=False).copy()
    display["Period"] = display["Period"].map(
        lambda period: format_financial_period(period, frequency)
    )
    display["Revenue"] = display["Revenue"].map(
        lambda value: f"{currency} {value:,.0f}".strip()
    )
    display["Growth"] = display["Growth"].map(
        lambda value: f"{value:.2%}" if pd.notna(value) else "N/A"
    )
    st.dataframe(
        display.loc[:, ["Period", "Revenue", "Growth"]].rename(
            columns={"Growth": growth_label}
        ),
        hide_index=True,
        width="stretch",
    )


def cost_of_revenue_chart(
    financials: pd.DataFrame,
    frequency: str,
) -> go.Figure:
    available = financials.dropna(subset=["CostOfRevenuePercent"])
    periods = available["Period"].map(
        lambda period: format_financial_period(period, frequency)
    )
    figure = go.Figure(
        go.Bar(
            x=periods,
            y=available["CostOfRevenuePercent"],
            name="Cost of revenue / revenue",
            marker_color="#7c3aed",
            text=available["CostOfRevenuePercent"],
            texttemplate="%{text:.1%}",
            hovertemplate="%{x}<br>%{y:.2%}<extra></extra>",
        )
    )
    figure.update_layout(
        height=500,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        xaxis={"type": "category"},
        yaxis={"title": "Cost of revenue as % of revenue", "tickformat": ".0%"},
    )
    return figure


def render_cost_of_revenue_history(
    financials: pd.DataFrame,
    currency: str,
    frequency: str,
) -> None:
    available = financials.dropna(subset=["CostOfRevenuePercent"])
    if available.empty:
        st.info("Cost of revenue is not available for this security.")
        return

    latest = available.iloc[-1]
    latest_period = format_financial_period(latest["Period"], frequency)
    metrics = st.columns(2)
    metrics[0].metric(
        f"Latest cost of revenue ({latest_period})",
        compact_number(latest["CostOfRevenue"], currency),
    )
    metrics[1].metric(
        "Cost of revenue / revenue",
        f"{latest['CostOfRevenuePercent']:.2%}",
    )
    st.plotly_chart(
        cost_of_revenue_chart(available, frequency),
        width="stretch",
        config={"displaylogo": False},
    )

    display = available.sort_values("Period", ascending=False).copy()
    display["Period"] = display["Period"].map(
        lambda period: format_financial_period(period, frequency)
    )
    for column in ("Revenue", "CostOfRevenue"):
        display[column] = display[column].map(
            lambda value: f"{currency} {value:,.0f}".strip()
        )
    display["CostOfRevenuePercent"] = display["CostOfRevenuePercent"].map(
        lambda value: f"{value:.2%}"
    )
    st.dataframe(
        display.loc[
            :,
            ["Period", "Revenue", "CostOfRevenue", "CostOfRevenuePercent"],
        ].rename(
            columns={
                "CostOfRevenue": "Cost of revenue",
                "CostOfRevenuePercent": "Cost of revenue / revenue",
            }
        ),
        hide_index=True,
        width="stretch",
    )


def render_key_metrics(
    info: dict,
    shareholder_yield: dict | None,
    annual_financials: pd.DataFrame,
) -> None:
    sections = key_metric_sections(
        info,
        shareholder_yield,
        annual_financials,
    )
    if not sections:
        st.info("Key metrics are not available for this security.")
        return

    section_items = list(sections.items())
    for start in range(0, len(section_items), 2):
        columns = st.columns(2)
        for column, (title, rows) in zip(columns, section_items[start : start + 2]):
            with column:
                st.subheader(title)
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(
        "Metrics may be trailing, forward-looking, or provider estimates. "
        "Provider summary growth can use a newer interim or trailing period than "
        "the annual statement growth shown above it."
    )


def render_stock_drivers(drivers: dict[str, list[dict[str, str]]]) -> None:
    st.write(
        "Original business-context synthesis generated from industry data, "
        "country and sector proxies, and the company's reported revenue trend."
    )
    tailwind_column, headwind_column = st.columns(2)
    with tailwind_column:
        st.subheader("Tailwinds")
        if drivers["Tailwinds"]:
            for item in drivers["Tailwinds"]:
                st.success(f"**{item['Title']}**\n\n{item['Evidence']}")
        else:
            st.info("No strong contextual tailwinds met the current rules.")
    with headwind_column:
        st.subheader("Headwinds")
        if drivers["Headwinds"]:
            for item in drivers["Headwinds"]:
                st.warning(f"**{item['Title']}**\n\n{item['Evidence']}")
        else:
            st.info("No strong contextual headwinds met the current rules.")
    st.subheader("Major cost drivers")
    cost_drivers = drivers.get("CostDrivers", [])
    if cost_drivers:
        st.dataframe(pd.DataFrame(cost_drivers), hide_index=True, width="stretch")
        st.caption(
            "Industry-based cost hypotheses, not a company-reported expense "
            "breakdown. Use the monitoring variables to test the thesis against "
            "filings and management commentary."
        )
    else:
        st.info("No industry-specific cost-driver mapping is available.")
    context = drivers.get("Context", [])
    if context:
        st.subheader("Market context used")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Context": item["Label"],
                        "Proxy": item["Ticker"],
                        "1-year return": f"{item['Return']:.1%}",
                        "vs. ACWI": (
                            f"{item['RelativeToGlobal']:+.1%}"
                            if item["RelativeToGlobal"] is not None
                            else "N/A"
                        ),
                    }
                    for item in context
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    st.caption(
        "The mechanisms and interpretations are authored in the app—not copied "
        "from external commentary. ETF returns are market proxies, not direct "
        "measures of company demand. These are hypotheses, not forecasts or "
        "investment advice."
    )


def render_stock_catalysts(
    catalyst_data: dict,
    catalysts: list[dict[str, str]],
    error: str | None,
) -> None:
    st.write(
        "Structured upcoming events and locally generated catalyst hypotheses. "
        "No external commentary is copied into this analysis."
    )
    if error:
        st.error(error)

    st.subheader("Upcoming events")
    events = catalyst_data.get("Events", [])
    if events:
        st.dataframe(pd.DataFrame(events), hide_index=True, width="stretch")
    else:
        st.info("No upcoming dated events are available from the provider.")

    st.subheader("Potential catalysts")
    if catalysts:
        for catalyst in catalysts:
            st.success(
                f"**{catalyst['Catalyst']}**\n\n"
                f"{catalyst['Evidence']}\n\n"
                f"**Watch:** {catalyst['Watch']}"
            )
    else:
        st.info("No catalyst hypotheses met the current evidence rules.")

    expectations = catalyst_data.get("Expectations", [])
    if expectations:
        st.subheader("Consensus setup")
        display = pd.DataFrame(expectations)
        for column in ("RevenueGrowth", "EarningsGrowth"):
            display[column] = display[column].map(
                lambda value: f"{value:.1%}" if pd.notna(value) else "N/A"
            )
        for column in ("EPSCurrent", "EPS30DaysAgo"):
            display[column] = display[column].map(
                lambda value: f"{value:,.2f}" if pd.notna(value) else "N/A"
            )
        st.dataframe(
            display.rename(
                columns={
                    "RevenueGrowth": "Revenue growth estimate",
                    "EarningsGrowth": "EPS growth estimate",
                    "EPSCurrent": "Current EPS estimate",
                    "EPS30DaysAgo": "EPS estimate 30 days ago",
                    "RevisionsUp30Days": "Up revisions (30d)",
                    "RevisionsDown30Days": "Down revisions (30d)",
                }
            ),
            hide_index=True,
            width="stretch",
        )

    rating_actions = catalyst_data.get("RatingActions", [])
    if rating_actions:
        st.subheader("Recent analyst rating actions")
        st.dataframe(
            pd.DataFrame(rating_actions),
            hide_index=True,
            width="stretch",
        )
    st.caption(
        "Event dates and analyst estimates can change and coverage varies by market. "
        "Catalysts are conditions to monitor, not predictions or investment advice."
    )


def render_revenue_acceleration_reasons(
    reasons: list[dict[str, str]],
    error: str | None,
) -> None:
    if error:
        st.warning(error)
        return
    if not reasons:
        return
    st.subheader("Why revenue might accelerate")
    for reason in reasons:
        st.success(
            f"**{reason['Reason']}**\n\n"
            f"{reason['Why']}\n\n"
            f"**Evidence:** {reason['Evidence']} "
            f"({reason['Provider']}, {reason['Date']})\n\n"
            f"**Watch:** {reason['Watch']}"
        )
        if reason["URL"]:
            st.link_button(
                f"Open source: {reason['Provider']}",
                reason["URL"],
            )
    st.caption(
        "Only recent company-named developments matching strict commercial-event "
        "rules are shown. These are plausible mechanisms, not revenue forecasts."
    )


def share_count_chart(
    shares: pd.DataFrame,
    frequency: str,
) -> go.Figure:
    periods = shares["Period"].map(
        lambda period: format_financial_period(period, frequency)
    )
    figure = go.Figure(
        go.Scatter(
            x=periods,
            y=shares["Shares"],
            mode="lines+markers",
            name="Shares outstanding",
            line={"color": "#0891b2", "width": 3},
            hovertemplate="%{x}<br>%{y:,.0f} shares<extra></extra>",
        )
    )
    figure.update_layout(
        height=450,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        xaxis={"type": "category"},
        yaxis={"title": "Ordinary shares outstanding", "tickformat": "~s"},
    )
    return figure


def render_share_count_history(
    shares: pd.DataFrame,
    frequency: str,
) -> None:
    if shares.empty:
        st.info("Share-count history is not available for this security.")
        return

    latest = shares.iloc[-1]
    latest_period = format_financial_period(latest["Period"], frequency)
    columns = st.columns(2)
    columns[0].metric(
        f"Shares outstanding ({latest_period})",
        compact_number(latest["Shares"]),
    )
    columns[1].metric(
        "Change from prior period",
        f"{latest['Change']:.2%}" if pd.notna(latest["Change"]) else "N/A",
    )
    st.plotly_chart(
        share_count_chart(shares, frequency),
        width="stretch",
        config={"displaylogo": False},
    )
    display = shares.sort_values("Period", ascending=False).copy()
    display["Period"] = display["Period"].map(
        lambda period: format_financial_period(period, frequency)
    )
    display["Shares"] = display["Shares"].map(lambda value: f"{value:,.0f}")
    display["Change"] = display["Change"].map(
        lambda value: f"{value:.2%}" if pd.notna(value) else "N/A"
    )
    st.dataframe(
        display.rename(
            columns={
                "Shares": "Shares outstanding",
                "Change": "Period-over-period change",
            }
        ),
        hide_index=True,
        width="stretch",
    )


def render_shareholder_returns(
    shareholder_yield: dict | None,
    shareholder_error: str | None,
    annual_shares: pd.DataFrame,
    quarterly_shares: pd.DataFrame,
    currency: str,
) -> None:
    st.subheader("Shareholder yield")
    if shareholder_error:
        st.error(shareholder_error)
    elif shareholder_yield is None:
        st.info(
            "Shareholder yield is unavailable because dividends and net share "
            "issuance are not both reported for a complete, current period."
        )
    else:
        columns = st.columns(4)
        columns[0].metric(
            shareholder_yield["Period"],
            format_value(shareholder_yield["ShareholderYield"], "percent"),
        )
        columns[1].metric(
            "Dividends paid",
            compact_number(shareholder_yield["Dividends"], currency),
        )
        columns[2].metric(
            "Net buybacks",
            compact_number(shareholder_yield["NetBuybacks"], currency),
        )
        columns[3].metric(
            "Total capital returned",
            compact_number(shareholder_yield["TotalReturned"], currency),
        )
        st.caption(
            "Shareholder yield = (cash dividends + net buybacks) / current "
            "market capitalization. Net buybacks subtract proceeds from share issuance."
        )

    st.subheader("Share-count trend")
    annual_tab, quarterly_tab = st.tabs(["Annual", "Quarterly"])
    with annual_tab:
        render_share_count_history(annual_shares, "annual")
    with quarterly_tab:
        render_share_count_history(quarterly_shares, "quarterly")


def format_financial_period(period: pd.Timestamp, frequency: str) -> str:
    if frequency == "rolling":
        return f"{period:%Y-%m-%d}"
    if frequency == "quarterly":
        quarter = ((period.month - 1) // 3) + 1
        return f"{period.year} Q{quarter}"
    return str(period.year)


def render_overview(info: dict, history: pd.DataFrame) -> None:
    currency = str(info.get("currency") or "")
    last_close = history["Close"].iloc[-1]
    previous_close = history["Close"].iloc[-2] if len(history) > 1 else None
    change = (
        (last_close - previous_close) / previous_close
        if previous_close is not None and previous_close != 0
        else None
    )

    columns = st.columns(5)
    columns[0].metric(
        "Last close",
        f"{currency} {last_close:,.2f}".strip(),
        f"{change:.2%}" if change is not None else None,
    )
    columns[1].metric("Market cap", compact_number(info.get("marketCap"), currency))
    columns[2].metric("Trailing P/E", format_value(info.get("trailingPE")))
    columns[3].metric("EV / Revenue", format_value(info.get("enterpriseToRevenue")))
    columns[4].metric(
        "52-week high",
        compact_number(info.get("fiftyTwoWeekHigh"), currency),
    )

    facts = {
        "Exchange": info.get("exchange") or "N/A",
        "Country": info.get("country") or "N/A",
        "Sector": info.get("sector") or "N/A",
        "Industry": info.get("industry") or "N/A",
    }
    st.caption(" · ".join(f"{key}: {value}" for key, value in facts.items()))


def step_etf(entry_ids: list[str], direction: int) -> None:
    current = st.session_state.get("atlas_entry")
    index = entry_ids.index(current) if current in entry_ids else 0
    st.session_state["atlas_entry"] = entry_ids[
        (index + direction) % len(entry_ids)
    ]


def step_scanner(symbols: list[str], direction: int) -> None:
    current = st.session_state.get("scanner_symbol")
    index = symbols.index(current) if current in symbols else 0
    st.session_state["scanner_symbol"] = symbols[
        (index + direction) % len(symbols)
    ]


def open_stock_research(
    symbol: str, symbols: list[str], queue_label: str = "U-recovery candidates",
) -> None:
    st.session_state["stock_research_queue"] = symbols
    st.session_state["stock_research_queue_label"] = queue_label
    st.session_state["stock_research_symbol"] = symbol
    st.session_state["stock_query"] = symbol
    st.session_state.pop("search_results", None)
    st.session_state["_stock_research_handoff"] = True
    st.session_state["research_area"] = "Individual stocks"


def select_stock_research_symbol() -> None:
    symbol = st.session_state["stock_research_symbol"]
    st.session_state["stock_query"] = symbol
    st.session_state.pop("search_results", None)


def step_stock_research(symbols: list[str], direction: int) -> None:
    current = st.session_state.get("stock_research_symbol")
    index = symbols.index(current) if current in symbols else 0
    symbol = symbols[(index + direction) % len(symbols)]
    st.session_state["stock_research_symbol"] = symbol
    st.session_state["stock_query"] = symbol
    st.session_state.pop("search_results", None)


def render_bookmark_button(
    symbol: str, company_name: str, *, label: str = "Bookmark stock",
) -> None:
    try:
        saved = any(row["symbol"] == symbol.strip().upper() for row in list_bookmarks())
    except BookmarkError as exc:
        st.error(str(exc))
        return
    if st.button(
        "Remove bookmark" if saved else label,
        key=f"bookmark_toggle_{symbol}",
        help="Saved locally across browser sessions and app restarts.",
    ):
        try:
            if saved:
                remove_bookmark(symbol)
            else:
                add_bookmark(symbol, company_name)
        except BookmarkError as exc:
            st.error(str(exc))
        else:
            st.rerun()


def step_bookmark(symbols: list[str], direction: int) -> None:
    current = st.session_state.get("bookmark_symbol")
    index = symbols.index(current) if current in symbols else 0
    st.session_state["bookmark_symbol"] = symbols[(index + direction) % len(symbols)]


def render_bookmarks() -> None:
    render_page_header("Bookmarked stocks and ETFs", "bookmarks")
    st.caption(
        "Your locally saved stocks and ETFs. Bookmarks survive browser refreshes, "
        "cache refreshes and app restarts. Shared by browsers using this local app."
    )
    try:
        bookmarks = list_bookmarks()
    except BookmarkError as exc:
        st.error(str(exc))
        return
    if not bookmarks:
        st.info(
            "No bookmarks yet. Use Bookmark stock on a research page or scanner "
            "candidate, or Bookmark ETF in the ETF market atlas."
        )
        return
    by_symbol = {row["symbol"]: row for row in bookmarks}
    symbols = list(by_symbol)
    if st.session_state.get("bookmark_symbol") not in symbols:
        st.session_state["bookmark_symbol"] = symbols[0]
    symbol = st.selectbox(
        "Bookmarked stock or ETF", symbols, key="bookmark_symbol",
        format_func=lambda value: f"{value} - {by_symbol[value]['name']}",
    )
    previous, position, following = st.columns([1, 2, 1])
    previous.button(
        "Previous bookmark", on_click=step_bookmark, args=(symbols, -1),
        disabled=len(symbols) == 1, width="stretch",
    )
    position.write(f"{symbols.index(symbol) + 1} / {len(symbols)}")
    following.button(
        "Next bookmark", on_click=step_bookmark, args=(symbols, 1),
        disabled=len(symbols) == 1, width="stretch",
    )
    st.subheader(f"{by_symbol[symbol]['name']} ({symbol})")
    render_bookmark_button(symbol, by_symbol[symbol]["name"])
    st.button(
        "Open in Individual Stocks", type="primary",
        on_click=open_stock_research, args=(symbol, symbols, "Bookmarked stocks"),
    )
    with st.expander(f"All bookmarks ({len(symbols)})"):
        st.dataframe(
            pd.DataFrame(bookmarks).rename(columns={
                "symbol": "Symbol", "name": "Company / fund", "created_at": "Saved at (UTC)",
            }),
            hide_index=True, width="stretch",
        )
    try:
        history = cached_history(symbol, "5y", "1d")
    except StockDataError as exc:
        st.warning(f"Price history is unavailable. Your bookmark is still saved. {exc}")
        render_stock_assistant(symbol, by_symbol[symbol]["name"], {}, pd.DataFrame())
        return
    try:
        info = cached_info(symbol)
    except StockDataError as exc:
        info = {}
        st.warning(f"Company metadata is unavailable; the chart is still shown. {exc}")
    render_overview(info, history)
    render_chart_and_assistant(symbol, by_symbol[symbol]["name"], info, history)


def refresh_cached_data() -> None:
    """Run before rendering so no section reads an entry invalidated later in the page."""
    st.cache_data.clear()
    st.session_state["manual_cache_refresh_at"] = datetime.now(timezone.utc)
    # Loaded/automatic summaries would otherwise make a paid request on this rerun.
    had_news = st.session_state.get("news_auto_summary") or st.session_state.get("news_loaded_requests")
    st.session_state["news_auto_summary"] = False
    st.session_state["news_loaded_requests"] = set()
    st.session_state["_data_refresh_notice"] = (
        "Shared data caches cleared. This page will request fresh provider data; "
        "provider timestamps below show what was available. Saved bookmarks, management "
        "reviews and chat history are unchanged."
        + (" News summaries are paused; use Load news and summarize to request a new analysis."
           if had_news else "")
    )


def render_refresh_button(key: str, label: str = "Refresh data") -> None:
    st.button(
        label, key=key, on_click=refresh_cached_data, icon=":material/refresh:",
        width="stretch",
        help=(
            "Fetch again now, bypassing the normal 24-hour cache. Clears shared data "
            "caches across pages and connected browsers; only data needed by the active "
            "page is reloaded now. Does not redo source-based research or send AI requests. "
            "Large scans can take a few minutes; repeated refreshes may hit provider limits."
        ),
    )


def render_page_header(title: str, key: str) -> None:
    heading, refresh = st.columns([4, 1], vertical_alignment="center")
    with heading:
        st.title(title)
    with refresh:
        render_refresh_button(f"refresh_{key}")
    notice = st.session_state.pop("_data_refresh_notice", "")
    if notice:
        st.info(notice)
    last_refresh = st.session_state.get("manual_cache_refresh_at")
    if isinstance(last_refresh, datetime):
        st.caption(f"Last manual refresh requested: {last_refresh:%Y-%m-%d %H:%M:%S} UTC.")


def render_cache_controls() -> None:
    render_refresh_button("refresh_all_cached_data", "Refresh all cached data")
    st.caption(
        "Each unique external-data request is cached for 24 hours. Interface reruns "
        "reuse cached entries. Manual refresh is available anytime and bypasses the "
        "cache; it does not update curated research or automatically generate paid AI summaries."
    )
    st.caption(
        "Scanner market-data failures are also cached as unavailable for up to 24 hours, "
        "rather than retried on each checkbox change. Use Refresh data to retry sooner."
    )


ScannerValue = TypeVar("ScannerValue")


def load_scanner_data(
    symbols: list[str], loader: Callable[[str], ScannerValue], label: str,
) -> BatchResult[ScannerValue]:
    progress = st.progress(0, text=f"{label}: checking cached data...")

    def update(state: LoadProgress) -> None:
        progress.progress(
            state.completed / state.total if state.total else 1.0,
            text=f"{label}: {state.completed}/{state.total} candidates processed",
        )

    try:
        batch = load_symbol_batch(symbols, loader, update)
    finally:
        progress.empty()
    state = batch.progress
    st.caption(
        f"{label}: {state.completed}/{state.total} processed in {state.elapsed:.2f}s | "
        f"{state.reused} cached entries reused | {state.computed} entries loaded/computed. "
        "Up to four candidates load concurrently; nested data and assessment entries are counted separately."
    )
    if state.unavailable or batch.errors:
        st.warning(
            f"{label}: some data is unavailable. Failed market requests are retained in the "
            "24-hour cache; use Refresh data to retry. Unavailable evidence never passes a filter."
        )
    return batch


def render_u_shape_reference_patterns() -> None:
    with st.expander("Reference patterns"):
        st.caption(
            "Curated examples help interpret the shape model. They never enter scanner "
            "results or alter strict and near-miss rules. Measurements are fixed at the "
            "stated reference date; open the stock for current data."
        )
        for reference in U_SHAPE_REFERENCE_PATTERNS:
            st.markdown(f"**{reference['Symbol']} — {reference['Company']}**")
            st.write(f"**{reference['Stage']}.** {reference['Reason']}")
            metrics = st.columns(4)
            metrics[0].metric(
                f"Prior peak ({reference['PriorPeakDate']})",
                f"${reference['PriorPeak']:,.2f}",
            )
            metrics[1].metric(
                f"Low ({reference['LowDate']})",
                f"${reference['Low']:,.2f}",
            )
            metrics[2].metric(
                f"Reference close ({reference['AsOf']})",
                f"${reference['ReferenceClose']:,.2f}",
            )
            metrics[3].metric(
                "Recovery through full peak-to-low range",
                f"{reference['RecoveryProgress']:.1%}",
            )
            st.caption(
                "The current incomplete-U scanner intentionally excludes this snapshot: "
                "TWST had already exceeded the peak selected inside its five-year model "
                "window and had recovered about 88% of the older 2021 peak-to-low range. "
                "The scanner requires 5–75% recovery and at least 10% distance below its "
                "selected peak."
            )
            st.button(
                "Open TWST reference in Individual Stocks",
                key="open_u_reference_twst",
                on_click=open_stock_research,
                args=("TWST", ["TWST"], "U-shape reference patterns"),
            )


def render_inflection_scanner() -> None:
    render_page_header("U-Recovery Scanner", "u_recovery")
    preserve_handoff = st.session_state.pop("_stock_research_handoff", False)
    if (
        st.session_state.get("stock_research_queue_label") == "U-recovery candidates"
        and not preserve_handoff
    ):
        st.session_state.pop("stock_research_queue", None)
        st.session_state.pop("stock_research_queue_label", None)
    st.caption(
        "Incomplete U-shaped recoveries: a meaningful decline, a long low-price "
        "base, and the beginning of a positive right side."
    )
    st.caption(
        f"Shape model: {U_RECOVERY_MODEL_VERSION}. Pattern tests use dividend/split-adjusted closes; "
        "displayed price charts use provider OHLC without automatic dividend adjustment."
    )
    render_u_shape_reference_patterns()
    with st.sidebar:
        scanner_universe = st.radio(
            "Scanner universe",
            (
                "Russell 2000 stocks",
                "S&P 500 stocks",
                "European stocks",
                "ETF atlas",
            ),
        )
        st.subheader("Chart shape")
        include_strict = st.checkbox(
            "Strict U-shape matches", value=True, key="u_shape_strict",
            help="All existing U-recovery rules pass. This does not mean a visually perfect U or guaranteed returns.",
        )
        include_near = st.checkbox(
            "Near misses", value=False, key="u_shape_near",
            help=(
                "Misses one or two strict rules: bounded base/trend deviations or a completed "
                "intermediate cycle before the final low. Core decline, recovery and failed-cycle guards still apply."
            ),
        )
        st.caption(
            "Independent choices: either group alone, or both combined (OR). "
            "Near misses exclude strict matches and show the rules they miss."
        )
        if scanner_universe != "ETF atlas":
            st.subheader("Additional stock criteria")
            require_revenue_growth = st.checkbox(
                "Positive rolling revenue growth",
                help="Latest rolling four-quarter revenue is higher year over year.",
            )
            st.checkbox(
                "Expected positive revenue growth (placeholder)",
                value=False, disabled=True, key="expected_revenue_growth_placeholder",
                help=(
                    "Not implemented yet. No forecast data is requested and this placeholder "
                    "does not filter or rank candidates."
                ),
            )
            require_accelerating_growth = st.checkbox(
                "Accelerating revenue growth",
                help=(
                    "The latest three rolling four-quarter growth rates increased "
                    "consecutively and the latest rate is positive."
                ),
            )
            require_insider_buys = st.checkbox(
                "Open-market insider buys",
                help="At least one reported purchase at a price in the past six months.",
            )
            require_net_buybacks = st.checkbox(
                "Positive net buybacks (>0)", key="require_net_buybacks",
                help=(
                    "Actual repurchase spending exceeds cash proceeds from share issuance. "
                    "Latest complete TTM or labeled fiscal-year fallback; dividends and authorizations do not count."
                ),
            )
            require_high_short_interest = st.checkbox(
                "High short interest (≥10% of float)",
                help="Provider-reported short shares are at least 10% of public float.",
            )
            require_low_float = st.checkbox(
                "Limit public float (%)", key="require_low_float",
                help="Public float divided by shares outstanding, not short interest as a percentage of float.",
            )
            maximum_float_percent = st.number_input(
                "Maximum public float (%)", min_value=0.0, max_value=100.0,
                value=25.0, step=1.0, key="maximum_float_percent", disabled=not require_low_float,
                help="Includes values at or below this limit. Missing, nonpositive or inconsistent share counts do not pass.",
            )
            require_positive_pe = st.checkbox(
                "Positive trailing P/E (>0)", key="require_positive_pe",
                help="Requires a finite provider-reported trailing P/E strictly above zero. No forward P/E substitute.",
            )
            require_ev_revenue_under_10 = st.checkbox(
                "EV / Revenue below 10",
                help="Provider-reported enterprise value divided by revenue is below 10.",
            )
            st.subheader("Business recovery")
            extra_requirements = {
                criterion: st.checkbox(label, key=f"require_recovery_{criterion}")
                for criterion, (label, _, _, _) in RECOVERY_CRITERIA.items()
            }
            st.caption(
                "Profitability: higher operating margin AND improving free cash flow "
                "(reduced burn allowed). Debt: lower gross AND net debt, positive free cash flow. "
                "Shareholder yield: dividends plus buybacks minus issuance, divided by market cap; "
                "latest complete TTM, or labeled fiscal-year fallback. "
                "Management: your source-backed review, not an automatic signal."
            )
            st.caption("After the shape selection, results must satisfy every checked stock criterion (AND).")
        else:
            require_revenue_growth = False
            require_accelerating_growth = False
            require_insider_buys = False
            require_net_buybacks = False
            require_high_short_interest = False
            require_low_float = False
            maximum_float_percent = 25.0
            require_positive_pe = False
            require_ev_revenue_under_10 = False
            extra_requirements = {}

    if not include_strict and not include_near:
        st.info("Select Strict U-shape matches, Near misses, or both to run the scanner.")
        return

    metadata: dict[str, dict[str, str]] = {}
    try:
        if scanner_universe == "Russell 2000 stocks":
            holdings = cached_russell_holdings()
            coverage = "Russell 2000"
            source_fund = "IWM"
        elif scanner_universe == "S&P 500 stocks":
            holdings = cached_sp500_holdings()
            coverage = "S&P 500"
            source_fund = "IVV"
        elif scanner_universe == "European stocks":
            holdings = cached_european_holdings()
            coverage = "European equities"
            source_fund = "IEUR"
        else:
            holdings = None

        if holdings is not None:
            symbols = tuple(sorted(set(holdings["Symbol"].tolist())))
            metadata = {
                row.Symbol: {
                    "Name": row.Name,
                    "Coverage": (
                        f"{row.Country} · {row.Sector}"
                        if scanner_universe == "European stocks"
                        else coverage
                    ),
                }
                for row in holdings.itertuples(index=False)
            }
            spinner_text = (
                f"Loading the {source_fund} scan from the 24-hour cache "
                "(fetches only if missing or expired)..."
            )
        else:
            catalog = etf_catalog()
            symbol_rows: dict[str, list[dict]] = {}
            for row in catalog:
                if row["Symbol"]:
                    symbol_rows.setdefault(row["Symbol"], []).append(row)
            symbols = tuple(sorted(symbol_rows))
            metadata = {
                symbol: {
                    "Name": rows[0]["Fund"],
                    "Coverage": ", ".join(
                        sorted({row["Category"] for row in rows})
                    ),
                }
                for symbol, rows in symbol_rows.items()
            }
            spinner_text = (
                "Loading the ETF scan from the 24-hour cache "
                "(fetches only if missing or expired)..."
            )

        shape_activity = CacheActivity()
        with st.spinner(spinner_text), track_cache_activity(shape_activity):
            if scanner_universe != "ETF atlas":
                scan = cached_stock_inflection_scan(symbols, U_RECOVERY_MODEL_VERSION)
            else:
                scan = cached_inflection_scan(symbols, U_RECOVERY_MODEL_VERSION)
    except StockDataError as exc:
        st.error(str(exc))
        st.caption("Unavailable market-data results are cached. Use Refresh data for an explicit retry.")
        return
    reused, computed, _ = shape_activity.counts()
    st.caption(f"Technical scan cache: {reused} entries reused; {computed} entries loaded/computed.")
    selected_shapes = [
        label for enabled, label in ((include_strict, U_SHAPE_STRICT), (include_near, U_SHAPE_NEAR_MISS))
        if enabled
    ]
    if scan.empty:
        st.info("No securities currently match the selected U-shape groups.")
        return
    counts = scan["ShapeMatch"].value_counts()
    st.caption(
        f"Technical shape scan: {counts.get(U_SHAPE_STRICT, 0)} strict matches; "
        f"{counts.get(U_SHAPE_NEAR_MISS, 0)} near misses. Groups are disjoint; both selections combine them."
    )
    scan = scan.loc[scan["ShapeMatch"].isin(selected_shapes)].copy()
    if scan.empty:
        st.info("No securities currently match the selected U-shape groups.")
        return
    scan["Fund"] = scan["Symbol"].map(lambda symbol: metadata[symbol]["Name"])
    scan["Coverage"] = scan["Symbol"].map(
        lambda symbol: metadata[symbol]["Coverage"]
    )
    require_revenue_data = (
        require_revenue_growth or require_accelerating_growth
    )
    if require_revenue_data:
        batch = load_scanner_data(
            scan["Symbol"].tolist(),
            lambda symbol: cached_stock_revenue_growth(symbol, REVENUE_MODEL_VERSION),
            "Revenue data",
        )
        revenue = pd.DataFrame([
            {"Symbol": symbol, **data} for symbol, data in batch.values.items()
        ] + [
            {"Symbol": symbol, "RevenueGrowth": float("nan"), "RevenueAccelerating": False,
             "RevenueGrowthTrend": "Unavailable", "RevenuePeriod": error}
            for symbol, error in batch.errors.items()
        ])
        scan = scan.merge(revenue, on="Symbol", how="left")
        unavailable_count = int(scan["RevenueGrowth"].isna().sum())
        if require_revenue_growth:
            scan = scan.loc[scan["RevenueGrowth"] > 0].copy()
        if require_accelerating_growth:
            scan = scan.loc[scan["RevenueAccelerating"]].copy()
        revenue_requirements = []
        if require_revenue_growth:
            revenue_requirements.append("positive rolling four-quarter growth")
        if require_accelerating_growth:
            revenue_requirements.append(
                "three consecutively increasing rolling growth rates"
            )
        st.caption(
            f"Revenue filter requires {' and '.join(revenue_requirements)}. "
            f"{unavailable_count} technical candidates had no usable growth value."
        )
        if scan.empty:
            st.info("No U-pattern candidates meet this revenue-growth filter.")
            return
    if require_net_buybacks:
        batch = load_scanner_data(scan["Symbol"].tolist(), cached_net_buyback_assessment, "Net buyback data")
        buybacks = pd.DataFrame([
            {"Symbol": symbol, **data} for symbol, data in batch.values.items()
        ] + [
            {"Symbol": symbol, "BuybackStatus": "Unknown", "BuybackReason": error}
            for symbol, error in batch.errors.items()
        ])
        counts = buybacks["BuybackStatus"].value_counts()
        st.caption(
            "Positive net buybacks: "
            + ", ".join(f"{status}: {counts.get(status, 0)}" for status in ("Pass", "Fail", "Unknown", "Not applicable"))
            + ". Requires cash repurchases net of issuance > 0. No dividend or market-cap requirement."
        )
        st.caption(
            "TTM uses four complete consecutive quarters ending within 200 days; otherwise a "
            "fiscal-year fallback ending within 550 days is labeled. Missing or stale data does not pass. "
            "These are reported cash flows, not buyback authorizations, insider purchases or proof that "
            "shares outstanding fell. Noncash stock compensation and other dilution may still increase "
            "share count. Source: Yahoo Finance; cash-flow definitions and coverage vary."
        )
        with st.expander("Buyback filter audit: passing, failing & unknown candidates"):
            st.dataframe(
                buybacks.rename(columns={
                    "BuybackStatus": "Status", "NetBuybacks": "Net buybacks",
                    "BuybackCurrency": "Reporting currency", "BuybackPeriod": "Buyback period",
                    "BuybackReason": "Evidence / limitations", "BuybackSourceURL": "Source",
                }),
                column_config={"Net buybacks": st.column_config.NumberColumn(format="localized"),
                               "Source": st.column_config.LinkColumn()},
                hide_index=True, width="stretch",
            )
        scan = scan.merge(buybacks, on="Symbol", how="left")
        scan = scan.loc[scan["BuybackStatus"].eq("Pass")].copy()
        if scan.empty:
            st.info("No U-pattern candidates have reported positive net buybacks in an available current reporting period.")
            return
    if require_insider_buys:
        batch = load_scanner_data(scan["Symbol"].tolist(), cached_insider_buys, "Insider-purchase data")
        unavailable_insiders = len(batch.errors)
        insider_rows = [
            {"Symbol": symbol, **summarize_insider_buys(buys)}
            for symbol, buys in batch.values.items()
        ]
        insider_scan = pd.DataFrame(insider_rows)
        if insider_scan.empty:
            st.info("No candidate has available qualifying insider-purchase data.")
            return
        scan = scan.merge(insider_scan, on="Symbol", how="inner")
        scan = scan.loc[scan["InsiderBuyCount"] > 0].copy()
        st.caption(
            "Requires at least one open-market purchase reported at a price in the "
            f"past six months. Data was unavailable for {unavailable_insiders} "
            "technical candidates."
        )
        if scan.empty:
            st.info("No U-pattern candidates have a qualifying recent insider purchase.")
            return
    company_info_by_symbol = {}
    if require_high_short_interest or require_ev_revenue_under_10 or require_low_float or require_positive_pe:
        company_metric_rows = []
        unavailable_short_interest = 0
        unavailable_ev_revenue = 0
        unavailable_float = 0
        unavailable_pe = 0
        requested_metrics = []
        if require_high_short_interest:
            requested_metrics.append("short interest")
        if require_ev_revenue_under_10:
            requested_metrics.append("EV / revenue")
        if require_low_float:
            requested_metrics.append("public float")
        if require_positive_pe:
            requested_metrics.append("trailing P/E")
        batch = load_scanner_data(
            scan["Symbol"].tolist(), cached_info, "Company data: " + ", ".join(requested_metrics),
        )
        company_info_by_symbol = batch.values
        for symbol in scan["Symbol"]:
            if symbol in batch.errors:
                values = company_screening_metrics({})
                values["FloatDataReason"] = "Unavailable: company metadata could not be loaded."
            else:
                values = company_screening_metrics(company_info_by_symbol[symbol])
            if require_high_short_interest and pd.isna(values["ShortPercentOfFloat"]):
                unavailable_short_interest += 1
            if require_ev_revenue_under_10 and pd.isna(values["EnterpriseToRevenue"]):
                unavailable_ev_revenue += 1
            if require_low_float and pd.isna(values["FloatPercentOfSharesOutstanding"]):
                unavailable_float += 1
            if require_positive_pe and pd.isna(values["TrailingPE"]):
                unavailable_pe += 1
            company_metric_rows.append({"Symbol": symbol, **values})
        company_metrics = pd.DataFrame(company_metric_rows)
        if company_metrics.empty:
            st.info("No candidate has available company screening data.")
            return
        scan = scan.merge(company_metrics, on="Symbol", how="inner")
        if require_low_float:
            scan["FloatPercentLimit"] = maximum_float_percent / 100
            st.caption(
                f"Requires public float / shares outstanding at or below {maximum_float_percent:g}%. "
                f"Unavailable or inconsistent data: {unavailable_float} candidates assessed. "
                "Unknown values do not pass. Source: Yahoo Finance company metadata, cached for 24 hours; "
                "the chart's data date is not a verified share-count date."
            )
            st.caption(
                "Low float percentage is not necessarily a small absolute float or a volatility forecast. "
                "Review trading volume, spreads, dilution and share classes/ADR ratios; provider share bases "
                "may differ. No insider-ownership proxy, clipping or ADR conversion is applied."
            )
            audit = scan.loc[:, [
                "Symbol", "FloatShares", "SharesOutstanding", "FloatPercentOfSharesOutstanding", "FloatDataReason",
            ]].copy()
            audit["Status"] = "Fail"
            audit.loc[audit["FloatPercentOfSharesOutstanding"].le(maximum_float_percent / 100), "Status"] = "Pass"
            audit.loc[audit["FloatPercentOfSharesOutstanding"].isna(), "Status"] = "Unknown"
            with st.expander("Float filter audit: passing, failing & unknown candidates"):
                st.dataframe(
                    audit.rename(columns={
                        "FloatShares": "Public float (shares)", "SharesOutstanding": "Shares outstanding",
                        "FloatPercentOfSharesOutstanding": "Public float (% of outstanding)",
                        "FloatDataReason": "Evidence / limitations",
                    }),
                    column_config={
                        "Public float (% of outstanding)": st.column_config.NumberColumn(format="percent"),
                        "Public float (shares)": st.column_config.NumberColumn(format="localized"),
                        "Shares outstanding": st.column_config.NumberColumn(format="localized"),
                    },
                    hide_index=True, width="stretch",
                )
        if require_positive_pe:
            st.caption(
                "Requires provider-reported trailing P/E strictly above 0, with no upper limit. "
                f"Unavailable or invalid P/E: {unavailable_pe} candidates assessed. "
                "Missing values do not pass and forward P/E is not substituted. "
                "Source: Yahoo Finance company metadata, cached for 24 hours; a positive P/E "
                "does not establish sustainable profitability or cheapness."
            )
        if require_low_float:
            scan = scan.loc[scan["FloatPercentOfSharesOutstanding"].le(maximum_float_percent / 100)].copy()
            if scan.empty:
                st.info("No U-pattern candidates have a valid public float percentage within the selected limit.")
                return
        if require_positive_pe:
            scan = scan.loc[scan["TrailingPE"].gt(0)].copy()
            if scan.empty:
                st.info("No remaining U-pattern candidates have an available trailing P/E above 0.")
                return
        if require_high_short_interest:
            scan = scan.loc[scan["ShortPercentOfFloat"] >= 0.10].copy()
            st.caption(
                "Requires provider-reported short interest of at least 10% of float. "
                f"Data was unavailable for {unavailable_short_interest} technical "
                "candidates."
            )
            if scan.empty:
                st.info(
                    "No U-pattern candidates have short interest of at least 10% "
                    "of float."
                )
                return
        if require_ev_revenue_under_10:
            scan = scan.loc[scan["EnterpriseToRevenue"] < 10].copy()
            st.caption(
                "Requires provider-reported EV / Revenue below 10. "
                f"Data was unavailable for {unavailable_ev_revenue} technical "
                "candidates."
            )
            if scan.empty:
                st.info("No U-pattern candidates have EV / Revenue below 10.")
                return
    active_recovery = tuple(key for key, enabled in extra_requirements.items() if enabled)
    if active_recovery:
        batch = load_scanner_data(
            scan["Symbol"].tolist(), lambda symbol: load_recovery_signals(symbol, active_recovery),
            "Business-recovery data",
        )
        recovery_by_symbol = {symbol: {"Symbol": symbol, **data} for symbol, data in batch.values.items()}
        for symbol, error in batch.errors.items():
            row = {"Symbol": symbol}
            for criterion in active_recovery:
                _, status, reason, _ = RECOVERY_CRITERIA[criterion]
                row.update({status: "Unknown", reason: error})
            recovery_by_symbol[symbol] = row
        recovery = pd.DataFrame([recovery_by_symbol[symbol] for symbol in scan["Symbol"]])
        scan = scan.merge(recovery, on="Symbol", how="left")
        mask = pd.Series(True, index=scan.index)
        for criterion in active_recovery:
            label, status, reason, required_status = RECOVERY_CRITERIA[criterion]
            # Treat missing evidence as unknown, never as a successful comparison.
            if status not in scan:
                scan[status] = "Unknown"
            counts = scan[status].fillna("Unknown").value_counts()
            st.caption(f"{label}: " + ", ".join(f"{name}: {count}" for name, count in counts.items()))
            mask &= scan[status].eq(required_status)
        with st.expander("Business-filter audit: passing, failing & unknown candidates"):
            st.dataframe(recovery, hide_index=True, width="stretch")
        scan = scan.loc[mask].copy()
        if scan.empty:
            st.info(
                "No U-pattern candidates meet every selected business criterion. "
                "Unknown and unreviewed records do not pass. Management evidence can be "
                "added in Individual stocks or Management & incentives."
            )
            return
    with st.sidebar:
        st.header("Inflection candidates")
        signals = ["All"] + sorted(scan["Signal"].unique().tolist())
        signal = st.selectbox("Signal stage", signals)
        lowest_score = int(scan["Score"].min())
        highest_score = int(scan["Score"].max())
        if lowest_score == highest_score:
            minimum_score = lowest_score
            st.caption(f"All remaining candidates score {lowest_score}/16.")
        else:
            minimum_score = st.slider(
                "Minimum score",
                min_value=lowest_score,
                max_value=highest_score,
                value=lowest_score,
            )
        candidates = scan.loc[scan["Score"] >= minimum_score]
        if signal != "All":
            candidates = candidates.loc[candidates["Signal"] == signal]
        candidate_symbols = candidates["Symbol"].tolist()
        if not candidate_symbols:
            st.warning("No candidates match these filters.")
            return
        if st.session_state.get("scanner_symbol") not in candidate_symbols:
            st.session_state["scanner_symbol"] = candidate_symbols[0]
        selected_symbol = st.selectbox(
            "Chart candidate",
            candidate_symbols,
            key="scanner_symbol",
            format_func=lambda symbol: (
                f"{symbol} — {candidates.set_index('Symbol').loc[symbol, 'Coverage']}"
            ),
        )
        previous, position, following = st.columns([1, 2, 1])
        previous.button(
            "←",
            help="Previous candidate",
            width="stretch",
            on_click=step_scanner,
            args=(candidate_symbols, -1),
        )
        current_index = candidate_symbols.index(selected_symbol)
        position.markdown(
            f"<p style='text-align:center'>{current_index + 1} / "
            f"{len(candidate_symbols)}</p>",
            unsafe_allow_html=True,
        )
        following.button(
            "→",
            help="Next candidate",
            width="stretch",
            on_click=step_scanner,
            args=(candidate_symbols, 1),
        )
        if (
            scanner_universe != "ETF atlas"
            and st.session_state.get("research_area") != "Individual stocks"
        ):
            st.session_state["stock_research_queue"] = candidate_symbols
            st.session_state["stock_research_queue_label"] = "U-recovery candidates"
            st.session_state["stock_research_symbol"] = selected_symbol
            st.session_state["stock_query"] = selected_symbol
            st.session_state.pop("search_results", None)

    display = candidates.copy()
    display["Score"] = display["Score"].map(lambda value: f"{value}/16")
    for column in (
        "20DReturn",
        "60DReturn",
        "OneYearReturn",
        "ReboundFromLow",
        "RecoveryProgress",
        "BestPriorRecovery",
        "RecoveryGiveback",
        "PriorDecline",
        "DistanceToPeak",
        "MA50Slope20D",
        "HigherLow",
        "VsMA50",
        "VsMA200",
    ):
        display[column] = display[column].map(lambda value: f"{value:.1%}")
    display["MA200CrossDays"] = display["MA200CrossDays"].map(
        lambda value: f"{int(value)} days ago" if pd.notna(value) else "No recent cross"
    )
    display["AsOf"] = pd.to_datetime(display["AsOf"]).dt.strftime("%Y-%m-%d")
    display_columns = [
        "Symbol",
        "Fund",
        "Coverage",
        "Signal",
        "Score",
        "ShapeMatch",
        "ShapeMissCount",
        "ShapeMissedRules",
        "20DReturn",
        "60DReturn",
        "OneYearReturn",
        "ReboundFromLow",
        "RecoveryProgress",
        "BestPriorRecovery",
        "RecoveryGiveback",
        "PriorDecline",
        "DistanceToPeak",
        "LowAge",
        "BaseSpan",
        "BaseDays",
        "MA50Slope20D",
        "HigherLow",
        "VsMA50",
        "VsMA200",
        "MA200CrossDays",
        "AsOf",
    ]
    if require_revenue_data:
        display["RevenueGrowth"] = display["RevenueGrowth"].map(
            lambda value: f"{value:.1%}"
        )
        display_columns[5:5] = [
            "RevenueGrowth",
            "RevenueGrowthTrend",
            "RevenuePeriod",
        ]
    if require_high_short_interest:
        display["ShortPercentOfFloat"] = display["ShortPercentOfFloat"].map(
            lambda value: f"{value:.1%}"
        )
        display_columns.insert(5, "ShortPercentOfFloat")
    if require_ev_revenue_under_10:
        display["EnterpriseToRevenue"] = display["EnterpriseToRevenue"].map(
            lambda value: f"{value:.2f}"
        )
        display_columns.insert(5, "EnterpriseToRevenue")
    if require_low_float:
        display["FloatPercentOfSharesOutstanding"] = display["FloatPercentOfSharesOutstanding"].map(
            lambda value: f"{value:.2%}"
        )
        display["FloatShares"] = display["FloatShares"].map(lambda value: f"{value:,.0f}")
        display_columns[5:5] = ["FloatPercentOfSharesOutstanding", "FloatShares"]
    if require_positive_pe:
        display["TrailingPE"] = display["TrailingPE"].map(lambda value: f"{value:,.6g}")
        display_columns.insert(5, "TrailingPE")
    if require_net_buybacks:
        display["NetBuybacks"] = display["NetBuybacks"].map(lambda value: f"{value:,.2f}")
        display_columns[5:5] = ["NetBuybacks", "BuybackCurrency", "BuybackPeriod"]
    if require_insider_buys:
        display["LatestInsiderBuy"] = pd.to_datetime(
            display["LatestInsiderBuy"]
        ).dt.strftime("%Y-%m-%d")
        display["InsiderBuyShares"] = display["InsiderBuyShares"].map(
            lambda value: f"{value:,.0f}"
        )
        display["InsiderBuyValue"] = display["InsiderBuyValue"].map(
            lambda value: f"${value:,.0f}"
        )
        display_columns[5:5] = [
            "InsiderBuyCount",
            "InsiderBuyShares",
            "InsiderBuyValue",
            "LatestInsiderBuy",
        ]
    recovery_columns = [RECOVERY_CRITERIA[key][1] for key in active_recovery]
    if "small_cap" in active_recovery and "MarketCapUSD" in display:
        display["MarketCapUSD"] = display["MarketCapUSD"].map(lambda value: f"${value:,.0f}")
        recovery_columns.append("MarketCapUSD")
    if "sector" in active_recovery:
        for column in ("SectorExcess3M", "SectorExcess6M"):
            if column in display:
                display[column] = display[column].map(lambda value: f"{100 * value:+.2f} pp")
                recovery_columns.append(column)
        if "SectorBenchmark" in display:
            recovery_columns.append("SectorBenchmark")
    if "shareholder_yield" in active_recovery:
        display["ShareholderYield"] = display["ShareholderYield"].map(lambda value: f"{value:.2%}")
        recovery_columns.extend(["ShareholderYield", "ShareholderYieldPeriod"])
    recovery_column_labels = {
        "ShareholderYield": "Shareholder yield",
        "ShareholderYieldPeriod": "Shareholder yield period",
        "ShareholderYieldStatus": "Shareholder yield status",
    }
    display_columns[5:5] = recovery_columns
    st.subheader(f"Matching candidates ({len(candidates)})")
    st.caption("Select a candidate in the sidebar. Open the table's column menu for all technical measures.")
    st.dataframe(
        display.loc[:, display_columns].rename(
            columns={
                **recovery_column_labels,
                "Fund": "Company / fund",
                "ShapeMatch": "Shape match",
                "ShapeMissCount": "Missed strict rules",
                "ShapeMissedRules": "Why near miss",
                "RevenueGrowth": "Revenue growth",
                "RevenueGrowthTrend": "Recent growth trend",
                "RevenuePeriod": "Revenue period",
                "ShortPercentOfFloat": "Short % of float",
                "EnterpriseToRevenue": "EV / Revenue",
                "FloatPercentOfSharesOutstanding": "Public float (% of outstanding)",
                "FloatShares": "Public float (shares)",
                "TrailingPE": "Trailing P/E",
                "NetBuybacks": "Net buybacks",
                "BuybackCurrency": "Buyback currency",
                "BuybackPeriod": "Buyback period",
                "InsiderBuyCount": "Insider buys (6m)",
                "InsiderBuyShares": "Shares bought",
                "InsiderBuyValue": "Reported buy value",
                "LatestInsiderBuy": "Latest insider buy",
                "20DReturn": "20-day return",
                "60DReturn": "60-day return",
                "OneYearReturn": "1-year return",
                "ReboundFromLow": "Rebound from low",
                "RecoveryProgress": "Recovery through U",
                "BestPriorRecovery": "Best prior recovery",
                "RecoveryGiveback": "Giveback from best recovery",
                "PriorDecline": "Decline into low",
                "DistanceToPeak": "Still below prior peak",
                "LowAge": "Low age (trading days)",
                "BaseSpan": "Base span (trading days)",
                "BaseDays": "Days near low",
                "MA50Slope20D": "50-day MA slope",
                "HigherLow": "Recent vs. prior low",
                "VsMA50": "vs. 50-day MA",
                "VsMA200": "vs. 200-day MA",
                "MA200CrossDays": "MA200 crossover",
                "AsOf": "Data date",
            }
        ),
        column_order=[
            "Symbol", "Company / fund", "Shape match", "Missed strict rules", "Why near miss", "Signal", "Score",
            *(
                label for active, label in (
                    (require_revenue_data, "Revenue growth"),
                    (require_high_short_interest, "Short % of float"),
                    (require_ev_revenue_under_10, "EV / Revenue"),
                    (require_low_float, "Public float (% of outstanding)"),
                    (require_low_float, "Public float (shares)"),
                    (require_positive_pe, "Trailing P/E"),
                    (require_net_buybacks, "Net buybacks"),
                    (require_net_buybacks, "Buyback currency"),
                    (require_net_buybacks, "Buyback period"),
                    (require_insider_buys, "Insider buys (6m)"),
                ) if active
            ),
            *(recovery_column_labels.get(column, column) for column in recovery_columns),
            "Recovery through U", "Data date",
        ],
        height=min(300, 38 + 35 * len(display)),
        hide_index=True,
        width="stretch",
    )

    selected = candidates.set_index("Symbol").loc[selected_symbol]
    if selected["ShapeMatch"] == U_SHAPE_NEAR_MISS:
        st.warning(
            f"Near miss, not a strict U-shape match: {selected['ShapeMissedRules']}. "
            "The score measures technical features, not the probability of a successful trade."
        )
    else:
        st.caption("Strict U-shape match: all strict technical rules pass; visual perfection and future returns are not guaranteed.")
    if require_net_buybacks:
        st.metric(
            "Net buybacks", compact_number(selected["NetBuybacks"], selected["BuybackCurrency"]),
            help=f"{selected['BuybackPeriod']}. {selected['BuybackMethod']}",
        )
        st.caption(
            f"Buyback period: {selected['BuybackPeriod']} | Reporting currency: {selected['BuybackCurrency']}. "
            "Cash repurchases net of issuance, not the change in outstanding shares."
        )
    if require_low_float or require_positive_pe:
        company_metrics_columns = st.columns((2 if require_low_float else 0) + int(require_positive_pe))
        if require_low_float:
            company_metrics_columns[0].metric(
                "Public float (% of outstanding)", format_value(selected["FloatPercentOfSharesOutstanding"], "percent"),
                help="Provider floatShares / sharesOutstanding. Not short interest or a volatility forecast.",
            )
            company_metrics_columns[1].metric(
                "Public float (shares)", format_value(selected["FloatShares"], "integer"),
                help=f"Reported shares outstanding: {selected['SharesOutstanding']:,.0f}. Share-count dates/bases are not verified.",
            )
        if require_positive_pe:
            company_metrics_columns[-1].metric(
                "Trailing P/E", f"{selected['TrailingPE']:,.6g}",
                help="Provider-reported trailing P/E, not forward P/E; strictly above 0.",
            )
    if scanner_universe != "ETF atlas":
        with st.expander("Revenue outlook: assess supplied excerpts"):
            render_revenue_outlook_research(selected_symbol, str(selected["Fund"]))
    try:
        history = cached_history(selected_symbol, "5y", "1d")
    except StockDataError as exc:
        st.error(str(exc))
        render_stock_assistant(
            selected_symbol, str(selected["Fund"]), {}, pd.DataFrame(), selected.to_dict(),
        )
        return
    try:
        info = (
            company_info_by_symbol[selected_symbol]
            if selected_symbol in company_info_by_symbol else cached_info(selected_symbol)
        )
    except StockDataError as exc:
        info = {}
        st.warning(
            f"Fund metadata is temporarily unavailable, but the price chart is "
            f"still shown. {exc}"
        )
    st.subheader(f"{selected['Fund']} ({selected_symbol})")
    render_bookmark_button(selected_symbol, str(selected["Fund"]))
    if scanner_universe != "ETF atlas":
        st.button(
            "Open in Individual Stocks",
            type="primary",
            on_click=open_stock_research,
            args=(selected_symbol, candidate_symbols),
        )
    metrics = st.columns(5)
    metrics[0].metric("Signal", selected["Signal"])
    metrics[1].metric("Score", f"{selected['Score']}/16")
    metrics[2].metric("20-day return", f"{selected['20DReturn']:.1%}")
    metrics[3].metric(
        "Recovery through U",
        f"{selected['RecoveryProgress']:.1%}",
    )
    if "shareholder_yield" in active_recovery:
        st.metric(
            "Shareholder yield", format_value(selected["ShareholderYield"], "percent"),
            help=selected["ShareholderYieldPeriod"],
        )
    if require_revenue_data:
        metrics[4].metric(
            "Revenue growth",
            format_value(selected["RevenueGrowth"], "percent"),
            help=selected["RevenuePeriod"],
        )
    elif require_high_short_interest:
        metrics[4].metric(
            "Short % of float",
            format_value(selected["ShortPercentOfFloat"], "percent"),
        )
    elif require_ev_revenue_under_10:
        metrics[4].metric(
            "EV / Revenue",
            format_value(selected["EnterpriseToRevenue"], "decimal"),
        )
    elif require_insider_buys:
        metrics[4].metric(
            "Insider buys (6m)",
            int(selected["InsiderBuyCount"]),
        )
    else:
        metrics[4].metric(
            "Dividend yield",
            format_value(info.get("yield"), "percent"),
        )
    render_chart_and_assistant(
        selected_symbol, str(selected["Fund"]), info, history, selected.to_dict(),
    )
    if scanner_universe == "ETF atlas":
        with st.expander("Top holdings"):
            render_etf_holdings(selected_symbol)
    else:
        render_recovery_research(selected_symbol, str(selected["Fund"]), selected.to_dict())
        render_company_news(
            selected_symbol,
            str(info.get("longName") or info.get("shortName") or selected["Fund"]),
        )
    with st.expander("How the scanner works"):
        st.write(
            "At least 500 usable daily closing prices are required. "
            "Strict matches must have declined at least 15% from a five-year peak, "
            "have a low-zone base spanning at least 120 trading days with at least "
            "50 observations in the bottom 20% of the peak-to-trough range, and "
            "remain at least 10% below that peak. The low must be at least 60 "
            "trading days old. The emerging right side must have recovered 5–75% "
            "of the lost price range, formed a "
            "recent low no more than 3% below the prior low, have a non-negative "
            "one-year return, keep its 20-day return at least -10% and its "
            "60-day return at least -3%, and move above a rising 50-day "
            "average. A recent reversal may qualify despite a "
            "negative one-year return when the low is at most 180 trading days old "
            "and its 60-day return is at least 8%. Charts are rejected if "
            "they completed an earlier decline of at least 25% followed by a "
            "recovery lasting at least 120 trading days into the selected peak, or if "
            "they previously recovered at least 75% of the lost range and then "
            "gave back at least 25 percentage points, which indicates a failed "
            "late recovery or repeated cycle rather than one developing U."
        )
        st.write(
            "A completed intermediate cycle between the selected peak and final low is a "
            "near miss, not a strict match: an earlier drop of at least 25% from that peak "
            "recovered at least 75% of its range at least 120 trading days after its trough. "
            "This counts as one missed strict rule, leaving room for at most one additional "
            "bounded base/trend miss. It does not override either hard cycle exclusion above."
        )
        st.write(
            "Near misses fail at most two strict rules in total. Base/trend deviations must stay within these limits: "
            "low age >=45 trading days, base span >=90, low-zone days >=40; "
            "20-day return >=-15%, 60-day return >=-8%, recent low no more than 8% "
            "below the prior low; 50-day average slope >=-2% over 20 sessions and "
            "price no more than 3% below that average. Every tolerance must hold. "
            "The non-negative 1-year return / recent-reversal exception, "
            "15% decline, 5–75% recovery range, "
            "10% distance below peak and both failed-cycle exclusions are unchanged. "
            "Insufficient history is not a near miss. These tolerances are screening "
            "heuristics, not a backtested return forecast."
        )
        st.caption(
            "A screen can fail after publication, and historical price patterns "
            "do not establish that a bottom will hold. Review liquidity, holdings, "
            "currency, country, and macro risks before drawing conclusions."
        )


def render_etf_explorer() -> None:
    render_page_header("Global ETF Market Atlas", "etf_atlas")
    st.caption(
        "Browse global stock-market building blocks using GICS sectors and "
        "country-market classifications."
    )
    catalog = [
        row
        for row in etf_catalog()
        if row["Universe"] != "Country markets"
        or (row["Symbol"] and row["Symbol"].strip())
    ]
    selection_message = st.empty()
    with st.sidebar:
        st.header("ETF chart queue")
        universe = st.radio(
            "Taxonomy view",
            (
                "Country markets",
                "Regional markets",
                "Thematic ETFs",
                "Commodity ETFs",
                "Global sectors",
                "Industry exposures",
                "Full GICS hierarchy",
            ),
            horizontal=True,
        )
        market_group = None
        region = None
        parent_sector = None
        industry_group = None
        industry = None
        if universe == "Country markets":
            st.caption("Countries without a mapped ETF are hidden.")
            market_groups = ["All"] + sorted(
                {
                    row["Market group"]
                    for row in catalog
                    if row["Universe"] == universe
                }
            )
            regions = ["All"] + sorted(
                {row["Region"] for row in catalog if row["Universe"] == universe}
            )
            market_group = st.selectbox("Market group", market_groups)
            region = st.selectbox("Region", regions)
        elif universe == "Regional markets":
            regions = sorted(
                {row["Region"] for row in catalog if row["Universe"] == universe}
            )
            region = st.selectbox("Region", regions)
        elif universe in {"Thematic ETFs", "Commodity ETFs"}:
            themes = sorted(
                {row["Category"] for row in catalog if row["Universe"] == universe}
            )
            parent_sector = st.selectbox(
                "Theme" if universe == "Thematic ETFs" else "Commodity group",
                ["All"] + themes,
            )
            theme_rows = (
                [
                    row
                    for row in catalog
                    if row["Universe"] == universe
                    and (
                        parent_sector == "All"
                        or row["Category"] == parent_sector
                    )
                ]
            )
            subthemes = sorted({row["Market group"] for row in theme_rows})
            market_group = st.selectbox("Subtheme", ["All"] + subthemes)
        elif universe in {"Industry exposures", "Full GICS hierarchy"}:
            parent_sectors = ["All"] + sorted(
                {
                    row["Parent sector"]
                    for row in catalog
                    if row["Universe"] == universe
                }
            )
            parent_sector = st.selectbox("Parent GICS sector", parent_sectors)
            if universe == "Full GICS hierarchy":
                sector_rows = filter_etfs(
                    catalog,
                    universe,
                    parent_sector=parent_sector,
                )
                industry_groups = ["All"] + sorted(
                    {row["Industry group"] for row in sector_rows}
                )
                industry_group = st.selectbox(
                    "Industry group",
                    industry_groups,
                )
                group_rows = filter_etfs(
                    sector_rows,
                    universe,
                    industry_group=industry_group,
                )
                industries = ["All"] + sorted(
                    {row["Industry"] for row in group_rows}
                )
                industry = st.selectbox("Industry", industries)

        visible = filter_etfs(
            catalog,
            universe,
            market_group,
            region,
            None if universe in {"Thematic ETFs", "Commodity ETFs"} else parent_sector,
            industry_group,
            industry,
        )
        if universe in {"Thematic ETFs", "Commodity ETFs"} and parent_sector != "All":
            visible = [
                row for row in visible if row["Category"] == parent_sector
            ]
        if not visible:
            st.session_state.pop("atlas_entry", None)
            selection_message.info(
                "No countries with a mapped ETF match these filters."
                if universe == "Country markets"
                else "No ETF categories match these filters."
            )
            return
        entry_ids = [row["Entry ID"] for row in visible]
        by_entry = {row["Entry ID"]: row for row in visible}
        current_entry = st.session_state.get("atlas_entry")
        if current_entry not in entry_ids:
            current_entry = ETF_ENTRY_REPLACEMENTS.get(current_entry, current_entry)
        if current_entry not in entry_ids:
            current_entry = entry_ids[0]
        if st.session_state.get("atlas_entry") != current_entry:
            st.session_state["atlas_entry"] = current_entry
        entry_id = st.selectbox(
            "Market category",
            entry_ids,
            key="atlas_entry",
            format_func=lambda item: (
                (
                    f"{by_entry[item]['Symbol']} — {by_entry[item]['Category']}"
                    if by_entry[item]["Symbol"]
                    else f"{by_entry[item]['Category']} — no ETF proxy"
                )
            ),
        )
        previous, position, following = st.columns([1, 2, 1])
        previous.button(
            "←",
            help="Previous ETF",
            width="stretch",
            on_click=step_etf,
            args=(entry_ids, -1),
        )
        current_index = entry_ids.index(entry_id)
        position.markdown(
            f"<p style='text-align:center'>{current_index + 1} / {len(entry_ids)}</p>",
            unsafe_allow_html=True,
        )
        following.button(
            "→",
            help="Next ETF",
            width="stretch",
            on_click=step_etf,
            args=(entry_ids, 1),
        )
        st.caption(
            "Charts request five years of daily prices and the 200-day MA. "
            "Available history may be shorter."
        )

    selected = by_entry[entry_id]
    symbol = selected["Symbol"]
    if not symbol:
        st.subheader(selected["Category"])
        hierarchy = [
            f"Classification: {selected['Market group']}",
            f"Region: {selected['Region']}",
        ]
        if selected["Parent sector"]:
            hierarchy = [
                f"Sector: {selected['Parent sector']}",
                f"Industry group: {selected['Industry group']}",
                f"Industry: {selected['Industry']}",
                f"Sub-industry: {selected['Sub-industry']}",
                f"Code: {selected['Taxonomy code']}",
            ]
        st.caption(" · ".join(hierarchy))
        st.info(
            "No suitable active ETF proxy with a complete five-year history is "
            "currently mapped to this category."
        )
        st.dataframe(
            pd.DataFrame(visible).loc[
                :,
                [
                    "Category",
                    "Symbol",
                    "Fund",
                    "Parent sector",
                    "Industry group",
                    "Industry",
                    "Market group",
                    "Region",
                ],
            ],
            hide_index=True,
            width="stretch",
        )
        return

    render_bookmark_button(symbol, str(selected["Fund"] or symbol), label="Bookmark ETF")
    try:
        with st.spinner(f"Loading {symbol}..."):
            history = cached_history(symbol, "5y", "1d")
            summary = summarize_price_history(history)
    except StockDataError as exc:
        st.error(
            f"ETF chart and statistics are unavailable for {symbol}: {exc} "
            "Use Refresh data to retry, or choose another ETF from the queue."
        )
        return

    try:
        info = cached_info(symbol)
        info_error = None
    except StockDataError as exc:
        info = {}
        info_error = str(exc)

    name = info.get("longName") or info.get("shortName") or selected["Fund"]
    currency = str(info.get("currency") or "")
    st.subheader(f"{name} ({symbol})")
    st.caption(
        " · ".join(
            item
            for item in [
                f"View: {selected['Universe']}",
                f"Classification: {selected['Category']}",
                (
                    f"Parent sector: {selected['Parent sector']}"
                    if selected["Parent sector"]
                    else None
                ),
                f"Region: {selected['Region']}",
                f"Exchange: {info.get('exchange') or 'N/A'}",
            ]
            if item is not None
        )
    )

    metrics = st.columns(7)
    metrics[0].metric(
        "Last close",
        f"{currency} {summary['LatestClose']:,.2f}".strip(),
    )
    metrics[1].metric(
        "Dividend yield",
        format_value(info.get("yield"), "percent"),
        help="Provider-reported fund distribution yield; methodology can vary by fund.",
    )
    metrics[2].metric(
        "Period return",
        f"{summary['TotalReturn']:.1%}",
        help="Return over the available price history, which may be shorter than five years.",
    )
    metrics[3].metric(
        "Annualized return",
        f"{summary['AnnualizedReturn']:.1%}",
    )
    metrics[4].metric(
        "Annualized volatility",
        (
            f"{summary['AnnualizedVolatility']:.1%}"
            if summary["AnnualizedVolatility"] is not None
            else "N/A"
        ),
    )
    metrics[5].metric("Max drawdown", f"{summary['MaxDrawdown']:.1%}")
    metrics[6].metric(
        "vs. 200-day MA",
        (
            f"{summary['LatestClose'] / summary['LatestMA200'] - 1:+.1%}"
            if summary["LatestMA200"]
            else "N/A"
        ),
    )

    chart_tab, holdings_tab, details_tab, queue_tab = st.tabs(
        ["5-year chart", "Holdings", "ETF information", "Chart queue"]
    )
    with chart_tab:
        render_chart_and_assistant(symbol, str(name), info, history, selected)
    with holdings_tab:
        render_etf_holdings(symbol)
    with details_tab:
        if info_error:
            st.warning(info_error)
        details = [
            {"Field": "Fund", "Value": name},
            {"Field": "Ticker", "Value": symbol},
            {"Field": "Taxonomy", "Value": selected["Taxonomy"]},
            {"Field": "Classification", "Value": selected["Category"]},
            {
                "Field": "Parent GICS sector",
                "Value": selected["Parent sector"] or "N/A",
            },
            {
                "Field": "Industry group",
                "Value": selected["Industry group"] or "N/A",
            },
            {"Field": "Industry", "Value": selected["Industry"] or "N/A"},
            {
                "Field": "Sub-industry",
                "Value": selected["Sub-industry"] or "N/A",
            },
            {
                "Field": "GICS code",
                "Value": selected["Taxonomy code"] or "N/A",
            },
            {
                "Field": "ETF proxy level",
                "Value": selected["Proxy level"] or "N/A",
            },
            {"Field": "Market group", "Value": selected["Market group"]},
            {"Field": "Region", "Value": selected["Region"]},
            {"Field": "Fund category", "Value": info.get("category") or "N/A"},
            {
                "Field": "Net assets",
                "Value": compact_number(info.get("totalAssets"), currency),
            },
            {
                "Field": "Expense ratio",
                "Value": format_value(
                    info.get("annualReportExpenseRatio"),
                    "percent",
                ),
            },
            {
                "Field": "Dividend yield",
                "Value": format_value(info.get("yield"), "percent"),
            },
        ]
        st.dataframe(pd.DataFrame(details), hide_index=True, width="stretch")
    with queue_tab:
        queue_columns = ["Symbol", "Fund", "Category"]
        if universe in {"Industry exposures", "Full GICS hierarchy"}:
            queue_columns.append("Parent sector")
        if universe == "Full GICS hierarchy":
            queue_columns.extend(
                ["Industry group", "Industry", "Taxonomy code", "Proxy level"]
            )
        queue_columns.extend(["Market group", "Region"])
        st.dataframe(
            pd.DataFrame(visible).loc[:, queue_columns],
            hide_index=True,
            width="stretch",
        )

    st.caption(
        "GICS defines the 11 sector buckets. Industry exposures are investable "
        "proxies aligned to parts of the GICS hierarchy; they are not exhaustive "
        "or exact replications, and available funds skew toward the US. "
        "Country market groups follow the "
        "developed/emerging/frontier convention used by major index providers. "
        "ETFs are investable proxies, not the complete local market. IBKR access "
        "depends on residence, account permissions, exchange access, and product rules."
    )


def render_infrastructure_coverage(companies: list[dict]) -> None:
    st.metric("Researched candidates in scope", len(companies))
    st.info(
        "This view shows the researched universe before financial filters and "
        "does not fetch market data. A missing dividend or failed yield test "
        "does not remove a company from this coverage view."
    )
    st.markdown(f"[Official IBKR venue list]({IBKR_EXCHANGE_SOURCE})")
    if companies:
        st.dataframe(
            pd.DataFrame(companies).rename(columns={
                "MarketStructure": "Monopoly / oligopoly evidence",
                "Source": "Evidence source", "ListingMarket": "Listing market",
                "IBKRExchange": "IBKR venue code", "AccessStatus": "Venue access",
                "AccessNote": "Access limitation", "AccessSource": "Access source",
            }),
            column_config={
                "Evidence source": st.column_config.LinkColumn("Evidence source"),
                "Access source": st.column_config.LinkColumn("Access source"),
            },
            hide_index=True, width="stretch",
        )
    else:
        st.info("No infrastructure companies match the selected scope.")
    with st.expander("Access, data and business-review gaps"):
        st.caption(
            "Global research log, independent of the region filter. These are "
            "not failed financial screens. Local symbols are not necessarily "
            "Yahoo symbols. Absence from the published venue list is not proof "
            "that no IBKR entity can ever offer access."
        )
        st.dataframe(
            pd.DataFrame(INFRASTRUCTURE_RESEARCH_GAPS),
            column_config={"Source": st.column_config.LinkColumn("Source")},
            hide_index=True, width="stretch",
        )


def load_infrastructure_income(companies: list[dict]) -> tuple[list[dict], list[dict]]:
    screened = [company for company in companies if company["AccessStatus"] != "Unverified venue"]
    if not screened:
        return [], []

    def load_company(company: dict) -> dict:
        info = cached_info(company["Symbol"])
        history = cached_history(company["Symbol"], "5y", "1d")
        price_dates = history.index[history["Close"].notna()]
        price_date = (
            str(price_dates[-1].date())
            if isinstance(price_dates, pd.DatetimeIndex) and len(price_dates) else None
        )
        return {
            **company, **analyze_infrastructure_income(info, history),
            "InfrastructurePriceDate": price_date,
            "InfrastructureCurrency": info.get("currency"),
        }

    rows, errors = {}, {}
    progress = st.progress(0, text=f"Loading 0 / {len(screened)} infrastructure companies")
    with ThreadPoolExecutor(max_workers=min(8, len(screened))) as executor:
        futures = {executor.submit(load_company, company): company["Symbol"] for company in screened}
        for completed, future in enumerate(as_completed(futures), start=1):
            symbol = futures[future]
            try:
                rows[symbol] = future.result()
            except StockDataError as exc:
                errors[symbol] = {"Symbol": symbol, "Error": str(exc)}
            progress.progress(
                completed / len(screened),
                text=f"Loading {completed} / {len(screened)} infrastructure companies",
            )
    progress.empty()
    return (
        [rows[company["Symbol"]] for company in screened if company["Symbol"] in rows],
        [errors[company["Symbol"]] for company in screened if company["Symbol"] in errors],
    )


def render_infrastructure_income_strategy() -> None:
    render_page_header("Infrastructure Income Strategy", "infrastructure")
    st.caption(
        "Globally listed monopoly-like infrastructure assets screened for forward dividend yield "
        "above 4%, dividend payout of at most 80%, and a price at least 5% below "
        "its five-year high."
    )
    st.caption(
        f"Venue-access research: {RESEARCH_AS_OF}. This is a source-researched "
        "catalog, not an exhaustive inventory of every IBKR contract. Research "
        "regions describe business exposure, not formal MSCI/FTSE classifications. "
        "Supported venue does not guarantee account-specific stock or ADR access."
    )
    with st.sidebar:
        infrastructure_view = st.selectbox(
            "Infrastructure view", ("Income screen", "Research coverage")
        )
        region_options = ("All regions",) + tuple(
            sorted({company["Region"] for company in INFRASTRUCTURE_COMPANIES})
        )
        region = st.selectbox("Infrastructure region", region_options)
        show_all = st.checkbox("Show companies that fail financial criteria")
    companies = [
        {**company, **infrastructure_listing_details(company["Symbol"])}
        for company in INFRASTRUCTURE_COMPANIES
        if region == "All regions" or company["Region"] == region
    ]
    if infrastructure_view == "Research coverage":
        render_infrastructure_coverage(companies)
        return
    unverified = [
        company for company in companies if company["AccessStatus"] == "Unverified venue"
    ]
    if unverified:
        st.warning(
            f"{len(unverified)} researched listings in this region have unverified "
            "IBKR venue access and are not financially screened: "
            + ", ".join(company["Symbol"] for company in unverified)
            + ". See Research coverage for details."
        )
    companies = [
        company for company in companies if company["AccessStatus"] != "Unverified venue"
    ]
    if any(company["AccessStatus"] == "Restricted venue" for company in companies):
        st.info(
            "Indian listings are included as restricted-venue research, not as "
            "generally accessible foreign-retail investments. IBKR's stock "
            "schedule restricts NSE stocks to Indian residents; confirm eligibility."
        )
    if not companies:
        st.info("No infrastructure companies match the selected scope.")
        return
    with st.spinner(
        "Applying income criteria with 24-hour cached market data "
        "(fetches only missing or expired entries)..."
    ):
        rows, errors = load_infrastructure_income(companies)
    unavailable = [f"{error['Symbol']}: {error['Error']}" for error in errors]
    results = pd.DataFrame(rows)
    qualified_count = int(results["Qualifies"].sum()) if not results.empty else 0
    qualification_metric, availability_metric = st.columns(2)
    qualification_metric.metric(
        "Qualifying income candidates",
        f"{qualified_count} / {len(companies)}",
    )
    availability_metric.metric(
        "Market data loaded",
        f"{len(results)} / {len(companies)}",
    )
    if results.empty:
        st.info("No infrastructure candidates have complete market data.")
        if unavailable:
            st.warning("Unavailable: " + " | ".join(unavailable))
        return
    if not show_all:
        results = results.loc[results["Qualifies"]].copy()
    if results.empty:
        st.info("No companies currently meet every income criterion.")
    else:
        display = results.copy()
        display["DividendYield"] = display["DividendYield"].map(
            lambda value: f"{value:.2f}%" if pd.notna(value) else "N/A"
        )
        display["DividendCoverageRatio"] = display["DividendCoverageRatio"].map(
            lambda value: f"{value:.1%}" if pd.notna(value) else "N/A"
        )
        display["DistanceToFiveYearHigh"] = display["DistanceToFiveYearHigh"].map(
            lambda value: f"{value:.1%}"
        )
        st.dataframe(
            display[
                [
                    "Symbol",
                    "Name",
                    "Region",
                    "ListingMarket",
                    "AccessStatus",
                    "AccessNote",
                    "Type",
                    "DividendYield",
                    "DividendCoverageRatio",
                    "CoverageBasis",
                    "DistanceToFiveYearHigh",
                    "MarketStructure",
                    "Source",
                    "Qualifies",
                    "ExclusionReason",
                ]
            ].rename(
                columns={
                    "DividendYield": "Forward yield",
                    "DividendCoverageRatio": "Payout / coverage",
                    "CoverageBasis": "Coverage basis",
                    "DistanceToFiveYearHigh": "Below 5-year high",
                    "MarketStructure": "Monopoly / oligopoly evidence",
                    "Source": "Evidence source",
                    "ExclusionReason": "Why excluded",
                    "ListingMarket": "Listing market",
                    "AccessStatus": "Venue access",
                    "AccessNote": "Access limitation",
                }
            ),
            column_config={
                "Evidence source": st.column_config.LinkColumn("Evidence source"),
                "Qualifies": st.column_config.CheckboxColumn("Qualifies"),
            },
            hide_index=True,
            width="stretch",
        )
    if unavailable:
        with st.expander(f"Unavailable market data ({len(unavailable)})"):
            for message in unavailable:
                st.write(message)
    st.caption(
        "The monopoly/oligopoly universe is evidence-curated; the income metrics are "
        "provider-reported and refreshed through the 24-hour cache. Five-year high "
        "is a practical price-cycle proxy, not a literal lifetime all-time high."
    )
    if not results.empty:
        render_strategy_candidate_research(results, "infrastructure", "Infrastructure income candidates")


def render_fashion_trend_strategy() -> None:
    render_page_header("Out-of-Fashion Short Strategy", "fashion")
    st.caption(
        "Short-only research screen for brands losing consumer attention before the "
        "decline appears in reported revenue. A company qualifies when at least two "
        "available sources show a meaningful attention decline, its latest close is "
        "below its 200-day moving average, and its 50-day average is below its "
        "200-day average."
    )
    company_map = {company["Symbol"]: company for company in FASHION_COMPANIES}
    with st.sidebar:
        region = st.selectbox("Fashion region", ("Europe and US", "Europe", "US"))
        eligible_symbols = [
            symbol
            for symbol, company in company_map.items()
            if region == "Europe and US" or company["Region"] == region
        ]
        selected_symbols = st.multiselect(
            "Brands to compare (maximum 5)",
            eligible_symbols,
            default=eligible_symbols[:5],
            format_func=lambda symbol: f"{symbol} — {company_map[symbol]['Name']}",
        )
    if not selected_symbols:
        st.info("Select at least one fashion company.")
        return
    if len(selected_symbols) > 5:
        st.error("Select no more than five brands per comparison.")
        return

    rows = []
    source_errors = set()
    price_errors = []
    with st.spinner(
        "Loading attention signals from the 24-hour cache "
        "(Google Trends is paced; rate-limit retries can take several minutes)..."
    ):
        for symbol in selected_symbols:
            company = company_map[symbol]
            term = company["SearchTerm"]
            google = cached_google_trends_signal(term)
            reddit = cached_reddit_mention_signal(term)
            news = cached_news_volume_signal(term)
            summary = summarize_fashion_signals(google, reddit, news)
            try:
                downtrend = analyze_fashion_downtrend(
                    cached_history(symbol, "1y", "1d")
                )
            except StockDataError as exc:
                downtrend = {
                    "LatestClose": None,
                    "MA50": None,
                    "MA200": None,
                    "BelowMA200": False,
                    "MA50BelowMA200": False,
                    "DowntrendQualifies": False,
                }
                price_errors.append(f"{symbol}: {exc}")
            for signal in (google, reddit, news):
                if not signal.get("Available") and signal.get("Reason"):
                    source_errors.add(signal["Reason"])
            rows.append(
                {
                    **company,
                    "GoogleMomentum": google.get("Momentum"),
                    "GoogleInterest": google.get("CurrentInterest"),
                    "GooglePreviousInterest": google.get("PreviousInterest"),
                    "RedditMomentum": reddit.get("Momentum"),
                    "RedditMentions": reddit.get("RecentCount"),
                    "RedditPreviousMentions": reddit.get("PreviousCount"),
                    "NewsMomentum": news.get("Momentum"),
                    "NewsMentions": news.get("RecentCount"),
                    "NewsPreviousMentions": news.get("PreviousCount"),
                    **summary,
                    **downtrend,
                    "AttentionQualifies": summary["Qualifies"],
                    "Qualifies": (
                        summary["Qualifies"]
                        and downtrend["DowntrendQualifies"]
                    ),
                }
            )
    results = pd.DataFrame(rows).sort_values(
        ["Qualifies", "SignalCount"],
        ascending=[False, False],
    )
    display = results.copy()
    for column in ("GoogleMomentum", "RedditMomentum", "NewsMomentum"):
        display[column] = display[column].map(
            lambda value: f"{value:+.1%}" if pd.notna(value) else "N/A"
        )
    display["GoogleInterest"] = display["GoogleInterest"].map(
        lambda value: f"{value:.1f}" if pd.notna(value) else "N/A"
    )
    for column in ("RedditMentions", "NewsMentions"):
        display[column] = display[column].map(
            lambda value: f"{int(value)}" if pd.notna(value) else "N/A"
        )
    for column in ("LatestClose", "MA50", "MA200"):
        display[column] = display[column].map(
            lambda value: f"{value:,.2f}" if pd.notna(value) else "N/A"
        )
    st.dataframe(
        display[
            [
                "Symbol",
                "Name",
                "Region",
                "SearchTerm",
                "GoogleInterest",
                "GoogleMomentum",
                "RedditMentions",
                "RedditMomentum",
                "NewsMentions",
                "NewsMomentum",
                "DecliningSources",
                "LatestClose",
                "MA50",
                "MA200",
                "BelowMA200",
                "MA50BelowMA200",
                "AttentionQualifies",
                "Qualifies",
            ]
        ].rename(
            columns={
                "SearchTerm": "Tracked brand term",
                "GoogleInterest": "Google interest",
                "GoogleMomentum": "Google 4-week change",
                "RedditMentions": "Reddit mentions (30d)",
                "RedditMomentum": "Reddit monthly pace change",
                "NewsMentions": "News items (30d)",
                "NewsMomentum": "News monthly pace change",
                "DecliningSources": "Declining sources",
                "LatestClose": "Latest close",
                "MA50": "50-day average",
                "MA200": "200-day average",
                "BelowMA200": "Close below 200-day",
                "MA50BelowMA200": "50-day below 200-day",
                "AttentionQualifies": "Attention decline",
                "Qualifies": "Short candidate",
            }
        ),
        hide_index=True,
        width="stretch",
    )
    for error in sorted(source_errors):
        st.warning(error)
    if price_errors:
        with st.expander(f"Unavailable downtrend analysis ({len(price_errors)})"):
            for error in price_errors:
                st.warning(error)
    st.caption(
        "Decline thresholds: Google prior-period interest >=10 and down >=20%; "
        "Reddit or news prior monthly pace >=3 mentions and current pace down >=25%. "
        "At least two independent declining sources are required. The chart must also "
        "have the latest daily close below its 200-day average and the 50-day average "
        "below the 200-day average. Signals measure attention and price trend, not "
        "sentiment, sales deterioration, valuation, borrow availability, or investment "
        "quality."
    )
    st.warning(
        "Short selling can produce unlimited losses and may involve borrow fees, recalls, "
        "and squeezes. Treat matches as research leads, not trade recommendations."
    )
    short_candidates = results.loc[results["Qualifies"]].copy()
    downtrend_stocks = results.loc[results["DowntrendQualifies"]].copy()
    if short_candidates.empty:
        st.info(
            "No selected companies currently meet the out-of-fashion short screen. "
            "You can still browse selected companies that pass the chart-downtrend "
            "rules below."
        )
    else:
        st.success(
            f"{len(short_candidates)} of {len(results)} scanned companies currently "
            "meet the complete short screen."
        )
    if downtrend_stocks.empty:
        st.info(
            "None of the selected companies currently have both a close below the "
            "200-day average and a 50-day average below the 200-day average. Select "
            "other brands or refresh the data."
        )
        return
    st.subheader("Browse downtrending fashion stocks")
    st.caption(
        "Every stock in this browser passes both chart-downtrend rules. Some may not "
        "pass the separate attention-decline requirement; check the Attention decline "
        "and Short candidate columns above."
    )
    render_strategy_candidate_research(
        downtrend_stocks,
        "fashion",
        "Fashion chart-downtrend scan",
        browse=True,
    )


def step_star_candidate(symbols: list[str], direction: int) -> None:
    current = st.session_state.get("star_symbol")
    index = symbols.index(current) if current in symbols else 0
    st.session_state["star_symbol"] = symbols[(index + direction) % len(symbols)]


def render_star_principle_strategy() -> None:
    render_page_header("Richard Koch Star Principle", "star")
    st.caption(
        "Strict screen: the company must be the documented leader in a precisely "
        "defined niche whose market is documented to grow at least 10% annually."
    )
    st.caption(
        "Refresh reloads market data and the selected listing universe. Leadership and "
        "niche-growth assessments are curated research: their evidence dates and review "
        "statuses do not change unless the underlying research is updated."
    )
    with st.sidebar:
        universe = st.selectbox(
            "Star universe", ("Reviewed shortlist", "US and European stock universe"),
        )
        region = st.selectbox("Star region", ("Europe and US", "Europe", "US"))
        status = st.selectbox(
            "Evidence status",
            ("All", "Evidence-qualified", "Near miss", "Does not meet",
             "Insufficient evidence", "Unreviewed"),
        )
    reviews = star_principle_catalog()
    if universe == "Reviewed shortlist":
        all_rows = reviews
        st.caption(
            "A source-reviewed shortlist, not an exhaustive US, European or IBKR evaluation. "
            "Historical niche growth and forecast CAGR are identified separately in the evidence."
        )
    else:
        try:
            with st.spinner("Loading the US and European stock universe from the 24-hour cache..."):
                holdings = []
                for loader, listing_region in (
                    (cached_sp500_holdings, "US"),
                    (cached_russell_holdings, "US"),
                    (cached_european_holdings, "Europe"),
                ):
                    holdings.extend(
                        {"Symbol": row.Symbol, "Name": row.Name, "Region": listing_region}
                        for row in loader().itertuples(index=False)
                    )
        except StockDataError as exc:
            st.error(str(exc))
            return
        all_rows = build_star_research_universe(holdings, reviews)
        st.caption(
            "Listing-level union of S&P 500, Russell 2000 and IEUR holdings, not all IBKR "
            "stocks or a guarantee of account-specific tradability. Loading this universe "
            "does not evaluate it: unreviewed stocks are explicitly marked."
        )
    counts = st.columns(3)
    counts[0].metric("Stocks in this universe", len(all_rows))
    counts[1].metric("Source-reviewed", sum(row["ReviewStatus"] != "Unreviewed" for row in all_rows))
    counts[2].metric("Evidence-qualified stars", sum(row["ReviewStatus"] == "Evidence-qualified" for row in all_rows))
    rows = [
        row for row in all_rows
        if (region == "Europe and US" or row["Region"] == region)
        and (status == "All" or row["ReviewStatus"] == status)
    ]
    if not rows:
        st.info("No stocks match these region and evidence-status filters.")
        return
    symbols = [row["Symbol"] for row in rows]
    by_symbol = {row["Symbol"]: row for row in rows}
    with st.sidebar:
        if st.session_state.get("star_symbol") not in symbols:
            st.session_state["star_symbol"] = symbols[0]
        symbol = st.selectbox(
            "Star candidate", symbols, key="star_symbol",
            format_func=lambda value: f"{value} - {by_symbol[value]['Name']}",
        )
        previous, position, following = st.columns([1, 2, 1])
        previous.button(
            "Previous", key="star_previous", on_click=step_star_candidate,
            args=(symbols, -1), disabled=len(symbols) == 1,
        )
        position.write(f"{symbols.index(symbol) + 1} / {len(symbols)}")
        following.button(
            "Next", key="star_next", on_click=step_star_candidate,
            args=(symbols, 1), disabled=len(symbols) == 1,
        )
    display = pd.DataFrame(rows)
    display["GrowthRate"] = display["GrowthRate"].map(
        lambda value: f"{value:.1%}" if pd.notna(value) else "Not established"
    )
    st.dataframe(
        display[
            [
                "Symbol",
                "Name",
                "Region",
                "ReviewStatus",
                "Niche",
                "LeadershipEvidence",
                "LeadershipSource",
                "GrowthEvidence",
                "GrowthRate",
                "GrowthPeriod",
                "GrowthSource",
                "EvidenceAsOf",
                "MissingEvidence",
            ]
        ].rename(
            columns={
                "LeadershipEvidence": "Market-leadership evidence",
                "LeadershipSource": "Leadership source",
                "GrowthRate": "Niche growth",
                "GrowthPeriod": "Growth period",
                "GrowthSource": "Growth source",
                "EvidenceAsOf": "Evidence checked",
                "ReviewStatus": "Evidence status",
                "GrowthEvidence": "Niche-growth evidence",
                "MissingEvidence": "Limitations / why not qualified",
            }
        ),
        column_config={
            "Leadership source": st.column_config.LinkColumn("Leadership source"),
            "Growth source": st.column_config.LinkColumn("Growth source"),
        },
        column_order=["Symbol", "Name", "Region", "Evidence status", "Niche", "Niche growth", "Evidence checked"],
        height=min(300, 38 + 35 * len(display)),
        hide_index=True,
        width="stretch",
    )
    selected = by_symbol[symbol]
    st.subheader(f"{selected['Name']} ({symbol})")
    st.write(f"**Evidence status:** {selected['ReviewStatus']}")
    if selected["Niche"]:
        st.write(f"**Defined niche:** {selected['Niche']}")
    if selected["MissingEvidence"]:
        st.info(selected["MissingEvidence"])
    with st.expander("Leadership and growth evidence"):
        leadership, growth = st.columns(2)
        for column, title, text_field, source_field in (
            (leadership, "Niche leadership", "LeadershipEvidence", "LeadershipSource"),
            (growth, "Niche growth", "GrowthEvidence", "GrowthSource"),
        ):
            with column:
                st.markdown(f"**{title}**")
                st.write(selected[text_field] or "Not established.")
                if selected[source_field]:
                    st.link_button(f"{title} source", selected[source_field])
        st.caption(f"{selected['GrowthPeriod']} | Evidence checked: {selected['EvidenceAsOf']}")
    render_bookmark_button(symbol, selected["Name"])
    st.button(
        "Open in Individual Stocks", type="primary", on_click=open_stock_research,
        args=(symbol, symbols, "Star Principle candidates"),
    )
    try:
        history = cached_history(symbol, "5y", "1d")
    except StockDataError as exc:
        st.warning(f"Price history is unavailable; evidence and bookmark controls remain available. {exc}")
        render_stock_assistant(symbol, selected["Name"], {}, pd.DataFrame(), selected)
        return
    try:
        info = cached_info(symbol)
    except StockDataError as exc:
        info = {}
        st.warning(f"Company metadata is unavailable; the chart is still shown. {exc}")
    render_overview(info, history)
    render_chart_and_assistant(symbol, selected["Name"], info, history, selected)
    with st.expander("How Star Principle evaluation works"):
        st.write(
            "Requires clear niche leadership and at least 10% annual growth in that exact "
            "niche. Company revenue growth, adjacent markets and qualitative leader claims "
            "are not substitutes. Forecasts are expectations, not realized growth. "
            "A chart is provided for research, not used to qualify a company as a star. "
            "Unreviewed means no assessment yet, not a failure. Evidence can become stale."
        )
    render_company_news(symbol, selected["Name"])


def step_adr_candidate(symbols: list[str], direction: int) -> None:
    current = st.session_state.get("adr_symbol")
    index = symbols.index(current) if current in symbols else 0
    st.session_state["adr_symbol"] = symbols[(index + direction) % len(symbols)]


def render_adr_dividend_strategy() -> None:
    render_page_header("ADR dividend yield", "adr")
    st.caption(
        "Live trailing-12-month cash dividend yields for the same 100 NYSE/Nasdaq "
        "ADR/ADS securities researched in the ADR screen. Highest yields first; "
        "the top 50 are shown by default."
    )
    st.caption(
        f"Universe and business research: {ADR_RESEARCH_AS_OF}. This is a fixed, "
        "non-exhaustive research universe, not an automatically updated ADR directory "
        "or a guarantee of broker availability. PBR and PBR.A are separate share "
        "classes of the same company."
    )
    st.warning(
        "Historical cash yields are not forecasts or guaranteed income. Special and "
        "irregular payouts are included. Provider ADR cash amounts may already reflect "
        "foreign withholding or depositary deductions; these are not uniformly gross "
        "yields or your personal after-tax returns."
    )
    with st.expander("ADR yield methodology and sources"):
        st.write(
            "Live source: Yahoo Finance via yfinance, not the saved yield figures. "
            "Sum recorded USD dividends with ex-dates after the price date minus one "
            "calendar year and on or before the price date, then divide by that day's "
            "closing price and multiply by 100. Payment dates and forward annualized "
            "dividends are not used. Provider split-adjusted historical cash amounts "
            "and Close are used without dividend-adjusting the price."
        )
        st.write(
            "Today's New York calendar day is excluded to avoid incomplete daily bars. "
            "Each row shows its price date and dividend window. Quotes over seven "
            "calendar days old, incomplete histories, missing dividends, non-USD quotes "
            "and unsupported exchanges are unavailable, never zero-yield substitutes. "
            "A valid history with no payouts has a 0% yield; provider omissions can "
            "still occur. Different price dates can affect comparisons."
        )
        st.write(
            "Requests use the platform's 24-hour cache. Refresh data above, or Refresh "
            "all cached data in the sidebar, forces a reload anytime. "
            "Retry unavailable ADRs retries failures without clearing successful "
            "per-security requests. The original research links and dated notes are "
            "provided for context, not as current live dividend evidence."
        )
        st.markdown(
            "[NYSE listing directory](https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt) "
            "| [Nasdaq listing directory](https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt)"
        )
    try:
        catalog = adr_catalog()
    except StockDataError as exc:
        st.error(str(exc))
        return
    with st.sidebar:
        country = st.selectbox(
            "ADR country / main market",
            ["All countries"] + sorted(catalog["Country"].unique().tolist()),
            key="adr_country",
        )
        minimum_yield = st.number_input(
            "Minimum TTM yield (%)", min_value=0.0, value=0.0, step=0.5,
            key="adr_minimum_yield",
        )
        result_limit = st.selectbox(
            "Maximum ADR results", (25, 50, 100), index=1, key="adr_result_limit",
        )
    as_of = pd.Timestamp.now(tz="America/New_York").date().isoformat()
    with st.spinner("Loading ADR prices and dividends (24-hour cache; up to 100 securities)..."):
        rows, errors = cached_adr_scan(tuple(catalog["Symbol"]), as_of)
    if errors:
        st.warning(
            f"{len(errors)} / {len(catalog)} ADRs have unavailable market data. "
            "The ranking covers available securities only and may omit higher yields."
        )
        with st.expander(f"Unavailable ADRs ({len(errors)})"):
            unavailable = catalog[["Ticker", "Symbol", "Name"]].merge(
                pd.DataFrame(errors), on="Symbol", validate="one_to_one",
            )
            st.dataframe(unavailable, hide_index=True, width="stretch")
            if st.button("Retry unavailable ADRs", key="adr_retry"):
                cached_adr_scan.clear()
                st.rerun()
    available_metric, paying_metric, shown_metric = st.columns(3)
    available_metric.metric("ADRs with live data", f"{len(rows)} / {len(catalog)}")
    if not rows:
        paying_metric.metric("ADRs with TTM payouts", 0)
        shown_metric.metric("ADRs shown", 0)
        st.info("No ADRs have complete market data. See the unavailable reasons and retry.")
        return
    results = catalog.merge(pd.DataFrame(rows), on="Symbol", validate="one_to_one")
    paying_metric.metric("ADRs with TTM payouts", int((results["TTMCash"] > 0).sum()))
    filtered = results.loc[results["YieldPercent"] >= minimum_yield]
    if country != "All countries":
        filtered = filtered.loc[filtered["Country"] == country]
    filtered = filtered.sort_values(
        ["YieldPercent", "Ticker"], ascending=[False, True],
    ).head(result_limit).reset_index(drop=True)
    shown_metric.metric("ADRs shown", len(filtered))
    st.caption(
        f"Price dates: {results['PriceDate'].min()} to {results['PriceDate'].max()} | "
        f"Fetched (UTC): {results['FetchedAt'].min()} to {results['FetchedAt'].max()}."
    )
    if results["PriceDate"].nunique() > 1:
        st.warning("Available quotes have different price dates; compare the per-row dates.")
    if filtered.empty:
        st.info("No ADRs match the selected country and minimum yield.")
        return
    display = filtered.rename(columns={
        "Symbol": "Yahoo symbol", "Name": "Company", "Overview": "Business overview",
        "YieldPercent": "TTM yield (%)", "Price": "Close (USD)",
        "TTMCash": "TTM cash / ADR (USD)", "PriceDate": "Price date",
        "WindowStart": "Window start (exclusive)", "DividendCount": "Ex-date count",
        "LastExDate": "Last TTM ex-date", "FetchedAt": "Fetched (UTC)",
        "LiveSource": "Live dividend history", "ResearchSource": "Original research source",
        "ResearchNotes": f"Research notes ({ADR_RESEARCH_AS_OF})",
    })
    display.insert(0, "Rank", range(1, len(display) + 1))
    columns = [
        "Rank", "Ticker", "Company", "Country", "TTM yield (%)", "Business overview",
        "Close (USD)", "TTM cash / ADR (USD)", "Price date", "Window start (exclusive)",
        "Ex-date count", "Last TTM ex-date", f"Research notes ({ADR_RESEARCH_AS_OF})",
        "Live dividend history", "Original research source", "Yahoo symbol", "Fetched (UTC)",
    ]
    display = display[columns]
    st.dataframe(
        display, hide_index=True, width="stretch",
        column_config={
            "TTM yield (%)": st.column_config.NumberColumn(format="%.2f%%"),
            "Close (USD)": st.column_config.NumberColumn(format="$%.4f"),
            "TTM cash / ADR (USD)": st.column_config.NumberColumn(format="$%.5f"),
            "Business overview": st.column_config.TextColumn(width="large"),
            "Live dividend history": st.column_config.LinkColumn(),
            "Original research source": st.column_config.LinkColumn(),
        },
    )
    st.download_button(
        "Download ADR results (CSV)", data=display.to_csv(index=False).encode("utf-8"),
        file_name=f"adr-dividend-yield-{as_of}.csv", mime="text/csv", key="adr_download",
    )
    symbols = filtered["Symbol"].tolist()
    by_symbol = filtered.set_index("Symbol").to_dict("index")
    with st.sidebar:
        if st.session_state.get("adr_symbol") not in symbols:
            st.session_state["adr_symbol"] = symbols[0]
        symbol = st.selectbox(
            "ADR candidate", symbols, key="adr_symbol",
            format_func=lambda value: f"{by_symbol[value]['Ticker']} - {by_symbol[value]['Name']}",
        )
        previous, position, following = st.columns([1, 2, 1])
        previous.button(
            "Previous", key="adr_previous", on_click=step_adr_candidate,
            args=(symbols, -1), disabled=len(symbols) == 1,
        )
        position.write(f"{symbols.index(symbol) + 1} / {len(symbols)}")
        following.button(
            "Next", key="adr_next", on_click=step_adr_candidate,
            args=(symbols, 1), disabled=len(symbols) == 1,
        )
    selected = by_symbol[symbol]
    st.subheader(f"{selected['Name']} ({selected['Ticker']})")
    st.write(selected["Overview"])
    st.caption(f"Research note ({ADR_RESEARCH_AS_OF}): {selected['ResearchNotes']}")
    render_bookmark_button(symbol, selected["Name"])
    st.button(
        "Open in Individual Stocks", type="primary", key="adr_open_research",
        on_click=open_stock_research, args=(symbol, symbols, "ADR dividend yield candidates"),
    )
    chart_column, assistant_column = st.columns([2.2, 1], gap="large")
    history = pd.DataFrame()
    with chart_column:
        if st.checkbox("Show selected ADR chart", key="adr_show_chart"):
            try:
                history = cached_history(symbol, "5y", "1d")
            except StockDataError as exc:
                st.warning(f"Price chart unavailable; ADR results and research controls remain available. {exc}")
            else:
                st.plotly_chart(
                    price_chart(history, symbol, "Line"), width="stretch",
                    config={"displaylogo": False},
                )
    with assistant_column:
        render_stock_assistant(symbol, selected["Name"], {}, history, selected)


def render_income_methodology() -> None:
    st.caption(
        "One row per Yahoo listing; a listing can belong to both strategies. Different "
        "share classes and ordinary-share/ADR listings remain separate. Forward and "
        "historical yields are not interchangeable, so no blended yield or combined score is used."
    )
    with st.expander("Income strategy rules, yield bases & sources"):
        st.markdown("**Infrastructure income**")
        st.write(
            "The existing source-curated monopoly/oligopoly universe requires provider-reported "
            "forward yield >4%, earnings payout (or dividend/free-cash-flow coverage fallback) "
            "<=80%, and price at least 5% below its five-year high. The five-year high is a "
            "cycle proxy, not a lifetime high. Missing required metrics do not pass."
        )
        st.caption(
            f"Infrastructure venue research: {RESEARCH_AS_OF}. Unverified venues are not "
            "financially screened. Restricted Indian venues remain research-only unless "
            "you meet IBKR eligibility; supported venues never guarantee account-specific access."
        )
        st.markdown(f"[Official IBKR venue list]({IBKR_EXCHANGE_SOURCE})")
        st.markdown("**ADR dividend yield**")
        st.write(
            "The fixed 100-security NYSE/Nasdaq ADR universe retains its historical cash-yield "
            "method: sum recorded USD dividends with ex-dates after the price date minus one "
            "calendar year and through the price date, divide by that day's Close, multiply "
            "by 100. Provider split-adjusted cash and Close are used without dividend-adjusting "
            "the price. Today's New York calendar day is excluded. This is not a forward yield."
        )
        st.write(
            "Complete history without payouts is a valid 0% yield. Missing dividends, incomplete "
            "history, unsupported exchanges, non-USD quotes and quotes older than seven days "
            "are unavailable, not zero. ADR inclusion does not imply passing infrastructure rules."
        )
        st.caption(
            f"ADR business research: {ADR_RESEARCH_AS_OF}. Neither catalog is exhaustive or "
            "automatically researched on refresh. Special/irregular dividends are included; "
            "cash amounts may reflect foreign withholding or depositary deductions and are "
            "not uniformly gross or your personal after-tax yield."
        )
        st.write(
            "The union includes a stock when either selected strategy admits it. Infrastructure "
            "region and excluded-row controls apply only to infrastructure; ADR country and "
            "minimum TTM yield apply only to ADRs. Sorting by one yield leaves the other "
            "strategy's missing values last; the default company order avoids comparing unlike yields."
        )
        st.caption(
            "Normal data caching remains 24 hours. Refresh data fetches again anytime. "
            "Retry unavailable ADRs retains successfully cached per-security requests."
        )


def step_income_candidate(symbols: list[str], direction: int) -> None:
    current = st.session_state.get("income_symbol")
    index = symbols.index(current) if current in symbols else 0
    st.session_state["income_symbol"] = symbols[(index + direction) % len(symbols)]


def render_income_candidate(results: pd.DataFrame) -> None:
    symbols = results["Symbol"].tolist()
    by_symbol = results.set_index("Symbol").to_dict("index")
    if st.session_state.get("income_symbol") not in symbols:
        st.session_state["income_symbol"] = symbols[0]
    with st.sidebar:
        symbol = st.selectbox(
            "Income candidate", symbols, key="income_symbol",
            format_func=lambda value: f"{by_symbol[value]['Ticker']} - {by_symbol[value]['Name']}",
        )
        previous, position, following = st.columns([1, 2, 1])
        previous.button(
            "Previous", key="income_previous", on_click=step_income_candidate,
            args=(symbols, -1), disabled=len(symbols) == 1,
        )
        position.write(f"{symbols.index(symbol) + 1} / {len(symbols)}")
        following.button(
            "Next", key="income_next", on_click=step_income_candidate,
            args=(symbols, 1), disabled=len(symbols) == 1,
        )
    selected = by_symbol[symbol]
    st.subheader(f"{selected['Name']} ({selected['Ticker']})")
    st.caption(f"Included via: {selected['IncomeIncludedVia']}")
    if selected["ADRMember"]:
        st.write(selected["Overview"])
        st.caption(f"ADR research note ({ADR_RESEARCH_AS_OF}): {selected['ResearchNotes']}")
        st.write(f"ADR data status: **{selected['ADRStatus']}**")
        if pd.notna(selected["ADRYieldPercent"]):
            st.metric("ADR TTM yield", f"{selected['ADRYieldPercent']:.2f}%")
            st.caption(
                f"ADR window: ({selected['WindowStart']}, {selected['PriceDate']}] | "
                f"Fetched (UTC): {selected['FetchedAt']} | Cash and price in USD."
            )
        if selected["ADRReason"]:
            st.warning(selected["ADRReason"])
    if selected["InfrastructureMember"]:
        st.write(f"Infrastructure screen: **{selected['InfrastructureStatus']}**")
        if pd.notna(selected["InfrastructureYieldPercent"]):
            st.metric("Infrastructure forward yield", f"{selected['InfrastructureYieldPercent']:.2f}%")
            st.caption(
                f"Price date: {selected['InfrastructurePriceDate']} | "
                f"Quote currency: {selected['InfrastructureCurrency']} | "
                f"Payout / coverage: {format_value(selected['DividendCoverageRatio'], 'percent')} "
                f"({selected['CoverageBasis']})"
            )
        st.write(selected["MarketStructure"])
        st.caption(
            f"{selected['Region']} | {selected['Type']} | "
            f"Venue: {selected['AccessStatus']}. {selected['AccessNote']}"
        )
        if selected["InfrastructureReason"]:
            st.info(selected["InfrastructureReason"])
    with st.expander("Selected listing: comparison values and evidence"):
        st.dataframe(
            pd.DataFrame([{"Field": field, "Value": str(value) if pd.notna(value) else "Unavailable"}
                          for field, value in selected.items()]),
            hide_index=True, width="stretch",
        )
        for field, label in (
            ("Source", "Infrastructure business evidence"), ("AccessSource", "Venue access source"),
            ("LiveSource", "ADR dividend history"), ("ResearchSource", "ADR business research"),
        ):
            value = selected.get(field)
            if isinstance(value, str) and value.startswith(("https://", "http://")):
                st.link_button(label, value)
    actions = st.columns([1, 2, 2])
    with actions[0]:
        render_bookmark_button(symbol, selected["Name"])
    with actions[1]:
        st.button(
            "Open in Individual Stocks", type="primary", key="income_open_research",
            on_click=open_stock_research, args=(symbol, symbols, "Income strategy candidates"),
        )
    with actions[2]:
        show_chart = st.checkbox("Show selected income chart", value=True, key="income_show_chart")
    history = pd.DataFrame()
    info = {}
    if show_chart:
        try:
            history = cached_history(symbol, "5y", "1d")
        except StockDataError as exc:
            st.warning(f"Price chart unavailable; income results and research remain available. {exc}")
        if not history.empty:
            try:
                info = cached_info(symbol)
            except StockDataError as exc:
                st.warning(f"Company metadata unavailable; the chart remains available. {exc}")
            render_chart_and_assistant(symbol, selected["Name"], info, history, selected)
            return
    render_stock_assistant(symbol, selected["Name"], info, history, selected)


def render_income_strategy() -> None:
    from income_strategy import build_income_candidates, filter_income_candidates

    render_page_header("Income strategies", "income")
    st.caption("Infrastructure income and ADR dividend yields in one candidate table, with each method preserved.")
    render_income_methodology()
    with st.sidebar:
        view = st.selectbox(
            "Income view", ("Combined candidates", "Infrastructure research coverage"), key="income_view",
        )
        strategy = st.selectbox(
            "Income strategy", ("All income candidates", "Infrastructure", "ADRs"), key="income_strategy",
            disabled=view != "Combined candidates",
        )
        region = st.selectbox(
            "Infrastructure region",
            ("All regions", *sorted({company["Region"] for company in INFRASTRUCTURE_COMPANIES})),
            key="income_infrastructure_region", disabled=view == "Combined candidates" and strategy == "ADRs",
        )
    companies = [
        {**company, **infrastructure_listing_details(company["Symbol"])}
        for company in INFRASTRUCTURE_COMPANIES
        if region == "All regions" or company["Region"] == region
    ]
    if view == "Infrastructure research coverage":
        render_infrastructure_coverage(companies)
        return
    if strategy == "ADRs":
        companies = []
    catalog = pd.DataFrame()
    if strategy != "Infrastructure":
        try:
            catalog = adr_catalog()
        except StockDataError as exc:
            st.error(f"ADR research catalog unavailable; any infrastructure results are still shown. {exc}")
    with st.sidebar:
        countries = ["All countries"] + (sorted(catalog["Country"].unique().tolist()) if not catalog.empty else [])
        saved_country = st.session_state.get("income_adr_country")
        if catalog.empty and saved_country and saved_country not in countries:
            countries.append(saved_country)
        if st.session_state.get("income_adr_country") not in countries:
            st.session_state["income_adr_country"] = countries[0]
        country = st.selectbox(
            "ADR country / main market", countries, key="income_adr_country", disabled=catalog.empty,
        )
        minimum_yield = st.number_input(
            "Minimum ADR TTM yield (%)", min_value=0.0, value=0.0, step=0.5,
            key="income_minimum_adr_yield", disabled=catalog.empty,
        )
        show_excluded = st.checkbox(
            "Show excluded / unavailable infrastructure", key="income_show_excluded",
            disabled=strategy == "ADRs",
        )
        sort_by = st.selectbox(
            "Sort income candidates", ("Company", "Infrastructure forward yield", "ADR TTM yield"),
            key="income_sort",
        )
        limit = st.selectbox("Maximum income results", ("All", 25, 50, 100), key="income_limit")
    if not catalog.empty and country != "All countries":
        catalog = catalog.loc[catalog["Country"] == country].copy()
    as_of = pd.Timestamp.now(tz="America/New_York").date().isoformat()
    infrastructure_rows, infrastructure_errors, adr_rows, adr_errors = [], [], [], []
    if companies:
        with st.spinner("Loading infrastructure income criteria (24-hour cached data)..."):
            infrastructure_rows, infrastructure_errors = load_infrastructure_income(companies)
    if not catalog.empty:
        with st.spinner(f"Loading {len(catalog)} ADR dividend histories (24-hour cache)..."):
            try:
                adr_rows, adr_errors = cached_adr_scan(tuple(catalog["Symbol"]), as_of)
            except StockDataError as exc:
                adr_errors = [{"Symbol": symbol, "Error": str(exc)} for symbol in catalog["Symbol"]]
    results = build_income_candidates(
        companies, infrastructure_rows, infrastructure_errors, catalog, adr_rows, adr_errors,
    )
    filtered = filter_income_candidates(
        results, strategy=strategy, infrastructure_region=region, adr_country=country,
        minimum_adr_yield=minimum_yield, show_excluded_infrastructure=show_excluded,
        sort_by=sort_by, limit=None if limit == "All" else limit,
    )
    metrics = st.columns(3)
    metrics[0].metric(
        "Infrastructure passing", f"{int(results['InfrastructureStatus'].eq('Pass').sum())} / {len(companies)}",
    )
    metrics[1].metric("ADRs with live data", f"{int(results['ADRStatus'].eq('Available').sum())} / {len(catalog)}")
    metrics[2].metric("Unique listings shown", len(filtered))
    st.caption(
        "Strategy labels reflect the selected catalog scopes. Excluded or unavailable infrastructure "
        "may still appear via a valid ADR result; this is not an infrastructure pass. "
        "Company order is the default; choose a yield-specific sort to rank that method."
    )
    st.warning(
        "Historical cash yields are not forecasts or guaranteed income. Forward infrastructure "
        "yield and ADR TTM yield use different bases and possibly different price dates."
    )
    audit = results.loc[
        results["InfrastructureStatus"].isin(("Fail", "Unavailable", "Not screened"))
        | results["ADRStatus"].eq("Unavailable")
    ]
    if not audit.empty:
        with st.expander(f"Excluded and unavailable assessments ({len(audit)} listings)"):
            st.dataframe(
                audit[["Symbol", "Name", "InfrastructureStatus", "InfrastructureReason", "ADRStatus", "ADRReason"]],
                hide_index=True, width="stretch",
            )
            if adr_errors and st.button("Retry unavailable ADRs", key="income_retry_adr"):
                cached_adr_scan.clear()
                st.rerun()
    if results["AccessStatus"].eq("Restricted venue").any():
        st.info("Restricted-venue infrastructure is research only; confirm eligibility before trading.")
    if results["InfrastructureStatus"].eq("Not screened").any():
        st.info("Unverified infrastructure venues were not fetched. They remain in research coverage and the audit.")
    if filtered.empty:
        st.info("No income candidates match the selected scopes and rules. See the assessment audit or research coverage.")
        return
    display = filtered.rename(columns={
        "Name": "Company", "IncomeStrategies": "Strategies", "IncomeIncludedVia": "Included via",
        "InfrastructureStatus": "Infrastructure status", "ADRStatus": "ADR data status",
        "InfrastructureYieldPercent": "Infrastructure forward yield (%)", "ADRYieldPercent": "ADR TTM yield (%)",
        "InfrastructurePriceDate": "Infrastructure price date", "InfrastructureCurrency": "Quote currency",
        "PriceDate": "ADR price date", "DividendCoverageRatio": "Payout / coverage ratio",
        "DistanceToFiveYearHigh": "Distance to 5-year high", "Region": "Infrastructure region",
        "Country": "ADR country / main market",
    })
    st.dataframe(
        display, hide_index=True, width="stretch",
        column_order=[
            "Ticker", "Company", "Strategies", "Included via", "Infrastructure status", "ADR data status",
            "Infrastructure forward yield (%)", "ADR TTM yield (%)",
            "Infrastructure price date", "ADR price date", "Infrastructure region", "ADR country / main market",
        ],
        column_config={
            "Infrastructure forward yield (%)": st.column_config.NumberColumn(format="%.2f%%"),
            "ADR TTM yield (%)": st.column_config.NumberColumn(format="%.2f%%"),
            "Source": st.column_config.LinkColumn(), "AccessSource": st.column_config.LinkColumn(),
            "LiveSource": st.column_config.LinkColumn(), "ResearchSource": st.column_config.LinkColumn(),
        },
    )
    st.download_button(
        "Download income results (CSV)", data=display.to_csv(index=False).encode("utf-8"),
        file_name=f"income-strategies-{as_of}.csv", mime="text/csv", key="income_download",
    )
    render_income_candidate(filtered)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_breakout_history(symbol: str) -> pd.DataFrame:
    return get_breakout_history(symbol)


@cache_market_data(ttl=CACHE_TTL_SECONDS)
def cached_breakout_reference_history() -> pd.DataFrame:
    return get_breakout_history("CLMT", reference=True)


def load_breakout_scan(universe: str, custom_symbols: list[str]) -> dict:
    from breakout_strategy import parse_breakout_symbols

    if universe not in BREAKOUT_UNIVERSES:
        raise StockDataError("Select a supported breakout universe.")
    if universe == "Custom tickers":
        symbols = parse_breakout_symbols(" ".join(custom_symbols))
        names = {symbol: symbol for symbol in symbols}
    else:
        loaders = {
            "Russell 2000 stocks": cached_russell_holdings,
            "S&P 500 stocks": cached_sp500_holdings,
            "European stocks": cached_european_holdings,
        }
        with st.spinner(f"Loading {universe} listings from the 24-hour cache..."):
            holdings = loaders[universe]()
        if holdings.empty or not {"Symbol", "Name"}.issubset(holdings.columns):
            raise StockDataError("The selected universe returned no usable stock listings.")
        names = dict(zip(holdings["Symbol"], holdings["Name"]))
        symbols = sorted(names)
    as_of = completed_breakout_date()
    batch = load_scanner_data(symbols, cached_breakout_history, "Early breakout prices")
    rows = []
    for symbol in symbols:
        result = (
            {"Status": "Unavailable", "Reason": batch.errors[symbol], "AsOf": None}
            if symbol in batch.errors else analyze_early_breakout(batch.values[symbol], as_of=as_of)
        )
        rows.append({"Symbol": symbol, "Name": names[symbol], **result})
    if not any(row["Status"] != "Unavailable" for row in rows):
        reasons = "; ".join(f"{row['Symbol']}: {row['Reason']}" for row in rows[:3])
        raise StockDataError(f"No stocks could be assessed. {reasons} Use Refresh data before retrying provider failures.")
    return {
        "model_version": BREAKOUT_MODEL_VERSION, "universe": universe,
        "requested_symbols": symbols, "scanned_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of, "rows": rows,
    }


def render_early_breakout_strategy() -> None:
    from breakout_strategy_ui import render_early_breakout

    render_page_header("Early breakout strategy", "early_breakout")
    render_early_breakout(
        load_breakout_scan, cached_breakout_history, cached_breakout_reference_history,
        open_stock_research, render_bookmark_button,
    )


def render_ip_turnaround_strategy() -> None:
    from ip_turnaround_ui import render_ip_turnarounds

    render_page_header("IP-backed turnarounds", "ip_turnarounds")
    render_ip_turnarounds(open_stock_research, render_bookmark_button)


def render_volatility_strategy() -> None:
    from volatility_strategy_ui import render_sector_pilot

    st.title("Volatility Strategy")
    render_sector_pilot(open_stock_research)


def render_other_charts() -> None:
    from market_breadth_ui import render_market_breadth

    render_page_header("Other charts", "other_charts")
    st.subheader("S&P 500 market breadth")
    st.caption(
        "Market breadth measures how many stocks participate in a market move. "
        "Compare advancing versus declining stocks with the index and long-term trend participation."
    )
    st.info(
        "Calculated from current IVV equity holdings, not historical index membership. "
        "The first load downloads two years of prices for roughly 500 listings and can take a few minutes. "
        "Data is cached for 24 hours; no AI calls are used."
    )
    if st.button("Load S&P 500 breadth", key="load_sp500_breadth"):
        st.session_state["sp500_breadth_loaded"] = True
    if not st.session_state.get("sp500_breadth_loaded"):
        return
    try:
        with st.spinner("Loading S&P 500 breadth using the 24-hour cache..."):
            holdings = cached_sp500_holdings()
            if holdings.empty:
                raise StockDataError("The S&P 500 holdings source returned no stock listings.")
            snapshot = cached_market_breadth(tuple(holdings["Symbol"]), BREADTH_MODEL_VERSION)
    except StockDataError as exc:
        st.error(str(exc))
        return
    render_market_breadth(snapshot, str(holdings["AsOfDate"].iloc[0]))


def render_itpm_strategy() -> None:
    st.title("ITPM Strategy")
    st.caption("A dedicated workspace for your ITPM strategy.")
    st.info(
        "Details coming later. No screening rules, signals or assumptions have "
        "been configured. This section is ready for the requirements you will provide."
    )


def render_biotech_strategy() -> None:
    st.title("Biotech Strategy")
    st.caption("Planned approach: AI would assess biotech companies.")
    st.caption("Planned stock sources: PFC filings and Substack.")
    st.info(
        "Placeholder only. Assessment criteria and screening rules have not been configured. "
        "No AI assessments or data requests run in this section yet."
    )


def render_yellow_bricks_strategy() -> None:
    st.title("Yellow Bricks Strategy")
    st.caption("Planned basis: Yellow Bricks.")
    st.info(
        "Placeholder only. Strategy details, screening rules and source integration "
        "have not been configured. No analysis or data requests run in this section yet."
    )


def render_tax_loss_harvesting_strategy() -> None:
    st.title("Tax Loss Harvesting Strategy")
    st.caption("A dedicated workspace for a future tax loss harvesting strategy.")
    st.info(
        "Placeholder only. Tax jurisdiction, eligibility criteria and trading rules "
        "have not been configured. No tax calculations, screening or data requests "
        "run in this section yet."
    )


def render_druckenmiller_portfolio() -> None:
    st.title("Druckenmiller-like portfolio")
    st.caption("A dedicated workspace for your Druckenmiller-inspired portfolio.")
    st.info(
        "Placeholder only. Holdings, screening rules, allocations and risk controls "
        "have not been configured. Portfolio requirements will be added later."
    )
    st.caption("This is not a representation of Stanley Druckenmiller's actual holdings.")


def main() -> None:
    st.set_page_config(page_title="Global Stock Research", page_icon="📈", layout="wide")
    apply_workspace_style()
    legacy_area = st.session_state.get("research_area")
    if legacy_area == "Fashion trend":
        st.session_state["research_area"] = "Fashion shorts"
        legacy_area = "Fashion shorts"
    if legacy_area in ("Infrastructure income", "ADR dividend yield"):
        st.session_state["research_area"] = "Income strategies"
        st.session_state.setdefault(
            "income_strategy", "Infrastructure" if legacy_area == "Infrastructure income" else "ADRs",
        )
        if legacy_area == "ADR dividend yield":
            st.session_state.setdefault("income_sort", "ADR TTM yield")
            for old_key, new_key in (
                ("adr_country", "income_adr_country"),
                ("adr_minimum_yield", "income_minimum_adr_yield"),
                ("adr_result_limit", "income_limit"),
                ("adr_show_chart", "income_show_chart"),
            ):
                if old_key in st.session_state:
                    st.session_state.setdefault(new_key, st.session_state[old_key])
        old_symbol_key = "adr_symbol" if legacy_area == "ADR dividend yield" else "infrastructure_research_symbol"
        if st.session_state.get(old_symbol_key):
            st.session_state.setdefault("income_symbol", st.session_state[old_symbol_key])
    with st.sidebar:
        render_workspace_brand()
        research_area = st.radio(
            "Research area",
            (
                "Individual stocks",
                "ETF market atlas",
                "Other charts",
                "U-recovery scanner",
                "Early breakout strategy",
                "Bookmarks",
                "Trade checklist",
                "Management & incentives",
                "Income strategies",
                "IP-backed turnarounds",
                "Fashion shorts",
                "Star principle",
                "Volatility strategy",
                "ITPM strategy",
                "Biotech strategy",
                "Yellow Bricks strategy",
                "Tax loss harvesting strategy",
                "Druckenmiller-like portfolio",
            ),
            key="research_area",
        )
        st.divider()
        with st.expander("AI assistant settings"):
            render_ai_settings()
        st.session_state["workspace_ai_settings"] = True
        with st.expander("Data & cache"):
            render_cache_controls()
    if research_area == "U-recovery scanner":
        render_inflection_scanner()
        return
    if research_area == "Early breakout strategy":
        render_early_breakout_strategy()
        return
    if research_area == "Bookmarks":
        render_bookmarks()
        return
    if research_area == "Trade checklist":
        from trade_checklist_ui import render_trade_checklist

        render_trade_checklist()
        return
    if research_area == "Management & incentives":
        from management_evidence_ui import render_management_tracker

        render_management_tracker()
        return
    if research_area == "ETF market atlas":
        render_etf_explorer()
        return
    if research_area == "Other charts":
        render_other_charts()
        return
    if research_area == "Income strategies":
        render_income_strategy()
        return
    if research_area == "IP-backed turnarounds":
        render_ip_turnaround_strategy()
        return
    if research_area == "Fashion shorts":
        render_fashion_trend_strategy()
        return
    if research_area == "Star principle":
        render_star_principle_strategy()
        return
    if research_area == "Volatility strategy":
        render_volatility_strategy()
        return
    if research_area == "ITPM strategy":
        render_itpm_strategy()
        return
    if research_area == "Biotech strategy":
        render_biotech_strategy()
        return
    if research_area == "Yellow Bricks strategy":
        render_yellow_bricks_strategy()
        return
    if research_area == "Tax loss harvesting strategy":
        render_tax_loss_harvesting_strategy()
        return
    if research_area == "Druckenmiller-like portfolio":
        render_druckenmiller_portfolio()
        return

    st.session_state.pop("_stock_research_handoff", None)
    st.markdown('<div class="workspace-kicker">COMPANY RESEARCH</div>', unsafe_allow_html=True)
    render_page_header("Global Stock Research", "individual")
    st.caption("Understand the business. Compare the numbers. Ask better questions.")

    with st.sidebar:
        st.header("Find a stock")
        scanner_queue = st.session_state.get("stock_research_queue", [])
        if st.session_state.get("stock_research_queue_label") == "Bookmarked stocks":
            try:
                scanner_queue = [row["symbol"] for row in list_bookmarks()]
            except BookmarkError as exc:
                st.error(str(exc))
                return
            st.session_state["stock_research_queue"] = scanner_queue
        if scanner_queue:
            if st.session_state.get("stock_research_symbol") not in scanner_queue:
                st.session_state["stock_research_symbol"] = scanner_queue[0]
                select_stock_research_symbol()
            st.selectbox(
                st.session_state.get("stock_research_queue_label", "U-recovery candidates"),
                scanner_queue,
                key="stock_research_symbol",
                on_change=select_stock_research_symbol,
            )
            previous, position, following = st.columns([1, 2, 1])
            previous.button(
                "←",
                help="Previous candidate",
                width="stretch",
                on_click=step_stock_research,
                args=(scanner_queue, -1),
            )
            current_index = scanner_queue.index(
                st.session_state["stock_research_symbol"]
            )
            position.markdown(
                f"<p style='text-align:center'>{current_index + 1} / "
                f"{len(scanner_queue)}</p>",
                unsafe_allow_html=True,
            )
            following.button(
                "→",
                help="Next candidate",
                width="stretch",
                on_click=step_stock_research,
                args=(scanner_queue, 1),
            )
        if "stock_query" not in st.session_state:
            st.session_state["stock_query"] = "AAPL"
        query = st.text_input(
            "Company or ticker",
            key="stock_query",
            help="Examples: AAPL, BMW.DE, 7203.T, BHP.AX, RELIANCE.NS",
        )
        if st.button("Search", type="primary", width="stretch"):
            try:
                with st.spinner("Searching markets..."):
                    st.session_state["search_results"] = cached_search(query)
                st.session_state.pop("stock_research_queue", None)
                st.session_state.pop("stock_research_queue_label", None)
                scanner_queue = []
                if not st.session_state["search_results"]:
                    st.warning("No listed shares or ETFs matched that search.")
            except (ValueError, StockDataError) as exc:
                st.error(str(exc))

        results = st.session_state.get("search_results", [])
        if scanner_queue:
            symbol = st.session_state["stock_research_symbol"]
        elif results:
            selected = st.selectbox(
                "Matching securities",
                options=results,
                format_func=lambda item: (
                    f"{item['symbol']} — {item['name']} ({item['exchange']})"
                ),
            )
            symbol = selected["symbol"]
        else:
            symbol = query.strip().upper()

        period_label = st.selectbox("Chart period", options=list(PERIODS), index=5)
        chart_type = st.radio("Chart style", ("Candlestick", "Line"), horizontal=True)
        st.caption("Use Yahoo Finance exchange suffixes for non-US listings.")

    if not symbol:
        st.info("Enter a company name or ticker in the sidebar.")
        return

    period = PERIODS[period_label]
    try:
        with st.spinner(f"Loading {symbol}..."):
            history = cached_history(symbol, period, interval_for_period(period))
    except StockDataError as exc:
        st.error(str(exc))
        render_stock_assistant(symbol, symbol, {}, pd.DataFrame())
        with st.expander("Revenue outlook: assess supplied excerpts"):
            render_revenue_outlook_research(symbol, symbol)
        return
    try:
        info = cached_info(symbol)
    except StockDataError as exc:
        info = {}
        st.warning(f"Company metadata is unavailable; the price chart remains available. {exc}")

    company_name = info.get("longName") or info.get("shortName") or symbol
    title_column, action_column = st.columns([4, 1])
    with title_column:
        st.subheader(f"{company_name} ({symbol})")
    with action_column:
        render_bookmark_button(symbol, str(company_name))
    render_overview(info, history)
    description = info.get("longBusinessSummary")
    if description:
        preview = str(description)
        st.caption(preview if len(preview) <= 300 else preview[:300].rsplit(" ", 1)[0] + "...")

    research_column, assistant_column = st.columns([2.2, 1], gap="large")
    with research_column:
        overview_tab, financials_tab, ownership_tab, research_tab = st.tabs(
            ["Overview", "Financials", "Ownership", "Research"],
            key="stock_workspace_tab", on_change="rerun",
        )
        with overview_tab:
            chart_tab = st.container()
            profile_tab = st.expander("Company profile & full description")
        with financials_tab:
            revenue_tab, cost_tab, metrics_tab, recovery_tab = st.tabs(
                ["Revenue", "Cost of revenue", "Key metrics", "Recovery"],
                key="stock_financials_tab", on_change="rerun",
            )
            with recovery_tab:
                render_recovery_research(symbol, str(company_name))
        with ownership_tab:
            insider_tab, shareholder_tab, short_tab = st.tabs(
                ["Insider buys", "Shareholder returns", "Short interest"]
            )
        with research_tab:
            catalysts_tab, outlook_tab, drivers_tab, news_tab, x_tab = st.tabs(
                ["Catalysts", "Revenue outlook", "Drivers & costs", "News sentiment", "X discussion"]
            )
            with outlook_tab:
                render_revenue_outlook_research(symbol, str(company_name))
    with assistant_column:
        render_stock_assistant(symbol, str(company_name), info, history)
    with chart_tab:
        st.plotly_chart(
            price_chart(history, symbol, chart_type),
            width="stretch",
            config={"displaylogo": False},
        )
        st.download_button(
            "Download price data (CSV)",
            history.to_csv().encode("utf-8"),
            file_name=f"{symbol}_{period}_prices.csv",
            mime="text/csv",
        )

    with news_tab:
        render_company_news(symbol, str(company_name))

    currency = str(info.get("financialCurrency") or info.get("currency") or "")
    try:
        if info.get("quoteType") and info["quoteType"] != "EQUITY":
            shareholder_yield = None
        else:
            shareholder_market_cap, _ = shareholder_yield_inputs(info)
            shareholder_yield = cached_shareholder_yield(symbol, shareholder_market_cap)
        shareholder_error = None
    except StockDataError as exc:
        shareholder_yield = None
        shareholder_error = str(exc)
    try:
        annual_shares = cached_share_count_history(symbol, "annual")
        quarterly_shares = cached_share_count_history(symbol, "quarterly")
        share_count_error = None
    except StockDataError as exc:
        annual_shares = pd.DataFrame()
        quarterly_shares = pd.DataFrame()
        share_count_error = str(exc)
    try:
        annual_financials = load_financials(symbol, "annual")
        quarterly_financials = load_financials(symbol, "quarterly")
        financial_error = None
    except StockDataError as exc:
        annual_financials = pd.DataFrame()
        quarterly_financials = pd.DataFrame()
        financial_error = str(exc)
    try:
        business_context = cached_business_context(
            info.get("industryKey"),
            info.get("sector"),
            info.get("country"),
        )
        business_context_error = None
    except StockDataError as exc:
        business_context = {"Industry": None, "Benchmarks": []}
        business_context_error = str(exc)
    try:
        catalyst_data = cached_catalyst_data(symbol)
        catalyst_error = None
    except StockDataError as exc:
        catalyst_data = {
            "Events": [],
            "Expectations": [],
            "RatingActions": [],
        }
        catalyst_error = str(exc)
    try:
        company_developments = cached_company_developments(symbol)
        development_error = None
    except StockDataError as exc:
        company_developments = pd.DataFrame()
        development_error = str(exc)

    with revenue_tab:
        revenue_visible = financials_tab.open and revenue_tab.open
        if revenue_visible:
            render_scanner_revenue_comparison(symbol, currency)
        if financial_error:
            if revenue_visible:
                st.error(financial_error)
        else:
            annual_tab, quarterly_tab = st.tabs(
                ["Annual", "Quarterly"], key="stock_revenue_period", on_change="rerun",
            )
            with annual_tab:
                if revenue_visible and annual_tab.open:
                    render_revenue_history(
                        annual_financials,
                        currency,
                        "annual",
                        "Year-over-year growth",
                    )
            with quarterly_tab:
                if revenue_visible and quarterly_tab.open:
                    render_revenue_history(
                        quarterly_financials,
                        currency,
                        "quarterly",
                        "Quarter-over-quarter growth",
                    )
            if revenue_visible:
                st.caption(
                    "Annual and Quarterly growth compare each reported period with the immediately "
                    "preceding period shown. Financial statements may be restated or reported in "
                    "different currencies."
                )
                st.caption(
                    "The scanner normally compares the latest rolling four quarters with "
                    "the four quarters one year earlier, not the fiscal-year growth shown "
                    "above. Its Revenue period column identifies the comparison used, "
                    "including a fiscal-year fallback when rolling history is unavailable."
                )

    with cost_tab:
        st.caption(
            "Cost of revenue preserves the reported sign. Negative values represent "
            "reported credits or reversals, not positive expenses."
        )
        if financial_error:
            st.error(financial_error)
        else:
            annual_tab, quarterly_tab = st.tabs(["Annual", "Quarterly"])
            with annual_tab:
                render_cost_of_revenue_history(
                    annual_financials,
                    currency,
                    "annual",
                )
            with quarterly_tab:
                render_cost_of_revenue_history(
                    quarterly_financials,
                    currency,
                    "quarterly",
                )
            st.caption(
                "Uses the reported cost-of-revenue line item and verifies that "
                "revenue minus cost equals reported gross profit. Some industries "
                "do not report this line item."
            )

    with metrics_tab:
        render_key_metrics(info, shareholder_yield, annual_financials)

    with drivers_tab:
        drivers = generate_stock_drivers(
            info,
            annual_financials,
            quarterly_financials,
            business_context,
        )
        render_stock_drivers(drivers)
        if financial_error:
            st.warning(
                "Statement-based trend evidence was excluded: "
                f"{financial_error}"
            )
        if business_context_error:
            st.warning(
                "External industry/market context was unavailable: "
                f"{business_context_error}"
            )
        if share_count_error:
            st.warning(
                f"Share-count evidence was excluded: {share_count_error}"
            )

    with catalysts_tab:
        catalysts = (
            generate_stock_catalysts(
                info,
                annual_financials,
                quarterly_financials,
                catalyst_data,
            )
            if not financial_error
            else []
        )
        render_stock_catalysts(catalyst_data, catalysts, catalyst_error)
        acceleration_reasons = generate_revenue_acceleration_reasons(
            info,
            company_developments,
        )
        render_revenue_acceleration_reasons(
            acceleration_reasons,
            development_error,
        )

    with insider_tab:
        try:
            insider_buys = cached_insider_buys(symbol)
        except StockDataError as exc:
            st.error(str(exc))
        else:
            render_insider_buys(insider_buys, currency)

    with shareholder_tab:
        if share_count_error:
            st.error(share_count_error)
        else:
            render_shareholder_returns(
                shareholder_yield,
                shareholder_error,
                annual_shares,
                quarterly_shares,
                currency,
            )

    with short_tab:
        rows = short_interest_rows(info)
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            st.caption(
                "Short interest is reported periodically and may be delayed. "
                "Definitions and reporting schedules vary by exchange."
            )
        else:
            st.info(
                "Short-interest data is not available for this security from the data provider. "
                "Many markets do not publish it in a standardized public feed."
            )

    with x_tab:
        st.subheader(f"Public discussion about {symbol}")
        st.write(
            "Open current conversations on X using the ticker cashtag or company name."
        )
        links = x_discussion_links(symbol, str(company_name))
        columns = st.columns(len(links))
        for column, (label, url) in zip(columns, links.items()):
            with column:
                st.link_button(label, url, width="stretch")
        st.warning(
            "Posts on X are unverified public commentary and may include spam, "
            "promotions, or market manipulation. They are not investment advice."
        )

    with profile_tab:
        website = info.get("website")
        if website:
            st.link_button("Company website", website)
        description = info.get("longBusinessSummary")
        if description:
            st.write(description)
        else:
            st.info("No company profile is available for this security.")

    st.divider()
    st.caption(
        "Data supplied by Yahoo Finance. For research only; delayed or incomplete data may occur. "
        "This is not investment advice."
    )


if __name__ == "__main__":
    main()
