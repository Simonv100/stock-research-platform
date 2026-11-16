import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from breakout_strategy import (
    BREAKOUT_MODEL_VERSION,
    CLMT_REFERENCE,
    analyze_early_breakout,
    breakout_chart,
    completed_breakout_date,
    filter_breakout_candidates,
    get_breakout_history,
    parse_breakout_symbols,
)
from stock_data import StockDataError


def breakout_fixture():
    closes = [80 + i * 0.1 for i in range(180)] + [100 + i * 0.08 + (i % 5) * 0.05 for i in range(80)]
    frame = pd.DataFrame({
        "Open": np.array(closes) - 0.1,
        "High": np.array(closes) + 0.5,
        "Low": np.array(closes) - 0.5,
        "Close": closes, "Volume": [1_000_000.0] * len(closes),
    }, index=pd.bdate_range("2025-01-02", periods=len(closes)))
    frame.loc[frame.index[-1] + pd.offsets.BDay()] = [107, 111.1, 106, 111, 2_000_000]
    return frame


def assess(history):
    return analyze_early_breakout(history, as_of=history.index[-1].strftime("%Y-%m-%d"))


def candidates(result, age=5, extension=0.10):
    return filter_breakout_candidates([{"Symbol": "EX", "Name": "Example", **result}], age, extension)


