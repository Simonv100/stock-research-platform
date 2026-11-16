"""Explicit, excerpt-only revenue research with browser-session stock isolation."""

from __future__ import annotations

import streamlit as st

from revenue_outlook import (
    CHECK_LABELS,
    DEFAULT_OUTLOOK_MODEL,
    HORIZONS,
    MAX_EXCERPT_CHARS,
    MAX_SOURCES,
    analyze_revenue_outlook,
    outlook_report_json,
    validate_revenue_outlook_report,
)
from stock_chat import canonical_symbol, redact_credentials
from stock_data import StockDataError


OUTLOOK_STATE_KEY = "_revenue_outlook_sessions"
SOURCE_FIELDS = ("title", "date", "url", "excerpt")


def _empty_state() -> dict:
    return {
        "sources": [{field: "" for field in SOURCE_FIELDS} for _ in range(MAX_SOURCES)],
        "source_count": 1,
        "horizon_months": 12,
        "consent": False,
        "report": None,
        "report_inputs": None,
        "failed": False,
    }


def _widget_key(symbol: str, field: str, index: int | None = None) -> str:
    suffix = field if index is None else f"{index}_{field}"
    return f"_revenue_outlook_{symbol}_{suffix}"


def _save_draft(symbol: str, field: str, index: int | None = None) -> None:
    state = st.session_state[OUTLOOK_STATE_KEY][symbol]
    value = st.session_state[_widget_key(symbol, field, index)]
    if index is None:
        state[field] = value
    else:
        state["sources"][index][field] = value


def _clear_stock(symbol: str) -> None:
    state = _empty_state()
    st.session_state[OUTLOOK_STATE_KEY][symbol] = state
    for field in ("source_count", "horizon_months", "consent"):
        st.session_state[_widget_key(symbol, field)] = state[field]
    for index, source in enumerate(state["sources"]):
        for field, value in source.items():
            st.session_state[_widget_key(symbol, field, index)] = value


def _redact(value, api_key: str):
    if isinstance(value, str):
        return redact_credentials(value, api_key)
    if isinstance(value, dict):
        return {key: _redact(item, api_key) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, api_key) for item in value]
    return value


def _request_inputs(state: dict, company_name: str, model: str) -> dict:
    sources = [
        {field: source[field].strip() for field in SOURCE_FIELDS}
        for source in state["sources"][:state["source_count"]]
        if any(source[field].strip() for field in SOURCE_FIELDS)
    ]
    return {
        "company_name": company_name,
        "sources": sources,
        "horizon_months": state["horizon_months"],
        "model": model,
    }


def _source_refs(source_ids: list[int]) -> str:
    return "Sources: " + (", ".join(f"[{item}]" for item in source_ids) or "none established")


