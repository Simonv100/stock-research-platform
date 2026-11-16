import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import pandas as pd
from pytrends.exceptions import ResponseError
from pytrends.request import TrendReq

import stock_data


class GoogleTrendsPacingTests(unittest.TestCase):
    def setUp(self):
        self.clock = 1000.0
        self.sleeps = []
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(stock_data, "_google_trends_next_request", 0.0))
        self.stack.enter_context(patch.object(stock_data, "_google_trends_cooldown_until", 0.0))
        self.stack.enter_context(patch.object(stock_data.time, "monotonic", side_effect=lambda: self.clock))
        self.stack.enter_context(patch.object(stock_data.time, "sleep", side_effect=self.sleep))

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.clock += seconds

    @staticmethod
    def error(status=429, retry_after=None):
        response = Mock(status_code=status, headers={})
        if retry_after is not None:
            response.headers["Retry-After"] = retry_after
        return ResponseError.from_response(response)

    def test_requests_are_spaced_even_across_different_callers(self):
        stock_data._paced_google_trends_request(lambda: "first")
        self.assertEqual(stock_data._paced_google_trends_request(lambda: "second"), "second")
        self.assertEqual(self.sleeps, [10.0])

    def test_rate_limit_retries_then_succeeds(self):
        request = Mock(side_effect=[self.error(), self.error(), "data"])
        self.assertEqual(stock_data._paced_google_trends_request(request), "data")
        self.assertEqual(request.call_count, 3)
        self.assertEqual(self.sleeps, [30.0, 60.0])

    def test_persistent_rate_limit_stops_other_brands_during_cooldown(self):
        request = Mock(side_effect=self.error())
        with self.assertRaisesRegex(stock_data.StockDataError, "paused"):
            stock_data._paced_google_trends_request(request)
        self.assertEqual(request.call_count, 3)
        other_brand = Mock()
        with self.assertRaisesRegex(stock_data.StockDataError, "cooling down"):
            stock_data._paced_google_trends_request(other_brand)
        other_brand.assert_not_called()

    def test_long_retry_after_enters_cooldown_without_sleeping(self):
        request = Mock(side_effect=self.error(retry_after="600"))
        with self.assertRaises(stock_data.StockDataError):
            stock_data._paced_google_trends_request(request)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(self.sleeps, [])
        self.assertEqual(stock_data._google_trends_cooldown_until, 1600.0)

    def test_retry_after_is_respected(self):
        request = Mock(side_effect=[self.error(retry_after="45"), "data"])
        self.assertEqual(stock_data._paced_google_trends_request(request), "data")
        self.assertEqual(self.sleeps, [45.0])

    def test_other_http_errors_are_not_retried(self):
        request = Mock(side_effect=self.error(status=500))
        with self.assertRaises(ResponseError):
            stock_data._paced_google_trends_request(request)
        self.assertEqual(request.call_count, 1)

    def test_cookie_payload_and_time_series_are_all_paced(self):
        interest = pd.DataFrame(
            {"Brand": [20.0] * 4 + [10.0] * 4},
            index=pd.date_range("2026-08-01", periods=8, freq="7D"),
        )

        def initialize(client, **kwargs):
            client.GetGoogleCookie()
            hook = kwargs["requests_args"]["hooks"]["response"]
            with self.assertRaises(ResponseError):
                hook(Mock(status_code=429))

        with ExitStack() as stack:
            stack.enter_context(patch.object(TrendReq, "__init__", initialize))
            stack.enter_context(patch.object(TrendReq, "GetGoogleCookie", return_value={}))
            stack.enter_context(patch.object(TrendReq, "_get_data", return_value=interest))
            stack.enter_context(patch.object(
                TrendReq, "build_payload", lambda client, *args, **kwargs: client._get_data("payload"),
            ))
            stack.enter_context(patch.object(
                TrendReq, "interest_over_time", lambda client: client._get_data("series"),
            ))
            result = stock_data.get_google_trends_signal("Brand")

        self.assertEqual(self.sleeps, [10.0, 10.0])
        self.assertEqual(result["Momentum"], -0.5)
        self.assertTrue(result["Available"])


if __name__ == "__main__":
    unittest.main()
