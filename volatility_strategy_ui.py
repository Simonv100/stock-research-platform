"""Saved sector research results, with explicit evidence and coverage limits."""

from collections.abc import Callable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from market_breadth import new_york_today
from stock_data import StockDataError
from volatility_strategy import (
    BENCHMARK,
    MODEL_VERSION,
    UNIVERSE,
    analyze_pockets,
    read_saved_prices,
    refresh_saved_prices,
)


INFORMATION_COLORS = {
    "Positive (up)": "#22c55e",
    "Negative (down)": "#f87171",
    "Neutral (flat)": "#94a3b8",
    "Unavailable": "#94a3b8",
}


def render_sector_pilot(open_research: Callable[[str, list[str], str], None]) -> None:
    st.caption(
        "Semiconductor equipment pilot | Information Technology | "
        "Unusual repricing first, connected non-movers second."
    )
    st.info(
        "Price-only research leads, not proof of mispricing or buy/sell signals. "
        "Shared exposure does not guarantee a catch-up move."
    )
    refresh = st.button("Run / refresh sector analysis", type="primary", key="volatility_refresh")
    st.caption(
        "Saved locally; reopens without a download. This button updates the snapshot; clearing "
        "the shared cache does not. Two years of adjusted Yahoo prices, completed sessions only. No AI calls."
    )
    try:
        with st.spinner("Calculating sector pockets..."):
            snapshot = refresh_saved_prices() if refresh else read_saved_prices()
            if snapshot is None:
                st.info("Run the pilot to download prices and save the first sector analysis.")
                return
            result = analyze_pockets(snapshot)
    except StockDataError as exc:
        st.error(str(exc))
        st.caption("No new results are shown. A failed refresh does not replace the last valid saved snapshot.")
        return

    st.caption(
        f"Prices through {result.as_of:%Y-%m-%d} | "
        f"Five-session window: {result.window_start:%Y-%m-%d} to {result.as_of:%Y-%m-%d} | "
        f"Retrieved: {pd.Timestamp(snapshot.fetched_at):%Y-%m-%d %H:%M} UTC"
    )
    age = (new_york_today() - result.as_of).days
    if age > 7:
        st.warning(f"Historical snapshot: latest prices are {age} calendar days old. Refresh before treating this as current.")
    missing = result.stocks.loc[result.stocks["Status"] == "Unavailable"]
    if not missing.empty:
        st.warning(
            f"Partial coverage: {len(missing)}/{len(UNIVERSE)} stocks are unavailable. "
            "Missing, flat-baseline or incomplete histories are not treated as quiet stocks."
        )
    overview = result.pockets.iloc[0]
    metrics = st.columns(4)
    metrics[0].metric("Coverage", f"{int(overview['Eligible'])}/{len(UNIVERSE)}")
    metrics[1].metric("Unusual (5d)", str(int(overview["Unusual"])))
    metrics[2].metric("Active pockets", str(int(result.pockets.iloc[1:]["Active"].sum())))
    metrics[3].metric("Quiet peers", str(int((result.stocks["Status"] == "Research lead").sum())))

    st.subheader("Where unusual activity is concentrated")
    pockets = result.pockets.copy()
    pockets["Breadth"] *= 100
    st.dataframe(
        pockets[["Pocket", "Unusual", "PositiveUnusual", "NegativeUnusual", "NeutralUnusual",
                 "Breadth", "Percentile", "Status", "Direction", "Members", "Eligible"]],
        hide_index=True, width="stretch",
        column_config={
            "Breadth": st.column_config.NumberColumn("Breadth (%)", format="%.1f"),
            "Percentile": st.column_config.NumberColumn("Percentile", format="%.1f"),
            "PositiveUnusual": st.column_config.NumberColumn("Unusual up"),
            "NegativeUnusual": st.column_config.NumberColumn("Unusual down"),
            "NeutralUnusual": st.column_config.NumberColumn("Unusual flat"),
            "Direction": st.column_config.TextColumn("Leader direction vs SOXX"),
        },
    )
    st.caption(
        "Whole-bucket and sub-pocket rows overlap; do not add their counts. Percentiles compare "
        "five-session unusual-stock breadth with earlier windows in this same fixed universe, "
        "not with independent stocks or a theoretical normal distribution. Unusual up/down/flat "
        "splits count flagged stocks by their actual five-session price move, not their SOXX-relative move."
    )
    selected = st.selectbox(
        "Inspect a pocket", result.pockets["Pocket"].tolist(), key="volatility_pocket",
    )
    stocks = result.stocks if selected == result.pockets.iloc[0]["Pocket"] else result.stocks.loc[
        result.stocks["Pocket"] == selected
    ]
    st.subheader("Who moved, and who has not?")
    st.caption(
        "Price information: positive = price rose, negative = price fell, neutral = unchanged over "
        "the same five completed sessions (adjusted prices). These labels describe price direction, "
        "not verified good/bad news or information-theoretic surprise. Missing analysis data is unavailable."
    )
    display = stocks.copy()
    for column in ("Return5D", "Excess5D", "LeaderMedian", "Gap"):
        display[column] *= 100
    st.dataframe(
        display[["Symbol", "PriceInformation", "Return5D", "Status", "PeakZ", "Excess5D", "Leaders",
                 "Gap", "Company", "Pocket", "EventDate", "MoveZ5D", "LeaderMedian", "Reason"]].style.map(
            lambda value: f"color: {INFORMATION_COLORS[value]}; font-weight: 600",
            subset=["PriceInformation"],
        ),
        hide_index=True, width="stretch",
        column_config={
            "PeakZ": st.column_config.NumberColumn("Peak |z|", format="%.2f"),
            "PriceInformation": st.column_config.TextColumn("Price information (5d)"),
            "Return5D": st.column_config.NumberColumn("5d return (%)", format="%+.2f"),
            "Excess5D": st.column_config.NumberColumn(f"5d vs {BENCHMARK} (%)", format="%.2f"),
            "MoveZ5D": st.column_config.NumberColumn("5d relative move / normal scale", format="%.2f"),
            "LeaderMedian": st.column_config.NumberColumn("Leader median relative move (%)", format="%.2f"),
            "Gap": st.column_config.NumberColumn("Directional gap (pp)", format="%.2f"),
        },
    )
    candidates = stocks.loc[stocks["Status"] == "Research lead"]
    if candidates.empty:
        st.info("No quiet-peer research leads meet the pilot rules in this view. A lack of candidates is a valid result.")
    else:
        st.success("Investigate next: " + ", ".join(candidates["Symbol"]) + ". These are unverified delayed-response hypotheses.")
    st.caption(
        "Price information uses the stock's own return; leader direction and catch-up gaps still use "
        "the return relative to SOXX. A rising stock can underperform SOXX, and a falling stock can "
        "outperform it. Neither direction is the sign of acceleration. Gaps are comparisons, not target returns."
    )

    chart_tab, breadth_tab = st.tabs(["Acceleration & response", "Historical concentration"])
    with chart_tab:
        z = result.acceleration_z.loc[:, stocks["Symbol"]].tail(40)
        heatmap = go.Figure(go.Heatmap(
            x=z.index, y=z.columns, z=z.T.to_numpy(), zmid=0, zmin=-4, zmax=4,
            colorscale="RdBu", reversescale=True, colorbar={"title": "z"},
            hovertemplate="%{y}<br>%{x|%Y-%m-%d}<br>Acceleration z: %{z:.2f}<extra></extra>",
        ))
        heatmap.update_layout(
            height=370, title="Acceleration relative to the semiconductor benchmark",
            margin={"t": 55, "b": 30},
        )
        st.plotly_chart(heatmap, width="stretch", config={"displaylogo": False})
        figure = go.Figure()
        for symbol in stocks["Symbol"]:
            figure.add_trace(go.Scatter(
                x=result.relative_paths.index, y=100 * result.relative_paths[symbol],
                name=symbol, connectgaps=False,
            ))
        figure.update_layout(
            title=f"Five-session response relative to {BENCHMARK} (start = 0%)",
            yaxis_title="Relative return (%)", height=370, hovermode="x unified",
            margin={"t": 55, "b": 30},
        )
        st.plotly_chart(figure, width="stretch", config={"displaylogo": False})
    with breadth_tab:
        history = result.daily.loc[result.daily["Pocket"] == selected].tail(126)
        figure = go.Figure(go.Scatter(
            x=history.index, y=100 * history["Breadth"], name="Unusual-stock breadth",
            connectgaps=False,
        ))
        for column, label, color in (
            ("PositiveUnusual", "Positive / price up", INFORMATION_COLORS["Positive (up)"]),
            ("NegativeUnusual", "Negative / price down", INFORMATION_COLORS["Negative (down)"]),
            ("NeutralUnusual", "Neutral / flat", INFORMATION_COLORS["Neutral (flat)"]),
        ):
            split_breadth = (100 * history[column] / history["Eligible"].replace(0, float("nan"))).where(
                history["Breadth"].notna()
            )
            figure.add_trace(go.Scatter(
                x=history.index, y=split_breadth, name=label, line={"color": color}, connectgaps=False,
            ))
        figure.update_layout(
            title="Share of eligible stocks with unusual acceleration in the trailing five sessions",
            yaxis={"title": "Unusual stocks (%)", "range": [0, 100]}, height=350,
        )
        st.plotly_chart(figure, width="stretch", config={"displaylogo": False})

    symbols = stocks["Symbol"].tolist()
    if st.session_state.get("volatility_symbol") not in symbols:
        st.session_state["volatility_symbol"] = symbols[0]
    symbol = st.selectbox("Research a stock", symbols, key="volatility_symbol")
    st.button(
        "Open in Individual Stocks", key="volatility_open_research", on_click=open_research,
        args=(symbol, symbols, "Semiconductor equipment pilot"),
    )
    selected_stock = next(stock for stock in UNIVERSE if stock.symbol == symbol)
    st.write(f"**Economic exposure:** {selected_stock.exposure}")
    st.write(
        "**Verify before drawing a conclusion:** a common catalyst, orders/customer overlap, "
        "earnings timing, export controls, valuation, and whether the movers gained at a peer's expense. "
        "No catalyst or fundamental valuation has been verified by this price-only screen."
    )
    st.link_button("Company / exposure source", selected_stock.source)
    st.link_button("Adjusted-price history source", stocks.set_index("Symbol").loc[symbol, "Source"])
    with st.expander("Method, thresholds & limitations"):
        st.caption(f"Model: {MODEL_VERSION}")
        st.markdown(
            f"- Fixed, hand-picked US-listed semiconductor-equipment universe; {BENCHMARK} is a "
            "broad semiconductor ETF, not a pure equipment portfolio. It is a reference, not a candidate.\n"
            "- Daily excess log return: log(stock today / yesterday) minus the benchmark's log return. "
            "Acceleration is its first difference. Z uses the preceding 60 sessions' mean and sample "
            "standard deviation, shifted by one day. No current observation enters its own baseline.\n"
            "- Unusual = any |z| >= 2 in the last five completed sessions. Full baseline and event-window "
            "coverage are required; no price gaps are forward-filled.\n"
            "- Positive/negative price information uses the sign of the actual adjusted five-session stock "
            "return, not acceleration or excess return. Exactly zero is neutral; unavailable analysis "
            "data stays unavailable. Labels and directional breadth do not alter screening or ranking.\n"
            "- An active pocket requires >=80% coverage, at least two unusual stocks, >=30% unusual breadth, "
            "and breadth at or above the 80th midrank percentile of up to 252 earlier windows. "
            "At least 60 historical windows are needed; overlapping windows are descriptive, not p-values.\n"
            "- Directional leaders are unusual stocks whose five-session excess log move is at least one "
            "normal five-session scale in magnitude. That scale is the pre-window 60-day daily excess-return "
            "standard deviation times sqrt(5), not a calibrated probability model. At least two leaders and "
            ">=2/3 directional agreement are needed.\n"
            "- A quiet peer must share the leaders' sub-pocket, have no unusual event, |five-session move / "
            "normal scale| < 1, and have moved less than half as far as the leader median in that direction. "
            "Rank leads by the directional relative-return gap, not expected profit.\n"
            "- Unit benchmark exposure is assumed; this is not beta-neutral. Acceleration is noisy and can "
            "double-count a jump and its deceleration. Each stock counts only once per five-session window.\n"
            "- Current membership, revised adjusted data, subjective buckets, benchmark overlap and "
            "multiple comparisons limit interpretation. Historical context is not a point-in-time backtest. "
            "No out-of-sample return edge, news causality, fees, slippage or portfolio sizing is established."
        )
    st.download_button(
        "Download sector analysis (CSV)", result.stocks.assign(
            AsOf=str(result.as_of.date()), Retrieved=snapshot.fetched_at, Model=MODEL_VERSION,
        ).to_csv(index=False).encode("utf-8"),
        file_name=f"semiconductor-equipment-pockets-{result.as_of:%Y-%m-%d}.csv",
        mime="text/csv", key="volatility_download",
    )
