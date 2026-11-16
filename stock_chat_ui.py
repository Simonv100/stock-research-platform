"""Session-local, per-stock chat panel; data and AI calls happen only on Send."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st
from streamlit.errors import StreamlitAPIException

from stock_chat import (
    DEFAULT_CHAT_MODEL,
    MAX_HISTORY_MESSAGES,
    MAX_QUESTION_CHARS,
    answer_stock_question,
    canonical_symbol,
    prepare_messages,
    redact_credentials,
)
from stock_data import StockDataError


CHAT_STATE_KEY = "_stock_chat_sessions"


def _empty_chat() -> dict:
    return {"messages": [], "draft": "", "warning": "", "dropped": False}


def _clear_stock(symbol: str, widget_key: str) -> None:
    st.session_state[CHAT_STATE_KEY][symbol] = _empty_chat()
    st.session_state[widget_key] = ""


def render_stock_chat(
    symbol: str, company_name: str, context_loader: Callable[[], dict],
    api_key: str, model: str = DEFAULT_CHAT_MODEL,
) -> None:
    """Render without calling the context loader until a keyed Send is submitted."""
    try:
        symbol = canonical_symbol(symbol)
    except StockDataError:
        st.warning("Select a valid stock to use its chat.")
        return
    key = api_key.strip() if isinstance(api_key, str) else ""
    sessions = st.session_state.setdefault(CHAT_STATE_KEY, {})
    chat = sessions.setdefault(symbol, _empty_chat())
    widget_key = f"_stock_chat_question_{symbol}"
    if chat.pop("reset_input", False) or widget_key not in st.session_state:
        st.session_state[widget_key] = chat["draft"]

    # Key rotation must not retain a pasted active credential in an existing transcript.
    chat["messages"] = prepare_messages(chat["messages"], key)
    chat["draft"] = redact_credentials(chat["draft"], key)
    with st.container(border=True, gap=None):
        heading, clear = st.columns([1.8, 1], gap="small")
        with heading:
            st.markdown(f"**Ask about {symbol}**")
            st.caption(redact_credentials(str(company_name), key)[:100])
        with clear:
            st.button(
                "Clear", key=f"_stock_chat_clear_{symbol}",
                help="Clear only this stock's conversation.",
                on_click=_clear_stock, args=(symbol, widget_key),
                disabled=not (chat["messages"] or chat["draft"] or chat["warning"]),
                width="stretch",
            )
        st.caption(
            "Public stock data + your question/chat history go to OpenAI on Send. "
            "Do not enter private data."
        )
        history_panel = st.container(height=260, border=False, autoscroll=True)
        if not key:
            st.caption("Enable Send in **AI assistant settings in the sidebar**.")
        with st.form(f"_stock_chat_form_{symbol}", clear_on_submit=False, border=False):
            question = st.text_area(
                "Question", key=widget_key, max_chars=MAX_QUESTION_CHARS,
                height=68, placeholder="What does this stock's revenue growth mean?",
                help="Use Ctrl+Enter to send from the keyboard, or press Send.",
                disabled=not key,
            )
            submitted = st.form_submit_button("Send", disabled=not key, width="stretch")

        if submitted and key:
            chat["draft"] = redact_credentials(question, key)[:MAX_QUESTION_CHARS]
            chat["warning"] = ""
            if not question.strip():
                chat["warning"] = "Enter a question about this stock."
            else:
                try:
                    with st.spinner("Answering this stock question…"):
                        context = context_loader()
                        answer = answer_stock_question(
                            symbol, context, chat["messages"], chat["draft"], key, model,
                        )
                    # Validate again before storing an answer, including mocked/custom backends.
                    if not isinstance(answer, str) or not answer.strip():
                        raise StockDataError("No answer was returned.")
                    conversation = [
                        *chat["messages"],
                        {"role": "user", "content": chat["draft"]},
                        {"role": "assistant", "content": redact_credentials(answer, key)},
                    ]
                    chat["dropped"] |= len(conversation) > MAX_HISTORY_MESSAGES
                    chat["messages"] = prepare_messages(conversation, key)
                    chat["draft"] = ""
                    chat["reset_input"] = True
                    try:
                        st.rerun(scope="fragment")
                    except StreamlitAPIException:
                        st.rerun()
                except (StockDataError, ValueError):
                    # Loader/provider exceptions can contain URLs, account details or credentials.
                    # Keep the draft for a deliberate retry; never display raw exception text.
                    chat["warning"] = (
                        "Could not answer this question. Check public data availability, "
                        "API key/model access or quota. Your question is kept; press Send "
                        "to retry explicitly. No automatic retry was made."
                    )

        with history_panel:
            if not chat["messages"]:
                st.caption("Ask a question to clarify the supplied data or a financial concept.")
            for message in chat["messages"]:
                with st.chat_message(message["role"]):
                    # Turn Markdown images into inert links; rerenders must not fetch remote media.
                    st.markdown(message["content"].replace("![", "["))
        if chat["dropped"]:
            st.caption("Older messages were dropped; only the latest six completed turns are kept/sent.")
        if chat["warning"]:
            st.warning(chat["warning"])
        st.caption("API fees · no live browsing or guaranteed returns · Browser-session chat only.")
