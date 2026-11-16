import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class ITPMStrategyUITests(unittest.TestCase):
    def test_placeholder_is_reachable_without_market_or_ai_requests(self):
        import app
        with patch.object(app, "cached_info") as info, \
                patch.object(app, "cached_history") as history, \
                patch.object(app, "render_stock_assistant") as chat:
            ui = AppTest.from_string("from app import main\nmain()")
            ui.session_state["research_area"] = "ITPM strategy"
            ui.run()
            self.assertFalse(ui.exception)
            self.assertIn("ITPM strategy", ui.radio(key="research_area").options)
            self.assertEqual(ui.title[0].value, "ITPM Strategy")
            self.assertIn("Details coming later", ui.info[0].value)
            info.assert_not_called()
            history.assert_not_called()
            chat.assert_not_called()
            ui.radio(key="research_area").set_value("Volatility strategy").run()
            self.assertFalse(ui.exception)
            self.assertEqual(ui.title[0].value, "Volatility Strategy")


if __name__ == "__main__":
    unittest.main()
