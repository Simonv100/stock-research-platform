from __future__ import annotations

import json
import math
import os
import re
import time
from base64 import b64encode
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from email.utils import parsedate_to_datetime
from functools import lru_cache
from io import StringIO
from numbers import Real
from threading import Lock
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from xml.etree import ElementTree

import pandas as pd
import yfinance as yf
from curl_cffi.requests.exceptions import RequestException
from yfinance.exceptions import YFException


class StockDataError(RuntimeError):
    """Raised when market data cannot be retrieved or interpreted."""


MARKET_DATA_EXCEPTIONS = (YFException, RequestException)

GOOGLE_TRENDS_REQUEST_INTERVAL = 10.0
GOOGLE_TRENDS_RETRY_DELAYS = (30.0, 60.0)
GOOGLE_TRENDS_COOLDOWN = 300.0
_google_trends_lock = Lock()
_google_trends_next_request = 0.0
_google_trends_cooldown_until = 0.0


IWM_HOLDINGS_API = (
    "https://www.ishares.com/varnish-api/blk-one01-product-data/product-data/"
    "api/v2/get-product-data?appSubType=ISHARES&appType=PRODUCT_PAGE&"
    "component=holdings.all&locale=en_US&portfolioId=239710&"
    "targetSite=us-ishares&userType=individual&excludeContent=true&"
    "includeConfig=true"
)
IVV_HOLDINGS_API = (
    "https://www.ishares.com/varnish-api/blk-one01-product-data/product-data/"
    "api/v2/get-product-data?appSubType=ISHARES&appType=PRODUCT_PAGE&"
    "component=holdings.all&locale=en_US&portfolioId=239726&"
    "targetSite=us-ishares&userType=individual&excludeContent=true&"
    "includeConfig=true"
)
IEUR_HOLDINGS_CSV = (
    "https://www.ishares.com/us/products/264617/"
    "ishares-core-msci-europe-etf/latest-holdings.csv"
)
EUROPE_EXCHANGE_SUFFIXES = {
    "Borsa Italiana": ".MI",
    "Bolsa De Madrid": ".MC",
    "Deutsche Boerse Xetra": ".DE",
    "Euronext Amsterdam": ".AS",
    "Irish Stock Exchange - All Market": ".IR",
    "London Stock Exchange": ".L",
    "Nasdaq Omx Helsinki Ltd.": ".HE",
    "Nasdaq Omx Nordic": ".ST",
    "Nyse Euronext - Euronext Brussels": ".BR",
    "Nyse Euronext - Euronext Lisbon": ".LS",
    "Nyse Euronext - Euronext Paris": ".PA",
    "Omx Nordic Exchange Copenhagen A/S": ".CO",
    "Oslo Bors Asa": ".OL",
    "SIX Swiss Exchange": ".SW",
    "Wiener Boerse Ag": ".VI",
    "Xetra": ".DE",
}
SEC_TICKERS_API = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_API = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_HEADERS = {
    "User-Agent": "LocalStockResearch/1.0 research@example.com",
    "Accept": "application/json",
}
SEC_REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
YAHOO_SYMBOL_OVERRIDES = {
    "BFB": "BF-B",
    "BRKB": "BRK-B",
}


def search_stocks(query: str, max_results: int = 10) -> list[dict[str, str]]:
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("Enter a company name or ticker symbol.")

    try:
        quotes = yf.Search(
            cleaned_query,
            max_results=max_results,
            news_count=0,
            enable_fuzzy_query=True,
        ).quotes
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(f"Ticker search failed: {exc}") from exc

    results: list[dict[str, str]] = []
    for quote in quotes:
        if quote.get("quoteType") not in {"EQUITY", "ETF"}:
            continue
        symbol = str(quote.get("symbol", "")).strip()
        if not symbol:
            continue
        results.append(
            {
                "symbol": symbol,
                "name": str(
                    quote.get("longname")
                    or quote.get("shortname")
                    or symbol
                ),
                "exchange": str(
                    quote.get("exchDisp")
                    or quote.get("exchange")
                    or "Unknown exchange"
                ),
                "type": str(quote.get("quoteType", "")),
            }
        )
    return results


def get_price_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
    buffered_periods = {
        "1mo": "1y",
        "3mo": "1y",
        "6mo": "2y",
        "ytd": "2y",
        "1y": "2y",
        "5y": "10y",
    }
    try:
        history = yf.Ticker(symbol).history(
            period=buffered_periods.get(period, period),
            interval=interval,
            auto_adjust=False,
            actions=False,
        )
    except MARKET_DATA_EXCEPTIONS as exc:
        history = pd.DataFrame()
        primary_error = exc
    else:
        primary_error = None

    if history.empty:
        try:
            history = yf.download(
                symbol,
                period=buffered_periods.get(period, period),
                interval=interval,
                auto_adjust=False,
                actions=False,
                group_by="column",
                threads=False,
                progress=False,
            )
        except MARKET_DATA_EXCEPTIONS as exc:
            detail = primary_error or exc
            raise StockDataError(
                f"Price history for {symbol} could not be loaded: {detail}"
            ) from exc
        if isinstance(history.columns, pd.MultiIndex):
            if symbol in history.columns.get_level_values(-1):
                history = history.xs(symbol, axis=1, level=-1)
            elif symbol in history.columns.get_level_values(0):
                history = history.xs(symbol, axis=1, level=0)
        if history.empty:
            raise StockDataError(
                f"No price history was returned for {symbol} from either Yahoo "
                "price endpoint. Try refreshing the cached data."
            )

    return prepare_price_history(history, period)


