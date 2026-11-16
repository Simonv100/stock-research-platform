"""Equal-weight participation measures for a fixed, current stock universe."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

from stock_data import MARKET_DATA_EXCEPTIONS, StockDataError


BREADTH_MODEL_VERSION = "current-universe-breadth-v1"
BENCHMARK_SYMBOL = "^GSPC"
MINIMUM_COVERAGE = 0.95
DISPLAY_SESSIONS = 252


@dataclass
class BreadthSnapshot:
    daily: pd.DataFrame
    coverage: pd.DataFrame
    fetched_at: str


def _numeric_daily(values: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    result = values.copy()
    dates = pd.DatetimeIndex(pd.to_datetime(result.index))
    if dates.tz is not None:
        dates = dates.tz_localize(None)
    result.index = dates.normalize()
    result = result.loc[result.index.notna()]
    result = result.loc[~result.index.duplicated(keep="last")].sort_index()
    if isinstance(result, pd.DataFrame):
        result = result.apply(pd.to_numeric, errors="coerce")
        valid = result.map(lambda value: pd.notna(value) and math.isfinite(value) and value > 0)
    else:
        result = pd.to_numeric(result, errors="coerce")
        valid = result.map(lambda value: pd.notna(value) and math.isfinite(value) and value > 0)
    return result.where(valid)


def new_york_today(as_of: str | pd.Timestamp | None = None) -> pd.Timestamp:
    now = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    return now.tz_convert("America/New_York").normalize().tz_localize(None)


def calculate_market_breadth(
    prices: pd.DataFrame,
    benchmark: pd.Series,
    *,
    as_of: str | pd.Timestamp | None = None,
    display_sessions: int = DISPLAY_SESSIONS,
    minimum_coverage: float = MINIMUM_COVERAGE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not len(prices.columns) or prices.columns.has_duplicates:
        raise StockDataError("Breadth requires a non-empty universe of distinct listing symbols.")
    if display_sessions < 2 or not 0 < minimum_coverage <= 1:
        raise ValueError("Breadth requires at least two display sessions and coverage in (0, 1].")
    benchmark = _numeric_daily(benchmark).dropna()
    benchmark = benchmark.loc[benchmark.index < new_york_today(as_of)]
    if len(benchmark) < 2:
        raise StockDataError("S&P 500 index history needs at least two completed sessions.")
    prices = _numeric_daily(prices).reindex(benchmark.index)
    universe_size = len(prices.columns)
    eligible = prices.notna() & prices.shift(1).notna()
    change = prices - prices.shift(1)
    advances = ((change > 0) & eligible).sum(axis=1)
    declines = ((change < 0) & eligible).sum(axis=1)
    unchanged = ((change == 0) & eligible).sum(axis=1)
    comparable = eligible.sum(axis=1)
    enough = comparable / universe_size >= minimum_coverage
    daily = pd.DataFrame({
        "IndexClose": benchmark,
        "IndexReturn": benchmark.pct_change(fill_method=None),
        "UniverseSize": universe_size,
        "Advancing": advances, "Declining": declines, "Unchanged": unchanged,
        "ADComparable": comparable,
        "ADCoverage": comparable / universe_size,
        "NetAdvances": (advances - declines).where(enough),
        "AdvancingPercent": (100 * advances / comparable.replace(0, float("nan"))).where(enough),
    })
    ma_eligibility = {}
    for window in (50, 200):
        average = prices.rolling(window, min_periods=window).mean()
        available = prices.notna() & average.notna()
        denominator = available.sum(axis=1)
        above = ((prices > average) & available).sum(axis=1)
        daily[f"MA{window}Comparable"] = denominator
        daily[f"MA{window}Coverage"] = denominator / universe_size
        daily[f"AboveMA{window}Percent"] = (
            100 * above / denominator.replace(0, float("nan"))
        ).where(denominator / universe_size >= minimum_coverage)
        ma_eligibility[window] = available
    daily = daily.tail(display_sessions).copy()
    daily.index.name = "Date"
    daily["IndexRebased"] = 100 * daily["IndexClose"] / daily["IndexClose"].iloc[0]
    missing = daily["NetAdvances"].isna()
    daily["ADSegment"] = missing.cumsum()
    # Never bridge an unknown daily net advance with a fabricated zero.
    daily["ADLine"] = daily["NetAdvances"].groupby(daily["ADSegment"]).cumsum()
    latest = benchmark.index[-1]
    coverage = pd.DataFrame({
        "Symbol": prices.columns,
        "Last price date": [
            series.last_valid_index().strftime("%Y-%m-%d") if series.last_valid_index() is not None else ""
            for _, series in prices.items()
        ],
        "Price on latest index date": prices.loc[latest].notna().to_numpy(),
        "AD eligible": eligible.loc[latest].to_numpy(),
        "MA50 eligible": ma_eligibility[50].loc[latest].to_numpy(),
        "MA200 eligible": ma_eligibility[200].loc[latest].to_numpy(),
    })
    return daily, coverage


def download_adjusted_closes(symbols: list[str]) -> pd.DataFrame:
    """Download two years of adjusted daily closes for a research universe."""
    if not symbols:
        raise StockDataError("At least one price symbol is required.")
    try:
        downloaded = yf.download(
            symbols, period="2y", interval="1d", auto_adjust=True,
            actions=False, group_by="ticker", threads=True, progress=False,
        )
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(f"Adjusted prices could not be loaded for the batch starting with {symbols[0]}: {exc}") from exc
    if downloaded.empty:
        raise StockDataError(f"No adjusted prices returned for the batch starting with {symbols[0]}. Use Refresh data to retry.")
    if isinstance(downloaded.columns, pd.MultiIndex):
        if "Close" not in downloaded.columns.get_level_values(1):
            raise StockDataError("Adjusted price response is missing closing prices.")
        closes = downloaded.xs("Close", axis=1, level=1)
    elif len(symbols) == 1 and "Close" in downloaded:
        closes = downloaded[["Close"]].rename(columns={"Close": symbols[0]})
    else:
        raise StockDataError("The adjusted price response has an unexpected column format.")
    return closes.reindex(columns=symbols)


def get_market_breadth(symbols: tuple[str, ...]) -> BreadthSnapshot:
    unique = list(dict.fromkeys(symbols))
    if not unique or any(not symbol.strip() or symbol == BENCHMARK_SYMBOL for symbol in unique):
        raise StockDataError("A stock universe, excluding the benchmark itself, is required.")
    batches = []
    requested = [BENCHMARK_SYMBOL, *unique]
    for start in range(0, len(requested), 100):
        batches.append(download_adjusted_closes(requested[start:start + 100]))
    prices = pd.concat(batches, axis=1)
    fetched_at = pd.Timestamp.now(tz="UTC")
    daily, coverage = calculate_market_breadth(
        prices.reindex(columns=unique), prices[BENCHMARK_SYMBOL], as_of=fetched_at,
    )
    return BreadthSnapshot(daily=daily, coverage=coverage, fetched_at=fetched_at.isoformat())
