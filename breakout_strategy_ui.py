"""On-demand, session-local early breakout research; no automatic data requests."""

from collections.abc import Callable
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from breakout_strategy import (
    BREAKOUT_MODEL_VERSION,
    BREAKOUT_UNIVERSES,
    CLMT_REFERENCE,
    RULES_TEXT,
    breakout_chart,
    filter_breakout_candidates,
    parse_breakout_symbols,
)
from stock_data import StockDataError


SNAPSHOT_KEY = "_early_breakout_snapshot"
PERCENT_COLUMNS = {
    "BreakoutReturn": "Breakout day return",
    "BaseDepth": "Prior base depth",
    "EventVsMA50": "Breakout above MA50",
    "CloseLocation": "Close in day's range",
    "ExtensionFromBreakout": "Latest above pivot",
}
QUOTE_COLUMNS = {
    "Price": "Latest adjusted close",
    "BreakoutLevel": "Original pivot",
    "BreakoutClose": "Breakout adjusted close",
}


def _table(frame: pd.DataFrame) -> None:
    display = frame.copy()
    config = {
        column: st.column_config.NumberColumn(label, format="percent")
        for column, label in PERCENT_COLUMNS.items()
    }
    config.update({
        column: st.column_config.NumberColumn(
            label, format="%.2f", help="Adjusted quote units; currency is not inferred."
        )
        for column, label in QUOTE_COLUMNS.items()
    })
    config["BreakoutVolumeRatio"] = st.column_config.NumberColumn("Volume / prior 20-day mean", format="%.2fx")
    config["SessionsSinceBreakout"] = st.column_config.NumberColumn("Sessions since breakout", format="%d")
    for column in ("AsOf", "BreakoutDate"):
        if column in display:
            display[column] = pd.to_datetime(display[column], errors="coerce")
        config[column] = st.column_config.DateColumn(column, format="YYYY-MM-DD")
    st.dataframe(display, hide_index=True, width="stretch", column_config=config)


def _reference(reference_loader: Callable[[], pd.DataFrame]) -> None:
    with st.expander("CLMT reference — February 3, 2026", expanded=True):
        st.write(
            "The target is the early February 3 breakout, not the later explosive February 13 move. "
            "This is a separate early-breakout strategy, not the U-shape strategy."
        )
        columns = st.columns(4)
        columns[0].metric("Reference breakout", CLMT_REFERENCE["BreakoutDate"])
        columns[1].metric("Original pivot (adjusted units)", f'{CLMT_REFERENCE["BreakoutLevel"]:.2f}')
        columns[2].metric("Breakout day return", f'{CLMT_REFERENCE["BreakoutReturn"]:.2%}')
        columns[3].metric("Breakout volume / mean", f'{CLMT_REFERENCE["BreakoutVolumeRatio"]:.2f}×')
        st.markdown(RULES_TEXT)
        st.caption(
            "Unvalidated heuristic thresholds, not a backtested forecast or a guarantee of finding every "
            "future winner. CLMT is a historical illustration and is never automatically added to the current queue."
        )
        key = "_early_breakout_reference_chart"
        load_reference = st.button(
            "Load CLMT reference chart", key="early_breakout_load_reference", disabled=key in st.session_state,
        )
        if load_reference and key not in st.session_state:
            try:
                history = reference_loader()
                if history is None or history.empty:
                    raise StockDataError("No reference price history returned.")
                st.session_state[key] = breakout_chart(history, CLMT_REFERENCE)
            except Exception as exc:
                st.error(f"CLMT reference chart could not be loaded: {exc}")
        if key in st.session_state:
            st.plotly_chart(st.session_state[key], width="stretch", key="early_breakout_reference_chart")
        st.caption(
            "Charts and levels use split/dividend-adjusted quote units with volume; no USD or other "
            "currency is assumed. Reference prices are historical, not live quotes."
        )
    with st.expander("Sources and interpretation"):
        st.markdown(
            "- [CLMT historical market data](https://finance.yahoo.com/quote/CLMT/history/)\n"
            "- [yfinance historical-price documentation](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html)\n"
            "- [Russell 2000 universe: iShares IWM](https://www.ishares.com/us/products/239710/ishares-russell-2000-etf)\n"
            "- [S&P 500 universe: iShares IVV](https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf)\n\n"
            "Daily bars are conservatively restricted to UTC dates before today; today's bar is excluded "
            "even if a local exchange has closed. Each row's AsOf date shows its own latest usable data. "
            "Current constituents introduce survivorship bias. Missing history is unavailable, not a failed "
            "breakout. A failed breakout broke the original pivot on a subsequent close or failed the "
            "latest trend check. These source links do not fetch data."
        )


