"""Currency-consistent size and global-sector relative-strength screens."""

from __future__ import annotations

import math
from urllib.parse import quote

import pandas as pd
import yfinance as yf

from etf_catalog import GICS_SECTOR_ETFS
from stock_data import MARKET_DATA_EXCEPTIONS, StockDataError


SECTOR_ALIASES = {
    "Technology": "Information Technology",
    "Healthcare": "Health Care",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Financial Services": "Financials",
    "Basic Materials": "Materials",
}
MINOR_CURRENCIES = {"GBp": ("GBP", 0.01), "GBX": ("GBP", 0.01),
                    "ZAc": ("ZAR", 0.01), "ILA": ("ILS", 0.01)}
MAJOR_CURRENCIES = frozenset(
    "USD EUR GBP CHF SEK NOK DKK PLN CZK HUF JPY HKD CNY CNH TWD KRW INR "
    "AUD NZD CAD BRL MXN ZAR ILS SGD THB IDR MYR PHP TRY CLP COP PEN "
    "AED SAR QAR KWD BHD EGP PKR VND".split()
)
MARKET_EVIDENCE_FIELDS = frozenset("""
SmallCapStatus SmallCapReason MarketCapUSD MarketCapLocal MarketCapCurrency
MarketCapDate MarketCapSource MarketCapFX MarketCapFXDate MarketCapFXSource
SectorStrengthStatus SectorStrengthReason SectorBenchmark SectorBenchmarkName
SectorName SectorBenchmarkSource SectorStockSource SectorFXSource SectorAsOf
SectorStart3M SectorStart6M SectorStockReturn3M SectorStockReturn6M
SectorBenchmarkReturn3M SectorBenchmarkReturn6M SectorExcess3M SectorExcess6M
SectorCurrency SectorMethod
""".split())


def quote_currency(currency: str | None) -> tuple[str, float]:
    if currency in MINOR_CURRENCIES:
        return MINOR_CURRENCIES[currency]
    if currency in MAJOR_CURRENCIES:
        return str(currency), 1.0
    raise StockDataError(f"Unsupported or missing quote currency: {currency or 'unknown'}.")


def sector_benchmark(info: dict) -> tuple[str, str, str]:
    sector = SECTOR_ALIASES.get(info.get("sector"), info.get("sector"))
    for name, symbol, fund in GICS_SECTOR_ETFS:
        if name == sector:
            return name, symbol, fund
    raise StockDataError("No global sector proxy matches the reported sector.")


def yahoo_source(symbol: str) -> str:
    return f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}/history/"


def get_recovery_prices(symbol: str) -> pd.DataFrame:
    try:
        result = yf.Ticker(symbol).history(
            period="1y", interval="1d", auto_adjust=False, actions=False,
            raise_errors=True,
        )
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(f"Recovery price/FX history for {symbol} is unavailable: {exc}") from exc
    if result.empty:
        raise StockDataError(f"No recovery price/FX history was returned for {symbol}.")
    return result


def daily_series(history: pd.DataFrame, column: str) -> pd.Series:
    if column not in history:
        raise StockDataError(f"Required {column} series is unavailable; no unadjusted substitute is used.")
    values = pd.to_numeric(history[column], errors="coerce").copy()
    dates = pd.DatetimeIndex(pd.to_datetime(values.index))
    if dates.tz is not None:
        dates = dates.tz_localize(None)
    values.index = dates.normalize()
    values = values.loc[~values.index.duplicated(keep="last")].sort_index()
    return values.where(values.map(lambda v: pd.notna(v) and math.isfinite(v) and v > 0)).dropna()


def _today(as_of: str | pd.Timestamp | None) -> pd.Timestamp:
    value = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz="UTC")
    if value.tzinfo is not None:
        value = value.tz_localize(None)
    return value.normalize()


def assess_small_cap(
    symbol: str, info: dict, fx_history: pd.DataFrame | None = None,
    as_of: str | pd.Timestamp | None = None,
) -> dict:
    result = {
        "SmallCapStatus": "Unknown", "SmallCapReason": "",
        "MarketCapSource": f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}/key-statistics/",
    }
    if info.get("quoteType") and info["quoteType"] != "EQUITY":
        return {**result, "SmallCapStatus": "Not applicable", "SmallCapReason": "Company equity market cap is not a fund-size filter."}
    try:
        currency, _ = quote_currency(info.get("currency"))
        cap = pd.to_numeric(info.get("marketCap"), errors="coerce")
        if isinstance(info.get("marketCap"), bool) or pd.isna(cap) or not math.isfinite(cap) or cap <= 0:
            raise StockDataError("Positive provider-reported market capitalization is unavailable.")
        timestamp = pd.to_numeric(info.get("regularMarketTime"), errors="coerce")
        if pd.isna(timestamp) or not math.isfinite(timestamp):
            raise StockDataError("The provider quote date is unavailable.")
        quote_date = pd.to_datetime(timestamp, unit="s", utc=True, errors="coerce")
        if pd.isna(quote_date):
            raise StockDataError("The provider quote date is invalid.")
        quote_date = quote_date.tz_localize(None).normalize()
        today = _today(as_of)
        if not 0 <= (today - quote_date).days <= 10:
            raise StockDataError("The provider quote is future-dated or more than 10 calendar days old.")
        rate = 1.0
        fx_date = quote_date
        if currency != "USD":
            if fx_history is None:
                raise StockDataError(f"{currency}/USD conversion history is unavailable.")
            fx = daily_series(fx_history, "Close").loc[:quote_date]
            if fx.empty or (quote_date - fx.index[-1]).days > 5:
                raise StockDataError("No FX observation within five days of the quote date.")
            rate = float(fx.iloc[-1])
            fx_date = fx.index[-1]
        usd_cap = float(cap) * rate
        if not math.isfinite(usd_cap):
            raise StockDataError("Converted market capitalization is not finite.")
        result.update({
            "SmallCapStatus": "Pass" if usd_cap < 2_000_000_000 else "Fail",
            "SmallCapReason": "Requires 0 < equity market capitalization < USD 2 billion. "
                "Yahoo marketCap is in major currency units, even when the share quote uses pence/cents. "
                "The date is the provider quote date, not a verified shares-outstanding date.",
            "MarketCapUSD": usd_cap, "MarketCapLocal": float(cap),
            "MarketCapCurrency": currency, "MarketCapDate": str(quote_date.date()),
            "MarketCapFX": rate, "MarketCapFXDate": str(fx_date.date()),
            "MarketCapFXSource": yahoo_source(f"{currency}USD=X") if currency != "USD" else "",
        })
    except StockDataError as exc:
        result["SmallCapReason"] = str(exc)
    return result


