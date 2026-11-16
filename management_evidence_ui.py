"""No-key Streamlit views of local, manually sourced management evidence."""

from __future__ import annotations

import streamlit as st

from management_evidence import (
    CEO_ORIGINS,
    MANAGEMENT_STATUSES,
    ManagementEvidenceError,
    get_management_evidence,
    list_management_evidence,
    management_search_links,
    reset_management_evidence,
    save_management_evidence,
)


def _date_field(label: str, field: str, data: dict, key: str) -> str:
    return st.text_input(
        label, value=data[field], placeholder="YYYY-MM-DD; blank if unknown",
        key=f"{key}_{field}",
    )


def _text_field(label: str, field: str, data: dict, key: str) -> str:
    return st.text_area(label, value=data[field], key=f"{key}_{field}", height=80)


def render_management_evidence(symbol: str, company_name: str = "") -> None:
    """Render in the current container; no sidebar, parent routing, fetches or AI."""
    try:
        data = get_management_evidence(symbol)
    except ManagementEvidenceError as exc:
        st.error(str(exc))
        return
    symbol = data["ManagementSymbol"]
    key = f"_management_{symbol}"
    editor_key = f"{key}_editor_data"
    editor_data = st.session_state.setdefault(editor_key, data)
    generation = st.session_state.get(f"{key}_editor_generation", 0)
    revision = f"{key}_{editor_data['ManagementUpdatedAt'] or 'new'}_{generation}"
    st.subheader("Management & Incentives")
    st.caption(
        "Local manual research · no API key, automatic web research or AI calls. "
        "Favorable means your judgment, not automatic alpha or a recommendation. "
        "A new CEO or stock-linked pay alone is not positive evidence. "
        "Notes stay local and must not be sent to AI without explicit consent."
    )
    message = st.session_state.pop(f"{key}_message", "")
    if message:
        st.success(message)
    st.text(
        f"{symbol} · {data['ManagementStatus']} · "
        f"Review: {data['ManagementReviewDate'] or 'not dated'} "
        f"({data['ManagementReviewFreshness']})"
    )
    st.caption(data["ManagementReason"])
    if data["ManagementNewCEO"]:
        st.info("NEW CEO: recorded appointment within 365 days. This is not a favorable assessment.")
    if data["ManagementCEOName"]:
        st.text(
            f"CEO: {data['ManagementCEOName']} · {data['ManagementCEOOrigin']} · "
            f"Appointed: {data['ManagementCEOAppointmentDate'] or 'unknown'}"
        )
    if data["ManagementIncentiveChangeDate"] or data["ManagementNewMetrics"]:
        st.text(
            f"Incentive change: {data['ManagementIncentiveChangeDate'] or 'undated'} · "
            f"New metrics: {data['ManagementNewMetrics'] or 'not recorded'}"
        )
    if data["ManagementExecutionProgress"]:
        st.text(f"Execution: {data['ManagementExecutionProgress']}")
    if data["ManagementReviewStale"]:
        st.warning(
            "Review is older than 365 days. Saved judgment and evidence are preserved; "
            "refresh the review before using the favorable-only filter."
        )
    if data["ManagementManualAssessment"] != data["ManagementStatus"]:
        st.caption(f"Saved manual judgment: {data['ManagementManualAssessment']}")
    if data["ManagementNarrative"]:
        st.text(data["ManagementNarrative"])
    for label, prefix in (
        ("CEO primary source", "ManagementCEO"),
        ("Incentive primary source", "ManagementIncentive"),
        ("Execution primary source", "ManagementExecution"),
    ):
        if data[f"{prefix}SourceURL"]:
            st.link_button(
                f"{label} · {data[f'{prefix}SourceDate'] or 'date needed'}",
                data[f"{prefix}SourceURL"],
            )
    with st.expander("Research links — open manually", expanded=False):
        st.caption(
            "Only clicking a link opens an external search. Search results are not evidence: "
            "record dated issuer announcements, filed proxies/8-Ks or remuneration reports below."
        )
        for label, url in management_search_links(
            symbol, company_name or data["ManagementCompanyName"],
        ).items():
            st.link_button(label, url)

    with st.expander("Edit management evidence", expanded=False):
        if editor_data["ManagementUpdatedAt"] != data["ManagementUpdatedAt"]:
            st.warning(
                "The saved review changed in another editor. Your draft is preserved; "
                "reload saved evidence before editing the newer version."
            )
        if st.button("Reload saved evidence (discard unsaved form)", key=f"{key}_reload"):
            st.session_state[editor_key] = data
            st.session_state[f"{key}_editor_generation"] = generation + 1
            st.rerun()
        st.caption(
            "Blank means unknown. Save incomplete research as Needs evidence. "
            "For Favorable, fill every CEO/plan field and a reasoned narrative, "
            "cite dated primary CEO and incentive documents, and confirm their provenance. "
            "Write 'none' or 'not disclosed' when warranted, rather than inventing terms. "
            "A checklist cannot verify source accuracy or investment merit."
        )
        with st.form(f"{revision}_form"):
            fields = {
                "ManagementCompanyName": st.text_input(
                    "Company name", value=editor_data["ManagementCompanyName"] or company_name,
                    key=f"{revision}_company",
                ),
                "ManagementManualAssessment": st.selectbox(
                    "Manual assessment", MANAGEMENT_STATUSES,
                    index=MANAGEMENT_STATUSES.index(editor_data["ManagementManualAssessment"]),
                    key=f"{revision}_assessment",
                ),
                "ManagementReviewDate": _date_field(
                    "Review date", "ManagementReviewDate", editor_data, revision,
                ),
            }
            st.markdown("**CEO and mandate**")
            fields["ManagementCEOName"] = st.text_input(
                "CEO name", value=editor_data["ManagementCEOName"], key=f"{revision}_ceo",
            )
            fields["ManagementCEOAppointmentDate"] = _date_field(
                "CEO appointment date", "ManagementCEOAppointmentDate", editor_data, revision,
            )
            fields["ManagementCEOOrigin"] = st.selectbox(
                "Internal or external appointment", CEO_ORIGINS,
                index=CEO_ORIGINS.index(editor_data["ManagementCEOOrigin"]),
                key=f"{revision}_origin",
            )
            for label, field in (
                ("CEO background / relevant track record", "ManagementCEOBackground"),
                ("Mandate / changes expected", "ManagementCEOMandate"),
                ("Management ownership / personal capital at risk", "ManagementOwnershipEvidence"),
                ("Open-market purchases (distinguish awards and exercises)", "ManagementInsiderPurchaseEvidence"),
            ):
                fields[field] = _text_field(label, field, editor_data, revision)
            st.markdown("**Incentive changes and execution**")
            fields["ManagementIncentiveChangeDate"] = _date_field(
                "Incentive change date", "ManagementIncentiveChangeDate", editor_data, revision,
            )
            for label, field in (
                ("Old performance metrics", "ManagementOldMetrics"),
                ("New performance metrics", "ManagementNewMetrics"),
                ("Absolute share-price hurdles", "ManagementPriceHurdles"),
                ("Relative TSR hurdles / peer group", "ManagementRelativeTSRHurdles"),
                ("Measurement period", "ManagementMeasurementPeriod"),
                ("Holding / vesting period", "ManagementHoldingPeriod"),
                ("Dilution safeguards / award size", "ManagementDilutionSafeguards"),
                ("Reset / repricing / clawback safeguards", "ManagementResetSafeguards"),
                ("Execution progress / milestones / uncertainties", "ManagementExecutionProgress"),
                ("Assessment narrative / rationale / risks", "ManagementNarrative"),
            ):
                fields[field] = _text_field(label, field, editor_data, revision)
            st.markdown("**Dated primary sources**")
            for label, prefix in (
                ("CEO", "ManagementCEO"), ("Incentive", "ManagementIncentive"),
                ("Execution (optional additional citation)", "ManagementExecution"),
            ):
                fields[f"{prefix}SourceURL"] = st.text_input(
                    f"{label} source URL", value=editor_data[f"{prefix}SourceURL"],
                    key=f"{revision}_{prefix}_url",
                    placeholder="https://issuer-or-regulator.example/document",
                )
                fields[f"{prefix}SourceDate"] = _date_field(
                    f"{label} source publication date", f"{prefix}SourceDate", editor_data, revision,
                )
            fields["ManagementSourcesConfirmedPrimary"] = st.checkbox(
                "I checked that the cited documents are primary sources for these claims",
                value=editor_data["ManagementSourcesConfirmedPrimary"],
                key=f"{revision}_primary",
            )
            submitted = st.form_submit_button("Save management evidence")
        if submitted:
            try:
                saved = save_management_evidence(
                    symbol, fields, expected_updated_at=editor_data["ManagementUpdatedAt"],
                )
            except ManagementEvidenceError as exc:
                st.error(str(exc))
            else:
                st.session_state[editor_key] = saved
                st.session_state[f"{key}_message"] = "Management evidence saved locally."
                st.rerun()

    if data["ManagementUpdatedAt"]:
        with st.expander("Reset this stock's saved review", expanded=False):
            confirmed = st.checkbox(
                f"Permanently remove the saved management evidence for {symbol}",
                key=f"{revision}_confirm_reset",
            )
            if st.button("Reset management evidence", key=f"{revision}_reset", disabled=not confirmed):
                try:
                    reset_management_evidence(
                        symbol, confirmed=confirmed, expected_updated_at=editor_data["ManagementUpdatedAt"],
                    )
                except ManagementEvidenceError as exc:
                    st.error(str(exc))
                else:
                    del st.session_state[editor_key]
                    st.session_state[f"{key}_message"] = "Review reset. This stock is now Unreviewed."
                    st.session_state[f"{key}_editor_generation"] = generation + 1
                    st.rerun()


