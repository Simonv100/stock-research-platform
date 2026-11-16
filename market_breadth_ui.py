"""Market breadth charts with explicit coverage and current-universe limitations."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from market_breadth import BreadthSnapshot, MINIMUM_COVERAGE, new_york_today


def breadth_comparison_chart(daily: pd.DataFrame) -> go.Figure:
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(go.Scatter(
        x=daily.index, y=daily["IndexRebased"], name="S&P 500 (start = 100)",
        line={"color": "#2563eb"}, hovertemplate="%{x|%Y-%m-%d}<br>Index: %{y:.2f}<extra></extra>",
    ), secondary_y=False)
    figure.add_trace(go.Scatter(
        x=daily.index, y=daily["ADLine"], name="Cumulative advance/decline",
        line={"color": "#0f766e"}, connectgaps=False,
        hovertemplate="%{x|%Y-%m-%d}<br>A/D line: %{y:,.0f}<extra></extra>",
    ), secondary_y=True)
    figure.update_yaxes(title_text="S&P 500 rebased to 100", secondary_y=False)
    figure.update_yaxes(title_text="Cumulative net advancing listings", secondary_y=True, showgrid=False)
    figure.update_layout(
        template="plotly_white", height=440, hovermode="x unified",
        legend={"orientation": "h", "y": 1.15}, margin={"t": 65, "b": 30},
    )
    return figure


def breadth_participation_chart(daily: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    for column, label, color in (
        ("AboveMA50Percent", "Above 50-day average", "#2563eb"),
        ("AboveMA200Percent", "Above 200-day average", "#9333ea"),
    ):
        figure.add_trace(go.Scatter(
            x=daily.index, y=daily[column], name=label, line={"color": color}, connectgaps=False,
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f}%<extra></extra>",
        ))
    figure.add_hline(y=50, line_dash="dot", line_color="#64748b")
    figure.update_layout(
        template="plotly_white", height=330, hovermode="x unified",
        yaxis={"title": "Eligible listings above average (%)", "range": [0, 100]},
        legend={"orientation": "h", "y": 1.15}, margin={"t": 65, "b": 30},
    )
    return figure


def render_market_breadth(snapshot: BreadthSnapshot, holdings_date: str) -> None:
    daily = snapshot.daily
    latest = daily.iloc[-1]
    date = daily.index[-1]
    universe_size = int(latest["UniverseSize"])
    comparable = int(latest["ADComparable"])
    st.caption(
        f"Latest completed index date: {date:%Y-%m-%d} | "
        f"{universe_size} current IVV equity listings, holdings dated {holdings_date} | "
        f"Fetched: {snapshot.fetched_at}"
    )
    age = (new_york_today() - date).days
    if age > 7:
        st.warning(f"Price data is stale: the latest index date is {age} calendar days old. Refresh before interpreting current breadth.")
    if comparable < universe_size:
        st.warning(
            f"Partial daily breadth: {comparable}/{universe_size} listings have prices on both latest sessions. "
            "Missing listings are not counted as declining or unchanged."
        )
    st.caption(
        "Current-constituent reconstruction, not the official historical S&P 500 breadth series. "
        "Membership changes introduce survivorship bias; multiple share classes count as separate listings."
    )
    metrics = st.columns(5)
    index_return = latest["IndexReturn"]
    metrics[0].metric("S&P 500 daily move", f"{index_return:+.2%}" if pd.notna(index_return) else "N/A")
    sufficient = latest["ADCoverage"] >= MINIMUM_COVERAGE
    metrics[1].metric("Advancing / declining", (
        f"{int(latest['Advancing'])} / {int(latest['Declining'])}" if sufficient else "N/A"
    ), help=f"{int(latest['Unchanged'])} unchanged among {comparable} comparable listings.")
    advancing = latest["AdvancingPercent"]
    metrics[2].metric("Stocks advancing", f"{advancing:.1f}%" if pd.notna(advancing) else "N/A")
    for metric, window in zip(metrics[3:], (50, 200)):
        value = latest[f"AboveMA{window}Percent"]
        metric.metric(f"Above {window}-day MA", f"{value:.1f}%" if pd.notna(value) else "N/A")
    st.caption(
        f"Latest coverage: daily A/D {comparable}/{universe_size}; "
        f"50-day MA {int(latest['MA50Comparable'])}/{universe_size}; "
        f"200-day MA {int(latest['MA200Comparable'])}/{universe_size}. "
        f"Each metric requires at least {MINIMUM_COVERAGE:.0%} coverage; otherwise it is N/A."
    )
    st.subheader("Is participation confirming the index?")
    st.plotly_chart(breadth_comparison_chart(daily), width="stretch", config={"displaylogo": False})
    st.caption(
        "A/D adds the daily number advancing minus declining, with each listing weighted equally. "
        "The S&P 500 is capitalization weighted. Compare direction and turning points, not line heights: "
        "the two axes have different units. The A/D total starts from zero before this chart window."
    )
    if daily["NetAdvances"].isna().any():
        st.warning(
            "A/D has gaps where coverage is insufficient. The cumulative line restarts after each gap; "
            "levels across those breaks are not comparable."
        )
    st.subheader("How broad is the trend?")
    st.plotly_chart(breadth_participation_chart(daily), width="stretch", config={"displaylogo": False})
    st.caption(
        "Percentages use only listings with a full 50- or 200-session history, including today's chart date. "
        "Gaps are not forward-filled; insufficient history is not a bearish reading."
    )
    with st.expander("How to read market breadth", expanded=False):
        st.write(
            "If the index rises while the A/D line and the percentage above moving averages rise too, "
            "participation is broadening. If the index makes new highs while breadth weakens, leadership "
            "may be narrowing. Divergence is a warning to investigate, not a standalone sell signal."
        )
        st.write(
            "These measures ask whether stocks are rising, not whether they outperform the index. "
            "The chart uses up to 252 index sessions, with two years of prices for moving-average warm-up. "
            "Today's New York session is always excluded to avoid mixing intraday and completed prices. "
            "Stock comparisons use Yahoo's dividend/split-adjusted closes; the S&P 500 benchmark (^GSPC) "
            "is a price index, not a total-return index."
        )
        st.link_button("Universe source: iShares Core S&P 500 ETF (IVV)", "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf")
        st.link_button("Index source: Yahoo Finance S&P 500", "https://finance.yahoo.com/quote/%5EGSPC/history/")
    with st.expander("Data coverage & daily values"):
        st.dataframe(snapshot.coverage, hide_index=True, width="stretch")
        st.dataframe(daily, width="stretch")
    st.download_button(
        "Download breadth data (CSV)", daily.to_csv().encode("utf-8"),
        file_name="sp500-current-universe-breadth.csv", mime="text/csv", key="breadth_download",
    )
