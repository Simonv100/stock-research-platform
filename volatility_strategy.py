"""A reproducible, sector-only acceleration and delayed-response research pilot."""

from __future__ import annotations

import math
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import pandas as pd

from market_breadth import download_adjusted_closes, new_york_today
from recovery_market import daily_series, yahoo_source
from stock_data import StockDataError


SNAPSHOT_PATH = Path(__file__).resolve().parent / "data" / "volatility-pilot.sqlite3"
MODEL_VERSION = "semiconductor-pockets-v2-direction-labels"
BENCHMARK = "SOXX"
BASELINE = 60
EVENT_WINDOW = 5
Z_THRESHOLD = 2.0
ALL_POCKET = "All semiconductor equipment"


@dataclass(frozen=True)
class EquipmentStock:
    symbol: str
    company: str
    pocket: str
    exposure: str
    source: str


UNIVERSE = (
    EquipmentStock("AMAT", "Applied Materials", "Wafer fabrication",
                   "Deposition, materials engineering and other wafer-fabrication tools; broad customer mix.",
                   "https://www.appliedmaterials.com/"),
    EquipmentStock("LRCX", "Lam Research", "Wafer fabrication",
                   "Etch, deposition and cleaning; memory and advanced logic spending matter.",
                   "https://www.lamresearch.com/"),
    EquipmentStock("ASML", "ASML", "Wafer fabrication",
                   "Lithography, including EUV; not interchangeable with deposition or implant suppliers.",
                   "https://www.asml.com/"),
    EquipmentStock("ACLS", "Axcelis Technologies", "Wafer fabrication",
                   "Ion implantation, including power-device manufacturing; different end-market mix from EUV.",
                   "https://www.axcelis.com/"),
    EquipmentStock("KLAC", "KLA", "Process control",
                   "Inspection and metrology across advanced semiconductor manufacturing.",
                   "https://www.kla.com/"),
    EquipmentStock("ONTO", "Onto Innovation", "Process control",
                   "Inspection, metrology and advanced-packaging process control; some lithography exposure.",
                   "https://ontoinnovation.com/"),
    EquipmentStock("NVMI", "Nova", "Process control",
                   "Dimensional and materials metrology; advanced-node process complexity.",
                   "https://www.novami.com/"),
    EquipmentStock("TER", "Teradyne", "Test & interfaces",
                   "Automated semiconductor testing, with additional robotics exposure.",
                   "https://www.teradyne.com/"),
    EquipmentStock("COHU", "Cohu", "Test & interfaces",
                   "Test, handling and inspection; automotive/industrial mix can differ from compute.",
                   "https://www.cohu.com/"),
    EquipmentStock("FORM", "FormFactor", "Test & interfaces",
                   "Probe cards and wafer-level test/measurement; not a direct substitute for test systems.",
                   "https://www.formfactor.com/"),
)


@dataclass
class PilotPrices:
    prices: pd.DataFrame
    fetched_at: str


@dataclass
class PocketAnalysis:
    stocks: pd.DataFrame
    pockets: pd.DataFrame
    daily: pd.DataFrame
    acceleration_z: pd.DataFrame
    relative_paths: pd.DataFrame
    as_of: pd.Timestamp
    window_start: pd.Timestamp