def render_management_tracker() -> None:
    """Browse saved manual reviews or enter a ticker; never navigate parent routes."""
    st.subheader("Management research tracker")
    try:
        rows = list_management_evidence()
    except ManagementEvidenceError as exc:
        st.error(str(exc))
        return
    favorable_only = st.checkbox(
        "Favorable manual reviews only (current evidence, not automatic alpha)",
        key="_management_tracker_favorable",
    )
    visible = [row for row in rows if row["ManagementFavorableFilterEligible"] or not favorable_only]
    if visible:
        st.dataframe(
            [{
                "Symbol": row["ManagementSymbol"],
                "Company": row["ManagementCompanyName"],
                "Status": row["ManagementStatus"],
                "Manual judgment": row["ManagementManualAssessment"],
                "Review date": row["ManagementReviewDate"],
                "Freshness": row["ManagementReviewFreshness"],
                "New CEO": row["ManagementNewCEO"],
            } for row in visible],
            hide_index=True,
        )
    else:
        st.info("No matching saved reviews." if rows else "No management reviews yet. Unresearched stocks are Unreviewed.")
    symbols = [row["ManagementSymbol"] for row in visible]
    if (
        st.session_state.pop("_management_tracker_clear_selection", False)
        or st.session_state.get("_management_tracker_selection", "") not in ["", *symbols]
    ):
        st.session_state["_management_tracker_selection"] = ""
    selected = st.selectbox(
        "Saved review", ["", *symbols], key="_management_tracker_selection",
        format_func=lambda symbol: symbol or "Choose a saved review",
    )
    with st.form("_management_tracker_open"):
        ticker = st.text_input("Research another ticker", key="_management_tracker_ticker")
        name = st.text_input("Company name (optional)", key="_management_tracker_company")
        opened = st.form_submit_button("Open local management review")
    if opened:
        try:
            data = get_management_evidence(ticker)
        except ManagementEvidenceError as exc:
            st.error(str(exc))
        else:
            st.session_state["_management_tracker_opened"] = (data["ManagementSymbol"], name)
            st.session_state["_management_tracker_clear_selection"] = True
            st.rerun()
    if selected:
        row = next(row for row in visible if row["ManagementSymbol"] == selected)
        render_management_evidence(selected, row["ManagementCompanyName"])
    elif "_management_tracker_opened" in st.session_state:
        render_management_evidence(*st.session_state["_management_tracker_opened"])