def _render_report(report: dict, previous_inputs: bool) -> None:
    assessment = report["assessment"]
    st.subheader("Revenue outlook assessment")
    st.text(
        f"{report['symbol']} · {report['company_name']} · "
        f"{report['horizon_months']}-month horizon\n"
        f"As of: {report['as_of']}\n"
        f"Last successful assessment generated: {report['generated_at']}\n"
        f"Model: {report['model']}"
    )
    if previous_inputs:
        st.warning(
            "Previous assessment of old inputs: the sources, horizon, company or model "
            "have changed. The result below still describes its original inputs. "
            "Press Run assessment explicitly to assess the current inputs."
        )
    st.text(f"Evidence balance: {report['evidence_balance']}")
    st.caption(
        "Evidence balance describes only the supplied indicators and checks. "
        "Supportive evidence can coexist with unknown checks and incomplete coverage; "
        "it is not a revenue forecast."
    )
    st.text(assessment["summary"])
    st.caption(_source_refs(assessment["summary_source_ids"]))
    st.markdown("**Leading revenue indicators**")
    if not assessment["indicators"]:
        st.text("No leading indicators established from the supplied excerpts.")
    for indicator in assessment["indicators"]:
        st.text(
            f"{indicator['name']} — {indicator['signal']}\n"
            f"Evidence type: {indicator['evidence_type']}\n"
            f"Evidence: {indicator['evidence']}\n"
            f"Revenue link: {indicator['revenue_link']}\n"
            f"Timing: {indicator['timing']}"
        )
        st.caption(_source_refs(indicator["source_ids"]))
    st.markdown("**Five evidence checks**")
    for check_key, label in CHECK_LABELS.items():
        check = assessment["checks"][check_key]
        st.text(f"{label} — {check['status']}\n{check['reason']}")
        st.caption(_source_refs(check["source_ids"]))
    st.markdown("**What to check next**")
    st.text("\n".join(f"• {item}" for item in assessment["next_checks"]))
    st.markdown("**Limitations**")
    st.text(assessment["limitations"])
    with st.expander("Original source excerpts used in this assessment"):
        for source in report["sources"]:
            st.text(f"[{source['id']}] {source['title']}\nSource date: {source['date']}")
            st.text(source["excerpt"])
            if source["url"]:
                st.link_button(f"Open supplied source [{source['id']}]", source["url"])
            else:
                st.caption("No source URL supplied; this excerpt is not independently verified.")
    st.caption(
        "User-provided excerpts are not independently verified. URLs are not fetched. "
        "This is a qualitative evidence assessment, not a revenue forecast, "
        "probability of growth, guaranteed return or investment recommendation. "
        "Insufficient evidence does not mean zero demand or a negative finding."
    )
    st.caption(
        "JSON export includes the original source excerpts and assessment. "
        "Download only if you want to save this evidence outside the browser session."
    )
    st.download_button(
        "Download assessment JSON",
        data=outlook_report_json(report),
        file_name=f"revenue-outlook-{report['symbol'].replace('/', '-')}-{report['as_of']}.json",
        mime="application/json",
        key=_widget_key(report["symbol"], "download"),
        on_click="ignore",
    )