def analyze_pockets(snapshot: PilotPrices) -> PocketAnalysis:
    raw = snapshot.prices
    if raw.columns.has_duplicates or BENCHMARK not in raw:
        raise StockDataError("The sector pilot requires unique price symbols and its SOXX benchmark.")
    series = {}
    for symbol in [BENCHMARK, *[stock.symbol for stock in UNIVERSE]]:
        if symbol in raw:
            series[symbol] = daily_series(raw[[symbol]].rename(columns={symbol: "Adj Close"}), "Adj Close")
        else:
            series[symbol] = pd.Series(dtype=float)
    calendar = pd.DatetimeIndex(pd.to_datetime(raw.index))
    if calendar.tz is not None:
        calendar = calendar.tz_localize(None)
    calendar = calendar.dropna().normalize().unique().sort_values()
    prices = pd.DataFrame(series).reindex(calendar)
    prices = prices.loc[prices.index < new_york_today(snapshot.fetched_at)]
    benchmark = prices[BENCHMARK].dropna()
    if len(benchmark) < 130:
        raise StockDataError("SOXX needs at least 130 completed daily prices for baseline and historical context.")
    prices = prices.loc[:benchmark.index[-1]]
    symbols = [stock.symbol for stock in UNIVERSE]
    logs = prices.map(lambda value: math.log(value) if pd.notna(value) else float("nan"))
    returns = logs.diff()
    excess = returns[symbols].sub(returns[BENCHMARK], axis=0)
    acceleration = excess.diff()
    previous = acceleration.shift(1).rolling(BASELINE, min_periods=BASELINE)
    scale = previous.std().where(lambda values: values > 1e-12)
    z = (acceleration - previous.mean()) / scale
    eligible = z.notna().rolling(EVENT_WINDOW, min_periods=EVENT_WINDOW).sum().eq(EVENT_WINDOW)
    unusual = (z.abs() >= Z_THRESHOLD).rolling(EVENT_WINDOW, min_periods=EVENT_WINDOW).max().eq(1) & eligible
    excess_log5 = excess.rolling(EVENT_WINDOW, min_periods=EVENT_WINDOW).sum()
    pre_window_scale = excess.shift(EVENT_WINDOW).rolling(BASELINE, min_periods=BASELINE).std()
    move_z = excess_log5 / (pre_window_scale.where(pre_window_scale > 1e-12) * math.sqrt(EVENT_WINDOW))
    eligible &= move_z.notna()
    unusual &= eligible
    relative5 = excess_log5.map(lambda value: math.expm1(value) if pd.notna(value) else float("nan"))
    absolute5 = prices[symbols] / prices[symbols].shift(EVENT_WINDOW) - 1
    groups = {ALL_POCKET: symbols}
    for stock in UNIVERSE:
        groups.setdefault(stock.pocket, []).append(stock.symbol)

    pocket_rows = []
    histories = []
    leader_groups: dict[str, tuple[str, list[str], float]] = {}
    for pocket, members in groups.items():
        count = eligible[members].sum(axis=1)
        hits = unusual[members].sum(axis=1)
        positive = (unusual[members] & (absolute5[members] > 0)).sum(axis=1)
        negative = (unusual[members] & (absolute5[members] < 0)).sum(axis=1)
        neutral = (unusual[members] & (absolute5[members] == 0)).sum(axis=1)
        sufficient = count / len(members) >= 0.8
        breadth = (hits / count.replace(0, float("nan"))).where(sufficient)
        history = pd.DataFrame({
            "Pocket": pocket, "Eligible": count, "Unusual": hits, "Breadth": breadth,
            "PositiveUnusual": positive, "NegativeUnusual": negative, "NeutralUnusual": neutral,
        })
        histories.append(history)
        # The current event's five sessions never enter its historical comparison.
        reference = breadth.iloc[:-EVENT_WINDOW].dropna().tail(252)
        current = breadth.iloc[-1]
        percentile = float("nan")
        if len(reference) >= BASELINE and pd.notna(current):
            percentile = 100 * ((reference < current).sum() + 0.5 * (reference == current).sum()) / len(reference)
        active = bool(
            sufficient.iloc[-1] and hits.iloc[-1] >= 2 and current >= 0.3
            and pd.notna(percentile) and percentile >= 80
        )
        up = [s for s in members if unusual[s].iloc[-1] and move_z[s].iloc[-1] >= 1]
        down = [s for s in members if unusual[s].iloc[-1] and move_z[s].iloc[-1] <= -1]
        direction = "Mixed / unconfirmed"
        leaders = up if len(up) > len(down) else down
        if len(leaders) >= 2 and len(leaders) / max(len(up) + len(down), 1) >= 2 / 3:
            direction = "Up" if leaders is up else "Down"
        else:
            leaders = []
        median = float(relative5.loc[prices.index[-1], leaders].median()) if leaders else float("nan")
        leader_groups[pocket] = (direction, leaders if active else [], median)
        status = "Active" if active else "Below concentration threshold"
        if not sufficient.iloc[-1]:
            status = "Insufficient coverage"
        elif pd.isna(percentile):
            status = "Insufficient historical context"
        pocket_rows.append({
            "Pocket": pocket, "Members": len(members), "Eligible": int(count.iloc[-1]),
            "Unusual": int(hits.iloc[-1]), "Breadth": current, "Percentile": percentile,
            "PositiveUnusual": int(positive.iloc[-1]), "NegativeUnusual": int(negative.iloc[-1]),
            "NeutralUnusual": int(neutral.iloc[-1]),
            "Direction": direction, "Status": status, "Active": active,
        })

    rows = []
    last_date = prices.index[-1]
    for stock in UNIVERSE:
        symbol = stock.symbol
        recent = z[symbol].tail(EVENT_WINDOW)
        valid = bool(eligible[symbol].iloc[-1])
        flagged = bool(unusual[symbol].iloc[-1])
        peak = float(recent.abs().max()) if valid else float("nan")
        event_date = recent.abs().idxmax().strftime("%Y-%m-%d") if valid and flagged else ""
        direction, leaders, median = leader_groups[stock.pocket]
        sign = 1 if direction == "Up" else -1
        relative = float(relative5[symbol].iloc[-1]) if valid else float("nan")
        absolute = float(absolute5[symbol].iloc[-1]) if valid else float("nan")
        information = "Unavailable"
        if valid:
            information = "Positive (up)" if absolute > 0 else "Negative (down)" if absolute < 0 else "Neutral (flat)"
        gap = sign * (median - relative) if valid and leaders else float("nan")
        status = "No setup"
        reason = "No active, directionally confirmed sub-pocket; no delayed-response inference."
        if not valid:
            status = "Unavailable"
            reason = "Missing latest prices, incomplete 60-session baseline / 5-session window, or zero baseline variation."
        elif flagged:
            status = "Unusual mover"
            reason = "At least one unusual acceleration event; inspect catalyst and business exposure."
        elif leaders:
            if abs(move_z[symbol].iloc[-1]) < 1 and sign * relative < 0.5 * abs(median):
                status = "Research lead"
                reason = f"Quiet relative to its own history while {', '.join(leaders)} moved {direction.lower()}; common catalyst unverified."
            else:
                reason = "Already responding or making a large opposite move; not a quiet catch-up candidate."
        rows.append({
            "Symbol": symbol, "Company": stock.company, "Pocket": stock.pocket,
            "Status": status, "PeakZ": peak, "EventDate": event_date,
            "Return5D": absolute, "PriceInformation": information,
            "Excess5D": relative, "MoveZ5D": float(move_z[symbol].iloc[-1]) if valid else float("nan"),
            "Leaders": ", ".join(leaders) if valid else "", "LeaderMedian": median if leaders and valid else float("nan"),
            "Gap": gap, "Reason": reason, "Source": yahoo_source(symbol),
        })
    stocks = pd.DataFrame(rows)
    order = {"Research lead": 0, "Unusual mover": 1, "No setup": 2, "Unavailable": 3}
    stocks["_order"] = stocks["Status"].map(order)
    stocks = stocks.sort_values(["_order", "Gap", "PeakZ"], ascending=[True, False, False]).drop(columns="_order")
    relative_prices = prices[symbols].div(prices[BENCHMARK], axis=0).tail(EVENT_WINDOW + 1)
    relative_paths = relative_prices.div(relative_prices.iloc[0]) - 1
    return PocketAnalysis(
        stocks=stocks.reset_index(drop=True), pockets=pd.DataFrame(pocket_rows),
        daily=pd.concat(histories).rename_axis("Date"), acceleration_z=z,
        relative_paths=relative_paths, as_of=last_date, window_start=prices.index[-EVENT_WINDOW],
    )


