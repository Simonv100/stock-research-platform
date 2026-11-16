import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import stock_chat_ui
from stock_chat import MAX_HISTORY_MESSAGES
from stock_data import StockDataError


SCRIPT = """
import pandas as pd
import streamlit as st
import stock_chat
from stock_chat_ui import render_stock_chat
symbol = st.selectbox("Test stock", ["EX", "ex", "EX2"])
key = st.text_input("Test API key", type="password")
view = st.radio("Test view", ["Stock research", "Scanner"])
visible = st.checkbox("Show chat", value=True)
if visible:
    render_stock_chat(
        symbol, "Example",
        lambda: stock_chat.build_stock_context(symbol, "Example", {}, pd.DataFrame()),
        key,
    )
"""


def send(ui, question):
    ui.text_area[0].input(question)
    next(button for button in ui.button if button.label == "Send").click().run()
    return ui


class StockChatUITests(unittest.TestCase):
    def test_fragment_wrapper_explicit_send_and_rerun_do_not_duplicate_calls(self):
        script = SCRIPT.replace("if visible:", "@st.fragment\ndef panel():")
        script += "\nif visible:\n    panel()\n"
        with patch("stock_chat.build_stock_context", return_value={"symbol": "EX"}) as loader, \
                patch("stock_chat_ui.answer_stock_question", return_value="A grounded explanation.") as answer:
            ui = AppTest.from_string(script).run()
            ui.text_input[0].input("test-key").run()
            loader.assert_not_called()
            send(ui, "Explain the selected evidence.")
            self.assertFalse(ui.exception)
            self.assertEqual(len(ui.chat_message), 2)
            self.assertEqual(ui.text_area[0].value, "")
            ui.run()
            ui.radio[0].set_value("Scanner").run()
            loader.assert_called_once()
            answer.assert_called_once()

    def test_missing_key_disabled_no_loader_no_network_and_disclosure(self):
        with patch("stock_chat.build_stock_context") as loader, \
                patch("stock_chat_ui.answer_stock_question") as answer, \
                patch("openai_transport.urlopen") as network:
            ui = AppTest.from_string(SCRIPT).run()
            self.assertFalse(ui.exception)
            self.assertTrue(ui.text_area[0].disabled)
            self.assertTrue(next(button for button in ui.button if button.label == "Send").disabled)
            ui.run()
            ui.selectbox[0].select("EX2").run()
            loader.assert_not_called()
            answer.assert_not_called()
            network.assert_not_called()
            captions = " ".join(caption.value for caption in ui.caption)
            self.assertIn("question/chat history go to OpenAI", captions)
            self.assertIn("Do not enter private data", captions)
            self.assertIn("API fees", captions)
            self.assertIn("no live browsing", captions)
            self.assertIn("AI assistant settings in the sidebar", captions)

    def test_success_continuation_reruns_view_changes_and_key_removal(self):
        with patch("stock_chat.build_stock_context", return_value={"symbol": "EX"}) as loader, \
                patch("stock_chat_ui.answer_stock_question", return_value="A grounded explanation.") as answer:
            ui = AppTest.from_string(SCRIPT).run()
            ui.text_input[0].input("test-key").run()
            loader.assert_not_called()
            answer.assert_not_called()
            send(ui, "What is revenue?")
            self.assertFalse(ui.exception)
            self.assertEqual(len(ui.chat_message), 2)
            self.assertEqual(ui.text_area[0].value, "")
            answer.assert_called_once()
            loader.assert_called_once()
            send(ui, "And its growth?")
            self.assertEqual(len(answer.call_args.args[2]), 2)
            self.assertEqual(answer.call_args.args[2][0]["content"], "What is revenue?")
            self.assertEqual(len(ui.chat_message), 4)
            ui.run()
            ui.radio[0].set_value("Scanner").run()
            ui.text_input[0].input("").run()
            self.assertEqual(len(ui.chat_message), 4)
            self.assertTrue(next(button for button in ui.button if button.label == "Send").disabled)
            ui.text_input[0].input("new-key").run()
            self.assertEqual(answer.call_count, 2)
            self.assertEqual(loader.call_count, 2)
            send(ui, "Continue.")
            self.assertEqual(answer.call_args.args[4], "new-key")
            self.assertFalse(ui.exception)

    def test_canonical_per_stock_isolation_hide_show_and_clear_current_only(self):
        with patch("stock_chat.build_stock_context", return_value={"symbol": "EX"}), \
                patch("stock_chat_ui.answer_stock_question", return_value="Public explanation.") as answer:
            ui = AppTest.from_string(SCRIPT).run()
            ui.text_input[0].input("test-key").run()
            send(ui, "EX question")
            ui.selectbox[0].select("ex").run()
            self.assertEqual(len(ui.chat_message), 2)
            ui.checkbox[0].uncheck().run()
            ui.checkbox[0].check().run()
            self.assertEqual(len(ui.chat_message), 2)
            ui.selectbox[0].select("EX2").run()
            self.assertEqual(len(ui.chat_message), 0)
            send(ui, "EX2 question")
            self.assertEqual(answer.call_args.args[0], "EX2")
            self.assertEqual(answer.call_args.args[2], [])
            ui.selectbox[0].select("EX").run()
            self.assertEqual(len(ui.chat_message), 2)
            next(button for button in ui.button if button.label == "Clear").click().run()
            self.assertEqual(len(ui.chat_message), 0)
            self.assertEqual(ui.text_area[0].value, "")
            ui.selectbox[0].select("EX2").run()
            self.assertEqual(len(ui.chat_message), 2)
            self.assertIn("EX2 question", ui.chat_message[0].markdown[0].value)
            self.assertEqual(answer.call_count, 2)
            self.assertFalse(ui.exception)

    def test_failure_keeps_question_and_never_retries_until_explicit_send(self):
        with patch("stock_chat.build_stock_context", return_value={"symbol": "EX"}) as loader, \
                patch("stock_chat_ui.answer_stock_question",
                      side_effect=StockDataError("test-key upstream body")) as answer:
            ui = AppTest.from_string(SCRIPT).run()
            ui.text_input[0].input("test-key").run()
            send(ui, "Why did it grow?")
            self.assertFalse(ui.exception)
            self.assertIn("retry explicitly", ui.warning[0].value)
            self.assertNotIn("test-key", ui.warning[0].value)
            self.assertEqual(ui.text_area[0].value, "Why did it grow?")
            self.assertEqual(len(ui.chat_message), 0)
            ui.run()
            ui.selectbox[0].select("EX2").run()
            ui.selectbox[0].select("EX").run()
            self.assertEqual(ui.text_area[0].value, "Why did it grow?")
            self.assertEqual(answer.call_count, 1)
            self.assertEqual(loader.call_count, 1)
            answer.side_effect = None
            answer.return_value = "Growth compares two periods."
            send(ui, ui.text_area[0].value)
            self.assertEqual(answer.call_count, 2)
            self.assertEqual(len(ui.chat_message), 2)
            self.assertEqual(len(ui.warning), 0)

    def test_context_loader_failure_never_calls_ai_and_keeps_draft(self):
        with patch("stock_chat.build_stock_context", side_effect=ValueError("private test-key")) as loader, \
                patch("stock_chat_ui.answer_stock_question") as answer:
            ui = AppTest.from_string(SCRIPT).run()
            ui.text_input[0].input("test-key").run()
            send(ui, "Explain valuation")
            self.assertFalse(ui.exception)
            self.assertEqual(ui.text_area[0].value, "Explain valuation")
            self.assertEqual(len(ui.chat_message), 0)
            self.assertNotIn("private", ui.warning[0].value)
            ui.run()
            loader.assert_called_once()
            answer.assert_not_called()

    def test_accumulated_history_bounded_disclosed_and_key_never_stored(self):
        with patch("stock_chat.build_stock_context", return_value={"symbol": "EX"}), \
                patch("stock_chat_ui.answer_stock_question", return_value="Answer test-key") as answer:
            ui = AppTest.from_string(SCRIPT).run()
            ui.text_input[0].input("test-key").run()
            for number in range(8):
                send(ui, f"Question {number} test-key")
            state = ui.session_state[stock_chat_ui.CHAT_STATE_KEY]
            self.assertEqual(len(state["EX"]["messages"]), MAX_HISTORY_MESSAGES)
            self.assertNotIn("test-key", str(state))
            self.assertNotIn("test-key", str(answer.call_args.args[2:4]))
            self.assertTrue(any("Older messages were dropped" in item.value for item in ui.caption))
            self.assertEqual(len(ui.chat_message), MAX_HISTORY_MESSAGES)
            self.assertEqual(answer.call_count, 8)
            self.assertFalse(ui.exception)

    def test_separate_browser_sessions_do_not_share_conversation(self):
        with patch("stock_chat.build_stock_context", return_value={"symbol": "EX"}), \
                patch("stock_chat_ui.answer_stock_question", return_value="Explanation"):
            first = AppTest.from_string(SCRIPT).run()
            first.text_input[0].input("test-key").run()
            send(first, "Private to this browser session")
            second = AppTest.from_string(SCRIPT).run()
            self.assertEqual(len(second.chat_message), 0)
            self.assertEqual(second.session_state[stock_chat_ui.CHAT_STATE_KEY]["EX"]["messages"], [])


if __name__ == "__main__":
    unittest.main()