def render_revenue_outlook(
    symbol: str, company_name: str, api_key: str, model: str = DEFAULT_OUTLOOK_MODEL,
) -> None:
    """Only Run sends the selected stock and supplied public excerpts to OpenAI."""
    try:
        symbol = canonical_symbol(symbol)
    except StockDataError:
        st.warning("Select a valid stock to assess leading revenue indicators.")
        return
    key = api_key.strip() if isinstance(api_key, str) else ""
    sessions = st.session_state.setdefault(OUTLOOK_STATE_KEY, {})
    state = sessions.setdefault(symbol, _empty_state())
    state["sources"] = _redact(state["sources"], key)
    state["report_inputs"] = _redact(state["report_inputs"], key)
    company_name = redact_credentials(str(company_name), key)
    safe_model = redact_credentials(str(model), key)

    # Streamlit removes hidden widgets; durable drafts restore them after stock/tab switches.
    for field in ("source_count", "horizon_months", "consent"):
        widget_key = _widget_key(symbol, field)
        st.session_state[widget_key] = state[field]
    for index, source in enumerate(state["sources"][:state["source_count"]]):
        for field, value in source.items():
            widget_key = _widget_key(symbol, field, index)
            st.session_state[widget_key] = value

    with st.container(border=True):
        st.subheader("Leading revenue indicators")
        st.text(f"{symbol} · {company_name}")
        st.caption(
            "Assess orders, backlog, book-to-bill, RPO, customer usage and their "
            "conversion into revenue. Use only public source excerpts you provide: "
            "no web search, live browsing or URL fetching."
        )
        st.caption(
            "Sources, drafts and reports are browser-session-local for each stock, "
            "not saved across a server restart. Download JSON deliberately to keep a copy."
        )
        st.button(
            "Clear this stock's sources and report",
            key=_widget_key(symbol, "clear"),
            help="Deletes this stock's source drafts and assessment only; also resets consent.",
            on_click=_clear_stock, args=(symbol,),
        )
        st.selectbox(
            "Number of source excerpts", options=list(range(1, MAX_SOURCES + 1)),
            key=_widget_key(symbol, "source_count"),
            on_change=_save_draft, args=(symbol, "source_count"),
            help="Reducing the count excludes extra sources from Run, but keeps their drafts.",
        )
        st.selectbox(
            "Revenue assessment horizon (months)", options=HORIZONS,
            key=_widget_key(symbol, "horizon_months"),
            on_change=_save_draft, args=(symbol, "horizon_months"),
        )
        st.caption(
            "For each source, supply a title, its publication date (YYYY-MM-DD) and "
            "an exact public excerpt. URLs are optional and never fetched. "
            "Blank source slots are omitted. Hidden source drafts are not sent."
        )
        for index in range(state["source_count"]):
            with st.expander(f"Source {index + 1}", expanded=True):
                for field, label, help_text in (
                    ("title", "Source title (required)", "For example, Q2 earnings release or call transcript."),
                    ("date", "Publication date (required, YYYY-MM-DD)", "Use the source's date, not a future date."),
                    ("url", "Source URL (optional)", "A supplied URL is a reference only, never fetched."),
                ):
                    st.text_input(
                        label, key=_widget_key(symbol, field, index), help=help_text,
                        on_change=_save_draft, args=(symbol, field, index),
                    )
                st.text_area(
                    "Public source excerpt (required)",
                    key=_widget_key(symbol, "excerpt", index),
                    height=150, max_chars=MAX_EXCERPT_CHARS,
                    help="Include reporting period, units, context and any cancellation or timing caveats.",
                    on_change=_save_draft, args=(symbol, "excerpt", index),
                )
        st.checkbox(
            "I consent to send only this selected stock's symbol/company and the public "
            "excerpts I provide (with source labels/dates and horizon) to OpenAI. "
            "Paid API fees apply; store=false. App chat, notes and holdings are not sent.",
            key=_widget_key(symbol, "consent"),
            on_change=_save_draft, args=(symbol, "consent"),
        )
        if not key:
            st.caption("Add an API key in AI assistant settings in the sidebar to enable Run.")
        st.caption(
            "Run is the only action that calls OpenAI. Editing sources, switching stocks "
            "or tabs, rerunning the page and downloading do not run an assessment. "
            "Do not paste private data or credentials."
        )
        inputs = _request_inputs(state, company_name, safe_model)
        submitted = st.button(
            "Run assessment", key=_widget_key(symbol, "run"),
            disabled=not key or not state["consent"],
        )
        if submitted and key and state["consent"]:
            try:
                with st.spinner("Assessing the supplied revenue evidence…"):
                    result = analyze_revenue_outlook(
                        symbol=symbol, company_name=inputs["company_name"],
                        sources=inputs["sources"], horizon_months=inputs["horizon_months"],
                        api_key=key, model=inputs["model"],
                    )
                result = validate_revenue_outlook_report(_redact(result, key))
                if result["symbol"] != symbol or result["horizon_months"] != inputs["horizon_months"]:
                    raise StockDataError("The returned assessment does not match this request.")
                state["report"] = result
                state["report_inputs"] = inputs
                state["failed"] = False
            except (StockDataError, ValueError, TypeError, KeyError):
                state["failed"] = True
        if state["failed"]:
            st.warning(
                "Run failed; no new successful assessment was saved. Any previous result "
                "below is not a new success. Check required source fields, publication dates, "
                "URLs, API key/model access and quota. Drafts are kept. No automatic retry "
                "was made; press Run assessment explicitly to retry."
            )
        if state["report"] is not None:
            try:
                report = validate_revenue_outlook_report(_redact(state["report"], key))
                if report["symbol"] != symbol:
                    raise StockDataError("The saved assessment belongs to another stock.")
                state["report"] = report
                _render_report(report, state["report_inputs"] != inputs)
            except (StockDataError, ValueError, TypeError, KeyError):
                st.warning("The saved assessment could not be validated and is not displayed or exported.")