def read_saved_prices() -> PilotPrices | None:
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        with closing(sqlite3.connect(SNAPSHOT_PATH, timeout=10)) as connection:
            row = connection.execute(
                "SELECT fetched_at, prices FROM snapshot WHERE id = 1"
            ).fetchone()
        if row is None:
            raise StockDataError("The saved sector snapshot is empty. Refresh the pilot.")
        prices = pd.read_json(StringIO(row[1]), orient="split")
        prices.index = pd.to_datetime(prices.index)
        fetched_at = pd.Timestamp(row[0])
        if pd.isna(fetched_at) or fetched_at.tzinfo is None:
            raise StockDataError("The saved snapshot has no valid UTC retrieval time.")
        return PilotPrices(prices, fetched_at.isoformat())
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        raise StockDataError(f"The saved sector snapshot could not be read: {exc}") from exc


def refresh_saved_prices() -> PilotPrices:
    prices = download_adjusted_closes([BENCHMARK, *[stock.symbol for stock in UNIVERSE]])
    snapshot = PilotPrices(prices, pd.Timestamp.now(tz="UTC").isoformat())
    analysis = analyze_pockets(snapshot)
    covered = int(analysis.pockets.iloc[0]["Eligible"])
    if covered / len(UNIVERSE) < 0.8:
        raise StockDataError(
            f"Only {covered}/{len(UNIVERSE)} stocks have usable histories. "
            "At least 80% coverage is required to replace the saved sector snapshot."
        )
    try:
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(SNAPSHOT_PATH, timeout=10)) as connection:
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS snapshot ("
                    "id INTEGER PRIMARY KEY CHECK(id = 1), fetched_at TEXT NOT NULL, prices TEXT NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO snapshot VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                    "fetched_at = excluded.fetched_at, prices = excluded.prices",
                    (snapshot.fetched_at, prices.to_json(orient="split", date_format="iso")),
                )
    except (OSError, sqlite3.Error) as exc:
        raise StockDataError(f"The sector snapshot could not be saved: {exc}") from exc
    return snapshot
