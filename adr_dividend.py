"""Live, trailing ex-date cash yields for a fixed, dated ADR research universe."""

from __future__ import annotations

from datetime import date, datetime, timezone
from math import fsum, isfinite
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from stock_data import MARKET_DATA_EXCEPTIONS, StockDataError


ADR_RESEARCH_AS_OF = "2026-09-11"
_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "adr_catalog.csv"
_CATALOG_COLUMNS = [
    "Ticker", "Symbol", "Name", "Country", "Overview", "ResearchNotes", "ResearchSource",
]
_SYMBOL_OVERRIDES = {"PBR.A": "PBR-A", "AKO.B": "AKO-B"}
_US_EXCHANGES = {"NYQ", "NMS", "NGM", "NCM"}


def adr_catalog() -> pd.DataFrame:
    """Load research metadata only; never use saved prices or yields as a fallback."""
    try:
        catalog = pd.read_csv(_CATALOG_PATH, dtype=str, keep_default_na=False)
    except (OSError, ValueError) as exc:
        raise StockDataError(f"ADR catalog could not be read at {_CATALOG_PATH}: {exc}") from exc

    missing = set(_CATALOG_COLUMNS).difference(catalog.columns)
    if missing:
        raise StockDataError(f"ADR catalog is missing columns: {', '.join(sorted(missing))}.")
    catalog = catalog.loc[:, _CATALOG_COLUMNS].copy()
    for column in _CATALOG_COLUMNS:
        if catalog[column].isna().any() or catalog[column].str.strip().eq("").any():
            raise StockDataError(f"ADR catalog has an empty required field in {column}.")
        catalog[column] = catalog[column].str.strip()
    for column in ("Ticker", "Symbol"):
        if catalog[column].duplicated().any():
            raise StockDataError(f"ADR catalog contains duplicate {column} values.")
    if len(catalog) != 100:
        raise StockDataError(f"ADR catalog must contain exactly 100 securities; found {len(catalog)}.")
    expected_symbols = catalog["Ticker"].map(lambda value: _SYMBOL_OVERRIDES.get(value, value))
    if not catalog["Symbol"].equals(expected_symbols.rename("Symbol")):
        raise StockDataError("ADR catalog contains an invalid Yahoo symbol mapping.")
    return catalog


def _as_of_date(symbol: str, as_of: str) -> pd.Timestamp:
    try:
        parsed = date.fromisoformat(as_of)
    except (TypeError, ValueError) as exc:
        raise StockDataError(f"{symbol}: as_of must be a New York calendar date (YYYY-MM-DD).") from exc
    if parsed.isoformat() != as_of:
        raise StockDataError(f"{symbol}: as_of must use YYYY-MM-DD.")
    return pd.Timestamp(parsed)


def _history_dates(symbol: str, index: pd.Index) -> pd.DatetimeIndex:
    dates = []
    for value in index:
        if not isinstance(value, (str, date, datetime, pd.Timestamp)):
            raise StockDataError(f"{symbol}: history contains an invalid timestamp: {value!r}.")
        try:
            timestamp = pd.Timestamp(value)
            if pd.isna(timestamp):
                raise ValueError("missing date")
            if timestamp.tzinfo is not None:
                timestamp = timestamp.tz_convert("America/New_York").tz_localize(None)
            dates.append(timestamp.normalize())
        except (TypeError, ValueError, OverflowError) as exc:
            raise StockDataError(f"{symbol}: history contains an invalid timestamp: {value!r}.") from exc
    return pd.DatetimeIndex(dates)