class EarlyBreakoutCalculationTests(unittest.TestCase):
    def test_clean_early_breakout_has_prior_only_pivot_and_volume(self):
        history = breakout_fixture()
        result = assess(history)
        self.assertEqual(result["Status"], "Recent breakout")
        self.assertEqual(result["BreakoutDate"], history.index[-1].strftime("%Y-%m-%d"))
        self.assertEqual(result["BreakoutLevel"], history.High.iloc[-61:-1].max())
        self.assertEqual(result["BreakoutVolumeRatio"], 2.0)
        self.assertAlmostEqual(result["BaseDepth"], (
            history.High.iloc[-61:-1].max() - history.Low.iloc[-61:-1].min()
        ) / history.High.iloc[-61:-1].max())
        self.assertEqual(result["SessionsSinceBreakout"], 0)
        self.assertFalse(candidates(result).empty)
        self.assertEqual(result["BreakoutClose"], 111)

    def test_volume_boundary_and_future_volume_are_not_used(self):
        history = breakout_fixture()
        history.iloc[-1, history.columns.get_loc("Volume")] = 1_500_000
        self.assertEqual(assess(history)["Status"], "Recent breakout")
        history.iloc[-1, history.columns.get_loc("Volume")] = 1_499_999
        self.assertEqual(assess(history)["Status"], "No recent breakout")

    def test_price_breakout_boundary_uses_previous_high_not_same_day_high(self):
        history = breakout_fixture()
        history.iloc[-2, :4] = [103, 103.5, 102.5, 103]
        level = history.High.iloc[-61:-1].max()
        close = level * 1.01
        history.iloc[-1, :4] = [level, close, level - 1, close]
        self.assertEqual(assess(history)["Status"], "Recent breakout")
        history.iloc[-1, history.columns.get_loc("Close")] = close - 0.00001
        self.assertEqual(assess(history)["Status"], "No recent breakout")

    def test_daily_return_boundary_does_not_confuse_breakout_distance_with_return(self):
        history = breakout_fixture()
        prior = 111 / 1.03
        history.iloc[-2, :4] = [prior, prior + 0.1, prior - 0.1, prior]
        self.assertEqual(assess(history)["Status"], "Recent breakout")
        history.iloc[-1, history.columns.get_loc("Close")] = 110.999
        self.assertEqual(assess(history)["Status"], "No recent breakout")

    def test_consolidation_depth_and_overextended_spikes_are_not_early_breakouts(self):
        history = breakout_fixture()
        level = history.High.iloc[-61:-1].max()
        history.iloc[-40, history.columns.get_loc("Low")] = level * 0.70
        self.assertEqual(assess(history)["Status"], "Recent breakout")
        history.iloc[-40, history.columns.get_loc("Low")] = level * 0.70 - 0.01
        self.assertEqual(assess(history)["Status"], "No recent breakout")
        spike = breakout_fixture()
        spike.iloc[-1, :4] = [130, 150, 125, 149]
        self.assertEqual(assess(spike)["Status"], "No recent breakout")

    def test_weak_close_and_declining_long_term_trend_do_not_pass(self):
        history = breakout_fixture()
        history.iloc[-1, history.columns.get_loc("High")] = 130
        self.assertEqual(assess(history)["Status"], "No recent breakout")
        history = breakout_fixture()
        history.iloc[:180, :4] += 70
        self.assertEqual(assess(history)["Status"], "No recent breakout")

    def test_close_location_boundary_is_inclusive(self):
        history = breakout_fixture()
        history.iloc[-1, :4] = [107, 114, 104, 111]
        self.assertEqual(assess(history)["Status"], "Recent breakout")
        self.assertAlmostEqual(assess(history)["CloseLocation"], 0.7)
        history.iloc[-1, history.columns.get_loc("Close")] = 110.9999
        self.assertEqual(assess(history)["Status"], "No recent breakout")

    def test_losing_current_ma50_invalidates_even_if_original_pivot_is_held(self):
        history = breakout_fixture()
        pivot = assess(history)["BreakoutLevel"]
        for _ in range(19):
            history.loc[history.index[-1] + pd.offsets.BDay()] = [130, 131, 129, 130, 1_000_000]
        history.loc[history.index[-1] + pd.offsets.BDay()] = [pivot, pivot + 1, pivot - 1, pivot, 1_000_000]
        result = assess(history)
        self.assertTrue(result["BreakoutHeld"])
        self.assertEqual(result["Status"], "Failed breakout")
        self.assertEqual(result["SessionsSinceBreakout"], 20)
        self.assertTrue(candidates(result, age=20).empty)

    def test_later_qualifying_event_can_replace_a_failed_breakout(self):
        history = breakout_fixture()
        pivot = assess(history)["BreakoutLevel"]
        history.loc[history.index[-1] + pd.offsets.BDay()] = [pivot, pivot + 0.1, pivot - 2, pivot - 1, 1_000_000]
        self.assertEqual(assess(history)["Status"], "Failed breakout")
        history.loc[history.index[-1] + pd.offsets.BDay()] = [111, 114.1, 110, 114, 3_000_000]
        result = assess(history)
        self.assertEqual(result["Status"], "Recent breakout")
        self.assertEqual(result["BreakoutDate"], history.index[-1].strftime("%Y-%m-%d"))
        self.assertAlmostEqual(result["BreakoutLevel"], 111.1)

    def test_no_lookahead_when_future_data_is_appended_or_corrupted(self):
        history = breakout_fixture()
        day = history.index[-1].strftime("%Y-%m-%d")
        expected = analyze_early_breakout(history, as_of=day)
        history.loc[history.index[-1] + pd.offsets.BDay()] = [1, 1000, 0.01, 999, 1e12]
        history.loc[history.index[-1] + pd.offsets.BDay()] = [np.nan] * 5
        self.assertEqual(analyze_early_breakout(history, as_of=day), expected)
        self.assertEqual(
            analyze_early_breakout(history, as_of=history.index[-4].strftime("%Y-%m-%d"))["Status"],
            "No recent breakout",
        )

    def test_pivot_retest_close_is_allowed_but_failed_breakout_stays_failed_after_bounce(self):
        history = breakout_fixture()
        pivot = assess(history)["BreakoutLevel"]
        history.loc[history.index[-1] + pd.offsets.BDay()] = [pivot, pivot + 1, pivot - 1, pivot, 1_000_000]
        self.assertEqual(assess(history)["Status"], "Recent breakout")
        history.iloc[-1, history.columns.get_loc("Close")] = pivot - 0.1
        self.assertEqual(assess(history)["Status"], "Failed breakout")
        history.loc[history.index[-1] + pd.offsets.BDay()] = [111, 112, 110, 111, 1_000_000]
        result = assess(history)
        self.assertEqual(result["Status"], "Failed breakout")
        self.assertFalse(result["BreakoutHeld"])
        self.assertTrue(candidates(result).empty)

    def test_local_recency_and_extension_filters_do_not_change_event_detection(self):
        history = breakout_fixture()
        for _ in range(6):
            history.loc[history.index[-1] + pd.offsets.BDay()] = [111, 112, 110, 111, 1_000_000]
        result = assess(history)
        self.assertEqual(result["SessionsSinceBreakout"], 6)
        self.assertTrue(candidates(result, age=5).empty)
        self.assertFalse(candidates(result, age=6).empty)
        result["ExtensionFromBreakout"] = 0.1
        self.assertFalse(candidates(result, age=6).empty)
        result["ExtensionFromBreakout"] = 0.100001
        self.assertTrue(candidates(result, age=6).empty)
        result["ExtensionFromBreakout"] = -0.01
        self.assertTrue(candidates(result, age=6).empty)

    def test_old_event_is_not_resurrected_after_twenty_sessions(self):
        history = breakout_fixture()
        for _ in range(21):
            history.loc[history.index[-1] + pd.offsets.BDay()] = [111, 112, 110, 111, 1_000_000]
        self.assertEqual(assess(history)["Status"], "No recent breakout")

    def test_invalid_missing_duplicate_and_stale_data_is_explicitly_unavailable(self):
        original = breakout_fixture()
        for column, value in (("Volume", np.nan), ("Volume", -1), ("Close", 0), ("High", np.inf), ("Low", 200)):
            history = original.copy()
            history.iloc[-1, history.columns.get_loc(column)] = value
            with self.subTest(column=column, value=value):
                self.assertEqual(assess(history)["Status"], "Unavailable")
        for history in (
            original.tail(220), original.drop(columns="Volume"),
            pd.concat([original, original.tail(1)]),
            original.assign(Volume=True), original.assign(Volume=0),
            original.reset_index(drop=True),
        ):
            result = analyze_early_breakout(history, as_of=original.index[-1].strftime("%Y-%m-%d"))
            self.assertEqual(result["Status"], "Unavailable")
            self.assertTrue(result["Reason"])
        result = analyze_early_breakout(original, as_of=(original.index[-1] + pd.Timedelta(days=8)).strftime("%Y-%m-%d"))
        self.assertEqual(result["Status"], "Unavailable")
        self.assertIn("seven", result["Reason"])

    def test_inputs_are_not_mutated_and_timezone_dates_are_preserved(self):
        history = breakout_fixture()
        history.index = history.index.tz_localize("Asia/Tokyo")
        original = history.copy(deep=True)
        result = assess(history)
        self.assertEqual(result["AsOf"], history.index[-1].strftime("%Y-%m-%d"))
        pd.testing.assert_frame_equal(history, original)

    def test_chart_marks_original_breakout_and_never_displays_future_bars(self):
        history = breakout_fixture()
        result = {"Symbol": "EX", **assess(history)}
        event_date = result["BreakoutDate"]
        history.loc[history.index[-1] + pd.offsets.BDay()] = [150, 200, 140, 190, 1e7]
        chart = breakout_chart(history, result)
        self.assertEqual(chart.data[0].x[-1], event_date)
        self.assertEqual(chart.data[-1].x[0], event_date)
        self.assertEqual(chart.layout.shapes[0].y0, result["BreakoutLevel"])
        self.assertEqual(chart.data[-1].y[0], result["BreakoutClose"])
        self.assertIn("Adjusted", chart.layout.yaxis.title.text)

    def test_custom_symbols_are_normalized_bounded_and_invalid_inputs_rejected(self):
        self.assertEqual(parse_breakout_symbols("clmt, 7203.T;005930.KS CLMT"), ["CLMT", "7203.T", "005930.KS"])
        for text in ("", "CLMT !", "^GSPC", "EURUSD=X", " ".join(f"A{i}" for i in range(51))):
            with self.subTest(text=text), self.assertRaises(StockDataError):
                parse_breakout_symbols(text)
        self.assertTrue(filter_breakout_candidates([], 5, 0.1).empty)
        for age, ext in ((0, 0.1), (21, 0.1), (True, 0.1), (5, -0.1), (5, np.inf), (5, True)):
            with self.assertRaises(StockDataError):
                filter_breakout_candidates([], age, ext)


