"""Price/volume consolidation breakouts inspired by CLMT's February 2026 move."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from numbers import Real
import re
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf

from stock_chat import canonical_symbol
from stock_data import MARKET_DATA_EXCEPTIONS, StockDataError


BREAKOUT_MODEL_VERSION = "early-breakout-v1"
BREAKOUT_UNIVERSES = ("Russell 2000 stocks", "S&P 500 stocks", "European stocks", "Custom tickers")
PRICE_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
MIN_HISTORY = 221
MAX_EVENT_AGE = 20
CLMT_REFERENCE = {
    "Symbol": "CLMT", "Name": "Calumet", "AsOf": "2026-02-03", "BreakoutDate": "2026-02-03",
    "BreakoutLevel": 23.41, "BreakoutClose": 23.99, "BreakoutReturn": 0.05543,
    "BreakoutVolumeRatio": 1.657, "BaseDepth": 0.2375, "EventVsMA50": 0.191,
    "CloseLocation": 0.993, "Price": 23.99, "SessionsSinceBreakout": 0,
    "ExtensionFromBreakout": 0.02478, "BreakoutHeld": True,
}
RULES_TEXT = """
Early breakout rules (research heuristics, not optimized or backtested):

- Close at least 1% above the highest intraday high of the PREVIOUS 60 trading sessions.
- The previous 60-session range depth, (highest high - lowest low) / highest high,
  is no more than 30%. This is a bounded consolidation, not a fitted chart template.
- Breakout-day close rises at least 3% from the preceding close.
- Breakout-day volume is at least 1.5 times the mean volume of the PREVIOUS 20
  sessions, excluding the breakout day. At least 15 of those sessions have positive volume.
- Close > 50-day moving average > 200-day moving average, and the 50-day average
  is higher than 20 sessions earlier.
- The breakout close is no more than 25% above the 50-day average and finishes in
  the upper 30% of its daily high-low range, avoiding some already extended surges.
- A current candidate must still be above its 50-day average and every subsequent
  close must hold at or above the ORIGINAL breakout level. Intraday retests are allowed.
- Default freshness: breakout at most 5 trading sessions ago and current close
  at most 10% above the original level. These display filters can be changed locally.