def _validate_snapshot(snapshot: dict) -> None:
    if not isinstance(snapshot, dict) or snapshot.get("model_version") != BREAKOUT_MODEL_VERSION:
        raise StockDataError("The scanner returned an incompatible model version.")
    if (
        not isinstance(snapshot.get("rows"), list)
        or not snapshot["rows"]
        or not all(isinstance(row, dict) for row in snapshot["rows"])
        or not isinstance(snapshot.get("requested_symbols"), list)
        or not snapshot["requested_symbols"]
        or not snapshot.get("universe")
        or not snapshot.get("scanned_at")
        or not snapshot.get("as_of")
    ):
        raise StockDataError("The scanner returned an incomplete snapshot; no report was replaced.")


def render_early_breakout(
    scan_loader: Callable[[str, list[str]], dict],
    chart_loader: Callable[[str], pd.DataFrame],
    reference_loader: Callable[[], pd.DataFrame],
    open_research: Callable[[str, list[str], str], None],
    bookmark_button: Callable[[str, str], None],
) -> None:
    st.write(
        "Find recent, volume-confirmed breaks above a 60-session base while price remains close to the "
        "original pivot. Scan a universe explicitly, then narrow the saved results without downloading again."
    )
    universe = st.selectbox("Breakout universe", BREAKOUT_UNIVERSES, key="early_breakout_universe")
    custom_text = ""
    if universe == "Custom tickers":
        custom_text = st.text_input(
            "Custom tickers (maximum 50)", value="CLMT", key="early_breakout_custom",
            help="Separate symbols with commas or spaces; international exchange suffixes are preserved.",
        )
    input_identity = (universe, custom_text.strip().upper())
    filters = st.columns(2)
    recent_sessions = filters[0].number_input(
        "Maximum breakout age (sessions ago)", min_value=1, max_value=20, value=5,
        step=1, key="early_breakout_recent_sessions",
        help="Age 0 is the latest completed bar. A maximum age of 5 includes events at most five sessions ago.",
    )
    max_extension = filters[1].number_input(
        "Maximum price above original pivot (%)", min_value=0, max_value=30, value=10,
        step=1, key="early_breakout_max_extension",
    )
    st.caption(
        "Filters are local to the loaded snapshot. Refresh data clears market caches but does not reload "
        "this report or its charts: use Run breakout scan to rescan, then explicitly load a selected chart "
        "again for revised levels. No AI requests are made by this strategy."
    )
    if st.button("Run breakout scan", type="primary", key="early_breakout_run"):
        try:
            custom_symbols = parse_breakout_symbols(custom_text) if universe == "Custom tickers" else []
            with st.spinner("Scanning completed daily bars…"):
                snapshot = scan_loader(universe, custom_symbols)
            _validate_snapshot(snapshot)
            st.session_state[SNAPSHOT_KEY] = snapshot
            st.session_state["_early_breakout_loaded_input"] = input_identity
            st.session_state.pop("_early_breakout_error", None)
            st.session_state.pop("_early_breakout_selected_chart", None)
        except Exception as exc:
            st.session_state["_early_breakout_error"] = f"Breakout scan failed: {exc}"
    if st.session_state.get("_early_breakout_error"):
        st.error(st.session_state["_early_breakout_error"])

    snapshot = st.session_state.get(SNAPSHOT_KEY)
    if snapshot and snapshot.get("model_version") != BREAKOUT_MODEL_VERSION:
        st.warning("Saved report uses an incompatible model version and is hidden. Run breakout scan again.")
        snapshot = None
    if snapshot:
        if st.session_state.get("_early_breakout_error"):
            st.warning("Showing the prior successful report, not the failed scan. Its loaded universe and dates are below.")
        if st.session_state.get("_early_breakout_loaded_input") != input_identity:
            st.warning("Inputs changed. Showing the previously loaded report, not the current inputs. Run breakout scan to apply them.")
        st.subheader("Loaded breakout report")
        st.caption(
            f"Loaded universe: {snapshot['universe']} | Scanned: {snapshot['scanned_at']} | "
            f"Completed-data cutoff: {snapshot['as_of']} | Model: {snapshot['model_version']}"
        )
        as_of = pd.to_datetime(snapshot["as_of"], errors="coerce", utc=True)
        if pd.isna(as_of):
            st.warning("The saved report's cutoff date is missing or invalid. Run breakout scan again.")
        elif (datetime.now(timezone.utc).date() - as_of.date()).days > 7:
            st.warning("Historical/stale snapshot: its cutoff is more than seven calendar days old. Run breakout scan for fresh data.")

        rows = snapshot["rows"]
        audit = pd.DataFrame(rows)
        for column, default in (("Symbol", "Unknown"), ("Name", ""), ("Status", "Unavailable"), ("Reason", "")):
            if column not in audit:
                audit[column] = default
            audit[column] = audit[column].fillna(default)
        unavailable = audit["Status"].eq("Unavailable")
        audit.loc[unavailable & audit["Reason"].eq(""), "Reason"] = "Data unavailable; no provider reason supplied."
        matches = filter_breakout_candidates(rows, int(recent_sessions), float(max_extension) / 100)
        metrics = st.columns(3)
        requested = len(snapshot["requested_symbols"])
        available = int((~unavailable).sum())
        metrics[0].metric("Available / requested", f"{available} / {requested}")
        metrics[1].metric("Qualifying matches", str(len(matches)))
        metrics[2].metric("Failed breakouts", str(audit["Status"].eq("Failed breakout").sum()))
        if available < requested:
            st.warning(f"Partial coverage: {requested - available} requested listing(s) are unavailable or missing. See the audit reasons.")
        st.caption("Price and pivot columns are in adjusted quote units, not assumed USD. Percentage columns use fractional values.")
        if matches.empty:
            st.info("No matches for these local filters. The full audit and historical CLMT reference remain available below.")
        else:
            _table(matches)
            st.download_button(
                "Download displayed matches (CSV)", matches.to_csv(index=False).encode("utf-8"),
                file_name="early-breakout-matches.csv", mime="text/csv", key="early_breakout_download",
            )
            queue = matches["Symbol"].astype(str).tolist()
            if st.session_state.get("early_breakout_symbol") not in queue:
                st.session_state["early_breakout_symbol"] = queue[0]
            selected = st.selectbox("Inspect a matching stock", queue, key="early_breakout_symbol")
            row = matches.loc[matches["Symbol"].eq(selected)].iloc[0].to_dict()
            name = row.get("Name")
            bookmark_button(selected, name if isinstance(name, str) and name else selected)
            if st.button("Open in Individual Stocks", key="early_breakout_open_research"):
                open_research(selected, queue, f"Early breakout strategy — {snapshot['universe']}")
            cached_chart = st.session_state.get("_early_breakout_selected_chart")
            if cached_chart and cached_chart["symbol"] != selected:
                st.session_state.pop("_early_breakout_selected_chart", None)
                cached_chart = None
            load_chart = st.button(
                "Load selected breakout chart", key="early_breakout_load_chart", disabled=cached_chart is not None,
            )
            if load_chart and cached_chart is None:
                try:
                    history = chart_loader(selected)
                    if history is None or history.empty:
                        raise StockDataError("No chart history returned.")
                    cached_chart = {"symbol": selected, "figure": breakout_chart(history, row)}
                    st.session_state["_early_breakout_selected_chart"] = cached_chart
                except Exception as exc:
                    st.error(f"Chart for {selected} could not be loaded: {exc}")
            if cached_chart:
                st.plotly_chart(cached_chart["figure"], width="stretch", key="early_breakout_selected_chart")
        with st.expander("All scanned listings — audit and unavailable reasons"):
            _table(audit)
    else:
        st.info("No current scan report is loaded. Choose a universe and select Run breakout scan.")
    _reference(reference_loader)
