import unittest
from unittest.mock import patch

import pandas as pd

from recovery_market import (
    assess_sector_strength, assess_small_cap, get_recovery_prices, quote_currency,
    sector_benchmark,
)
from stock_data import StockDataError


AS_OF = "2026-09-11"


def info(currency="USD", cap=1_000_000_000):
    return {"currency": currency, "marketCap": cap, "sector": "Technology",
            "quoteType": "EQUITY", "regularMarketTime": pd.Timestamp(AS_OF, tz="UTC").timestamp()}


def prices(start=100, end=130):
    dates = pd.bdate_range("2025-09-11", AS_OF)
    values = [start + (end - start) * i / (len(dates) - 1) for i in range(len(dates))]
    return pd.DataFrame({"Adj Close": values, "Close": values}, index=dates)


class SmallCapTests(unittest.TestCase):
    def test_strict_usd_boundary(self):
        for cap, status in ((1_999_999_999, "Pass"), (2_000_000_000, "Fail"), (3e9, "Fail"),
                            (0, "Unknown"), (-1, "Unknown"), (None, "Unknown"),
                            (float("nan"), "Unknown"), (float("inf"), "Unknown")):
            with self.subTest(cap=cap):
                result = assess_small_cap("EX", info(cap=cap), as_of=AS_OF)
                self.assertEqual(result["SmallCapStatus"], status)

    def test_fx_conversion_not_raw_foreign_market_cap(self):
        result = assess_small_cap("EX.PA", info("EUR", 1.8e9), prices(1.2, 1.2), AS_OF)
        self.assertEqual(result["SmallCapStatus"], "Fail")
        self.assertEqual(result["MarketCapUSD"], 2.16e9)
        self.assertEqual(result["MarketCapCurrency"], "EUR")
        self.assertEqual(result["MarketCapFXDate"], AS_OF)

    def test_pence_quote_does_not_divide_yahoo_marketcap_by_100(self):
        result = assess_small_cap("EX.L", info("GBp", 1.8e9), prices(1.3, 1.3), AS_OF)
        self.assertEqual(result["MarketCapUSD"], 2.34e9)
        self.assertEqual(result["SmallCapStatus"], "Fail")
        self.assertEqual(quote_currency("GBp"), ("GBP", 0.01))

    def test_missing_and_stale_fx_remain_unknown(self):
        for fx in (None, prices().iloc[:-15]):
            result = assess_small_cap("EX.PA", info("EUR"), fx, AS_OF)
            self.assertEqual(result["SmallCapStatus"], "Unknown")
            self.assertNotIn("MarketCapUSD", result)

    def test_future_fx_is_not_used(self):
        fx = pd.DataFrame({"Close": [1.2]}, index=pd.to_datetime(["2026-09-12"]))
        result = assess_small_cap("EX.PA", info("EUR"), fx, AS_OF)
        self.assertEqual(result["SmallCapStatus"], "Unknown")

    def test_missing_stale_future_quote_dates(self):
        for value in (None, 0, pd.Timestamp("2026-09-12", tz="UTC").timestamp()):
            data = {**info(), "regularMarketTime": value}
            self.assertEqual(assess_small_cap("EX", data, as_of=AS_OF)["SmallCapStatus"], "Unknown")

    def test_funds_and_unknown_currency(self):
        self.assertEqual(assess_small_cap("ETF", {**info(), "quoteType": "ETF"})["SmallCapStatus"], "Not applicable")
        self.assertEqual(assess_small_cap("EX", info("unknown"), as_of=AS_OF)["SmallCapStatus"], "Unknown")


