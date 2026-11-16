"""Curated strategy view with explicit handoffs; no market-data or AI requests."""

from collections.abc import Callable

import pandas as pd
import streamlit as st

from ip_turnaround import (
    IP_EVALUATION_CHECKLIST,
    IP_RESEARCH_AS_OF,
    IP_RESEARCH_QUEUE_LABEL,
    IP_RESEARCH_TIERS,
    IP_TURNAROUND_CANDIDATES,
)


def _escape_currency(text: str) -> str:
    # Streamlit otherwise interprets pairs of dollar signs as inline LaTeX.
    return text.replace("$", r"\$")


def render_ip_turnarounds(
    open_research: Callable[[str, list[str], str], None],
    bookmark_button: Callable[[str, str], None],
) -> None:
    st.caption(
        "Valuable products and technology surviving a business setback, with a credible "
        "route to recovery. A cross-sector, Sonos-like product-company archetype, not a "
        "screen for growing royalty income."
    )
    st.info(
        "Curated research, not an automated screener or buy list. Revenue and profit recovery, "
        "licensing income and an exact U-shape are not prerequisites. These research categories "
        "are not scores, and inclusion does not mean a current U-recovery scanner match."
    )
    st.caption(
        f"Research as of {IP_RESEARCH_AS_OF}. Financial figures and pending transactions below "
        "are dated evidence, not live observations. Refresh data does not update this research. "
        "Open Individual Stocks for current charts, financials and short interest."
    )

    with st.expander("Strategy framework and evaluation checklist"):
        st.markdown(
            "**Research thesis:** the market may have lost confidence in execution or demand "
            "while useful technology, customer relationships and product capabilities remain. "
            "Investigate whether those assets can generate sustainable per-share cash flow again."
        )
        for number, (question, explanation) in enumerate(IP_EVALUATION_CHECKLIST, start=1):
            st.markdown(f"**{number}. {question}**")
            st.write(explanation)
        st.warning(
            "There is no guaranteed patent-value floor. Patent validity, remaining life, "
            "ownership and substitutability need separate verification; no patent portfolio "
            "has been independently appraised here."
        )
        st.caption(
            "These are reference prompts, not saved review marks or automatically verified "
            "criteria. Use Trade checklist for saved personal review notes."
        )

    st.subheader("Researched shortlist")
    st.caption(
        "Core research candidates are closest to the archetype, not lower-risk endorsements. "
        "The more-confirmed recovery is a comparison; the high-risk watchlist is a separate case."
    )
    category_column, sector_column = st.columns(2)
    category = category_column.selectbox(
        "Research category", ("All categories", *IP_RESEARCH_TIERS),
        key="ip_turnaround_category",
    )
    sectors = sorted({candidate.sector for candidate in IP_TURNAROUND_CANDIDATES})
    sector = sector_column.selectbox(
        "Sector", ("All sectors", *sectors), key="ip_turnaround_sector",
    )
    candidates = [
        candidate for candidate in IP_TURNAROUND_CANDIDATES
        if (category == "All categories" or candidate.tier == category)
        and (sector == "All sectors" or candidate.sector == sector)
    ]
    if not candidates:
        st.info("No researched companies match these filters. Choose another category or sector.")
        return

    st.dataframe(
        pd.DataFrame([
            {
                "Symbol": candidate.symbol,
                "Company": candidate.name,
                "Sector": candidate.sector,
                "Research category": candidate.tier,
            }
            for candidate in candidates
        ]),
        hide_index=True, width="stretch",
    )
    by_symbol = {candidate.symbol: candidate for candidate in candidates}
    symbols = list(by_symbol)
    if st.session_state.get("ip_turnaround_symbol") not in symbols:
        st.session_state["ip_turnaround_symbol"] = symbols[0]
    symbol = st.selectbox(
        "Research a company", symbols, key="ip_turnaround_symbol",
        format_func=lambda value: f"{value} - {by_symbol[value].name}",
    )
    selected = by_symbol[symbol]
    st.subheader(f"{selected.name} ({symbol})")
    st.caption(f"{selected.tier} | {selected.sector} | Research as of {IP_RESEARCH_AS_OF}")
    bookmark, research = st.columns([1, 3])
    with bookmark:
        bookmark_button(symbol, selected.name)
    with research:
        st.button(
            "Open in Individual Stocks", type="primary", key="ip_turnaround_open_research",
            on_click=open_research, args=(symbol, symbols, IP_RESEARCH_QUEUE_LABEL),
        )
        st.caption("Carries this filtered shortlist into the stock-research navigation queue.")

    thesis, evidence = st.columns(2)
    with thesis:
        st.markdown("**Why the technology may matter**")
        st.write(_escape_currency(selected.ip_case))
        st.markdown("**Recovery route and catalysts**")
        st.write(_escape_currency(selected.recovery_case))
    with evidence:
        st.markdown("**Dated financial evidence**")
        st.write(_escape_currency(selected.financial_evidence))
        st.markdown("**Risks and qualifications**")
        if selected.tier == "High-risk watchlist":
            st.warning(_escape_currency(selected.risks))
        else:
            st.write(_escape_currency(selected.risks))
    st.markdown("**What to verify next**")
    st.write(_escape_currency(selected.watch_for))
    st.markdown("**Primary sources**")
    for source in selected.sources:
        st.link_button(f"{source.label} ({source.date})", source.url)
    st.caption("Sources open only when clicked. This page makes no market-data or AI requests.")
