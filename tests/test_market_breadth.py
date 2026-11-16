import unittest
from unittest.mock import patch

import pandas as pd
from curl_cffi.requests.exceptions import Timeout

from market_breadth import (
    BENCHMARK_SYMBOL,
    calculate_market_breadth,
    get_market_breadth,
)
from stock_data import StockDataError


class MarketBreadthCalculationTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.bdate_range("2026-09-01", periods=5)
        self.benchmark = pd.Series([100, 101, 102, 103, 104], index=self.dates)
        self.prices = pd.DataFrame({
            "AAA": [10, 11, 12, 11, 12], "BBB": [20, 19, 19, 20, 21],
            "CCC": [30, 30, 29, 30, 30], "DDD": [40, 41, 42, 43, 44],
        }, index=self.dates)

    def calculate(self, prices=None, **kwargs):
        return calculate_market_breadth(
            self.prices if prices is None else prices, self.benchmark,
            as_of="2026-09-20T12:00:00Z", **kwargs,
        )

    def test_daily_direction_unchanged_counts_and_cumulative_line(self):
        daily, coverage = self.calculate()
        self.assertEqual(daily["Advancing"].tolist(), [0, 2, 2, 3, 3])
        self.assertEqual(daily["Declining"].tolist(), [0, 1, 1, 1, 0])
        self.assertEqual(daily["Unchanged"].tolist(), [0, 1, 1, 0, 1])
        self.assertTrue(pd.isna(daily["NetAdvances"].iloc[0]))
        self.assertEqual(daily["ADLine"].iloc[1:].tolist(), [1, 2, 4, 7])
        self.assertEqual(daily["AdvancingPercent"].iloc[-1], 75)
        self.assertEqual(daily["IndexRebased"].iloc[0], 100)
        self.assertAlmostEqual(daily["IndexReturn"].iloc[-1], 104 / 103 - 1)
        self.assertTrue(coverage["AD eligible"].all())
        self.assertEqual(
            (daily["Advancing"] + daily["Declining"] + daily["Unchanged"]).tolist(),
            daily["ADComparable"].tolist(),
        )

    def test_missing_prices_are_not_flat_declines_or_multi_day_advances(self):
        self.prices.loc[self.dates[2], "AAA"] = float("nan")
        daily, coverage = self.calculate()
        self.assertEqual(daily["ADComparable"].tolist(), [0, 4, 3, 3, 4])
        self.assertTrue(daily["NetAdvances"].iloc[2:4].isna().all())
        self.assertTrue(daily["AdvancingPercent"].iloc[2:4].isna().all())
        self.assertEqual(daily["ADLine"].iloc[4], 3)
        self.assertGreater(daily["ADSegment"].iloc[4], daily["ADSegment"].iloc[1])
        self.assertEqual(daily["Unchanged"].iloc[2], 1)
        self.assertTrue(coverage["AD eligible"].all())

    def test_coverage_threshold_includes_exactly_95_percent_and_tracks_missing_symbols(self):
        prices = pd.DataFrame({f"S{i}": [10, 11, 12, 13, 14] for i in range(20)}, index=self.dates)
        prices["S0"] = float("nan")
        daily, coverage = self.calculate(prices)
        self.assertEqual(daily["UniverseSize"].iloc[-1], 20)
        self.assertEqual(daily["ADCoverage"].iloc[-1], 0.95)
        self.assertEqual(daily["AdvancingPercent"].iloc[-1], 100)
        self.assertEqual(coverage.loc[coverage["Symbol"] == "S0", "Last price date"].iloc[0], "")
        prices["S1"] = float("nan")
        daily, _ = self.calculate(prices)
        self.assertTrue(pd.isna(daily["ADLine"].iloc[-1]))
        self.assertTrue(pd.isna(daily["AdvancingPercent"].iloc[-1]))

    def test_full_ma_windows_equal_is_not_above_and_no_fill_for_gaps(self):
        dates = pd.bdate_range("2025-10-01", periods=220)
        prices = pd.DataFrame({
            "UP": range(1, 221), "DOWN": range(221, 1, -1), "FLAT": [100] * 220,
        }, index=dates)
        benchmark = pd.Series(range(100, 320), index=dates)
        daily, _ = calculate_market_breadth(prices, benchmark, as_of="2026-09-20", display_sessions=20)
        self.assertEqual(len(daily), 20)
        self.assertEqual(daily["MA200Comparable"].iloc[-1], 3)
        self.assertAlmostEqual(daily["AboveMA200Percent"].iloc[-1], 100 / 3)
        self.assertAlmostEqual(daily["AboveMA50Percent"].iloc[-1], 100 / 3)
        prices.loc[dates[-60], "UP"] = float("nan")
        daily, coverage = calculate_market_breadth(prices, benchmark, as_of="2026-09-20")
        self.assertEqual(daily["MA50Comparable"].iloc[-1], 3)
        self.assertEqual(daily["MA200Comparable"].iloc[-1], 2)
        self.assertTrue(pd.isna(daily["AboveMA200Percent"].iloc[-1]))
        self.assertFalse(coverage.set_index("Symbol").loc["UP", "MA200 eligible"])

    def test_new_york_current_session_and_future_prices_are_excluded(self):
        dates = pd.to_datetime(["2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22"]).tz_localize("America/New_York")
        prices = pd.DataFrame({"AAA": [10, 11, 12, 13]}, index=dates)
        benchmark = pd.Series([100, 101, 102, 103], index=dates)
        daily, _ = calculate_market_breadth(prices, benchmark, as_of="2026-09-22T01:00:00Z")
        self.assertEqual(daily.index[-1], pd.Timestamp("2026-09-18"))

    def test_nonpositive_and_nonfinite_closes_are_missing(self):
        for invalid in (0, -1, float("inf"), float("-inf"), "invalid"):
            with self.subTest(invalid=invalid):
                prices = self.prices.astype(object)
                prices.loc[self.dates[-1], "AAA"] = invalid
                daily, coverage = self.calculate(prices)
                self.assertEqual(daily["ADComparable"].iloc[-1], 3)
                self.assertFalse(coverage.set_index("Symbol").loc["AAA", "AD eligible"])

    def test_chart_window_rebases_index_and_ad_total(self):
        daily, _ = self.calculate(display_sessions=2)
        self.assertEqual(daily["IndexRebased"].iloc[0], 100)
        self.assertEqual(daily["ADLine"].tolist(), [2, 5])
        self.assertEqual(daily["ADComparable"].tolist(), [4, 4])

    def test_invalid_universe_or_missing_benchmark_is_explicit(self):
        for prices in (pd.DataFrame(), pd.concat([self.prices, self.prices], axis=1)):
            with self.subTest(columns=prices.columns.tolist()), self.assertRaises(StockDataError):
                self.calculate(prices)
        with self.assertRaisesRegex(StockDataError, "completed sessions"):
            calculate_market_breadth(self.prices, pd.Series(dtype=float))