Levels, volumes and returns use the same adjusted daily price history. All rolling
baselines exclude the event session; trend averages include that session's close.
Signals are knowable only after that close, not at an assumed earlier execution price.
The newest qualifying event at most 20 sessions ago is assessed (age 0 is the latest
completed bar). At least 221 valid daily
observations are required. Missing/invalid/stale data is unavailable, never a match.
Current-date bars are excluded conservatively, even if a local exchange has closed.
The reference is an example, not a forecast, buy recommendation or stock-specific exception.
"""


def completed_breakout_date() -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()


def parse_breakout_symbols(text: str) -> list[str]:
    if not isinstance(text, str):
        raise StockDataError("Enter ticker symbols separated by spaces or commas.")
    parts = re.split(r"[\s,;]+", text.strip()) if text.strip() else []
    if not parts or len(parts) > 50:
        raise StockDataError("Enter between 1 and 50 ticker symbols.")
    symbols = list(dict.fromkeys(canonical_symbol(part) for part in parts))
    if any(not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,24}", symbol) for symbol in symbols):
        raise StockDataError("Use stock tickers with optional exchange suffixes, not indices, FX or futures.")
    return symbols


def get_breakout_history(symbol: str, *, reference: bool = False) -> pd.DataFrame:
    symbol = canonical_symbol(symbol)
    if reference and symbol != "CLMT":
        raise StockDataError("The fixed reference history is only defined for CLMT.")
    request: dict[str, Any] = (
        {"start": "2025-01-01", "end": "2026-02-04"} if reference else {"period": "2y"}
    )
    try:
        history = yf.Ticker(symbol).history(
            **request, interval="1d", auto_adjust=True, actions=False, raise_errors=True,
        )
    except (*MARKET_DATA_EXCEPTIONS, ValueError) as exc:
        raise StockDataError(f"Adjusted daily prices for {symbol} could not be loaded.") from exc
    if history.empty:
        raise StockDataError(f"No adjusted daily price history was returned for {symbol}.")
    return history


def _date(value: str) -> pd.Timestamp:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise StockDataError("Breakout assessment date must use YYYY-MM-DD.")
    try:
        return pd.Timestamp(value)
    except ValueError:
        raise StockDataError("Breakout assessment date is invalid.") from None


def _prices(history: pd.DataFrame, as_of: str) -> pd.DataFrame:
    cutoff = _date(as_of)
    if not isinstance(history, pd.DataFrame) or not set(PRICE_COLUMNS).issubset(history.columns):
        raise StockDataError("Breakout analysis requires daily Open, High, Low, Close and Volume.")
    if not isinstance(history.index, pd.DatetimeIndex) or history.index.hasnans:
        raise StockDataError("Breakout analysis requires valid daily price dates.")
    prices = history.loc[:, list(PRICE_COLUMNS)].copy()
    if prices.index.tz is not None:
        prices.index = prices.index.tz_localize(None)
    prices.index = prices.index.normalize()
    prices = prices.loc[prices.index <= cutoff].sort_index()
    if prices.empty:
        raise StockDataError("No completed prices are available on or before the assessment date.")
    if prices.index.has_duplicates:
        raise StockDataError("Duplicate daily price dates prevent a reliable breakout assessment.")
    # Two years are fetched; only the current analysis context needs validation.
    prices = prices.tail(320)
    for column in PRICE_COLUMNS:
        if not prices[column].map(
            lambda value: isinstance(value, Real) and not pd.api.types.is_bool(value)
        ).all():
            raise StockDataError(f"Missing or invalid {column} data prevents a reliable breakout assessment.")
        prices[column] = pd.to_numeric(prices[column], errors="coerce")
        if not prices[column].between(0, 1e100, inclusive="both").all():
            raise StockDataError(f"Missing, negative or nonfinite {column} data prevents a reliable breakout assessment.")
    if (prices.loc[:, ["Open", "High", "Low", "Close"]] <= 0).any().any():
        raise StockDataError("Nonpositive prices prevent a reliable breakout assessment.")
    if (
        (prices["Low"] > prices[["Open", "Close"]].min(axis=1)).any()
        or (prices["High"] < prices[["Open", "Close"]].max(axis=1)).any()
        or (prices["Low"] > prices["High"]).any()
    ):
        raise StockDataError("Inconsistent OHLC prices prevent a reliable breakout assessment.")
    return prices


def _breakout_measurements(prices: pd.DataFrame) -> pd.DataFrame:
    close = prices["Close"]
    level = prices["High"].shift(1).rolling(60, min_periods=60).max()
    bottom = prices["Low"].shift(1).rolling(60, min_periods=60).min()
    ma50 = close.rolling(50, min_periods=50).mean()
    ma200 = close.rolling(200, min_periods=200).mean()
    prior_volume = prices["Volume"].shift(1).rolling(20, min_periods=20).mean()
    positive_volume_days = prices["Volume"].shift(1).gt(0).rolling(20, min_periods=20).sum()
    measurements = pd.DataFrame({
        "BreakoutLevel": level,
        "BreakoutReturn": close / close.shift(1) - 1,
        "BreakoutVolumeRatio": prices["Volume"] / prior_volume.where(prior_volume > 0),
        "BaseDepth": (level - bottom) / level,
        "EventVsMA50": close / ma50 - 1,
        "CloseLocation": (close - prices["Low"]) / (prices["High"] - prices["Low"]).where(prices["High"] > prices["Low"]),
        "MA50": ma50, "MA200": ma200,
    })
    measurements["Qualifies"] = (
        (close >= level * 1.01)
        & (bottom >= level * 0.70)
        & (close >= close.shift(1) * 1.03)
        & (prices["Volume"] >= prior_volume * 1.5)
        & (prior_volume > 0) & (positive_volume_days >= 15)
        & (close > ma50) & (ma50 > ma200)
        & (ma50 > ma50.shift(20)) & (close <= ma50 * 1.25)
        & ((close - prices["Low"]) >= (prices["High"] - prices["Low"]) * 0.70)
        & (prices["High"] > prices["Low"])
    )
    return measurements


def analyze_early_breakout(history: pd.DataFrame, *, as_of: str) -> dict[str, Any]:
    cutoff = _date(as_of)
    try:
        prices = _prices(history, as_of)
    except StockDataError as exc:
        return {"Status": "Unavailable", "Reason": str(exc), "AsOf": None}
    latest_date = prices.index[-1]
    base = {"AsOf": latest_date.strftime("%Y-%m-%d"), "Price": float(prices["Close"].iloc[-1])}
    if len(prices) < MIN_HISTORY:
        return {**base, "Status": "Unavailable", "Reason": f"At least {MIN_HISTORY} valid daily observations are required; received {len(prices)}."}
    if (cutoff - latest_date).days > 7:
        return {**base, "Status": "Unavailable", "Reason": "Latest completed prices are more than seven calendar days old."}
    if prices["Volume"].tail(21).sum() == 0:
        return {**base, "Status": "Unavailable", "Reason": "Recent volume is unavailable or all zero."}
    metrics = _breakout_measurements(prices)
    recent = metrics.tail(MAX_EVENT_AGE + 1)
    signals = recent.loc[recent["Qualifies"]]
    if signals.empty:
        return {
            **base, "Status": "No recent breakout",
            "Reason": "No event at most 20 trading sessions ago meets every consolidation, price, volume and trend rule.",
        }
    event_date = signals.index[-1]
    event = signals.iloc[-1]
    level = float(event["BreakoutLevel"])
    after = prices.loc[event_date:, "Close"]
    held = bool(after.ge(level).all())
    above_ma50 = bool(prices["Close"].iloc[-1] > metrics["MA50"].iloc[-1])
    status = "Recent breakout" if held and above_ma50 else "Failed breakout"
    reason = (
        "Breakout holds its original level and current price remains above the 50-day average."
        if status == "Recent breakout" else
        "At least one subsequent close fell below the original breakout level or current price lost its 50-day average."
    )
    return {
        **base, "Status": status, "Reason": reason,
        "BreakoutDate": event_date.strftime("%Y-%m-%d"),
        "BreakoutLevel": level,
        "BreakoutClose": float(prices.loc[event_date, "Close"]),
        **{field: float(event[field]) for field in (
            "BreakoutReturn", "BreakoutVolumeRatio", "BaseDepth", "EventVsMA50", "CloseLocation",
        )},
        "SessionsSinceBreakout": len(after) - 1,
        "ExtensionFromBreakout": base["Price"] / level - 1,
        "BreakoutHeld": held,
    }


def filter_breakout_candidates(
    rows: list[dict[str, Any]], recent_sessions: int, max_extension: float,
) -> pd.DataFrame:
    if type(recent_sessions) is not int or not 1 <= recent_sessions <= MAX_EVENT_AGE:
        raise StockDataError("Breakout recency must be between 1 and 20 trading sessions.")
    if isinstance(max_extension, bool) or not isinstance(max_extension, Real) or not 0 <= max_extension <= 0.30:
        raise StockDataError("Maximum breakout extension must be between 0% and 30%.")
    columns = [
        "Symbol", "Name", "Status", "Reason", "AsOf", "Price", "BreakoutDate",
        "BreakoutLevel", "BreakoutClose", "BreakoutReturn", "BreakoutVolumeRatio",
        "BaseDepth", "EventVsMA50", "CloseLocation", "SessionsSinceBreakout",
        "ExtensionFromBreakout", "BreakoutHeld",
    ]
    frame = pd.DataFrame(rows).reindex(columns=columns)
    if frame.empty:
        return frame
    ages = pd.to_numeric(frame["SessionsSinceBreakout"], errors="coerce")
    extension = pd.to_numeric(frame["ExtensionFromBreakout"], errors="coerce")
    selected = frame.loc[
        frame["Status"].eq("Recent breakout") & frame["BreakoutHeld"].eq(True)
        & ages.between(0, recent_sessions) & extension.between(0, max_extension)
    ].copy()
    return selected.sort_values(
        ["SessionsSinceBreakout", "BreakoutVolumeRatio", "Symbol"],
        ascending=[True, False, True], kind="stable",
    ).reset_index(drop=True)


def breakout_chart(history: pd.DataFrame, row: dict[str, Any]) -> go.Figure:
    prices = _prices(history, str(row["AsOf"]))
    close = prices["Close"]
    dates = prices.index.strftime("%Y-%m-%d")
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.04)
    figure.add_trace(go.Candlestick(
        x=dates[-140:], open=prices["Open"].tail(140), high=prices["High"].tail(140),
        low=prices["Low"].tail(140), close=close.tail(140), name=str(row.get("Symbol", "Price")),
    ), row=1, col=1)
    for series, name, color in ((ma50, "50-day MA", "#f97316"), (ma200, "200-day MA", "#64748b")):
        figure.add_trace(go.Scatter(
            x=dates[-140:], y=series.tail(140), name=name, line={"color": color}, connectgaps=False,
        ), row=1, col=1)
    figure.add_trace(go.Bar(x=dates[-140:], y=prices["Volume"].tail(140), name="Volume", marker_color="#64748b"), row=2, col=1)
    figure.add_hline(
        y=float(row["BreakoutLevel"]), line_dash="dash", line_color="#2563eb",
        annotation_text="Original breakout level", row=1, col=1,
    )
    figure.add_trace(go.Scatter(
        x=[str(row["BreakoutDate"])], y=[float(row["BreakoutClose"])],
        mode="markers", name="Breakout close", marker={"size": 12, "color": "#16a34a", "symbol": "diamond"},
    ), row=1, col=1)
    figure.update_layout(
        height=510, xaxis_rangeslider_visible=False,
        legend={"orientation": "h"}, margin={"l": 10, "r": 10, "t": 40, "b": 10},
    )
    figure.update_yaxes(title_text="Adjusted quote units", row=1, col=1)
    figure.update_yaxes(title_text="Shares", row=2, col=1)
    return figure