class SectorStrengthTests(unittest.TestCase):
    def assess(self, stock=None, benchmark=None, data=None, fx=None):
        return assess_sector_strength(
            "EX", data if data is not None else info(),
            stock if stock is not None else prices(100, 150),
            benchmark if benchmark is not None else prices(100, 110),
            fx, AS_OF,
        )

    def test_outperformance_and_explained_periods(self):
        result = self.assess()
        self.assertEqual(result["SectorStrengthStatus"], "Pass")
        self.assertEqual(result["SectorBenchmark"], "IXN")
        self.assertEqual(result["SectorAsOf"], AS_OF)
        self.assertEqual(result["SectorStart3M"], "2026-06-11")
        self.assertEqual(result["SectorStart6M"], "2026-03-11")
        self.assertGreater(result["SectorExcess3M"], 0)
        self.assertGreater(result["SectorExcess6M"], 0)

    def test_rising_stock_that_lags_sector_fails(self):
        self.assertEqual(self.assess(prices(100, 110), prices(100, 150))["SectorStrengthStatus"], "Fail")

    def test_tie_does_not_pass(self):
        self.assertEqual(self.assess(prices(), prices())["SectorStrengthStatus"], "Fail")

    def test_three_month_failure_overrides_six_month_strength(self):
        stock = prices(100, 150)
        stock.loc["2026-06-11":, "Adj Close"] = 130
        stock.loc["2026-06-11", "Adj Close"] = 140
        result = self.assess(stock, prices(100, 100))
        self.assertGreater(result["SectorExcess6M"], 0)
        self.assertLess(result["SectorExcess3M"], 0)
        self.assertEqual(result["SectorStrengthStatus"], "Fail")

    def test_exchange_rate_changes_affect_stock_usd_returns(self):
        result = self.assess(prices(100, 110), prices(100, 100), info("EUR"), prices(1.5, 0.8))
        self.assertEqual(result["SectorStrengthStatus"], "Fail")
        self.assertIn("EURUSD", result["SectorFXSource"])

    def test_adjusted_prices_not_raw_close(self):
        stock = prices(100, 150)
        stock["Close"] = 1
        self.assertEqual(self.assess(stock)["SectorStrengthStatus"], "Pass")
        self.assertEqual(self.assess(stock.drop(columns="Adj Close"))["SectorStrengthStatus"], "Unknown")

    def test_history_coverage_and_staleness(self):
        for stock in (prices().iloc[-60:], prices().iloc[:-20], pd.DataFrame()):
            self.assertEqual(self.assess(stock)["SectorStrengthStatus"], "Unknown")

    def test_common_dates_are_used_with_timezone_and_holiday(self):
        stock = prices(100, 150)
        stock.index = stock.index.tz_localize("Europe/Paris")
        benchmark = prices(100, 110).drop(pd.Timestamp(AS_OF))
        result = self.assess(stock, benchmark)
        self.assertEqual(result["SectorStrengthStatus"], "Pass")
        self.assertEqual(result["SectorAsOf"], "2026-09-10")

    def test_no_common_currency_or_sector_is_unknown(self):
        for data in (info("EUR"), {**info(), "sector": "Mystery"}):
            self.assertEqual(self.assess(data=data)["SectorStrengthStatus"], "Unknown")

    def test_large_data_gap_is_unknown(self):
        stock = prices().drop(pd.bdate_range("2026-07-01", "2026-08-01"))
        self.assertEqual(self.assess(stock)["SectorStrengthStatus"], "Unknown")

    def test_all_provider_sector_aliases_map_to_existing_catalog(self):
        for name in ("Technology", "Healthcare", "Consumer Cyclical", "Consumer Defensive",
                     "Financial Services", "Basic Materials", "Industrials", "Energy",
                     "Communication Services", "Real Estate", "Utilities"):
            self.assertTrue(sector_benchmark({"sector": name})[1])

    def test_fetch_empty_history_surfaces_error(self):
        with patch("recovery_market.yf.Ticker") as ticker:
            ticker.return_value.history.return_value = pd.DataFrame()
            with self.assertRaises(StockDataError):
                get_recovery_prices("EX")


if __name__ == "__main__":
    unittest.main()
