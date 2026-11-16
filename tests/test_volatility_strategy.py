import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from stock_data import StockDataError
from volatility_strategy import (
    BENCHMARK, UNIVERSE, PilotPrices, analyze_pockets, read_saved_prices, refresh_saved_prices,
)


def pilot_fixture(direction=1):
    dates = pd.bdate_range(end="2026-09-25", periods=280)
    market = [0.001 * math.sin(i * 0.7) for i in range(len(dates))]
    data = {}
    for number, symbol in enumerate([BENCHMARK, *[stock.symbol for stock in UNIVERSE]]):
        log_price = math.log(100)
        values = []
        for i, market_return in enumerate(market):
            excess = 0 if symbol == BENCHMARK else 0.002 * math.sin(i * 1.7 + number * 0.4)
            if i >= len(dates) - 5:
                excess = 0
            if symbol in ("AMAT", "LRCX") and i == len(dates) - 3:
                excess += direction * 0.12
            log_price += market_return + excess
            values.append(math.exp(log_price))
        data[symbol] = values
    return PilotPrices(pd.DataFrame(data, index=dates), "2026-09-26T12:00:00+00:00")


class VolatilityCalculationTests(unittest.TestCase):
    def test_concentrated_movers_produce_only_connected_quiet_peers(self):
        result = analyze_pockets(pilot_fixture())
        stocks = result.stocks.set_index("Symbol")
        pockets = result.pockets.set_index("Pocket")
        self.assertEqual(stocks.loc["AMAT", "Status"], "Unusual mover")
        self.assertEqual(stocks.loc["LRCX", "Status"], "Unusual mover")
        self.assertEqual(set(stocks.index[stocks["Status"] == "Research lead"]), {"ASML", "ACLS"})
        self.assertTrue(pockets.loc["Wafer fabrication", "Active"])
        self.assertEqual(pockets.loc["Wafer fabrication", "Direction"], "Up")
        self.assertEqual(pockets.loc["Wafer fabrication", "Unusual"], 2)
        self.assertEqual(pockets.loc["Wafer fabrication", "Breadth"], 0.5)
        self.assertEqual(pockets.loc["Wafer fabrication", "Percentile"], 100)
        self.assertGreater(stocks.loc["ASML", "Gap"], 0)
        self.assertNotIn(BENCHMARK, stocks.index)

    def test_negative_shock_uses_return_direction_not_rebound_acceleration(self):
        result = analyze_pockets(pilot_fixture(-1))
        pocket = result.pockets.set_index("Pocket").loc["Wafer fabrication"]
        self.assertEqual(pocket["Direction"], "Down")
        self.assertGreater(result.acceleration_z["AMAT"].iloc[-2], 2)
        lead = result.stocks.set_index("Symbol").loc["ASML"]
        self.assertEqual(lead["Status"], "Research lead")
        self.assertLess(lead["LeaderMedian"], 0)
        self.assertGreater(lead["Gap"], 0)

    def test_zero_event_result_does_not_manufacture_candidates(self):
        snapshot = pilot_fixture(0)
        result = analyze_pockets(snapshot)
        self.assertEqual(result.pockets.iloc[0]["Unusual"], 0)
        self.assertFalse(result.pockets["Active"].any())
        self.assertFalse((result.stocks["Status"] == "Research lead").any())

    def test_missing_price_breaks_consecutive_baseline_and_coverage_gate(self):
        snapshot = pilot_fixture()
        snapshot.prices.loc[snapshot.prices.index[-20], "ASML"] = float("nan")
        result = analyze_pockets(snapshot)
        stocks = result.stocks.set_index("Symbol")
        self.assertEqual(stocks.loc["ASML", "Status"], "Unavailable")
        self.assertTrue(pd.isna(stocks.loc["ASML", "Excess5D"]))
        self.assertEqual(stocks.loc["ACLS", "Status"], "No setup")
        self.assertEqual(result.pockets.set_index("Pocket").loc["Wafer fabrication", "Status"], "Insufficient coverage")

    def test_missing_symbol_and_flat_or_invalid_prices_are_not_quiet(self):
        for invalid in (None, 0, -1, float("inf"), "invalid"):
            with self.subTest(invalid=invalid):
                snapshot = pilot_fixture()
                if invalid is None:
                    snapshot.prices = snapshot.prices.drop(columns=["ASML"])
                else:
                    snapshot.prices["ASML"] = snapshot.prices["ASML"].astype(object)
                    snapshot.prices.loc[snapshot.prices.index[-1], "ASML"] = invalid
                result = analyze_pockets(snapshot)
                self.assertEqual(result.stocks.set_index("Symbol").loc["ASML", "Status"], "Unavailable")
        snapshot = pilot_fixture()
        snapshot.prices["ASML"] = snapshot.prices[BENCHMARK] * 2
        self.assertEqual(analyze_pockets(snapshot).stocks.set_index("Symbol").loc["ASML", "Status"], "Unavailable")

    def test_current_and_future_sessions_do_not_change_completed_signals(self):
        snapshot = pilot_fixture()
        expected = analyze_pockets(snapshot)
        for date in ("2026-09-28", "2026-09-29"):
            snapshot.prices.loc[pd.Timestamp(date)] = snapshot.prices.iloc[-1] * 100
        snapshot.fetched_at = "2026-09-28T19:00:00+00:00"
        actual = analyze_pockets(snapshot)
        self.assertEqual(actual.as_of, pd.Timestamp("2026-09-25"))
        pd.testing.assert_frame_equal(actual.stocks, expected.stocks)
        pd.testing.assert_frame_equal(actual.acceleration_z, expected.acceleration_z)

    def test_acceleration_baseline_excludes_the_event_itself(self):
        snapshot = pilot_fixture()
        result = analyze_pockets(snapshot)
        logs = snapshot.prices.map(math.log)
        acceleration = (logs["AMAT"].diff() - logs[BENCHMARK].diff()).diff()
        event = len(acceleration) - 3
        previous = acceleration.iloc[event - 60:event]
        expected = (acceleration.iloc[event] - previous.mean()) / previous.std()
        self.assertAlmostEqual(result.acceleration_z["AMAT"].iloc[event], expected)

    def test_price_scale_does_not_affect_signals(self):
        snapshot = pilot_fixture()
        expected = analyze_pockets(snapshot)
        snapshot.prices["AMAT"] *= 100
        actual = analyze_pockets(snapshot)
        self.assertAlmostEqual(actual.stocks.set_index("Symbol").loc["AMAT", "PeakZ"],
                               expected.stocks.set_index("Symbol").loc["AMAT", "PeakZ"])

    def test_mixed_direction_pocket_has_no_quiet_peer_leads(self):
        snapshot = pilot_fixture()
        snapshot.prices.loc[snapshot.prices.index[-3]:, "LRCX"] *= math.exp(-0.24)
        result = analyze_pockets(snapshot)
        self.assertTrue(result.pockets.set_index("Pocket").loc["Wafer fabrication", "Active"])
        self.assertEqual(result.pockets.set_index("Pocket").loc["Wafer fabrication", "Direction"], "Mixed / unconfirmed")
        self.assertFalse((result.stocks["Status"] == "Research lead").any())

    def test_common_benchmark_shock_is_not_an_equipment_specific_event(self):
        snapshot = pilot_fixture(0)
        snapshot.prices.loc[snapshot.prices.index[-3]:] *= 1.5
        result = analyze_pockets(snapshot)
        self.assertEqual(result.pockets.iloc[0]["Unusual"], 0)

    def test_all_missing_session_is_not_bridged(self):
        snapshot = pilot_fixture()
        snapshot.prices.loc[snapshot.prices.index[-10]] = float("nan")
        result = analyze_pockets(snapshot)
        self.assertTrue((result.stocks["Status"] == "Unavailable").all())

    def test_missing_or_short_benchmark_is_explicit(self):
        for prices in (pilot_fixture().prices.drop(columns=[BENCHMARK]), pilot_fixture().prices.tail(100)):
            with self.assertRaises(StockDataError):
                analyze_pockets(PilotPrices(prices, "2026-09-26T12:00:00+00:00"))

    def test_price_information_follows_actual_return_not_relative_return(self):
        for stock_return, market_return, expected in (
            (0.05, 0.10, "Positive (up)"),
            (-0.05, -0.10, "Negative (down)"),
            (0.0, 0.10, "Neutral (flat)"),
        ):
            with self.subTest(stock_return=stock_return):
                snapshot = pilot_fixture()
                for symbol, change in (("AMAT", stock_return), (BENCHMARK, market_return)):
                    start = snapshot.prices[symbol].iloc[-6]
                    snapshot.prices.loc[snapshot.prices.index[-5]:, symbol] = [
                        start * (1 + change) ** (step / 5) for step in range(1, 6)
                    ]
                stock = analyze_pockets(snapshot).stocks.set_index("Symbol").loc["AMAT"]
                self.assertEqual(stock["PriceInformation"], expected)
                self.assertAlmostEqual(stock["Return5D"], stock_return)
                if stock_return > 0:
                    self.assertLess(stock["Excess5D"], 0)
                elif stock_return < 0:
                    self.assertGreater(stock["Excess5D"], 0)

    def test_unavailable_analysis_does_not_receive_positive_negative_or_neutral_label(self):
        for missing_row in (-1, -20):
            with self.subTest(missing_row=missing_row):
                snapshot = pilot_fixture()
                snapshot.prices.loc[snapshot.prices.index[missing_row], "AMAT"] = float("nan")
                stock = analyze_pockets(snapshot).stocks.set_index("Symbol").loc["AMAT"]
                self.assertEqual(stock["PriceInformation"], "Unavailable")
                self.assertTrue(pd.isna(stock["Return5D"]))

    def test_directional_unusual_counts_match_stocks_and_sum_to_total(self):
        for direction, column in ((1, "PositiveUnusual"), (-1, "NegativeUnusual")):
            with self.subTest(direction=direction):
                result = analyze_pockets(pilot_fixture(direction))
                self.assertEqual(result.pockets.iloc[0][column], 2)
                opposite = "NegativeUnusual" if direction == 1 else "PositiveUnusual"
                self.assertEqual(result.pockets.iloc[0][opposite], 0)
                for table in (result.pockets, result.daily):
                    pd.testing.assert_series_equal(
                        table[["PositiveUnusual", "NegativeUnusual", "NeutralUnusual"]].sum(axis=1),
                        table["Unusual"], check_names=False,
                    )
                flagged = result.stocks.loc[result.stocks["Status"] == "Unusual mover"]
                expected = "Positive (up)" if direction == 1 else "Negative (down)"
                self.assertTrue((flagged["PriceInformation"] == expected).all())


class VolatilitySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "pilot.sqlite3"
        self.patch = patch("volatility_strategy.SNAPSHOT_PATH", self.path)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_saved_snapshot_reopens_without_network(self):
        self.assertIsNone(read_saved_prices())
        with patch("volatility_strategy.download_adjusted_closes", return_value=pilot_fixture().prices) as download:
            saved = refresh_saved_prices()
            loaded = read_saved_prices()
        self.assertEqual(download.call_count, 1)
        self.assertEqual(download.call_args.args[0], [BENCHMARK, *[s.symbol for s in UNIVERSE]])
        self.assertEqual(loaded.fetched_at, saved.fetched_at)
        pd.testing.assert_frame_equal(loaded.prices, saved.prices, check_freq=False)
        self.assertEqual(analyze_pockets(loaded).as_of, pd.Timestamp("2026-09-25"))

    def test_invalid_refresh_does_not_replace_saved_snapshot(self):
        with patch("volatility_strategy.download_adjusted_closes", return_value=pilot_fixture().prices):
            saved = refresh_saved_prices()
        with patch("volatility_strategy.download_adjusted_closes", return_value=pd.DataFrame()):
            with self.assertRaises(StockDataError):
                refresh_saved_prices()
        self.assertEqual(read_saved_prices().fetched_at, saved.fetched_at)

    def test_corrupt_store_is_reported(self):
        self.path.write_bytes(b"not a sqlite database")
        with self.assertRaisesRegex(StockDataError, "could not be read"):
            read_saved_prices()

    def test_low_coverage_refresh_preserves_last_snapshot(self):
        with patch("volatility_strategy.download_adjusted_closes", return_value=pilot_fixture().prices):
            saved = refresh_saved_prices()
        incomplete = pilot_fixture().prices.drop(columns=["ASML", "KLAC", "FORM"])
        with patch("volatility_strategy.download_adjusted_closes", return_value=incomplete):
            with self.assertRaisesRegex(StockDataError, "80% coverage"):
                refresh_saved_prices()
        self.assertEqual(read_saved_prices().fetched_at, saved.fetched_at)


if __name__ == "__main__":
    unittest.main()