def prepare_price_history(history: pd.DataFrame, period: str) -> pd.DataFrame:
    required_columns = {"Open", "High", "Low", "Close", "Volume"}
    missing_columns = required_columns.difference(history.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise StockDataError(f"Price history is missing: {missing}.")

    result = history.loc[:, ["Open", "High", "Low", "Close", "Volume"]].copy()
    result = result.dropna(subset=["Close"])
    result.index = pd.to_datetime(result.index)
    result = result.sort_index()
    result["MA200"] = result["Close"].rolling(window=200, min_periods=200).mean()
    if result.empty:
        raise StockDataError("Price history contains no closing prices.")

    end = result.index.max()
    offsets = {
        "1mo": pd.DateOffset(months=1),
        "3mo": pd.DateOffset(months=3),
        "6mo": pd.DateOffset(months=6),
        "1y": pd.DateOffset(years=1),
        "5y": pd.DateOffset(years=5),
    }
    if period == "ytd":
        cutoff = pd.Timestamp(year=end.year, month=1, day=1, tz=end.tz)
        result = result.loc[result.index >= cutoff]
    elif period in offsets:
        result = result.loc[result.index >= end - offsets[period]]
    return result


def summarize_price_history(history: pd.DataFrame) -> dict[str, float | None]:
    if "Close" not in history:
        raise StockDataError("Price history is missing: Close.")
    closes = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if len(closes) < 2:
        raise StockDataError("At least two closing prices are required.")

    total_return = float(closes.iloc[-1] / closes.iloc[0] - 1)
    elapsed_days = max((closes.index[-1] - closes.index[0]).days, 1)
    annualized_return = float((1 + total_return) ** (365.25 / elapsed_days) - 1)
    daily_returns = closes.pct_change(fill_method=None).dropna()
    annualized_volatility = (
        float(daily_returns.std() * (252**0.5))
        if len(daily_returns) >= 2
        else None
    )
    drawdowns = closes / closes.cummax() - 1
    ma200 = history["MA200"].dropna() if "MA200" in history else pd.Series(dtype=float)
    latest_ma200 = ma200.iloc[-1] if not ma200.empty else None
    return {
        "TotalReturn": total_return,
        "AnnualizedReturn": annualized_return,
        "AnnualizedVolatility": annualized_volatility,
        "MaxDrawdown": float(drawdowns.min()),
        "LatestClose": float(closes.iloc[-1]),
        "LatestMA200": float(latest_ma200) if latest_ma200 is not None else None,
    }


U_RECOVERY_MODEL_VERSION = "u-recovery-v10-intermediate-cycles"
U_SHAPE_STRICT = "Strict U-shape"
U_SHAPE_NEAR_MISS = "Near miss"


def classify_u_recovery(
    metrics: dict[str, Any], *, completed_earlier_cycle: bool, failed_late_recovery: bool,
    completed_intermediate_cycle: bool = False,
) -> dict[str, Any] | None:
    fields = (
        "PriorDecline", "RecoveryProgress", "DistanceToPeak", "LowAge", "BaseSpan",
        "BaseDays", "20DReturn", "60DReturn", "OneYearReturn", "HigherLow", "MA50Slope20D", "VsMA50",
    )
    if any(pd.isna(metrics[field]) or not math.isfinite(metrics[field]) for field in fields):
        return None
    recent_early_reversal = metrics["LowAge"] <= 180 and metrics["60DReturn"] >= 0.08
    if not (
        metrics["PriorDecline"] <= -0.15
        and 0.05 <= metrics["RecoveryProgress"] <= 0.75
        and metrics["DistanceToPeak"] <= -0.10
        and (metrics["OneYearReturn"] >= 0 or recent_early_reversal)
        and not completed_earlier_cycle
        and not failed_late_recovery
    ):
        return None
    rules = [
        (
            metrics[field] >= strict, metrics[field] >= relaxed,
            f"{label}: {metrics[field]:.0f} trading days; needs >= {strict}",
        )
        for field, label, strict, relaxed in (
            ("LowAge", "Age of low", 60, 45),
            ("BaseSpan", "Base span", 120, 90),
            ("BaseDays", "Days in low zone", 50, 40),
        )
    ]
    rules.extend(
        (
            metrics[field] >= strict, metrics[field] >= relaxed,
            f"{label}: {metrics[field]:+.2%}; needs >= {strict:+.0%}",
        )
        for field, label, strict, relaxed in (
            ("20DReturn", "20-day return", -0.10, -0.15),
            ("60DReturn", "60-day return", -0.03, -0.08),
            ("HigherLow", "Recent vs. prior low", -0.03, -0.08),
        )
    )
    rules.extend((
        (
            metrics["MA50Slope20D"] > 0, metrics["MA50Slope20D"] >= -0.02,
            f"50-day MA slope: {metrics['MA50Slope20D']:+.2%}; needs > 0%",
        ),
        (
            metrics["VsMA50"] > 0, metrics["VsMA50"] >= -0.03,
            f"Price vs. 50-day MA: {metrics['VsMA50']:+.2%}; needs > 0%",
        ),
    ))
    rules.append((
        not completed_intermediate_cycle, True,
        "Completed intermediate cycle: a decline of at least 25% from the selected peak "
        "recovered at least 75% of its range, at least 120 trading days after its trough, "
        "before the final low; multi-cycle recovery rather than one clean U-shaped base",
    ))
    missed = [reason for passed, _, reason in rules if not passed]
    if len(missed) > 2 or not all(within_tolerance for _, within_tolerance, _ in rules):
        return None
    return {
        "ShapeMatch": U_SHAPE_NEAR_MISS if missed else U_SHAPE_STRICT,
        "ShapeMissCount": len(missed),
        "ShapeMissedRules": "; ".join(missed) if missed else "None - all strict rules met.",
    }


def has_completed_intermediate_cycle(before_final_low: pd.Series) -> bool:
    """Check the selected peak-to-final-low path for an earlier substantial recovery."""
    if before_final_low.empty:
        return False
    peak = float(before_final_low.iloc[0])
    trough = peak
    trough_position = 0
    for position, value in enumerate(before_final_low):
        price = float(value)
        if price < trough:
            trough = price
            trough_position = position
        if (
            trough <= peak * 0.75
            and position - trough_position >= 120
            and price >= trough + (peak - trough) * 0.75
        ):
            return True
    return False


def analyze_etf_inflection(
    history: pd.DataFrame, *, include_near_misses: bool = False,
) -> dict[str, Any] | None:
    closes = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if len(closes) < 500 or not closes.map(lambda value: math.isfinite(value) and value > 0).all():
        return None

    ma50 = closes.rolling(50).mean()
    ma200 = closes.rolling(200).mean()
    analysis_window = closes.tail(1260)
    peak_search = analysis_window.iloc[:-120]
    peak_date = peak_search.idxmax()
    pre_peak = analysis_window.loc[:peak_date]
    pre_peak_drawdown = pre_peak / pre_peak.cummax() - 1
    earlier_cycle_drawdown = float(pre_peak_drawdown.min())
    earlier_cycle_low_date = pre_peak_drawdown.idxmin()
    earlier_cycle_recovery_days = (
        pre_peak.index.get_loc(peak_date)
        - pre_peak.index.get_loc(earlier_cycle_low_date)
    )
    completed_earlier_cycle = (
        earlier_cycle_drawdown <= -0.25
        and earlier_cycle_recovery_days >= 120
    )
    after_peak = analysis_window.loc[peak_date:]
    low_date = after_peak.idxmin()
    completed_intermediate_cycle = has_completed_intermediate_cycle(
        after_peak.iloc[:after_peak.index.get_loc(low_date)]
    )
    low_price = float(closes.loc[low_date])
    peak_price = float(closes.loc[peak_date])
    if peak_price <= low_price:
        return None
    low_age = len(closes) - closes.index.get_loc(low_date) - 1
    decline_to_low = low_price / peak_price - 1
    rebound = float(closes.iloc[-1] / low_price - 1)
    distance_to_peak = float(closes.iloc[-1] / peak_price - 1)
    recovery_progress = float(
        (closes.iloc[-1] - low_price) / (peak_price - low_price)
    )
    post_low_recovery = (
        after_peak.loc[low_date:] - low_price
    ) / (peak_price - low_price)
    best_prior_recovery = float(post_low_recovery.iloc[:-1].max())
    recovery_giveback = best_prior_recovery - recovery_progress
    failed_late_recovery = (
        best_prior_recovery >= 0.75
        and recovery_giveback >= 0.25
    )

    low_zone_ceiling = low_price + (peak_price - low_price) * 0.20
    low_zone = after_peak <= low_zone_ceiling
    low_zone_dates = low_zone.index[low_zone]
    if len(low_zone_dates) < 2:
        return None
    base_start = low_zone_dates[0]
    base_end = low_zone_dates[-1]
    base_span = (
        closes.index.get_loc(base_end)
        - closes.index.get_loc(base_start)
        + 1
    )
    base_days = int(low_zone.sum())
    return_20d = float(closes.iloc[-1] / closes.iloc[-21] - 1)
    return_60d = float(closes.iloc[-1] / closes.iloc[-61] - 1)
    one_year_return = float(closes.iloc[-1] / closes.iloc[-253] - 1)
    ma50_slope = float(ma50.iloc[-1] / ma50.iloc[-21] - 1)
    above_ma200 = float(closes.iloc[-1] / ma200.iloc[-1] - 1)
    recent_low = float(closes.tail(60).min())
    preceding_low = float(closes.iloc[-180:-60].min())
    higher_low = recent_low / preceding_low - 1

    cross_mask = (closes > ma200) & (closes.shift(1) <= ma200.shift(1))
    cross_positions = [
        len(closes) - closes.index.get_loc(index) - 1
        for index in cross_mask.tail(40).index[cross_mask.tail(40)]
    ]
    crossover_days = min(cross_positions) if cross_positions else None

    measurements = {
        "20DReturn": return_20d,
        "60DReturn": return_60d,
        "OneYearReturn": one_year_return,
        "ReboundFromLow": rebound,
        "RecoveryProgress": recovery_progress,
        "BestPriorRecovery": best_prior_recovery,
        "RecoveryGiveback": recovery_giveback,
        "PriorDecline": decline_to_low,
        "DistanceToPeak": distance_to_peak,
        "LowAge": low_age,
        "BaseSpan": base_span,
        "BaseDays": base_days,
        "MA50Slope20D": ma50_slope,
        "HigherLow": higher_low,
        "VsMA50": float(closes.iloc[-1] / ma50.iloc[-1] - 1),
        "VsMA200": above_ma200,
        "MA200CrossDays": crossover_days,
        "AsOf": closes.index[-1],
    }
    classification = classify_u_recovery(
        measurements, completed_earlier_cycle=completed_earlier_cycle,
        failed_late_recovery=failed_late_recovery,
        completed_intermediate_cycle=completed_intermediate_cycle,
    )
    if classification is None or (not include_near_misses and classification["ShapeMatch"] != U_SHAPE_STRICT):
        return None

    score = 0
    score += 3 if base_span >= 500 else 2 if base_span >= 250 else 1
    score += 2 if base_days >= 150 else 1
    score += 2 if decline_to_low <= -0.25 else 1
    score += (
        3
        if 0.10 <= recovery_progress <= 0.35
        else 2 if recovery_progress <= 0.55 else 1
    )
    score += 2 if return_60d >= 0.06 else 1
    score += 2 if higher_low >= 0.05 else 1
    score += 1 if ma50_slope >= 0.02 else 0
    score += 1 if above_ma200 <= 0.05 else 0

    if recovery_progress < 0.25:
        signal = "Early right side"
    elif recovery_progress < 0.50:
        signal = "Right side developing"
    elif crossover_days is not None:
        signal = "MA200 reclaim"
    else:
        signal = "Late right side"
    return {
        **measurements,
        **classification,
        "Signal": signal,
        "Score": score,
    }


def get_inflection_scan(
    symbols: list[str],
    batch_size: int = 100,
    *,
    include_near_misses: bool = False,
) -> pd.DataFrame:
    columns = [
        "Symbol",
        "Signal",
        "ShapeMatch",
        "ShapeMissCount",
        "ShapeMissedRules",
        "Score",
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
    unique_symbols = sorted(set(symbols))
    if not unique_symbols:
        return pd.DataFrame(columns=columns)
    rows = []
    batches_with_data = 0
    for start in range(0, len(unique_symbols), batch_size):
        batch = unique_symbols[start : start + batch_size]
        try:
            downloaded = yf.download(
                batch,
                period="5y",
                interval="1d",
                auto_adjust=True,
                actions=False,
                group_by="ticker",
                threads=True,
                progress=False,
            )
        except MARKET_DATA_EXCEPTIONS as exc:
            raise StockDataError(
                f"Price scan failed for batch beginning with {batch[0]}: {exc}"
            ) from exc
        if downloaded.empty:
            continue
        batches_with_data += 1
        for symbol in batch:
            if isinstance(downloaded.columns, pd.MultiIndex):
                if symbol not in downloaded.columns.get_level_values(0):
                    continue
                history = downloaded[symbol]
            elif len(batch) == 1:
                history = downloaded
            else:
                continue
            analysis = analyze_etf_inflection(history, include_near_misses=include_near_misses)
            if analysis:
                rows.append({"Symbol": symbol, **analysis})
    if not batches_with_data:
        raise StockDataError("The inflection scan returned no price data.")
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["Score", "20DReturn"],
        ascending=[False, False],
    )


def get_etf_inflection_scan(
    symbols: list[str], *, include_near_misses: bool = False,
) -> pd.DataFrame:
    return get_inflection_scan(symbols, include_near_misses=include_near_misses)


def normalize_ishares_equity_holdings(
    payload: dict[str, Any],
    universe_name: str,
) -> pd.DataFrame:
    columns = ["Symbol", "Name", "Exchange", "Weight", "AsOfDate"]
    try:
        holdings = payload["componentsByNameMap"]["holdings"]
        container = holdings["containersByNameMap"]["all"]
        points = container["dataPointsByNameMap"]
        symbols = points["ticker"]["value"]
        names = points["issueName"]["value"]
        asset_classes = points["assetClass"]["value"]
        exchanges = points["exchange"]["value"]
        weights = points["holdingPercent"]["value"]
        as_of_date = points["asOfDate"]["value"]
    except (KeyError, TypeError) as exc:
        raise StockDataError(
            f"The iShares {universe_name} holdings payload has an unexpected format."
        ) from exc

    lengths = {len(symbols), len(names), len(asset_classes), len(exchanges), len(weights)}
    if len(lengths) != 1:
        raise StockDataError(
            f"The iShares {universe_name} holdings columns do not align."
        )

    rows = []
    for symbol, name, asset_class, exchange, weight in zip(
        symbols,
        names,
        asset_classes,
        exchanges,
        weights,
    ):
        cleaned_symbol = (
            str(symbol or "").strip().upper().replace(".", "-").replace(" ", "-")
        )
        cleaned_symbol = YAHOO_SYMBOL_OVERRIDES.get(
            cleaned_symbol,
            cleaned_symbol,
        )
        if asset_class != "Equity" or not cleaned_symbol or cleaned_symbol == "-":
            continue
        rows.append(
            {
                "Symbol": cleaned_symbol,
                "Name": str(name or cleaned_symbol).strip(),
                "Exchange": str(exchange or "").strip(),
                "Weight": float(weight) / 100,
                "AsOfDate": pd.to_datetime(str(as_of_date), format="%Y%m%d").date(),
            }
        )
    result = pd.DataFrame(rows, columns=columns)
    return result.drop_duplicates(subset=["Symbol"]).reset_index(drop=True)


def normalize_russell_holdings(payload: dict[str, Any]) -> pd.DataFrame:
    return normalize_ishares_equity_holdings(payload, "Russell 2000")


def normalize_sp500_holdings(payload: dict[str, Any]) -> pd.DataFrame:
    return normalize_ishares_equity_holdings(payload, "S&P 500")


def get_ishares_equity_holdings(
    url: str,
    universe_name: str,
) -> pd.DataFrame:
    request = Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except (OSError, ValueError) as exc:
        raise StockDataError(
            f"{universe_name} holdings could not be loaded from iShares: {exc}"
        ) from exc
    return normalize_ishares_equity_holdings(payload, universe_name)


def get_russell_2000_holdings() -> pd.DataFrame:
    return get_ishares_equity_holdings(IWM_HOLDINGS_API, "Russell 2000")


def get_sp500_holdings() -> pd.DataFrame:
    return get_ishares_equity_holdings(IVV_HOLDINGS_API, "S&P 500")


def normalize_european_holdings(
    holdings: pd.DataFrame,
    as_of_date: str,
) -> pd.DataFrame:
    columns = [
        "Symbol",
        "Name",
        "Country",
        "Sector",
        "Exchange",
        "Weight",
        "AsOfDate",
    ]
    required = {
        "Ticker",
        "Name",
        "Sector",
        "Asset Class",
        "Weight (%)",
        "Location",
        "Exchange",
    }
    if not required.issubset(holdings.columns):
        raise StockDataError(
            "The iShares Europe holdings CSV has an unexpected format."
        )

    rows = []
    parsed_date = pd.to_datetime(as_of_date, errors="raise").date()
    for record in holdings.to_dict("records"):
        exchange = str(record["Exchange"] or "").strip()
        suffix = EUROPE_EXCHANGE_SUFFIXES.get(exchange)
        ticker = str(record["Ticker"] or "").strip().upper()
        if record["Asset Class"] != "Equity" or not suffix or ticker in {"", "-"}:
            continue
        ticker = ticker.rstrip(".").replace(".", "-").replace(" ", "-")
        weight = pd.to_numeric(record["Weight (%)"], errors="coerce")
        if pd.isna(weight):
            continue
        rows.append(
            {
                "Symbol": f"{ticker}{suffix}",
                "Name": str(record["Name"] or ticker).strip(),
                "Country": str(record["Location"] or "").strip(),
                "Sector": str(record["Sector"] or "").strip(),
                "Exchange": exchange,
                "Weight": float(weight) / 100,
                "AsOfDate": parsed_date,
            }
        )
    return (
        pd.DataFrame(rows, columns=columns)
        .drop_duplicates(subset=["Symbol"])
        .reset_index(drop=True)
    )


def get_european_holdings() -> pd.DataFrame:
    request = Request(
        IEUR_HOLDINGS_CSV,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            text = response.read().decode("utf-8-sig")
        lines = text.splitlines()
        as_of_date = next(
            line.split(",", 1)[1].strip().strip('"')
            for line in lines[:10]
            if line.startswith("Fund Holdings as of,")
        )
        holdings = pd.read_csv(StringIO(text), skiprows=9)
    except (OSError, UnicodeError, ValueError, StopIteration, pd.errors.ParserError) as exc:
        raise StockDataError(
            f"European holdings could not be loaded from iShares: {exc}"
        ) from exc
    return normalize_european_holdings(holdings, as_of_date)


def _period_momentum(
    dates: pd.Series,
    now: pd.Timestamp,
) -> tuple[int, int, float | None]:
    normalized_dates = pd.to_datetime(dates, utc=True, errors="coerce").dropna()
    recent = int((normalized_dates >= now - pd.Timedelta(days=30)).sum())
    previous = int(
        (
            (normalized_dates < now - pd.Timedelta(days=30))
            & (normalized_dates >= now - pd.Timedelta(days=90))
        ).sum()
    )
    previous_monthly_rate = previous / 2
    momentum = (
        recent / previous_monthly_rate - 1
        if previous_monthly_rate > 0
        else (1.0 if recent > 0 else None)
    )
    return recent, previous, momentum


def _paced_google_trends_request(request: Callable[[], Any]) -> Any:
    from pytrends.exceptions import ResponseError

    global _google_trends_next_request, _google_trends_cooldown_until
    with _google_trends_lock:
        if time.monotonic() < _google_trends_cooldown_until:
            remaining = math.ceil(_google_trends_cooldown_until - time.monotonic())
            raise StockDataError(
                f"Google Trends is cooling down after HTTP 429. "
                f"Try refreshing in {remaining} seconds."
            )
        for attempt in range(len(GOOGLE_TRENDS_RETRY_DELAYS) + 1):
            delay = _google_trends_next_request - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            try:
                return request()
            except ResponseError as exc:
                if exc.response.status_code != 429:
                    raise
                retry_after = exc.response.headers.get("Retry-After")
                server_delay = 0.0
                if retry_after:
                    try:
                        server_delay = max(0.0, float(retry_after))
                    except ValueError:
                        try:
                            retry_date = parsedate_to_datetime(retry_after)
                        except (ValueError, TypeError, OverflowError):
                            retry_date = None
                        if retry_date is not None:
                            server_delay = max(0.0, retry_date.timestamp() - time.time())
                if (
                    attempt == len(GOOGLE_TRENDS_RETRY_DELAYS)
                    or server_delay > GOOGLE_TRENDS_RETRY_DELAYS[-1]
                ):
                    _google_trends_cooldown_until = time.monotonic() + max(
                        GOOGLE_TRENDS_COOLDOWN, server_delay,
                    )
                    raise StockDataError(
                        "Google Trends remains rate-limited (HTTP 429). Further "
                        "requests are paused for at least five minutes; try Refresh "
                        "data after the cooldown."
                    ) from exc
                _google_trends_next_request = time.monotonic() + max(
                    GOOGLE_TRENDS_RETRY_DELAYS[attempt], server_delay,
                )
            finally:
                _google_trends_next_request = max(
                    _google_trends_next_request,
                    time.monotonic() + GOOGLE_TRENDS_REQUEST_INTERVAL,
                )


def get_google_trends_signal(search_term: str) -> dict[str, Any]:
    try:
        from pytrends.exceptions import ResponseError
        from pytrends.request import TrendReq
        from requests.exceptions import RequestException as RequestsRequestException
    except ImportError as exc:
        raise StockDataError(
            "Google Trends support is unavailable; install the project requirements."
        ) from exc

    class PacedTrendReq(TrendReq):
        def GetGoogleCookie(self):
            return _paced_google_trends_request(super().GetGoogleCookie)

        def _get_data(self, *args, **kwargs):
            get_data = super()._get_data
            return _paced_google_trends_request(lambda: get_data(*args, **kwargs))

    def check_rate_limit(response, **kwargs):
        if response.status_code == 429:
            raise ResponseError.from_response(response)
        return response

    try:
        trends = PacedTrendReq(
            hl="en-US", tz=0, timeout=(10, 30),
            requests_args={"hooks": {"response": check_rate_limit}},
        )
        trends.build_payload([search_term], timeframe="today 12-m")
        interest = trends.interest_over_time()
    except (ResponseError, RequestsRequestException) as exc:
        raise StockDataError(
            f"Google Trends data for {search_term} could not be loaded: {exc}"
        ) from exc
    if interest.empty or search_term not in interest:
        raise StockDataError(f"Google Trends returned no data for {search_term}.")

    values = pd.to_numeric(interest[search_term], errors="coerce").dropna()
    median_spacing = values.index.to_series().diff().median()
    window = 28 if median_spacing <= pd.Timedelta(days=2) else 4
    if len(values) < window * 2:
        raise StockDataError(
            f"Google Trends returned insufficient history for {search_term}."
        )
    recent = float(values.tail(window).mean())
    previous = float(values.iloc[-window * 2:-window].mean())
    momentum = recent / previous - 1 if previous > 0 else (1.0 if recent > 0 else None)
    return {
        "Available": True,
        "CurrentInterest": recent,
        "PreviousInterest": previous,
        "Momentum": momentum,
        "Source": (
            "https://trends.google.com/trends/explore?"
            + urlencode({"q": search_term, "date": "today 12-m"})
        ),
    }


def get_news_volume_signal(search_term: str) -> dict[str, Any]:
    url = "https://news.google.com/rss/search?" + urlencode(
        {
            "q": f'"{search_term}" when:90d',
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
    )
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml"})
    try:
        with urlopen(request, timeout=30) as response:
            root = ElementTree.fromstring(response.read())
    except (OSError, ElementTree.ParseError) as exc:
        raise StockDataError(
            f"Recent news volume for {search_term} could not be loaded: {exc}"
        ) from exc
    dates = [
        parsedate_to_datetime(item.text)
        for item in root.findall("./channel/item/pubDate")
        if item.text
    ]
    recent, previous, momentum = _period_momentum(
        pd.Series(dates, dtype="object"),
        pd.Timestamp.now(tz="UTC"),
    )
    return {
        "Available": True,
        "RecentCount": recent,
        "PreviousCount": previous,
        "Momentum": momentum,
        "Source": url,
    }


def get_reddit_mention_signal(search_term: str) -> dict[str, Any]:
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        return {
            "Available": False,
            "Reason": (
                "Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET to enable official "
                "Reddit API data."
            ),
        }

    credentials = b64encode(f"{client_id}:{client_secret}".encode()).decode()
    token_request = Request(
        "https://www.reddit.com/api/v1/access_token",
        data=urlencode({"grant_type": "client_credentials"}).encode(),
        headers={
            "Authorization": f"Basic {credentials}",
            "User-Agent": "LocalStockResearch/1.0",
        },
    )
    try:
        with urlopen(token_request, timeout=30) as response:
            token = json.load(response)["access_token"]
        search_url = "https://oauth.reddit.com/search?" + urlencode(
            {
                "q": f'"{search_term}"',
                "sort": "new",
                "t": "year",
                "limit": 100,
                "type": "link",
            }
        )
        search_request = Request(
            search_url,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "LocalStockResearch/1.0",
            },
        )
        with urlopen(search_request, timeout=30) as response:
            payload = json.load(response)
    except (OSError, KeyError, ValueError, HTTPError) as exc:
        raise StockDataError(
            f"Reddit mentions for {search_term} could not be loaded: {exc}"
        ) from exc
    dates = [
        pd.Timestamp(child["data"]["created_utc"], unit="s", tz="UTC")
        for child in payload.get("data", {}).get("children", [])
        if child.get("data", {}).get("created_utc")
    ]
    recent, previous, momentum = _period_momentum(
        pd.Series(dates, dtype="object"),
        pd.Timestamp.now(tz="UTC"),
    )
    return {
        "Available": True,
        "RecentCount": recent,
        "PreviousCount": previous,
        "Momentum": momentum,
        "Source": "https://www.reddit.com/search/?" + urlencode({"q": search_term}),
    }


def summarize_fashion_signals(
    google: dict[str, Any],
    reddit: dict[str, Any],
    news: dict[str, Any],
) -> dict[str, Any]:
    declining_sources = []
    if (
        google.get("Available")
        and google.get("Momentum") is not None
        and google["Momentum"] <= -0.20
        and google.get("PreviousInterest", 0) >= 10
    ):
        declining_sources.append("Google Trends")
    if (
        reddit.get("Available")
        and reddit.get("Momentum") is not None
        and reddit["Momentum"] <= -0.25
        and reddit.get("PreviousCount", 0) >= 6
    ):
        declining_sources.append("Reddit")
    if (
        news.get("Available")
        and news.get("Momentum") is not None
        and news["Momentum"] <= -0.25
        and news.get("PreviousCount", 0) >= 6
    ):
        declining_sources.append("News")
    available_sources = sum(
        bool(signal.get("Available")) for signal in (google, reddit, news)
    )
    return {
        "AvailableSources": available_sources,
        "DecliningSources": ", ".join(declining_sources),
        "SignalCount": len(declining_sources),
        "Qualifies": available_sources >= 2 and len(declining_sources) >= 2,
    }


def analyze_fashion_downtrend(history: pd.DataFrame) -> dict[str, Any]:
    if "Close" not in history:
        raise StockDataError("Downtrend analysis requires closing prices.")
    closes = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if len(closes) < 200:
        raise StockDataError(
            "Downtrend analysis requires at least 200 daily closing prices."
        )
    recent_closes = closes.tail(200)
    if not recent_closes.map(
        lambda value: math.isfinite(value) and value > 0
    ).all():
        raise StockDataError(
            "Downtrend analysis requires finite, positive closing prices."
        )

    latest_close = float(recent_closes.iloc[-1])
    ma50 = float(recent_closes.tail(50).mean())
    ma200 = float(recent_closes.mean())
    below_ma200 = latest_close < ma200
    bearish_alignment = ma50 < ma200
    return {
        "LatestClose": latest_close,
        "MA50": ma50,
        "MA200": ma200,
        "BelowMA200": below_ma200,
        "MA50BelowMA200": bearish_alignment,
        "DowntrendQualifies": below_ma200 and bearish_alignment,
    }


def analyze_infrastructure_income(
    info: dict[str, Any],
    history: pd.DataFrame,
) -> dict[str, Any]:
    closes = pd.to_numeric(history.get("Close"), errors="coerce").dropna()
    if closes.empty:
        raise StockDataError("Infrastructure income analysis requires price history.")
    dividend_yield = pd.to_numeric(
        pd.Series([info.get("dividendYield")]),
        errors="coerce",
    ).iloc[0]
    earnings_payout = pd.to_numeric(
        pd.Series([info.get("payoutRatio")]),
        errors="coerce",
    ).iloc[0]
    dividend_rate = pd.to_numeric(
        pd.Series([info.get("dividendRate")]),
        errors="coerce",
    ).iloc[0]
    shares = pd.to_numeric(
        pd.Series([info.get("sharesOutstanding")]),
        errors="coerce",
    ).iloc[0]
    free_cash_flow = pd.to_numeric(
        pd.Series([info.get("freeCashflow")]),
        errors="coerce",
    ).iloc[0]
    fcf_payout = (
        float(dividend_rate * shares / free_cash_flow)
        if pd.notna(dividend_rate)
        and pd.notna(shares)
        and pd.notna(free_cash_flow)
        and free_cash_flow > 0
        else None
    )
    if pd.notna(earnings_payout) and earnings_payout >= 0:
        coverage_ratio = float(earnings_payout)
        coverage_basis = "Earnings payout ratio"
    else:
        coverage_ratio = fcf_payout
        coverage_basis = "Dividend / free cash flow"
    distance_to_high = float(closes.iloc[-1] / closes.max() - 1)
    yield_value = float(dividend_yield) if pd.notna(dividend_yield) else None
    qualifies = (
        yield_value is not None
        and yield_value > 4.0
        and coverage_ratio is not None
        and coverage_ratio <= 0.80
        and distance_to_high <= -0.05
    )
    exclusion_reasons = []
    if yield_value is None:
        exclusion_reasons.append("Forward yield unavailable")
    elif yield_value <= 4.0:
        exclusion_reasons.append("Forward yield must exceed 4%")
    if coverage_ratio is None:
        exclusion_reasons.append("Payout / coverage unavailable")
    elif coverage_ratio > 0.80:
        exclusion_reasons.append("Payout / coverage exceeds 80%")
    if distance_to_high > -0.05:
        exclusion_reasons.append("Price is less than 5% below five-year high")
    return {
        "DividendYield": yield_value,
        "DividendCoverageRatio": coverage_ratio,
        "CoverageBasis": coverage_basis if coverage_ratio is not None else None,
        "DistanceToFiveYearHigh": distance_to_high,
        "Qualifies": qualifies,
        "ExclusionReason": "; ".join(exclusion_reasons),
    }


def revenue_growth_summary(info: dict[str, Any]) -> dict[str, Any]:
    growth = info.get("revenueGrowth")
    numeric_growth = (
        float(growth)
        if growth is not None and pd.notna(growth)
        else None
    )
    reference = format_value(info.get("mostRecentQuarter"), "date")
    return {
        "RevenueGrowth": numeric_growth,
        "RevenuePeriod": (
            f"Provider reference: {reference}"
            if reference != "N/A"
            else "Provider period unavailable"
        ),
        "TotalRevenue": info.get("totalRevenue"),
    }


@lru_cache(maxsize=1)
def get_sec_ticker_ciks() -> dict[str, str]:
    request = Request(SEC_TICKERS_API, headers=SEC_HEADERS)
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (OSError, ValueError) as exc:
        raise StockDataError(f"SEC ticker mapping could not be loaded: {exc}") from exc
    return {
        str(row["ticker"]).upper().replace(".", "-"): f"{int(row['cik_str']):010d}"
        for row in payload.values()
        if row.get("ticker") and row.get("cik_str")
    }


def normalize_sec_quarterly_revenue(payload: dict[str, Any]) -> pd.DataFrame:
    columns = ["Period", "Revenue"]
    facts = payload.get("facts", {}).get("us-gaap", {})
    candidates = []
    for tag in SEC_REVENUE_TAGS:
        entries = facts.get(tag, {}).get("units", {}).get("USD", [])
        relevant = [
            entry
            for entry in entries
            if entry.get("form") in {"10-Q", "10-Q/A", "10-K", "10-K/A"}
            and entry.get("start")
            and entry.get("end")
            and entry.get("val") is not None
            and pd.notna(pd.to_datetime(entry["start"], errors="coerce"))
            and pd.notna(pd.to_datetime(entry["end"], errors="coerce"))
        ]
        if relevant:
            candidates.append((max(entry["end"] for entry in relevant), relevant))
    if not candidates:
        return pd.DataFrame(columns=columns)
    entries = max(candidates, key=lambda item: item[0])[1]

    # SEC fy/fp describe the filing, not necessarily the comparative fact's period.
    periods: dict[tuple[pd.Timestamp, pd.Timestamp], dict[str, Any]] = {}
    for entry in entries:
        start = pd.to_datetime(entry["start"], errors="coerce")
        end = pd.to_datetime(entry["end"], errors="coerce")
        filed = str(entry.get("filed") or "")
        key = (start, end)
        if key not in periods or filed > periods[key]["Filed"]:
            periods[key] = {
                "Start": start, "Period": end,
                "Revenue": float(entry["val"]), "Filed": filed,
            }

    direct = [
        row for row in periods.values()
        if 70 <= (row["Period"] - row["Start"]).days <= 110
    ]
    annual = [
        row for row in periods.values()
        if 330 <= (row["Period"] - row["Start"]).days <= 400
    ]
    rows = list(direct)
    for year in annual:
        if any(row["Period"] == year["Period"] for row in direct):
            continue
        nine_months = [
            row for row in periods.values()
            if row["Start"] == year["Start"]
            and 240 <= (row["Period"] - row["Start"]).days <= 300
            and 70 <= (year["Period"] - row["Period"]).days <= 110
        ]
        if nine_months:
            first_three_revenue = max(nine_months, key=lambda row: row["Filed"])["Revenue"]
        else:
            first_three = sorted(
                [
                    row for row in direct
                    if year["Start"] <= row["Start"]
                    and row["Period"] < year["Period"]
                ],
                key=lambda row: row["Period"],
            )
            if (
                len(first_three) != 3
                or abs((first_three[0]["Start"] - year["Start"]).days) > 7
                or not 70 <= (year["Period"] - first_three[-1]["Period"]).days <= 110
                or any(
                    not 0 < (right["Start"] - left["Period"]).days <= 7
                    for left, right in zip(first_three, first_three[1:])
                )
            ):
                continue
            first_three_revenue = sum(row["Revenue"] for row in first_three)
        rows.append({
            "Period": year["Period"],
            "Revenue": year["Revenue"] - first_three_revenue,
            "Filed": year["Filed"],
        })
    if not rows:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame(rows)
        .sort_values(["Period", "Filed"], kind="stable")
        .drop_duplicates(subset=["Period"], keep="last")
        .loc[:, columns]
        .reset_index(drop=True)
    )


def get_sec_quarterly_revenue(symbol: str) -> pd.DataFrame:
    cik = get_sec_ticker_ciks().get(symbol.upper().replace(".", "-"))
    if not cik:
        return pd.DataFrame(columns=["Period", "Revenue"])
    request = Request(SEC_COMPANY_FACTS_API.format(cik=cik), headers=SEC_HEADERS)
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (OSError, ValueError) as exc:
        raise StockDataError(f"SEC revenue history for {symbol} could not be loaded: {exc}") from exc
    return normalize_sec_quarterly_revenue(payload)


def rolling_revenue_growth_history(quarterly: pd.DataFrame) -> pd.DataFrame:
    columns = ["Period", "RollingRevenue", "RevenueGrowth"]
    if quarterly.empty:
        return pd.DataFrame(columns=columns)
    history = quarterly.loc[:, ["Period", "Revenue"]].copy()
    history = history.sort_values("Period", kind="stable").drop_duplicates("Period", keep="last")
    consecutive = history["Period"].diff().dt.days.between(70, 110)
    history["RollingRevenue"] = history["Revenue"].rolling(4, min_periods=4).sum()
    history["RollingRevenue"] = history["RollingRevenue"].where(
        consecutive.rolling(3, min_periods=3).sum().eq(3)
    )
    comparable = (
        consecutive.rolling(7, min_periods=7).sum().eq(7)
        & history["Period"].diff(4).dt.days.between(330, 400)
    )
    previous = history["RollingRevenue"].shift(4)
    history["RevenueGrowth"] = (history["RollingRevenue"] / previous - 1).where(
        comparable & previous.gt(0)
    )
    return history.loc[:, columns].reset_index(drop=True)


def merge_quarterly_revenue_histories(
    historical: pd.DataFrame,
    recent: pd.DataFrame,
) -> pd.DataFrame:
    columns = ["Period", "Revenue"]
    available = [
        frame.loc[:, columns]
        for frame in (historical, recent)
        if not frame.empty and set(columns).issubset(frame.columns)
    ]
    if not available:
        return pd.DataFrame(columns=columns)
    if len(available) == 2:
        historical, recent = available
        # Fiscal week-end dates and provider calendar-end dates can differ slightly.
        same_recent_period = historical["Period"].map(
            lambda period: (recent["Period"] - period).abs().le(pd.Timedelta(days=7)).any()
        )
        available = [historical.loc[~same_recent_period], recent]
    return (
        pd.concat(available, ignore_index=True)
        .sort_values("Period", kind="stable")
        .drop_duplicates(subset=["Period"], keep="last")
        .reset_index(drop=True)
    )


def statement_revenue_growth_summary(
    quarterly: pd.DataFrame,
    annual: pd.DataFrame,
) -> dict[str, Any]:
    unavailable = {
        "RevenueGrowth": None,
        "RevenuePeriod": "Statement growth unavailable",
        "TotalRevenue": None,
        "RevenueAccelerating": False,
        "RevenueGrowthTrend": "Unavailable",
        "RevenueBasis": "Unavailable",
        "PriorRollingRevenue": None,
        "PriorRollingPeriod": None,
        "RevenueGrowthHistory": [],
    }
    rolling = rolling_revenue_growth_history(quarterly)
    if not rolling.empty and pd.notna(rolling.iloc[-1]["RevenueGrowth"]):
        latest = rolling.iloc[-1]
        recent_growth = rolling["RevenueGrowth"].tail(3).astype(float).tolist()
        accelerating = (
            len(recent_growth) == 3
            and recent_growth[-1] > 0
            and recent_growth[0] < recent_growth[1] < recent_growth[2]
        )
        return {
            "RevenueGrowth": float(latest["RevenueGrowth"]),
            "RevenuePeriod": f"Four quarters ended {latest['Period']:%Y-%m-%d} (YoY)",
            "TotalRevenue": float(latest["RollingRevenue"]),
            "RevenueBasis": "Rolling four quarters",
            "PriorRollingRevenue": float(rolling.iloc[-5]["RollingRevenue"]),
            "PriorRollingPeriod": f"{rolling.iloc[-5]['Period']:%Y-%m-%d}",
            "RevenueAccelerating": accelerating,
            "RevenueGrowthTrend": " -> ".join(
                f"{growth:.1%}" if pd.notna(growth) else "Unavailable"
                for growth in recent_growth
            ),
            "RevenueGrowthHistory": rolling.tail(3).to_dict("records"),
        }

    if annual.empty:
        return unavailable
    annual_with_growth = annual.dropna(subset=["Growth"])
    if annual_with_growth.empty:
        return unavailable
    latest = annual_with_growth.iloc[-1]
    return {
        "RevenueGrowth": float(latest["Growth"]),
        "RevenuePeriod": f"Fiscal year ended {latest['Period']:%Y-%m-%d} (YoY)",
        "TotalRevenue": float(latest["Revenue"]),
        "RevenueBasis": "Fiscal-year fallback",
        "PriorRollingRevenue": None,
        "PriorRollingPeriod": None,
        "RevenueAccelerating": False,
        "RevenueGrowthTrend": f"{float(latest['Growth']):.1%}",
        "RevenueGrowthHistory": [],
    }


def get_revenue_growth_scan(
    symbols: list[str], *,
    sec_loader: Callable[[str], pd.DataFrame] | None = None,
    financial_loader: Callable[[str, str], pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Scan statement growth, optionally reusing cached source histories."""
    load_sec = sec_loader if sec_loader is not None else get_sec_quarterly_revenue
    load_financials = financial_loader if financial_loader is not None else get_financial_history
    rows = []
    for symbol in sorted(set(symbols)):
        try:
            historical_quarters = load_sec(symbol)
        except StockDataError:
            historical_quarters = pd.DataFrame()
        try:
            recent_quarters = load_financials(symbol, "quarterly")
        except StockDataError:
            recent_quarters = pd.DataFrame()
        quarterly = merge_quarterly_revenue_histories(
            historical_quarters,
            recent_quarters,
        )
        try:
            annual = load_financials(symbol, "annual")
        except StockDataError:
            annual = pd.DataFrame()
        rows.append(
            {
                "Symbol": symbol,
                **statement_revenue_growth_summary(quarterly, annual),
            }
        )
    return pd.DataFrame(rows)


def _finite_number(value: Any) -> float:
    if isinstance(value, (Real, Decimal, str)) and not pd.api.types.is_bool(value):
        try:
            number = float(value)
        except (ValueError, TypeError, OverflowError):
            return float("nan")
        if math.isfinite(number):
            return number
    return float("nan")


def company_screening_metrics(info: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for source, field in (
        ("shortPercentOfFloat", "ShortPercentOfFloat"),
        ("enterpriseToRevenue", "EnterpriseToRevenue"),
        ("floatShares", "FloatShares"),
        ("sharesOutstanding", "SharesOutstanding"),
        ("trailingPE", "TrailingPE"),
    ):
        metrics[field] = _finite_number(info.get(source))
    floating, outstanding = metrics["FloatShares"], metrics["SharesOutstanding"]
    metrics["FloatPercentOfSharesOutstanding"] = float("nan")
    if not (math.isfinite(floating) and math.isfinite(outstanding) and floating > 0 and outstanding > 0):
        reason = "Unavailable: float and shares outstanding must both be positive finite share counts."
    elif floating > outstanding:
        reason = "Unavailable: reported float exceeds shares outstanding; share bases may be inconsistent."
    else:
        metrics["FloatPercentOfSharesOutstanding"] = floating / outstanding
        reason = "Calculated from provider floatShares / sharesOutstanding; share-count dates and bases are not independently verified."
    metrics["FloatDataReason"] = reason
    metrics["CompanyMetricSource"] = "Yahoo Finance company metadata (24-hour cache)"
    return metrics


def get_company_info(symbol: str) -> dict[str, Any]:
    try:
        info = yf.Ticker(symbol).info
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(f"Company information for {symbol} could not be loaded: {exc}") from exc

    if not isinstance(info, dict) or not info:
        raise StockDataError(f"No company information was returned for {symbol}.")
    return info


def normalize_etf_holdings(holdings: pd.DataFrame) -> pd.DataFrame:
    columns = ["Symbol", "Name", "Weight"]
    if not isinstance(holdings, pd.DataFrame) or holdings.empty:
        return pd.DataFrame(columns=columns)
    required_columns = {"Name", "Holding Percent"}
    if not required_columns.issubset(holdings.columns):
        missing = ", ".join(sorted(required_columns.difference(holdings.columns)))
        raise StockDataError(f"ETF holdings data is missing: {missing}.")

    normalized = holdings.loc[:, ["Name", "Holding Percent"]].copy()
    normalized.insert(0, "Symbol", normalized.index.astype(str))
    normalized = normalized.rename(columns={"Holding Percent": "Weight"})
    normalized["Weight"] = pd.to_numeric(normalized["Weight"], errors="coerce")
    return normalized.dropna(subset=["Weight"]).reset_index(drop=True)


def get_etf_holdings(symbol: str) -> pd.DataFrame:
    try:
        holdings = yf.Ticker(symbol).funds_data.top_holdings
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(
            f"Holdings for {symbol} could not be loaded: {exc}"
        ) from exc
    return normalize_etf_holdings(holdings)


def normalize_insider_buys(
    transactions: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
    months: int = 6,
) -> pd.DataFrame:
    columns = [
        "Date",
        "Insider",
        "Position",
        "Shares",
        "Value",
        "Details",
        "FilingURL",
    ]
    if transactions is None or transactions.empty:
        return pd.DataFrame(columns=columns)
    required = {"Start Date", "Text", "Insider", "Shares"}
    if not required.issubset(transactions.columns):
        raise StockDataError("Insider transaction data has an unexpected format.")

    reference = as_of if as_of is not None else pd.Timestamp.now(tz="UTC")
    reference = pd.Timestamp(reference)
    if reference.tzinfo is not None:
        reference = reference.tz_localize(None)
    cutoff = reference.normalize() - pd.DateOffset(months=months)

    normalized = transactions.copy()
    normalized["Date"] = pd.to_datetime(
        normalized["Start Date"],
        errors="coerce",
    ).dt.tz_localize(None)
    normalized["Details"] = normalized["Text"].fillna("").astype(str)
    normalized = normalized.loc[
        normalized["Details"].str.match(r"^Purchase at price", case=False)
        & normalized["Date"].between(cutoff, reference.normalize())
    ].copy()
    if normalized.empty:
        return pd.DataFrame(columns=columns)

    normalized["Shares"] = pd.to_numeric(normalized["Shares"], errors="coerce")
    normalized["Value"] = pd.to_numeric(
        normalized.get("Value", pd.Series(index=normalized.index, dtype=float)),
        errors="coerce",
    )
    normalized["Position"] = normalized.get(
        "Position",
        pd.Series(index=normalized.index, dtype="object"),
    ).fillna("")
    normalized["FilingURL"] = normalized.get(
        "URL",
        pd.Series(index=normalized.index, dtype="object"),
    ).fillna("")
    return (
        normalized.loc[:, columns]
        .sort_values("Date", ascending=False)
        .reset_index(drop=True)
    )


def get_recent_insider_buys(symbol: str, months: int = 6) -> pd.DataFrame:
    try:
        transactions = yf.Ticker(symbol).insider_transactions
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(
            f"Insider transactions for {symbol} could not be loaded: {exc}"
        ) from exc
    return normalize_insider_buys(transactions, months=months)


def summarize_insider_buys(buys: pd.DataFrame) -> dict[str, Any]:
    if buys.empty:
        return {
            "InsiderBuyCount": 0,
            "InsiderBuyShares": 0.0,
            "InsiderBuyValue": 0.0,
            "LatestInsiderBuy": pd.NaT,
        }
    return {
        "InsiderBuyCount": len(buys),
        "InsiderBuyShares": float(buys["Shares"].fillna(0).sum()),
        "InsiderBuyValue": float(buys["Value"].fillna(0).sum()),
        "LatestInsiderBuy": buys["Date"].max(),
    }


def get_stock_catalyst_data(symbol: str) -> dict[str, Any]:
    ticker = yf.Ticker(symbol)
    try:
        return normalize_stock_catalyst_data(
            ticker.calendar,
            ticker.earnings_estimate,
            ticker.revenue_estimate,
            ticker.eps_trend,
            ticker.eps_revisions,
            ticker.upgrades_downgrades,
        )
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(
            f"Catalyst data for {symbol} could not be loaded: {exc}"
        ) from exc


def normalize_company_developments(news: list[dict[str, Any]]) -> pd.DataFrame:
    columns = ["Date", "Title", "Summary", "Provider", "URL"]
    rows = []
    for item in news or []:
        content = item.get("content", item) if isinstance(item, dict) else {}
        if not isinstance(content, dict):
            continue
        title = str(content.get("title") or "").replace("\ufffd", "").strip()
        published = pd.to_datetime(
            content.get("pubDate") or content.get("displayTime"),
            errors="coerce",
            utc=True,
        )
        if not title or pd.isna(published):
            continue
        provider = content.get("provider") or {}
        canonical_url = content.get("canonicalUrl") or {}
        rows.append(
            {
                "Date": published.tz_convert(None),
                "Title": title,
                "Summary": (
                    str(content.get("summary") or "").replace("\ufffd", "").strip()
                ),
                "Provider": (
                    str(provider.get("displayName") or "").strip()
                    if isinstance(provider, dict)
                    else ""
                ),
                "URL": (
                    str(canonical_url.get("url") or "").strip()
                    if isinstance(canonical_url, dict)
                    else ""
                ),
            }
        )
    if not rows:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values("Date", ascending=False)
        .drop_duplicates(subset=["Title"])
        .reset_index(drop=True)
    )


def get_company_developments(symbol: str) -> pd.DataFrame:
    try:
        news = yf.Ticker(symbol).get_news(count=100, tab="press releases")
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(
            f"Recent company developments for {symbol} could not be loaded: {exc}"
        ) from exc
    return normalize_company_developments(news)


def company_name_identifiers(info: dict[str, Any]) -> list[str]:
    generic_words = {
        "and",
        "company",
        "corporation",
        "energy",
        "financial",
        "global",
        "group",
        "holdings",
        "inc",
        "incorporated",
        "limited",
        "llc",
        "plc",
        "resources",
        "services",
        "systems",
        "technologies",
        "the",
        "water",
    }
    identifiers = []
    for key in ("longName", "shortName"):
        words = re.findall(r"[a-z0-9]+", str(info.get(key) or "").lower())
        meaningful = [word for word in words if word not in generic_words]
        if meaningful:
            identifiers.append(" ".join(meaningful))
            identifiers.extend(
                word for word in meaningful if len(word) >= 5
            )
    symbol = str(info.get("symbol") or "").strip().lower()
    if symbol:
        identifiers.append(symbol)
    return sorted(set(identifiers), key=len, reverse=True)


def generate_revenue_acceleration_reasons(
    info: dict[str, Any],
    developments: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
) -> list[dict[str, str]]:
    if developments.empty:
        return []
    reference = pd.Timestamp(as_of or datetime.now(timezone.utc))
    if reference.tzinfo is not None:
        reference = reference.tz_localize(None)
    cutoff = reference.normalize() - pd.DateOffset(years=1)
    identifiers = company_name_identifiers(info)
    if not identifiers:
        return []

    healthcare = (
        str(info.get("sector") or "").lower() == "healthcare"
        or any(
            term in str(info.get("industry") or "").lower()
            for term in ("biotech", "drug", "pharma")
        )
    )
    rules = [
        {
            "Reason": "A new contract or award could add revenue backlog",
            "Primary": r"\b(contract|task order|award(?:ed)?)\b",
            "Support": (
                r"\b(government|federal|department|army|navy|air force|defen[cs]e|"
                r"ministry|million|billion|multi-year)\b"
            ),
            "Why": (
                "The reported award creates a concrete customer commitment that "
                "can convert into recognized revenue as work is delivered."
            ),
            "Watch": "Contract start, funded value, delivery milestones, and backlog conversion.",
            "HealthcareOnly": False,
            "Exclude": None,
        },
        {
            "Reason": "A late-stage pipeline or regulatory milestone could enable future sales",
            "Primary": r"\b(phase 3|phase iii|fda|approval|approved|authorization)\b",
            "Support": r"\b(positive|met .*endpoint|approved|accepted|granted|authorized)\b",
            "Why": (
                "Positive late-stage or regulatory progress materially improves the "
                "path toward commercialization, although approval and uptake remain uncertain."
            ),
            "Watch": "Regulatory filing or decision, launch timing, label, pricing, and adoption.",
            "HealthcareOnly": True,
            "Exclude": r"\b(did not|failed|missed)\b",
        },
        {
            "Reason": "A completed acquisition could add an incremental revenue stream",
            "Primary": r"\b(completes? (?:the )?acquisition|acquires?|acquired)\b",
            "Support": r"\b(acquisition|business|company|assets)\b",
            "Why": (
                "A completed acquisition adds an operating business or assets whose "
                "sales can enter the acquirer's reported revenue."
            ),
            "Watch": "Closing contribution, purchase accounting, retention, and integration.",
            "HealthcareOnly": False,
            "Exclude": r"\b(plans?|proposed|intends?|agreement to acquire)\b",
        },
        {
            "Reason": "New production capacity could support higher sales volumes",
            "Primary": r"\b(opens?|inaugurates?|begins production|completed)\b",
            "Support": r"\b(factory|facility|manufacturing|production|capacity|plant)\b",
            "Why": (
                "Operational capacity coming online can remove a physical constraint "
                "on shipments if customer demand is present."
            ),
            "Watch": "Ramp utilization, customer orders, yields, and incremental margins.",
            "HealthcareOnly": False,
            "Exclude": r"\b(plans?|planned|proposed|expects?|will|to open)\b",
        },
        {
            "Reason": "A concrete commercial launch could open a new revenue source",
            "Primary": r"\b(commercial launch|launches|general availability)\b",
            "Support": r"\b(customer|commercial|market|orders?|sales)\b",
            "Why": (
                "The product has moved from development into commercial availability, "
                "creating a specific route to customer revenue."
            ),
            "Watch": "Bookings, paying customers, pricing, repeat demand, and disclosed sales.",
            "HealthcareOnly": False,
            "Exclude": (
                r"\b(prepar(?:e[sd]?|ing)|plans?|planned|expects?|will|to launch)\b"
            ),
        },
    ]

    reasons = []
    used_reasons = set()
    recent = developments.loc[
        pd.to_datetime(developments["Date"], errors="coerce") >= cutoff
    ]
    for row in recent.itertuples(index=False):
        title = str(row.Title)
        normalized_title = " ".join(re.findall(r"[a-z0-9]+", title.lower()))
        if not any(identifier in normalized_title for identifier in identifiers):
            continue
        evidence = f"{title} {row.Summary}".lower()
        for rule in rules:
            if rule["Reason"] in used_reasons:
                continue
            if rule["HealthcareOnly"] and not healthcare:
                continue
            if rule["Exclude"] and re.search(
                rule["Exclude"],
                title,
                flags=re.IGNORECASE,
            ):
                continue
            if not re.search(rule["Primary"], evidence, flags=re.IGNORECASE):
                continue
            if not re.search(rule["Support"], evidence, flags=re.IGNORECASE):
                continue
            reasons.append(
                {
                    "Reason": rule["Reason"],
                    "Why": rule["Why"],
                    "Watch": rule["Watch"],
                    "Evidence": title,
                    "Date": pd.Timestamp(row.Date).strftime("%Y-%m-%d"),
                    "Provider": str(row.Provider or "Source"),
                    "URL": str(row.URL or ""),
                }
            )
            used_reasons.add(rule["Reason"])
            break
        if len(reasons) == 3:
            break
    return reasons


def normalize_stock_catalyst_data(
    calendar: dict[str, Any] | None,
    earnings_estimate: pd.DataFrame,
    revenue_estimate: pd.DataFrame,
    eps_trend: pd.DataFrame,
    eps_revisions: pd.DataFrame,
    upgrades_downgrades: pd.DataFrame,
) -> dict[str, Any]:
    calendar = calendar if isinstance(calendar, dict) else {}
    events = []
    earnings_dates = calendar.get("Earnings Date") or []
    if not isinstance(earnings_dates, list):
        earnings_dates = [earnings_dates]
    valid_earnings_dates = [
        pd.Timestamp(value).date()
        for value in earnings_dates
        if value is not None
    ]
    if valid_earnings_dates:
        events.append(
            {
                "Event": "Earnings announcement",
                "Date": " to ".join(
                    date.isoformat() for date in valid_earnings_dates
                ),
                "Details": "Provider estimate; the company may change the date.",
            }
        )
    for key, label in (
        ("Ex-Dividend Date", "Ex-dividend date"),
        ("Dividend Date", "Dividend payment date"),
    ):
        value = calendar.get(key)
        if value is not None:
            events.append(
                {
                    "Event": label,
                    "Date": pd.Timestamp(value).date().isoformat(),
                    "Details": "Provider-reported scheduled date.",
                }
            )

    def frame_value(
        frame: pd.DataFrame,
        period: str,
        column: str,
    ) -> float | None:
        if (
            frame.empty
            or period not in frame.index
            or column not in frame.columns
        ):
            return None
        value = pd.to_numeric(
            pd.Series([frame.loc[period, column]]),
            errors="coerce",
        ).iloc[0]
        return float(value) if pd.notna(value) else None

    expectations = []
    for period, label in (("0q", "Current quarter"), ("+1q", "Next quarter")):
        revenue_growth = frame_value(revenue_estimate, period, "growth")
        earnings_growth = frame_value(earnings_estimate, period, "growth")
        eps_current = frame_value(eps_trend, period, "current")
        eps_30d = frame_value(eps_trend, period, "30daysAgo")
        revisions_up = frame_value(eps_revisions, period, "upLast30days")
        revisions_down = frame_value(eps_revisions, period, "downLast30days")
        if any(
            value is not None
            for value in (
                revenue_growth,
                earnings_growth,
                eps_current,
                eps_30d,
                revisions_up,
                revisions_down,
            )
        ):
            expectations.append(
                {
                    "Period": label,
                    "RevenueGrowth": revenue_growth,
                    "EarningsGrowth": earnings_growth,
                    "EPSCurrent": eps_current,
                    "EPS30DaysAgo": eps_30d,
                    "RevisionsUp30Days": revisions_up,
                    "RevisionsDown30Days": revisions_down,
                }
            )

    rating_actions = []
    if not upgrades_downgrades.empty:
        actions = upgrades_downgrades.copy()
        actions.index = pd.to_datetime(actions.index, errors="coerce")
        actions = actions.loc[actions.index.notna()].sort_index(ascending=False)
        for date, action in actions.head(10).iterrows():
            rating_actions.append(
                {
                    "Date": date.date().isoformat(),
                    "Firm": action.get("Firm"),
                    "Action": action.get("Action"),
                    "From": action.get("FromGrade"),
                    "To": action.get("ToGrade"),
                }
            )
    return {
        "Events": events,
        "Expectations": expectations,
        "RatingActions": rating_actions,
    }


def generate_stock_catalysts(
    info: dict[str, Any],
    annual_financials: pd.DataFrame,
    quarterly_financials: pd.DataFrame,
    catalyst_data: dict[str, Any],
) -> list[dict[str, str]]:
    catalysts = []
    expectations = catalyst_data.get("Expectations", [])
    current_quarter = next(
        (
            row
            for row in expectations
            if row["Period"] == "Current quarter"
        ),
        None,
    )
    if current_quarter:
        up = current_quarter["RevisionsUp30Days"] or 0
        down = current_quarter["RevisionsDown30Days"] or 0
        current_eps = current_quarter["EPSCurrent"]
        prior_eps = current_quarter["EPS30DaysAgo"]
        if up > down or (
            current_eps is not None
            and prior_eps is not None
            and current_eps > prior_eps
        ):
            catalysts.append(
                {
                    "Catalyst": "Improving earnings expectations",
                    "Evidence": (
                        f"Thirty-day EPS revisions include {up:.0f} upward versus "
                        f"{down:.0f} downward changes."
                    ),
                    "Watch": "Whether revisions remain positive into the next report.",
                }
            )
        revenue_growth = current_quarter["RevenueGrowth"]
        if revenue_growth is not None and revenue_growth >= 0.08:
            catalysts.append(
                {
                    "Catalyst": "Consensus revenue acceleration",
                    "Evidence": (
                        f"Analysts currently estimate {revenue_growth:.1%} "
                        "year-over-year revenue growth for the current quarter."
                    ),
                    "Watch": "Reported revenue and forward guidance versus consensus.",
                }
            )

    if len(quarterly_financials) >= 5:
        latest = float(quarterly_financials["Revenue"].iloc[-1])
        prior_year = float(quarterly_financials["Revenue"].iloc[-5])
        annual_growth = (
            annual_financials["Growth"].iloc[-1]
            if not annual_financials.empty
            else None
        )
        if prior_year and pd.notna(annual_growth):
            quarterly_yoy = latest / prior_year - 1
            if quarterly_yoy > float(annual_growth) + 0.03:
                catalysts.append(
                    {
                        "Catalyst": "Reported revenue acceleration",
                        "Evidence": (
                            f"Latest quarterly revenue grew {quarterly_yoy:.1%} "
                            f"year over year versus {float(annual_growth):.1%} "
                            "in the latest fiscal year."
                        ),
                        "Watch": "Whether the acceleration persists in the next quarter.",
                    }
                )

    earnings_events = [
        event
        for event in catalyst_data.get("Events", [])
        if event["Event"] == "Earnings announcement"
    ]
    if earnings_events:
        catalysts.append(
            {
                "Catalyst": "Upcoming earnings checkpoint",
                "Evidence": f"Estimated announcement window: {earnings_events[0]['Date']}.",
                "Watch": "Revenue, margins, guidance, and estimate revisions after results.",
            }
        )
    return catalysts


def get_statement_history(symbol: str, statement: str, frequency: str) -> pd.DataFrame:
    """Return an unmodified Yahoo income, cash-flow, or balance-sheet frame."""
    attributes = {
        "income": ("quarterly_income_stmt", "income_stmt"),
        "cashflow": ("quarterly_cashflow", "cashflow"),
        "balance": ("quarterly_balance_sheet", "balance_sheet"),
    }
    if statement not in attributes:
        raise ValueError("Statement must be 'income', 'cashflow', or 'balance'.")
    if frequency not in {"annual", "quarterly"}:
        raise ValueError("Statement frequency must be 'annual' or 'quarterly'.")
    try:
        ticker = yf.Ticker(symbol)
        attribute = attributes[statement][0 if frequency == "quarterly" else 1]
        return getattr(ticker, attribute)
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(
            f"{frequency.title()} {statement} statement for {symbol} could not be loaded: {exc}"
        ) from exc


def get_financial_history(
    symbol: str, frequency: str, *,
    statement_loader: Callable[[str, str, str], pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Extract revenue and costs using an optionally shared raw income loader."""
    if frequency not in {"annual", "quarterly"}:
        raise ValueError("Financial frequency must be 'annual' or 'quarterly'.")

    loader = statement_loader if statement_loader is not None else get_statement_history
    try:
        statement = loader(symbol, "income", frequency)
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(
            f"{frequency.title()} financials for {symbol} could not be loaded: {exc}"
        ) from exc
    return extract_financial_history(statement)


def get_revenue_history(symbol: str, frequency: str) -> pd.DataFrame:
    return get_financial_history(symbol, frequency).loc[
        :, ["Period", "Revenue", "Growth"]
    ]


def get_cashflow_history(
    symbol: str, frequency: str, *,
    statement_loader: Callable[[str, str, str], pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Return cash flows using an optionally shared raw statement loader."""
    if frequency not in {"quarterly", "annual"}:
        raise ValueError("Cash-flow frequency must be 'quarterly' or 'annual'.")
    loader = statement_loader if statement_loader is not None else get_statement_history
    try:
        return loader(symbol, "cashflow", frequency)
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(f"Cash-flow data for {symbol} could not be loaded: {exc}") from exc


def _current_capital_returns(
    symbol: str, include_dividends: bool, as_of: str | pd.Timestamp | None,
    cashflow_loader: Callable[[str, str], pd.DataFrame] | None,
) -> dict[str, Any] | None:
    today = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz="UTC")
    today = today.tz_localize(None).normalize()
    loader = cashflow_loader or get_cashflow_history
    for frequency, periods, label, maximum_age in (
        ("quarterly", 4, "TTM", 200), ("annual", 1, "Fiscal year", 550),
    ):
        result = _extract_capital_returns(loader(symbol, frequency), periods, label, include_dividends)
        if result is not None and 0 <= (today - pd.Timestamp(result["PeriodEnd"])).days <= maximum_age:
            return result
    return None


def get_net_buybacks(
    symbol: str, *, as_of: str | pd.Timestamp | None = None,
    cashflow_loader: Callable[[str, str], pd.DataFrame] | None = None,
) -> dict[str, Any] | None:
    return _current_capital_returns(symbol, False, as_of, cashflow_loader)


def get_shareholder_yield(
    symbol: str, market_cap: float | int | None, *,
    as_of: str | pd.Timestamp | None = None,
    cashflow_loader: Callable[[str, str], pd.DataFrame] | None = None,
) -> dict[str, Any] | None:
    market_cap = _finite_number(market_cap)
    if not math.isfinite(market_cap) or market_cap <= 0:
        return None
    data = _current_capital_returns(symbol, True, as_of, cashflow_loader)
    if data is None:
        return None
    return {**data, "MarketCap": market_cap, "ShareholderYield": data["TotalReturned"] / market_cap}


def _extract_capital_returns(
    cashflow: pd.DataFrame, periods: int, period_name: str, include_dividends: bool,
) -> dict[str, Any] | None:
    if not isinstance(cashflow, pd.DataFrame) or cashflow.empty or periods <= 0 or cashflow.index.has_duplicates:
        return None

    if "Net Common Stock Issuance" in cashflow.index:
        net_issuance = cashflow.loc["Net Common Stock Issuance"].map(_finite_number)
        method = "Negative of reported Net Common Stock Issuance."
    elif {"Repurchase Of Capital Stock", "Issuance Of Capital Stock"}.issubset(cashflow.index):
        repurchases = cashflow.loc["Repurchase Of Capital Stock"].map(_finite_number)
        issuance = cashflow.loc["Issuance Of Capital Stock"].map(_finite_number)
        net_issuance = repurchases.where(repurchases <= 0) + issuance.where(issuance >= 0)
        method = "Reported repurchase cash outflows minus reported cash proceeds from share issuance."
    else:
        return None

    flows = pd.DataFrame({"NetIssuance": net_issuance})
    if include_dividends:
        dividend_label = next(
            (label for label in ("Common Stock Dividend Paid", "Cash Dividends Paid") if label in cashflow.index),
            None,
        )
        if dividend_label is None:
            return None
        flows["Dividends"] = cashflow.loc[dividend_label].map(_finite_number)
    flows.index = pd.to_datetime(flows.index, errors="coerce")
    flows = flows.loc[flows.index.notna()].sort_index(ascending=False)
    if len(flows) < periods:
        return None
    selected = flows.head(periods)
    if selected.index.has_duplicates or not selected.map(
        lambda value: pd.notna(value) and math.isfinite(value)
    ).all().all():
        return None
    if periods == 4:
        gaps = selected.index.to_series().diff().abs().dropna().dt.days
        if not gaps.between(80, 105).all():
            return None

    net_buybacks = -float(selected["NetIssuance"].sum())
    if not math.isfinite(net_buybacks):
        return None
    end_date = selected.index.max()
    result = {
        "Period": f"{period_name} ending {end_date:%Y-%m-%d}",
        "PeriodBasis": period_name,
        "PeriodEnd": f"{end_date:%Y-%m-%d}",
        "NetBuybacks": net_buybacks,
        "NetBuybackMethod": method,
    }
    if include_dividends:
        dividends_paid = -float(selected["Dividends"].sum())
        total_returned = dividends_paid + net_buybacks
        if dividends_paid < 0 or not math.isfinite(dividends_paid) or not math.isfinite(total_returned):
            return None
        result.update({"Dividends": dividends_paid, "TotalReturned": total_returned})
    return result


def extract_net_buybacks(cashflow: pd.DataFrame, periods: int, period_name: str) -> dict[str, Any] | None:
    return _extract_capital_returns(cashflow, periods, period_name, False)


def extract_shareholder_yield(
    cashflow: pd.DataFrame, market_cap: float, periods: int, period_name: str,
) -> dict[str, Any] | None:
    market_cap = _finite_number(market_cap)
    if not math.isfinite(market_cap) or market_cap <= 0:
        return None
    data = _extract_capital_returns(cashflow, periods, period_name, True)
    if data is None:
        return None
    return {**data, "MarketCap": market_cap, "ShareholderYield": data["TotalReturned"] / market_cap}


def get_share_count_history(
    symbol: str, frequency: str, *,
    statement_loader: Callable[[str, str, str], pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Extract reported share counts using an optionally shared statement loader."""
    if frequency not in {"annual", "quarterly"}:
        raise ValueError("Share-count frequency must be 'annual' or 'quarterly'.")

    loader = statement_loader if statement_loader is not None else get_statement_history
    try:
        statement = loader(symbol, "balance", frequency)
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(
            f"{frequency.title()} share counts for {symbol} could not be loaded: {exc}"
        ) from exc
    return extract_share_count_history(statement)


def extract_share_count_history(statement: pd.DataFrame) -> pd.DataFrame:
    columns = ["Period", "Shares", "Change"]
    if statement.empty:
        return pd.DataFrame(columns=columns)

    share_label = next(
        (
            label
            for label in ("Ordinary Shares Number", "Share Issued")
            if label in statement.index
        ),
        None,
    )
    if share_label is None:
        return pd.DataFrame(columns=columns)

    shares = pd.to_numeric(statement.loc[share_label], errors="coerce").dropna()
    result = pd.DataFrame(
        {
            "Period": pd.to_datetime(shares.index, errors="coerce"),
            "Shares": shares.to_numpy(dtype=float),
        }
    )
    result = result.dropna(subset=["Period"]).sort_values("Period").reset_index(drop=True)
    result["Change"] = result["Shares"].pct_change(fill_method=None)
    return result.loc[:, columns]


def extract_financial_history(statement: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Period",
        "Revenue",
        "Growth",
        "CostOfRevenue",
        "CostOfRevenuePercent",
    ]
    if statement.empty:
        return pd.DataFrame(columns=columns)

    revenue_label = next(
        (
            label
            for label in ("Total Revenue", "Operating Revenue")
            if label in statement.index
        ),
        None,
    )
    if revenue_label is None:
        return pd.DataFrame(columns=columns)

    revenue = pd.to_numeric(statement.loc[revenue_label], errors="coerce").dropna()
    if revenue.empty:
        return pd.DataFrame(columns=columns)

    result = pd.DataFrame(
        {
            "Period": pd.to_datetime(revenue.index, errors="coerce"),
            "Revenue": revenue.to_numpy(dtype=float),
        }
    )
    result = result.dropna(subset=["Period"]).sort_values("Period").reset_index(drop=True)
    result["Growth"] = result["Revenue"].pct_change(fill_method=None)
    cogs_label = next(
        (
            label
            for label in ("Cost Of Revenue", "Reconciled Cost Of Revenue")
            if label in statement.index
        ),
        None,
    )
    if cogs_label is None:
        result["CostOfRevenue"] = pd.NA
    else:
        cogs = pd.to_numeric(statement.loc[cogs_label], errors="coerce")
        cogs.index = pd.to_datetime(cogs.index, errors="coerce")
        result["CostOfRevenue"] = result["Period"].map(cogs)

    if "Gross Profit" in statement.index:
        gross_profit = pd.to_numeric(
            statement.loc["Gross Profit"],
            errors="coerce",
        )
        gross_profit.index = pd.to_datetime(gross_profit.index, errors="coerce")
        reported_gross_profit = result["Period"].map(gross_profit)
        calculated_gross_profit = result["Revenue"] - result["CostOfRevenue"]
        comparable = reported_gross_profit.notna() & result["CostOfRevenue"].notna()
        tolerance = result["Revenue"].abs() * 0.000001
        mismatch = (
            (calculated_gross_profit - reported_gross_profit).abs() > tolerance
        ) & comparable
        if mismatch.any():
            periods = ", ".join(
                result.loc[mismatch, "Period"].dt.strftime("%Y-%m-%d")
            )
            raise StockDataError(
                f"Cost of revenue does not reconcile with gross profit for {periods}."
            )

    result["CostOfRevenuePercent"] = (
        result["CostOfRevenue"] / result["Revenue"].replace(0, pd.NA)
    )
    return result.loc[:, columns]


def extract_revenue_history(statement: pd.DataFrame) -> pd.DataFrame:
    return extract_financial_history(statement).loc[
        :, ["Period", "Revenue", "Growth"]
    ]


def key_metric_sections(
    info: dict[str, Any],
    shareholder_yield: dict[str, Any] | None = None,
    annual_financials: pd.DataFrame | None = None,
) -> dict[str, list[dict[str, str]]]:
    currency = str(info.get("financialCurrency") or info.get("currency") or "")
    definitions = {
        "Valuation": (
            ("Market cap", "marketCap", "compact"),
            ("Enterprise value", "enterpriseValue", "compact"),
            ("Trailing P/E", "trailingPE", "decimal"),
            ("Forward P/E", "forwardPE", "decimal"),
            ("Price / sales", "priceToSalesTrailing12Months", "decimal"),
            ("Price / book", "priceToBook", "decimal"),
            ("EV / Revenue", "enterpriseToRevenue", "decimal"),
            ("EV / EBITDA", "enterpriseToEbitda", "decimal"),
        ),
        "Profitability": (
            ("Gross margin", "grossMargins", "percent"),
            ("Operating margin", "operatingMargins", "percent"),
            ("Profit margin", "profitMargins", "percent"),
            ("Return on assets", "returnOnAssets", "percent"),
            ("Return on equity", "returnOnEquity", "percent"),
        ),
        "Growth": (
            ("Earnings growth (YoY)", "earningsGrowth", "percent"),
            (
                "Quarterly earnings growth (YoY)",
                "earningsQuarterlyGrowth",
                "percent",
            ),
        ),
        "Financial health": (
            ("Total cash", "totalCash", "compact"),
            ("Total debt", "totalDebt", "compact"),
            ("Debt / equity", "debtToEquity", "percentage_points"),
            ("Current ratio", "currentRatio", "decimal"),
            ("Free cash flow", "freeCashflow", "compact"),
        ),
        "Shareholder and trading": (
            ("Dividend yield (forward)", "dividendYield", "percentage_points"),
            ("Payout ratio", "payoutRatio", "percent"),
            ("Beta", "beta", "decimal"),
        ),
    }

    sections: dict[str, list[dict[str, str]]] = {}
    for section, metrics in definitions.items():
        rows = []
        for label, key, value_type in metrics:
            value = info.get(key)
            if value is None:
                continue
            formatted = (
                compact_number(value, currency)
                if value_type == "compact"
                else format_value(value, value_type)
            )
            rows.append({"Metric": label, "Value": formatted})
        if rows:
            sections[section] = rows
    growth_rows = sections.setdefault("Growth", [])
    if annual_financials is not None and not annual_financials.empty:
        latest = annual_financials.iloc[-1]
        if pd.notna(latest.get("Growth")):
            period = pd.Timestamp(latest["Period"]).year
            growth_rows.insert(
                0,
                {
                    "Metric": (
                        f"Reported annual revenue growth "
                        f"({period} vs. {period - 1})"
                    ),
                    "Value": format_value(latest["Growth"], "percent"),
                },
            )
    provider_growth = info.get("revenueGrowth")
    if provider_growth is not None:
        reference_date = format_value(info.get("mostRecentQuarter"), "date")
        reference = (
            f" (provider reference: {reference_date})"
            if reference_date != "N/A"
            else ""
        )
        growth_rows.append(
            {
                "Metric": f"Provider summary revenue growth{reference}",
                "Value": format_value(provider_growth, "percent"),
            }
        )
    if not growth_rows:
        sections.pop("Growth", None)
    if shareholder_yield is not None:
        rows = sections.setdefault("Shareholder and trading", [])
        rows.insert(
            0,
            {
                "Metric": f"Shareholder yield ({shareholder_yield['Period']})",
                "Value": format_value(
                    shareholder_yield["ShareholderYield"],
                    "percent",
                ),
            },
        )
    return sections


SECTOR_ETFS = {
    "Basic Materials": ("XLB", "US materials sector"),
    "Communication Services": ("XLC", "US communication services sector"),
    "Consumer Cyclical": ("XLY", "US consumer discretionary sector"),
    "Consumer Defensive": ("XLP", "US consumer staples sector"),
    "Energy": ("XLE", "US energy sector"),
    "Financial Services": ("XLF", "US financial sector"),
    "Healthcare": ("XLV", "US healthcare sector"),
    "Industrials": ("XLI", "US industrial sector"),
    "Real Estate": ("XLRE", "US real-estate sector"),
    "Technology": ("XLK", "US technology sector"),
    "Utilities": ("XLU", "US utilities sector"),
}

COUNTRY_ETFS = {
    "United States": ("SPY", "US equity market"),
    "Germany": ("EWG", "German equity market"),
    "Japan": ("EWJ", "Japanese equity market"),
    "Australia": ("EWA", "Australian equity market"),
    "India": ("INDA", "Indian equity market"),
    "United Kingdom": ("EWU", "UK equity market"),
    "China": ("MCHI", "Chinese equity market"),
    "Canada": ("EWC", "Canadian equity market"),
    "France": ("EWQ", "French equity market"),
    "Switzerland": ("EWL", "Swiss equity market"),
    "Brazil": ("EWZ", "Brazilian equity market"),
    "South Korea": ("EWY", "South Korean equity market"),
    "Taiwan": ("EWT", "Taiwanese equity market"),
}

INDUSTRY_THEMES = {
    "Consumer Electronics": (
        "Installed-base monetization",
        "A large device base can support services, accessories, and upgrade demand, creating revenue beyond new-unit sales.",
        "Mature replacement cycles",
        "Hardware demand can pause when replacement cycles lengthen, while product concentration increases launch and supply-chain risk.",
    ),
    "Semiconductors": (
        "Compute and electrification demand",
        "AI infrastructure, data centers, vehicles, and industrial automation can expand semiconductor content and revenue pools.",
        "Semiconductor cyclicality",
        "Inventory corrections, heavy capital spending, export controls, and rapid product transitions can reverse growth quickly.",
    ),
    "Software - Infrastructure": (
        "Cloud and AI adoption",
        "Cloud migration and AI-enabled automation can expand recurring workloads and customer spending.",
        "Cloud optimization and competition",
        "Customer optimization, platform competition, and high development costs can slow seat or consumption growth.",
    ),
    "Software - Application": (
        "Workflow digitization",
        "Businesses adopting digital workflows and AI features can support recurring subscription and usage growth.",
        "Crowded software markets",
        "Low switching barriers in some categories and AI-native entrants can pressure retention and pricing.",
    ),
    "Auto Manufacturers": (
        "Vehicle technology content",
        "Electrification, software, and driver-assistance content can raise revenue per vehicle.",
        "Capital-intensive price competition",
        "High fixed costs, financing sensitivity, and aggressive EV pricing can pressure volumes and margins.",
    ),
    "Banks - Diversified": (
        "Credit and fee growth",
        "Healthy loan demand, transaction activity, and wealth flows can broaden revenue beyond net interest income.",
        "Credit and rate sensitivity",
        "Credit losses, deposit competition, regulation, and falling or inverted rates can weaken revenue and returns.",
    ),
    "Drug Manufacturers - General": (
        "Pipeline and demographic demand",
        "New indications, aging populations, and successful launches can create multi-year pharmaceutical revenue growth.",
        "Patent and reimbursement risk",
        "Patent expirations, trial failures, and payer or government pricing pressure can create abrupt revenue gaps.",
    ),
}

SECTOR_THEMES = {
    "Technology": (
        "Digital investment cycle",
        "AI, cloud, cybersecurity, and automation spending can expand technology demand across industries.",
        "Fast innovation and regulation",
        "Short product cycles, concentrated supply chains, and expanding technology regulation can disrupt growth assumptions.",
    ),
    "Energy": (
        "Energy demand and capital discipline",
        "Global energy demand and disciplined industry investment can support cash generation and project economics.",
        "Commodity and transition exposure",
        "Commodity-price swings, geopolitics, and decarbonization policy can make revenue highly cyclical.",
    ),
    "Financial Services": (
        "Financial deepening",
        "Credit penetration, payments growth, and expanding wealth pools can increase financial-sector revenue.",
        "Macro and regulatory sensitivity",
        "Credit cycles, funding costs, and regulation can quickly alter growth and profitability.",
    ),
    "Healthcare": (
        "Structural healthcare demand",
        "Aging populations and medical innovation can support long-duration demand growth.",
        "Policy and development risk",
        "Reimbursement changes, regulation, and clinical or product failures can limit growth.",
    ),
    "Industrials": (
        "Capital investment cycle",
        "Infrastructure, reshoring, automation, and electrification can support industrial order growth.",
        "Economic-cycle exposure",
        "Industrial demand can weaken rapidly when capital spending and manufacturing activity slow.",
    ),
    "Consumer Cyclical": (
        "Consumer premiumization",
        "Income growth and premium products can expand discretionary spending and revenue per customer.",
        "Consumer and financing sensitivity",
        "High rates, weaker confidence, and promotional competition can delay discretionary purchases.",
    ),
}

COUNTRY_THEMES = {
    "United States": (
        "Large innovation and consumption base",
        "Deep capital markets, high technology adoption, and a large consumer economy can support scalable growth.",
        "US policy and rate exposure",
        "Interest rates, antitrust or sector regulation, tariffs, and election-driven policy shifts can affect demand and costs.",
    ),
    "Germany": (
        "Export-led industrial recovery",
        "A recovery in global manufacturing and European investment can lift German export demand.",
        "Energy and export dependence",
        "Energy costs and sensitivity to Chinese and European demand can constrain growth.",
    ),
    "Japan": (
        "Corporate reform and reflation",
        "Improving pricing power, governance reform, and wage growth can support domestic revenue and investment.",
        "Demographic and currency pressure",
        "Population decline and currency-driven import costs can limit domestic demand or margins.",
    ),
    "Australia": (
        "Commodity and Asian growth exposure",
        "Asian investment and commodity demand can support Australian corporate revenue.",
        "China and commodity-cycle dependence",
        "Slower Chinese demand or lower commodity prices can weigh heavily on growth.",
    ),
    "India": (
        "Structural domestic expansion",
        "Formalization, digital adoption, infrastructure, and rising incomes can support above-average demand growth.",
        "Valuation and execution risk",
        "High expectations, infrastructure constraints, and policy execution can limit realized growth.",
    ),
    "China": (
        "Large domestic market",
        "Policy support, advanced manufacturing, and a large consumer base can create significant growth opportunities.",
        "Policy and balance-sheet uncertainty",
        "Regulation, property-sector weakness, trade restrictions, and geopolitics can suppress demand or valuations.",
    ),
}


AIRLINE_COST_DRIVERS = [
    {
        "Driver": "Jet fuel",
        "Why it matters": (
            "Fuel is usually one of an airline's largest variable costs and can "
            "move faster than fares."
        ),
        "Monitor": "Jet-fuel prices, crude oil, refining spreads, hedging, and fuel efficiency",
    },
    {
        "Driver": "Labor",
        "Why it matters": (
            "Pilots, cabin crew, maintenance, and ground staff create a large "
            "partly fixed cost base."
        ),
        "Monitor": "Collective agreements, wage inflation, staffing, and productivity",
    },
    {
        "Driver": "Aircraft ownership and maintenance",
        "Why it matters": (
            "Leases, depreciation, engine overhauls, and scheduled maintenance "
            "depend on fleet age and utilization."
        ),
        "Monitor": "Lease rates, interest rates, fleet age, utilization, and shop-visit timing",
    },
    {
        "Driver": "Airport, navigation, and distribution fees",
        "Why it matters": (
            "Airports, air-traffic services, booking channels, and payment "
            "providers charge largely volume-linked fees."
        ),
        "Monitor": "Airport tariffs, route mix, passenger volumes, and direct-booking share",
    },
]

INDUSTRY_COST_DRIVER_RULES = [
    (
        ("airlines",),
        AIRLINE_COST_DRIVERS,
    ),
    (
        ("semiconductor",),
        [
            {
                "Driver": "Wafers, foundry capacity, and advanced packaging",
                "Why it matters": "Leading-edge manufacturing and packaging determine unit economics and supply availability.",
                "Monitor": "Foundry pricing, process-node mix, yields, substrates, and packaging capacity",
            },
            {
                "Driver": "Research and development",
                "Why it matters": "Short product cycles require sustained spending on architecture, design, and process technology.",
                "Monitor": "R&D growth, tape-outs, engineering headcount, and product cadence",
            },
            {
                "Driver": "Fab depreciation and utilization",
                "Why it matters": "For manufacturers, high fixed fab costs make margins sensitive to utilization and inventory cycles.",
                "Monitor": "Capacity utilization, inventories, capital expenditure, and depreciation",
            },
        ],
    ),
    (
        ("software", "internet content", "electronic gaming"),
        [
            {
                "Driver": "Technical and product talent",
                "Why it matters": "Engineering and product teams drive development but create a large recurring operating-cost base.",
                "Monitor": "Headcount, compensation, stock-based compensation, and R&D intensity",
            },
            {
                "Driver": "Cloud infrastructure and third-party data",
                "Why it matters": "Hosting, compute, storage, AI inference, and licensed data rise with usage.",
                "Monitor": "Cloud commitments, gross margin, usage growth, and infrastructure efficiency",
            },
            {
                "Driver": "Customer acquisition",
                "Why it matters": "Sales commissions and marketing can consume substantial cash before recurring revenue is earned.",
                "Monitor": "Sales and marketing ratio, payback period, retention, and organic traffic",
            },
        ],
    ),
    (
        ("auto manufacturer", "auto parts"),
        [
            {
                "Driver": "Materials, batteries, and components",
                "Why it matters": "Steel, aluminum, batteries, electronics, and supplier pricing dominate vehicle input costs.",
                "Monitor": "Battery costs, metals prices, semiconductor supply, and supplier negotiations",
            },
            {
                "Driver": "Labor and plant utilization",
                "Why it matters": "Assembly plants have high fixed labor and overhead costs that depend on production volumes.",
                "Monitor": "Production volumes, capacity utilization, wage agreements, and downtime",
            },
            {
                "Driver": "Warranty, incentives, and product investment",
                "Why it matters": "Quality claims, discounting, software development, and model launches can materially change margins.",
                "Monitor": "Warranty provisions, incentives per vehicle, R&D, and launch costs",
            },
        ],
    ),
    (
        ("bank", "credit services", "capital markets"),
        [
            {
                "Driver": "Funding costs",
                "Why it matters": "Deposit and wholesale-funding rates determine the spread earned on loans and securities.",
                "Monitor": "Deposit beta, funding mix, policy rates, and net interest margin",
            },
            {
                "Driver": "Credit losses",
                "Why it matters": "Defaults and reserve changes can overwhelm otherwise stable operating expenses.",
                "Monitor": "Delinquencies, non-performing loans, charge-offs, and loss provisions",
            },
            {
                "Driver": "Compensation, technology, and compliance",
                "Why it matters": "Staff, systems, cybersecurity, and regulation form the core controllable expense base.",
                "Monitor": "Efficiency ratio, compensation ratio, technology spending, and regulatory costs",
            },
        ],
    ),
    (
        ("drug manufacturer", "biotechnology"),
        [
            {
                "Driver": "Research and clinical development",
                "Why it matters": "Discovery, trials, and failed programs require spending years before potential commercialization.",
                "Monitor": "R&D intensity, trial enrollment, phase mix, and pipeline attrition",
            },
            {
                "Driver": "Manufacturing and quality",
                "Why it matters": "Complex production, validation, quality control, and external manufacturers affect gross margin.",
                "Monitor": "Batch yields, capacity utilization, contract-manufacturer pricing, and remediation costs",
            },
            {
                "Driver": "Commercialization and market access",
                "Why it matters": "Sales teams, launch spending, rebates, and payer access determine the net economics of approved products.",
                "Monitor": "Selling expense, gross-to-net deductions, launch costs, and reimbursement terms",
            },
        ],
    ),
    (
        ("oil & gas", "thermal coal", "uranium"),
        [
            {
                "Driver": "Extraction and field services",
                "Why it matters": "Lifting costs, drilling, labor, and service-company rates determine cash cost per unit.",
                "Monitor": "Unit operating cost, rig and service rates, production mix, and decline rates",
            },
            {
                "Driver": "Development capital",
                "Why it matters": "Reserves require sustained drilling, infrastructure, and project investment.",
                "Monitor": "Capital expenditure, project inflation, reserve replacement, and production growth",
            },
            {
                "Driver": "Royalties, transport, and energy",
                "Why it matters": "Government take, pipelines, shipping, and energy use vary by basin and realized price.",
                "Monitor": "Royalty rates, differentials, transport contracts, and local energy prices",
            },
        ],
    ),
    (
        ("retail", "apparel", "footwear"),
        [
            {
                "Driver": "Merchandise and sourcing",
                "Why it matters": "Product acquisition, supplier terms, tariffs, and markdowns drive gross margin.",
                "Monitor": "Input costs, tariffs, inventory growth, markdowns, and private-label mix",
            },
            {
                "Driver": "Freight and fulfillment",
                "Why it matters": "Inbound freight, warehouses, delivery, and returns rise with omnichannel volume.",
                "Monitor": "Freight rates, fulfillment cost per order, return rates, and delivery mix",
            },
            {
                "Driver": "Store labor and occupancy",
                "Why it matters": "Wages, rent, utilities, and store productivity determine fixed-cost leverage.",
                "Monitor": "Wage inflation, same-store sales, rent renewals, and sales per square foot",
            },
        ],
    ),
    (
        ("restaurant", "lodging", "resort"),
        [
            {
                "Driver": "Labor",
                "Why it matters": "Front-line staffing is essential and sensitive to wages, turnover, and utilization.",
                "Monitor": "Hourly wages, staffing levels, turnover, and revenue per employee",
            },
            {
                "Driver": "Food, supplies, and property operations",
                "Why it matters": "Ingredients, utilities, cleaning, repairs, and consumables move with inflation and occupancy.",
                "Monitor": "Food inflation, utility prices, occupancy, and maintenance expense",
            },
            {
                "Driver": "Occupancy and distribution",
                "Why it matters": "Rent, property ownership, franchise fees, and online booking commissions affect operating leverage.",
                "Monitor": "Lease terms, interest rates, OTA mix, franchise fees, and unit economics",
            },
        ],
    ),
]

SECTOR_COST_DRIVERS = {
    "Basic Materials": [
        ("Energy and consumables", "Mining and processing require fuel, electricity, chemicals, and replacement parts.", "Energy prices, consumables inflation, ore grades, and recovery rates"),
        ("Labor and equipment", "Skilled labor and heavy-equipment availability influence unit production costs.", "Wages, contractor rates, equipment utilization, and maintenance"),
        ("Sustaining capital and royalties", "Asset upkeep, waste removal, and government royalties consume cash beyond reported production costs.", "Capital expenditure, stripping ratios, royalties, and environmental obligations"),
    ],
    "Communication Services": [
        ("Network and content", "Networks, spectrum, interconnection, or licensed content are central service inputs.", "Capital expenditure, spectrum payments, content renewals, and traffic"),
        ("Customer acquisition and retention", "Marketing, handset subsidies, and churn management affect subscriber economics.", "Acquisition cost, churn, promotions, and lifetime value"),
        ("Labor and technology", "Operations, support, cybersecurity, and product development require sustained staffing and systems investment.", "Headcount, technology expense, automation, and service costs"),
    ],
    "Consumer Cyclical": [
        ("Products and materials", "Merchandise, components, and supplier pricing drive gross margin.", "Input inflation, supplier terms, tariffs, and markdowns"),
        ("Labor and occupancy", "Stores, factories, and service locations create wage and facility costs.", "Wages, rent, utilization, and same-location sales"),
        ("Freight and customer acquisition", "Distribution, delivery, promotions, and advertising determine contribution margins.", "Freight rates, marketing intensity, returns, and conversion"),
    ],
    "Consumer Defensive": [
        ("Agricultural and packaging inputs", "Commodities and packaging are major recurring product costs.", "Crop prices, resin, aluminum, paper, and hedging"),
        ("Manufacturing and logistics", "Plants, energy, freight, and warehousing determine conversion cost.", "Energy, freight rates, capacity utilization, and productivity"),
        ("Trade promotion and labor", "Retail promotions and workforce costs affect realized margins.", "Promotional intensity, retailer terms, wages, and pricing"),
    ],
    "Energy": [
        ("Production and service costs", "Labor, equipment, and field services determine cost per unit.", "Unit costs, service rates, and production mix"),
        ("Development capital", "Replacing reserves and building infrastructure require sustained investment.", "Capital expenditure, project inflation, and reserve replacement"),
        ("Royalties and transport", "Government take and moving products to market reduce realized economics.", "Royalties, transport contracts, and regional price differentials"),
    ],
    "Financial Services": [
        ("Funding and claims", "Interest paid, credit losses, or insurance claims are the principal economic inputs.", "Funding mix, loss provisions, claims trends, and reinsurance"),
        ("Compensation", "Skilled staff and incentive pay form a large controllable expense.", "Compensation ratio, headcount, and productivity"),
        ("Technology and compliance", "Secure systems and regulatory obligations require continuous spending.", "Technology investment, cybersecurity, and regulatory costs"),
    ],
    "Healthcare": [
        ("Clinical and product development", "Trials, engineering, and regulatory work precede revenue and carry failure risk.", "R&D intensity, trial progress, and regulatory milestones"),
        ("Manufacturing and quality", "Validated production and quality systems determine product cost and supply reliability.", "Yield, utilization, supplier pricing, and remediation"),
        ("Commercial access", "Sales, reimbursement, and distribution affect net realized revenue.", "Selling expense, rebates, payer mix, and distribution fees"),
    ],
    "Industrials": [
        ("Materials and components", "Metals, electronics, and purchased components drive direct cost.", "Commodity prices, supplier lead times, tariffs, and product mix"),
        ("Skilled labor", "Engineering and production depend on wages, availability, and productivity.", "Wage inflation, backlog conversion, utilization, and overtime"),
        ("Energy, freight, and warranty", "Factories, logistics, and product-performance obligations affect delivery margins.", "Energy, freight rates, warranty provisions, and execution"),
    ],
    "Real Estate": [
        ("Interest and refinancing", "Property economics are highly sensitive to debt costs and maturity schedules.", "Interest rates, leverage, fixed-rate share, and debt maturities"),
        ("Property operations", "Maintenance, utilities, insurance, and taxes determine net operating income.", "Operating-expense growth, insurance, taxes, and occupancy"),
        ("Capital expenditure", "Tenant improvements and asset maintenance consume cash not captured by simple earnings measures.", "Recurring capex, leasing commissions, and redevelopment spending"),
    ],
    "Technology": [
        ("Technical talent and R&D", "Engineering and product development sustain competitiveness but create a large recurring expense.", "Headcount, compensation, stock-based compensation, and R&D intensity"),
        ("Components or cloud infrastructure", "Hardware inputs, hosting, compute, and data costs scale with the business model.", "Gross margin, supplier pricing, cloud commitments, and utilization"),
        ("Sales and customer acquisition", "Distribution, commissions, and marketing determine how efficiently revenue is added.", "Sales efficiency, marketing ratio, retention, and payback period"),
    ],
    "Utilities": [
        ("Fuel and purchased power", "Generation fuel and externally purchased electricity directly affect delivered energy cost.", "Gas, coal, and power prices; fuel-adjustment mechanisms; generation mix"),
        ("Grid investment and financing", "Networks require heavy capital spending financed over long periods.", "Capital expenditure, interest rates, allowed returns, and rate-base growth"),
        ("Operations, maintenance, and regulation", "Reliability, storms, compliance, and asset upkeep drive recurring expenditure.", "Outage costs, maintenance, environmental rules, and regulatory recovery"),
    ],
}


def generate_cost_drivers(info: dict[str, Any]) -> list[dict[str, str]]:
    industry = str(info.get("industry") or "").lower()
    for keywords, drivers in INDUSTRY_COST_DRIVER_RULES:
        if any(keyword in industry for keyword in keywords):
            return [dict(driver) for driver in drivers]

    sector_drivers = SECTOR_COST_DRIVERS.get(str(info.get("sector") or ""), [])
    return [
        {"Driver": driver, "Why it matters": reason, "Monitor": monitor}
        for driver, reason, monitor in sector_drivers
    ]


def get_business_context(
    industry_key: str | None,
    sector: str | None,
    country: str | None,
) -> dict[str, Any]:
    context: dict[str, Any] = {"Industry": None, "Benchmarks": []}
    if industry_key:
        try:
            industry = yf.Industry(industry_key)
            overview = industry.overview
            performers = industry.top_performing_companies
            growth = industry.top_growth_companies
        except MARKET_DATA_EXCEPTIONS as exc:
            raise StockDataError(f"Industry context could not be loaded: {exc}") from exc

        overview = overview if isinstance(overview, dict) else {}
        performers = (
            performers if isinstance(performers, pd.DataFrame) else pd.DataFrame()
        )
        growth = growth if isinstance(growth, pd.DataFrame) else pd.DataFrame()
        ytd_returns = (
            pd.to_numeric(performers["ytd return"], errors="coerce").dropna()
            if not performers.empty and "ytd return" in performers
            else pd.Series(dtype=float)
        )
        growth_estimates = (
            pd.to_numeric(growth["growth estimate"], errors="coerce").dropna()
            if not growth.empty and "growth estimate" in growth
            else pd.Series(dtype=float)
        )
        context["Industry"] = {
            "Name": industry.name,
            "CompanyCount": overview.get("companies_count"),
            "MedianYTDReturn": (
                float(ytd_returns.median()) if not ytd_returns.empty else None
            ),
            "YTDCompanyCount": int(len(ytd_returns)),
            "MedianGrowthEstimate": (
                float(growth_estimates.median())
                if len(growth_estimates) >= 3
                else None
            ),
            "GrowthEstimateCount": int(len(growth_estimates)),
        }

    global_return = _one_year_return("ACWI")
    benchmark_specs = []
    if sector in SECTOR_ETFS:
        benchmark_specs.append(("Sector", *SECTOR_ETFS[sector]))
    if country in COUNTRY_ETFS:
        benchmark_specs.append(("Country", *COUNTRY_ETFS[country]))
    for context_type, ticker, label in benchmark_specs:
        benchmark_return = _one_year_return(ticker)
        if benchmark_return is None:
            continue
        context["Benchmarks"].append(
            {
                "Type": context_type,
                "Ticker": ticker,
                "Label": label,
                "Return": benchmark_return,
                "RelativeToGlobal": (
                    benchmark_return - global_return
                    if global_return is not None
                    else None
                ),
            }
        )
    return context


def _one_year_return(symbol: str) -> float | None:
    try:
        history = yf.Ticker(symbol).history(
            period="1y",
            interval="1d",
            auto_adjust=True,
            actions=False,
        )
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(
            f"Benchmark history for {symbol} could not be loaded: {exc}"
        ) from exc
    closes = history["Close"].dropna() if "Close" in history else pd.Series(dtype=float)
    if len(closes) < 2 or float(closes.iloc[0]) == 0:
        return None
    return float(closes.iloc[-1] / closes.iloc[0] - 1)


def generate_stock_drivers(
    info: dict[str, Any],
    annual_financials: pd.DataFrame,
    quarterly_financials: pd.DataFrame,
    business_context: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, str]]]:
    tailwinds: list[dict[str, str]] = []
    headwinds: list[dict[str, str]] = []
    business_context = business_context or {"Industry": None, "Benchmarks": []}

    industry = str(info.get("industry") or "")
    sector = str(info.get("sector") or "")
    country = str(info.get("country") or "")
    themes = INDUSTRY_THEMES.get(industry) or SECTOR_THEMES.get(sector)
    if themes:
        tailwinds.append({"Title": themes[0], "Evidence": themes[1]})
        headwinds.append({"Title": themes[2], "Evidence": themes[3]})
    country_themes = COUNTRY_THEMES.get(country)
    if country_themes:
        tailwinds.append(
            {"Title": country_themes[0], "Evidence": country_themes[1]}
        )
        headwinds.append(
            {"Title": country_themes[2], "Evidence": country_themes[3]}
        )

    annual_growth = None
    if not annual_financials.empty:
        annual_growth = annual_financials["Growth"].iloc[-1]
        costs = annual_financials.dropna(subset=["CostOfRevenuePercent"])
        if len(costs) >= 2:
            cost_change = (
                float(costs["CostOfRevenuePercent"].iloc[-1])
                - float(costs["CostOfRevenuePercent"].iloc[-2])
            )
            if abs(cost_change) >= 0.0025:
                item = {
                    "Title": "More room to fund growth"
                    if cost_change < 0
                    else "Rising cost burden",
                    "Evidence": (
                        "Cost of revenue as a share of revenue "
                        f"{'fell' if cost_change < 0 else 'rose'} "
                        f"{abs(cost_change) * 100:.1f} percentage points "
                        "in the latest fiscal year."
                    ),
                }
                (tailwinds if cost_change < 0 else headwinds).append(item)

    if len(quarterly_financials) >= 5:
        latest_revenue = float(quarterly_financials["Revenue"].iloc[-1])
        prior_year_revenue = float(quarterly_financials["Revenue"].iloc[-5])
        quarterly_yoy = (
            latest_revenue / prior_year_revenue - 1
            if prior_year_revenue != 0
            else None
        )
        if quarterly_yoy is not None and pd.notna(annual_growth):
            acceleration = quarterly_yoy - float(annual_growth)
            item = {
                "Title": "Revenue growth is accelerating"
                if acceleration >= 0.02 and quarterly_yoy > 0
                else "Revenue growth is not accelerating",
                "Evidence": (
                    f"Latest quarterly revenue grew {quarterly_yoy:.1%} year over "
                    f"year versus {annual_growth:.1%} in the latest fiscal year."
                ),
            }
            (
                tailwinds
                if acceleration >= 0.02 and quarterly_yoy > 0
                else headwinds
            ).append(item)

    industry_context = business_context.get("Industry")
    if industry_context:
        median_return = industry_context.get("MedianYTDReturn")
        coverage = industry_context.get("YTDCompanyCount", 0)
        if median_return is not None and coverage >= 3 and abs(median_return) >= 0.05:
            item = {
                "Title": "Positive industry market breadth"
                if median_return > 0
                else "Weak industry market breadth",
                "Evidence": (
                    f"The median YTD return among {coverage} available "
                    f"{industry_context['Name']} peer observations is {median_return:.1%}."
                ),
            }
            (tailwinds if median_return > 0 else headwinds).append(item)

        growth_estimate = industry_context.get("MedianGrowthEstimate")
        estimate_count = industry_context.get("GrowthEstimateCount", 0)
        if growth_estimate is not None:
            item = {
                "Title": "Peer growth expectations are constructive"
                if growth_estimate > 0
                else "Peer growth expectations are weak",
                "Evidence": (
                    f"Median published growth estimates across {estimate_count} "
                    f"available industry peers are {growth_estimate:.1%}."
                ),
            }
            (tailwinds if growth_estimate > 0 else headwinds).append(item)

    for benchmark in business_context.get("Benchmarks", []):
        benchmark_return = benchmark["Return"]
        relative = benchmark.get("RelativeToGlobal")
        if relative is not None and relative >= 0.03 and benchmark_return > 0:
            tailwinds.append(
                {
                    "Title": f"{benchmark['Label']} momentum",
                    "Evidence": (
                        f"{benchmark['Ticker']} returned {benchmark_return:.1%} "
                        f"over one year, outperforming ACWI by {relative:.1%}."
                    ),
                }
            )
        elif (
            benchmark_return <= -0.05
            or (relative is not None and relative <= -0.03)
        ):
            headwinds.append(
                {
                    "Title": f"{benchmark['Label']} weakness",
                    "Evidence": (
                        f"{benchmark['Ticker']} returned {benchmark_return:.1%} "
                        f"over one year"
                        + (
                            f", trailing ACWI by {abs(relative):.1%}."
                            if relative is not None and relative < 0
                            else "."
                        )
                    ),
                }
            )

    return {
        "Tailwinds": tailwinds[:6],
        "Headwinds": headwinds[:6],
        "CostDrivers": generate_cost_drivers(info),
        "Context": business_context.get("Benchmarks", []),
    }


def x_discussion_links(symbol: str, company_name: str) -> dict[str, str]:
    cashtag = f"${symbol.strip().upper()}"
    company_query = f'"{company_name.strip()}" stock'
    base_url = "https://x.com/search"
    return {
        "Latest cashtag posts": f"{base_url}?{urlencode({'q': cashtag, 'src': 'typed_query', 'f': 'live'})}",
        "Top cashtag posts": f"{base_url}?{urlencode({'q': cashtag, 'src': 'typed_query', 'f': 'top'})}",
        "Company mentions": f"{base_url}?{urlencode({'q': company_query, 'src': 'typed_query', 'f': 'live'})}",
    }


def short_interest_rows(info: dict[str, Any]) -> list[dict[str, str]]:
    definitions = (
        ("Shares short", "sharesShort", "integer"),
        ("Short % of float", "shortPercentOfFloat", "percent"),
        ("Short % of shares outstanding", "sharesPercentSharesOut", "percent"),
        ("Days to cover (short ratio)", "shortRatio", "decimal"),
        ("Prior-month shares short", "sharesShortPriorMonth", "integer"),
        ("Short-interest date", "dateShortInterest", "date"),
    )
    rows = []
    for label, key, value_type in definitions:
        value = info.get(key)
        if value is not None:
            rows.append({"Metric": label, "Value": format_value(value, value_type)})
    return rows


def format_value(value: Any, value_type: str = "decimal") -> str:
    if value is None:
        return "N/A"
    if value_type == "integer":
        return f"{int(value):,}"
    if value_type == "percent":
        percent = Decimal(str(value)) * Decimal("100")
        return f"{percent.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}%"
    if value_type == "percentage_points":
        percentage_points = Decimal(str(value))
        return (
            f"{percentage_points.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}%"
        )
    if value_type == "date":
        timestamp = datetime.fromtimestamp(float(value), tz=timezone.utc)
        return timestamp.strftime("%Y-%m-%d")
    decimal = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{decimal:,.2f}"


def compact_number(value: Any, currency: str = "") -> str:
    if value is None:
        return "N/A"
    number = float(value)
    for divisor, suffix in ((1_000_000_000_000, "T"), (1_000_000_000, "B"), (1_000_000, "M")):
        if abs(number) >= divisor:
            formatted = f"{number / divisor:.2f}{suffix}"
            return f"{currency} {formatted}".strip()
    return f"{currency} {number:,.0f}".strip()