def assess_sector_strength(
    symbol: str, info: dict, stock_history: pd.DataFrame, benchmark_history: pd.DataFrame,
    fx_history: pd.DataFrame | None = None, as_of: str | pd.Timestamp | None = None,
) -> dict:
    result = {
        "SectorStrengthStatus": "Unknown", "SectorStrengthReason": "",
        "SectorStockSource": yahoo_source(symbol), "SectorCurrency": "USD",
        "SectorMethod": "Dividend/split-adjusted USD returns on matching observed dates, "
            "strictly outperforming the global sector ETF over BOTH 3 and 6 calendar months. "
            "Global ETFs are imperfect, often US-heavy peers, not local-sector or industry-neutral benchmarks.",
    }
    if info.get("quoteType") and info["quoteType"] != "EQUITY":
        return {**result, "SectorStrengthStatus": "Not applicable", "SectorStrengthReason": "This sector filter evaluates company equities, not funds."}
    try:
        sector, benchmark, fund = sector_benchmark(info)
        result.update({"SectorName": sector, "SectorBenchmark": benchmark,
                       "SectorBenchmarkName": fund, "SectorBenchmarkSource": yahoo_source(benchmark)})
        currency, scale = quote_currency(info.get("currency"))
        series = {
            "stock": daily_series(stock_history, "Adj Close") * scale,
            "benchmark": daily_series(benchmark_history, "Adj Close"),
        }
        if currency != "USD":
            if fx_history is None:
                raise StockDataError(f"{currency}/USD conversion history is unavailable.")
            series["fx"] = daily_series(fx_history, "Close")
            result["SectorFXSource"] = yahoo_source(f"{currency}USD=X")
        aligned = pd.concat(series, axis=1, join="inner").dropna()
        today = _today(as_of)
        aligned = aligned.loc[aligned.index <= today]
        if aligned.empty or (today - aligned.index[-1]).days > 7:
            raise StockDataError("No common stock, benchmark and FX observation within seven calendar days.")
        end = aligned.index[-1]
        aligned["usd_stock"] = aligned["stock"] * (aligned["fx"] if "fx" in aligned else 1)
        result["SectorAsOf"] = str(end.date())
        for months in (3, 6):
            target = end - pd.DateOffset(months=months)
            previous = aligned.loc[:target]
            if previous.empty or (target - previous.index[-1]).days > 7:
                raise StockDataError(f"Insufficient matching history for the {months}-month comparison.")
            start = previous.index[-1]
            window = aligned.loc[start:end]
            if window.index.to_series().diff().max() > pd.Timedelta(days=14):
                raise StockDataError("Matching observations have a gap longer than 14 calendar days.")
            stock_return = float(aligned.loc[end, "usd_stock"] / aligned.loc[start, "usd_stock"] - 1)
            benchmark_return = float(aligned.loc[end, "benchmark"] / aligned.loc[start, "benchmark"] - 1)
            if not all(math.isfinite(value) for value in (stock_return, benchmark_return)):
                raise StockDataError("Return calculation is nonfinite; check the provider observations.")
            result.update({
                f"SectorStart{months}M": str(start.date()),
                f"SectorStockReturn{months}M": stock_return,
                f"SectorBenchmarkReturn{months}M": benchmark_return,
                f"SectorExcess{months}M": stock_return - benchmark_return,
            })
        passed = result["SectorExcess3M"] > 0 and result["SectorExcess6M"] > 0
        result["SectorStrengthStatus"] = "Pass" if passed else "Fail"
        result["SectorStrengthReason"] = (
            f"USD return minus {benchmark}: {result['SectorExcess3M']:+.1%} over 3 months; "
            f"{result['SectorExcess6M']:+.1%} over 6 months. Both must exceed zero."
        )
    except StockDataError as exc:
        result["SectorStrengthReason"] = str(exc)
    return result