def _numeric_history_column(history: pd.DataFrame, symbol: str, column: str) -> pd.Series:
    values = history[column]
    if (
        pd.api.types.is_datetime64_any_dtype(values.dtype)
        or pd.api.types.is_complex_dtype(values.dtype)
        or pd.api.types.is_bool_dtype(values.dtype)
    ):
        raise StockDataError(f"{symbol}: {column} must contain numeric values.")
    try:
        values = pd.to_numeric(values, errors="raise").astype(float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise StockDataError(f"{symbol}: {column} contains invalid numeric values.") from exc
    if not values.map(isfinite).all():
        raise StockDataError(f"{symbol}: {column} contains missing or non-finite values; refresh the data.")
    if column == "Close" and values.le(0).any():
        raise StockDataError(f"{symbol}: Close must be positive on every completed history row.")
    if column == "Dividends" and values.lt(0).any():
        raise StockDataError(f"{symbol}: Dividends contains negative cash amounts; verify provider data.")
    return values


def _analyze_adr_dividend(history: pd.DataFrame, symbol: str, as_of: str) -> dict[str, Any]:
    """Use provider split-adjusted Close and cash as-is, including special payouts."""
    end = _as_of_date(symbol, as_of)
    if not isinstance(history, pd.DataFrame) or history.empty:
        raise StockDataError(f"{symbol}: no daily history was returned; refresh or check the Yahoo listing.")
    if history.columns.duplicated().any():
        raise StockDataError(f"{symbol}: daily history contains duplicate columns.")
    missing = {"Close", "Dividends"}.difference(history.columns)
    if missing:
        raise StockDataError(f"{symbol}: daily history is missing {', '.join(sorted(missing))}.")

    history = history.loc[:, ["Close", "Dividends"]].copy()
    history.index = _history_dates(symbol, history.index)
    if history.index.duplicated().any():
        raise StockDataError(f"{symbol}: daily history contains duplicate New York dates.")
    # Ignore incomplete current-day bars and future action rows even if returned by the provider.
    history = history.loc[history.index < end].sort_index()
    if history.empty:
        raise StockDataError(f"{symbol}: no completed daily history exists before {as_of}.")
    price_date = history.index[-1]
    if (end - price_date).days > 7:
        raise StockDataError(
            f"{symbol}: stale price dated {price_date.date().isoformat()} "
            f"(more than 7 days before {as_of}); refresh or verify trading status."
        )
    window_start = price_date - pd.DateOffset(years=1)
    if history.index[0] > window_start:
        raise StockDataError(
            f"{symbol}: incomplete dividend coverage; history must begin on or before "
            f"{window_start.date().isoformat()} to validate a full trailing year."
        )
    closes = _numeric_history_column(history, symbol, "Close")
    dividends = _numeric_history_column(history, symbol, "Dividends")
    window_cash = dividends.loc[(dividends.index > window_start) & (dividends.index <= price_date)]
    payouts = window_cash.loc[window_cash > 0]
    price = float(closes.iloc[-1])
    try:
        cash = fsum(window_cash)
    except OverflowError as exc:
        raise StockDataError(f"{symbol}: total dividend cash is non-finite; verify provider data.") from exc
    yield_percent = cash / price * 100
    if not isfinite(cash) or not isfinite(yield_percent):
        raise StockDataError(f"{symbol}: dividend cash or yield is non-finite; verify provider data.")
    return {
        "Price": price,
        "TTMCash": cash,
        "YieldPercent": yield_percent,
        "PriceDate": price_date.date().isoformat(),
        "WindowStart": window_start.date().isoformat(),
        "DividendCount": int(len(payouts)),
        "LastExDate": payouts.index[-1].date().isoformat() if not payouts.empty else None,
    }


def get_adr_dividend(symbol: str, as_of: str) -> dict[str, Any]:
    """Fetch a USD NYSE/Nasdaq ADR's completed-bar TTM cash yield.

    ``as_of`` is the caller's current New York calendar date. The trailing window
    is (PriceDate minus one calendar year, PriceDate], not a forward estimate.
    Missing data raises StockDataError rather than producing a zero or a fallback.
    """
    if not isinstance(symbol, str) or symbol not in set(adr_catalog()["Symbol"]):
        raise StockDataError(f"{symbol!r}: not a Yahoo symbol in the fixed {ADR_RESEARCH_AS_OF} ADR universe.")
    end = _as_of_date(symbol, as_of)
    start = (end - pd.DateOffset(years=2)).date().isoformat()
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(
            start=start,
            end=as_of,
            interval="1d",
            actions=True,
            auto_adjust=False,
            raise_errors=True,
            timeout=15,
        )
        metadata = ticker.get_history_metadata()
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(f"{symbol}: Yahoo daily history could not be loaded; retry later. {exc}") from exc
    if not isinstance(metadata, dict):
        raise StockDataError(f"{symbol}: Yahoo history metadata is missing; cannot verify currency and exchange.")
    currency = metadata.get("currency")
    if not isinstance(currency, str) or not currency.strip():
        raise StockDataError(f"{symbol}: Yahoo history metadata is missing currency; cannot validate USD cash.")
    if currency != "USD":
        raise StockDataError(f"{symbol}: expected USD history but received currency {currency!r}.")
    exchange = metadata.get("exchangeName")
    if not isinstance(exchange, str) or not exchange.strip():
        raise StockDataError(f"{symbol}: Yahoo history metadata is missing exchangeName; cannot validate NYSE/Nasdaq.")
    if exchange not in _US_EXCHANGES:
        raise StockDataError(f"{symbol}: exchange {exchange!r} is not a supported NYSE/Nasdaq listing.")
    result = _analyze_adr_dividend(history, symbol, as_of)
    result["FetchedAt"] = datetime.now(timezone.utc).isoformat()
    result["LiveSource"] = f"https://finance.yahoo.com/quote/{symbol}/history/"
    return result
