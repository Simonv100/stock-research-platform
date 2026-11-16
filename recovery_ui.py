"""Explainable recovery metrics shared by scanner and individual-stock research."""

import pandas as pd
import streamlit as st


def render_recovery_evidence(evidence: dict) -> None:
    summaries = []
    for title, prefix in (("Profitability & cash", "Profitability"),
                          ("Sector-relative strength", "SectorStrength"),
                          ("Market cap < USD 2B", "SmallCap"),
                          ("Deleveraging", "Deleveraging"),
                          ("Positive shareholder yield", "ShareholderYield")):
        summaries.append({
            "Criterion": title, "Status": evidence.get(f"{prefix}Status", "Not loaded"),
            "Explanation": evidence.get(f"{prefix}Reason", "Load recovery evidence or enable this scanner filter."),
        })
    st.dataframe(pd.DataFrame(summaries), hide_index=True, width="stretch")
    if "ShareholderYield" in evidence:
        st.metric(
            "Shareholder yield", f"{evidence['ShareholderYield']:.2%}",
            help=evidence.get("ShareholderYieldPeriod"),
        )
        st.caption(
            f"{evidence.get('ShareholderYieldPeriod', 'Unknown period')}. "
            f"{evidence.get('ShareholderYieldMethod', '')}"
        )
    if "MarketCapUSD" in evidence:
        st.write(
            f"Equity market cap: **USD {evidence['MarketCapUSD']:,.0f}** "
            f"(provider quote {evidence.get('MarketCapDate', 'unknown')}; "
            f"FX {evidence.get('MarketCapFXDate', 'unknown')})."
        )
    if "SectorBenchmark" in evidence:
        st.write(f"Benchmark: **{evidence['SectorBenchmark']}** — {evidence.get('SectorBenchmarkName', '')}")
        returns = []
        for months in (3, 6):
            if f"SectorExcess{months}M" not in evidence:
                continue
            returns.append({
                "Horizon": f"{months} months", "From": evidence[f"SectorStart{months}M"],
                "To": evidence.get("SectorAsOf", ""),
                "Stock USD return": f"{evidence[f'SectorStockReturn{months}M']:.1%}",
                "Sector USD return": f"{evidence[f'SectorBenchmarkReturn{months}M']:.1%}",
                "Excess (percentage points)": f"{100 * evidence[f'SectorExcess{months}M']:+.2f}",
            })
        if returns:
            st.dataframe(pd.DataFrame(returns), hide_index=True, width="stretch")
        st.caption(evidence.get("SectorMethod", "Global-sector proxy; not exact local peers."))
    if any(key.startswith("Financial") for key in evidence):
        st.caption("Statement values use the reported financial currency, not the share quote currency.")
        currency = evidence.get("FinancialCurrency") or "Unknown currency"
        financial_rows = []
        for label, prefix, period_prefix, percent in (
            ("Operating margin", "OperatingMargin", "Financial", True),
            ("Free cash flow", "FreeCashFlow", "Financial", False),
            ("Gross debt", "GrossDebt", "FinancialDebt", False),
            ("Net debt", "NetDebt", "FinancialDebt", False),
        ):
            latest = evidence.get(f"{prefix}Latest")
            prior = evidence.get(f"{prefix}Prior")
            if latest is None or prior is None:
                continue
            financial_rows.append({
                "Metric": label,
                "Earlier period": evidence.get(f"{period_prefix}PriorPeriodEnd"),
                "Earlier value": f"{prior:.2%}" if percent else f"{currency} {prior:,.0f}",
                "Latest period": evidence.get(f"{period_prefix}PeriodEnd"),
                "Latest value": f"{latest:.2%}" if percent else f"{currency} {latest:,.0f}",
                "Basis": evidence.get(f"{period_prefix}PeriodBasis"),
            })
        if financial_rows:
            st.dataframe(pd.DataFrame(financial_rows), hide_index=True, width="stretch")
    details = {
        key: value for key, value in evidence.items()
        if key.startswith(("Financial", "Operating", "FreeCashFlow", "GrossDebt", "NetDebt",
                           "MarketCap", "Sector", "ShareholderYield"))
        and not key.endswith(("Status", "Reason"))
    }
    if details:
        with st.expander("Comparison values, dates & sources"):
            st.dataframe(
                pd.DataFrame([{"Field": key, "Value": str(value) if value is not None else "Unknown"}
                              for key, value in details.items()]),
                hide_index=True, width="stretch",
            )
            for key, value in details.items():
                if isinstance(value, str) and value.startswith("https://") and ("Source" in key or "URL" in key):
                    st.link_button(key, value)
    st.caption(
        "Shrinking cash burn can pass profitability, but is not positive cash generation. "
        "Deleveraging requires declining gross AND net debt plus positive free cash flow; "
        "it does not verify debt maturities, covenants, asset sales, refinancing terms or dilution. "
        "Missing data is not a pass. Financial companies and REITs need sector-specific accounting."
    )