class EarlyBreakoutProviderTests(unittest.TestCase):
    @patch("breakout_strategy.yf.Ticker")
    def test_current_and_reference_requests_use_consistent_adjustment(self, ticker):
        ticker.return_value.history.return_value = breakout_fixture()
        get_breakout_history("CLMT")
        ticker.return_value.history.assert_called_once_with(
            period="2y", interval="1d", auto_adjust=True, actions=False, raise_errors=True,
        )
        ticker.return_value.history.reset_mock()
        get_breakout_history("CLMT", reference=True)
        ticker.return_value.history.assert_called_once_with(
            start="2025-01-01", end="2026-02-04", interval="1d", auto_adjust=True,
            actions=False, raise_errors=True,
        )

    @patch("breakout_strategy.yf.Ticker")
    def test_provider_failure_never_becomes_a_no_match(self, ticker):
        ticker.return_value.history.return_value = pd.DataFrame()
        with self.assertRaisesRegex(StockDataError, "No adjusted"):
            get_breakout_history("EX")
        ticker.return_value.history.side_effect = ValueError("Provider error")
        with self.assertRaisesRegex(StockDataError, "could not be loaded"):
            get_breakout_history("EX")
        with self.assertRaises(StockDataError):
            get_breakout_history("OTHER", reference=True)

    def test_reference_is_fixed_and_completed_cutoff_precedes_today_utc(self):
        from datetime import datetime, timezone
        self.assertLess(pd.Timestamp(completed_breakout_date()).date(), datetime.now(timezone.utc).date())
        self.assertEqual(CLMT_REFERENCE["BreakoutDate"], "2026-02-03")
        self.assertEqual(CLMT_REFERENCE["BreakoutLevel"], 23.41)
        self.assertEqual(BREAKOUT_MODEL_VERSION, "early-breakout-v1")


