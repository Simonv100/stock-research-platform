"""Reusable manual checklist, separate from stock research and AI context."""

import streamlit as st

from trade_checklist import (
    ChecklistError,
    add_checklist_item,
    delete_checklist_item,
    list_checklist_items,
    reset_checklist_checks,
    set_checklist_checked,
    update_checklist_item,
)


def _save_check(item_id: int, revision: int, key: str) -> None:
    try:
        set_checklist_checked(item_id, revision, st.session_state[key])
    except ChecklistError as exc:
        st.session_state["_trade_checklist_error"] = str(exc)
        st.session_state.pop(key, None)


def _fields(key: str, item: dict | None = None) -> dict[str, str]:
    values = item or {}
    return {
        "title": st.text_input("Checklist item", value=values.get("title", ""), max_chars=160, key=f"{key}_title"),
        "note": st.text_area("Note", value=values.get("note", ""), max_chars=4000, key=f"{key}_note"),
        "attribution": st.text_input(
            "Attribution (optional)", value=values.get("attribution", ""), max_chars=300, key=f"{key}_attribution",
        ),
        "source_url": st.text_input(
            "Source URL (optional)", value=values.get("source_url", ""), max_chars=2000, key=f"{key}_source",
        ),
    }


def render_trade_checklist() -> None:
    st.title("Trade checklist")
    st.caption(
        "A reusable pre-trade review, not a trade journal or automatic buy/sell signal. "
        "Items and review marks are saved locally and shared across this app's browser sessions. "
        "These notes are not sent to AI."
    )
    if st.button("Reload checklist", key="trade_checklist_reload"):
        st.rerun()
    error = st.session_state.pop("_trade_checklist_error", None)
    if error:
        st.error(error)
    notice = st.session_state.pop("_trade_checklist_notice", None)
    if notice:
        st.success(notice)
    try:
        items = list_checklist_items()
    except ChecklistError as exc:
        st.error(str(exc))
        return

    st.subheader("Add checklist item")
    st.caption("Add a new point here. Only the title is required; it will be saved to your checklist unchecked.")
    generation = st.session_state.get("trade_checklist_add_generation", 0)
    key = f"trade_add_{generation}"
    with st.form(f"{key}_form"):
        fields = _fields(key)
        add = st.form_submit_button("Add item", key=f"{key}_submit", type="primary")
    if add:
        try:
            add_checklist_item(**fields)
        except ChecklistError as exc:
            st.error(str(exc))
        else:
            st.session_state["trade_checklist_add_generation"] = generation + 1
            st.session_state["_trade_checklist_notice"] = "Checklist item added."
            st.rerun()

    st.divider()
    st.subheader("Your checklist")
    completed = sum(item["checked"] for item in items)
    progress, reset = st.columns([3, 1])
    progress.metric("Reviewed", f"{completed} / {len(items)}")
    if items:
        progress.progress(completed / len(items))
    if reset.button("Start new review", disabled=not completed, key="trade_checklist_reset"):
        try:
            reset_checklist_checks()
        except ChecklistError as exc:
            st.error(str(exc))
        else:
            st.session_state["_trade_checklist_notice"] = "Review marks cleared. Your checklist items and notes are unchanged."
            st.rerun()
    st.caption("Check each item after reviewing it. Start new review clears only the checkmarks; it does not delete your principles.")
    if not items:
        st.info("Your checklist is empty. Add your first item above.")

    for position, item in enumerate(items, start=1):
        key = f"trade_item_{item['id']}_{item['revision']}"
        with st.container(border=True):
            check_key = f"{key}_checked_{int(item['checked'])}"
            st.checkbox(
                f"{position}. {item['title']}", value=item["checked"], key=check_key,
                on_change=_save_check, args=(item["id"], item["revision"], check_key),
            )
            if item["note"]:
                st.text(item["note"])
            if item["attribution"]:
                st.text(item["attribution"])
            if item["source_url"]:
                st.link_button("Open source", item["source_url"])
            with st.expander("Edit or remove item"):
                st.caption("Saving an edit unchecks this item so the revised wording can be reviewed.")
                editor_key = f"trade_editor_{item['id']}"
                editor = st.session_state.setdefault(editor_key, item.copy())
                if editor["revision"] != item["revision"]:
                    st.warning("This item changed in another view. Your draft is preserved; reload the saved item before editing it.")
                if st.button("Reload saved item (discard unsaved edits)", key=f"trade_reload_{item['id']}"):
                    st.session_state[editor_key] = item.copy()
                    generation_key = f"{editor_key}_generation"
                    st.session_state[generation_key] = st.session_state.get(generation_key, 0) + 1
                    st.rerun()
                editor_generation = st.session_state.get(f"{editor_key}_generation", 0)
                edit_key = f"trade_edit_{item['id']}_{editor['revision']}_{editor_generation}"
                with st.form(f"{edit_key}_form"):
                    fields = _fields(edit_key, editor)
                    save = st.form_submit_button("Save changes", key=f"{edit_key}_save")
                if save:
                    try:
                        update_checklist_item(item["id"], editor["revision"], **fields)
                    except ChecklistError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.pop(editor_key, None)
                        st.session_state["_trade_checklist_notice"] = "Item updated and unchecked for review."
                        st.rerun()
                confirmed = st.checkbox("Confirm removal", key=f"{key}_confirm")
                if st.button("Remove item", key=f"{key}_delete", disabled=not confirmed):
                    try:
                        delete_checklist_item(item["id"], item["revision"], confirmed=confirmed)
                    except ChecklistError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.pop(editor_key, None)
                        st.session_state["_trade_checklist_notice"] = "Checklist item removed."
                        st.rerun()

    st.caption("Attributions and source links are your notes, not independently verified quotations. Links open only when clicked.")