class MarketBreadthProviderTests(unittest.TestCase):
    def response(self, symbols):
        dates = pd.bdate_range("2026-08-03", periods=5)
        return pd.concat({
            symbol: pd.DataFrame({"Close": [10, 11, 12, 13, 14]}, index=dates)
            for symbol in symbols
        }, axis=1)

    def test_requests_adjusted_two_year_prices_and_preserves_absent_listing(self):
        with patch("market_breadth.yf.download", return_value=self.response(["^GSPC", "AAA"])) as download:
            result = get_market_breadth(("AAA", "BBB", "AAA"))
        self.assertEqual(download.call_args.args[0], ["^GSPC", "AAA", "BBB"])
        self.assertEqual(download.call_args.kwargs["period"], "2y")
        self.assertTrue(download.call_args.kwargs["auto_adjust"])
        self.assertEqual(result.daily["UniverseSize"].iloc[-1], 2)
        self.assertEqual(result.coverage["Symbol"].tolist(), ["AAA", "BBB"])
        self.assertTrue(result.daily["AdvancingPercent"].isna().all())
        self.assertTrue(result.fetched_at)

    def test_chunked_requests_keep_all_symbols_and_accept_single_symbol_flat_response(self):
        symbols = tuple(f"S{i}" for i in range(100))
        def response(requested, **kwargs):
            frame = self.response(requested)
            return frame[requested[0]] if len(requested) == 1 else frame
        with patch("market_breadth.yf.download", side_effect=response) as download:
            result = get_market_breadth(symbols)
        self.assertEqual(download.call_count, 2)
        self.assertEqual(result.daily["UniverseSize"].iloc[-1], 100)
        self.assertEqual(result.daily["AdvancingPercent"].iloc[-1], 100)

    def test_empty_failed_or_malformed_responses_are_not_successful_breadth(self):
        for response in (pd.DataFrame(), pd.DataFrame({"Unexpected": [1, 2]})):
            with self.subTest(response=response.to_dict()), patch(
                "market_breadth.yf.download", return_value=response,
            ), self.assertRaises(StockDataError):
                get_market_breadth(("AAA",))
        with patch("market_breadth.yf.download", side_effect=Timeout("timeout")), self.assertRaisesRegex(
            StockDataError, "could not be loaded",
        ):
            get_market_breadth(("AAA",))
        with patch("market_breadth.yf.download", return_value=self.response(["AAA"])), self.assertRaisesRegex(
            StockDataError, "completed sessions",
        ):
            get_market_breadth(("AAA",))

    def test_empty_universe_or_index_as_member_does_not_download(self):
        with patch("market_breadth.yf.download") as download:
            for symbols in ((), (BENCHMARK_SYMBOL,), ("",)):
                with self.subTest(symbols=symbols), self.assertRaises(StockDataError):
                    get_market_breadth(symbols)
            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