class EarlyBreakoutAppIntegrationTests(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app
        app.cached_breakout_history.clear()
        app.cached_breakout_reference_history.clear()
        self.addCleanup(app.cached_breakout_history.clear)
        self.addCleanup(app.cached_breakout_reference_history.clear)

    def test_current_scans_reuse_history_and_return_coverage_without_prefilling_clmt(self):
        history = breakout_fixture()
        as_of = history.index[-1].strftime("%Y-%m-%d")
        holdings = pd.DataFrame({"Symbol": ["BBB", "AAA"], "Name": ["Company B", "Company A"]})
        with (
            patch.object(self.app, "cached_sp500_holdings", return_value=holdings),
            patch.object(self.app, "completed_breakout_date", return_value=as_of),
            patch.object(self.app, "get_breakout_history", return_value=history) as provider,
        ):
            first = self.app.load_breakout_scan("S&P 500 stocks", [])
            second = self.app.load_breakout_scan("Custom tickers", ["AAA"])
        self.assertEqual(first["requested_symbols"], ["AAA", "BBB"])
        self.assertEqual([row["Status"] for row in first["rows"]], ["Recent breakout"] * 2)
        self.assertNotIn("CLMT", first["requested_symbols"])
        self.assertEqual(second["requested_symbols"], ["AAA"])
        self.assertEqual(provider.call_count, 2)

    def test_partial_failure_has_a_reason_all_failure_raises_and_unknown_universe_fails(self):
        history = breakout_fixture()

        def provider(symbol):
            if symbol == "BAD":
                raise StockDataError("No data")
            return history

        with patch.object(self.app, "get_breakout_history", side_effect=provider), \
                patch.object(self.app, "completed_breakout_date", return_value=history.index[-1].strftime("%Y-%m-%d")):
            snapshot = self.app.load_breakout_scan("Custom tickers", ["GOOD", "BAD"])
            self.assertEqual(snapshot["rows"][1]["Status"], "Unavailable")
            self.assertIn("No data", snapshot["rows"][1]["Reason"])
            with self.assertRaisesRegex(StockDataError, "No stocks could be assessed"):
                self.app.load_breakout_scan("Custom tickers", ["BAD"])
            with self.assertRaises(StockDataError):
                self.app.load_breakout_scan("Not a universe", [])

    def test_all_holdings_universes_use_existing_listing_loaders(self):
        history = breakout_fixture()
        for universe, loader, symbol in (
            ("Russell 2000 stocks", "cached_russell_holdings", "CLMT"),
            ("S&P 500 stocks", "cached_sp500_holdings", "EX"),
            ("European stocks", "cached_european_holdings", "ABC.DE"),
        ):
            with self.subTest(universe=universe), \
                    patch.object(self.app, loader, return_value=pd.DataFrame({"Symbol": [symbol], "Name": ["Example"]})) as holdings, \
                    patch.object(self.app, "cached_breakout_history", return_value=history), \
                    patch.object(self.app, "completed_breakout_date", return_value=history.index[-1].strftime("%Y-%m-%d")):
                snapshot = self.app.load_breakout_scan(universe, [])
                self.assertEqual(snapshot["requested_symbols"], [symbol])
                self.assertEqual(snapshot["rows"][0]["Name"], "Example")
                holdings.assert_called_once()

    def test_provider_failure_is_cached_until_explicit_refresh(self):
        with patch.object(self.app, "get_breakout_history", side_effect=StockDataError("Provider unavailable")) as provider:
            for _ in range(2):
                with self.assertRaises(StockDataError):
                    self.app.cached_breakout_history("EX")
            provider.assert_called_once_with("EX")
            self.app.cached_breakout_history.clear()
            with self.assertRaises(StockDataError):
                self.app.cached_breakout_history("EX")
            self.assertEqual(provider.call_count, 2)


if __name__ == "__main__":
    unittest.main()
