from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
from curl_cffi.requests.exceptions import Timeout
from yfinance.exceptions import YFException

import adr_dividend
from adr_dividend import ADR_RESEARCH_AS_OF, _analyze_adr_dividend, adr_catalog, get_adr_dividend
from stock_data import StockDataError


EXPECTED_TICKERS = (
    "BTI BP SHEL EQNR E EC PBR VALE RIO BHP HSBC ING SAN BBVA BCS LYG NVS SNY "
    "NVO GSK TAK VOD KT SKM TIMB CHT ABEV AMX BUD DEO UL SONY TM HMC TSM UMC "
    "ASX HIMX INFY WIT HDB IBN BABA JD NTES PDD BIDU LU QFIN FINV LX NOAH VIPS "
    "PAC ASR OMAB TEO PBR.A BCH BSAC CIB AVAL ITUB BBD GGB SID SUZ BAK TS YPF "
    "SQM PKX KB SHG WF SAP NOK ERIC RELX WPP PSO RDY SBS CIG ELPC AKO.B CCU VIV "
    "ENIC NGG SE TCOM NIO XPEV LI BILI PUK FMS MUFG MFG"
).split()


def daily_history(start="2024-09-12", end="2026-09-11"):
    history = pd.DataFrame(
        {"Close": 80.0, "Dividends": 0.0},
        index=pd.date_range(start, end, freq="B", tz="America/New_York"),
    )
    return history


class ADRCatalogTests(unittest.TestCase):
    def test_fixed_research_universe_and_metadata_only_schema(self):
        catalog = adr_catalog()
        self.assertEqual(ADR_RESEARCH_AS_OF, "2026-09-11")
        self.assertEqual(catalog["Ticker"].tolist(), EXPECTED_TICKERS)
        self.assertEqual(len(catalog), 100)
        self.assertEqual(catalog["Ticker"].nunique(), 100)
        self.assertEqual(catalog["Symbol"].nunique(), 100)
        self.assertEqual(
            catalog.columns.tolist(),
            ["Ticker", "Symbol", "Name", "Country", "Overview", "ResearchNotes", "ResearchSource"],
        )
        self.assertTrue(catalog.map(lambda value: isinstance(value, str) and bool(value.strip())).all().all())
        self.assertEqual(
            adr_dividend._CATALOG_PATH,
            Path(adr_dividend.__file__).resolve().parent / "data" / "adr_catalog.csv",
        )

    def test_share_class_symbols_and_original_sources_are_preserved(self):
        catalog = adr_catalog().set_index("Ticker")
        for ticker in EXPECTED_TICKERS:
            with self.subTest(ticker=ticker):
                expected = {"PBR.A": "PBR-A", "AKO.B": "AKO-B"}.get(ticker, ticker)
                self.assertEqual(catalog.loc[ticker, "Symbol"], expected)
                self.assertEqual(
                    catalog.loc[ticker, "ResearchSource"],
                    f"https://stockanalysis.com/stocks/{ticker.lower()}/dividend/",
                )

    def test_snapshot_warnings_are_explicitly_dated_not_live_claims(self):
        catalog = adr_catalog().set_index("Ticker")
        self.assertTrue(catalog["ResearchNotes"].str.startswith("Dated research (2026-09-11): ").all())
        self.assertIn("special dividends announced June 11 2026", catalog.loc["NOAH", "ResearchNotes"])
        self.assertIn("do not assume recurrence", catalog.loc["NOAH", "ResearchNotes"])
        self.assertIn("sub-dollar price", catalog.loc["LX", "ResearchNotes"])
        self.assertIn("No dividend history reported", catalog.loc["PDD", "ResearchNotes"])
        self.assertEqual(catalog.loc["BTI", "Name"], "British American Tobacco")
        self.assertEqual(catalog.loc["BTI", "Country"], "UK")
        self.assertEqual(catalog.loc["BTI", "Overview"], "Tobacco and nicotine products")

    def test_catalog_required_columns_and_fields_are_validated(self):
        catalog = adr_catalog()
        for column in catalog.columns:
            for invalid in ("missing", "", "   ", None):
                with self.subTest(column=column, invalid=invalid):
                    broken = catalog.copy()
                    if invalid == "missing":
                        broken = broken.drop(columns=column)
                    else:
                        broken.loc[0, column] = invalid
                    with patch.object(adr_dividend.pd, "read_csv", return_value=broken):
                        with self.assertRaisesRegex(StockDataError, column):
                            adr_catalog()

    def test_catalog_duplicate_identifiers_are_rejected(self):
        catalog = adr_catalog()
        for column in ("Ticker", "Symbol"):
            with self.subTest(column=column):
                broken = catalog.copy()
                broken.loc[1, column] = broken.loc[0, column]
                with patch.object(adr_dividend.pd, "read_csv", return_value=broken):
                    with self.assertRaisesRegex(StockDataError, f"duplicate {column}"):
                        adr_catalog()

    def test_catalog_wrong_count_and_symbol_mapping_are_rejected(self):
        catalog = adr_catalog()
        with patch.object(adr_dividend.pd, "read_csv", return_value=catalog.iloc[:-1]):
            with self.assertRaisesRegex(StockDataError, "exactly 100"):
                adr_catalog()
        catalog.loc[catalog["Ticker"] == "PBR.A", "Symbol"] = "PBR.A"
        with patch.object(adr_dividend.pd, "read_csv", return_value=catalog):
            with self.assertRaisesRegex(StockDataError, "Yahoo symbol mapping"):
                adr_catalog()

    def test_unreadable_or_malformed_catalog_has_explicit_error(self):
        for error in (FileNotFoundError("missing"), pd.errors.ParserError("bad CSV"),
                      pd.errors.EmptyDataError("empty CSV"), UnicodeError("encoding"),
                      ValueError("malformed CSV value")):
            with self.subTest(error=type(error).__name__):
                with patch.object(adr_dividend.pd, "read_csv", side_effect=error):
                    with self.assertRaisesRegex(StockDataError, "ADR catalog could not be read"):
                        adr_catalog()

    def test_catalog_returns_independent_frames(self):
        catalog = adr_catalog()
        catalog.loc[0, "Name"] = "changed"
        self.assertEqual(adr_catalog().loc[0, "Name"], "British American Tobacco")


class ADRDividendAnalysisTests(unittest.TestCase):
    def analyze(self, history, as_of="2026-09-12"):
        return _analyze_adr_dividend(history, "BTI", as_of)

    def test_trailing_cash_boundary_is_exclusive_then_inclusive(self):
        history = daily_history()
        for day, cash in (("2025-09-11", 100), ("2025-09-12", 0.5),
                          ("2026-03-11", 1.5), ("2026-09-11", 2.0)):
            history.loc[day, "Dividends"] = cash
        result = self.analyze(history)
        self.assertEqual(result["Price"], 80.0)
        self.assertEqual(result["TTMCash"], 4.0)
        self.assertEqual(result["YieldPercent"], 5.0)
        self.assertEqual(result["WindowStart"], "2025-09-11")
        self.assertEqual(result["PriceDate"], "2026-09-11")
        self.assertEqual(result["DividendCount"], 3)
        self.assertEqual(result["LastExDate"], "2026-09-11")

    def test_calendar_year_includes_leap_day_not_just_365_days(self):
        history = daily_history("2023-03-01", "2025-02-28")
        history.loc["2024-02-28", "Dividends"] = 99.0
        history.loc["2024-02-29", "Dividends"] = 0.5
        history.loc["2025-02-28", "Dividends"] = 1.5
        result = self.analyze(history, "2025-03-01")
        self.assertEqual(result["WindowStart"], "2024-02-28")
        self.assertEqual(result["TTMCash"], 2.0)
        self.assertEqual(result["DividendCount"], 2)

    def test_leap_day_price_date_uses_previous_february_28(self):
        history = daily_history("2022-03-01", "2024-02-29")
        history.loc["2023-02-28", "Dividends"] = 99.0
        history.loc["2023-03-01", "Dividends"] = 0.5
        result = self.analyze(history, "2024-03-01")
        self.assertEqual(result["WindowStart"], "2023-02-28")
        self.assertEqual(result["TTMCash"], 0.5)

    def test_new_york_timezone_and_utc_history_have_same_ex_dates(self):
        history = daily_history()
        history.loc["2025-12-10", "Dividends"] = 0.5
        history.loc["2026-06-10", "Dividends"] = 1.5
        expected = self.analyze(history)
        history.index = history.index.tz_convert("UTC")
        self.assertEqual(self.analyze(history), expected)
        self.assertEqual(expected["LastExDate"], "2026-06-10")

    def test_utc_timestamps_are_normalized_to_new_york_not_utc_dates(self):
        history = pd.DataFrame(
            {"Close": 80.0, "Dividends": [0, 99, 0.5, 1.5]},
            index=pd.to_datetime([
                "2024-09-12 04:00Z", "2025-09-12 01:00Z",
                "2025-09-12 04:00Z", "2026-09-12 01:00Z",
            ]),
        )
        result = self.analyze(history)
        self.assertEqual(result["PriceDate"], "2026-09-11")
        self.assertEqual(result["TTMCash"], 2.0)

    def test_naive_daily_dates_are_new_york_dates(self):
        history = daily_history()
        history.loc["2026-09-11", "Dividends"] = 1.0
        expected = self.analyze(history)
        history.index = history.index.tz_localize(None)
        self.assertEqual(self.analyze(history), expected)

    def test_incomplete_current_bar_and_future_action_rows_are_excluded(self):
        history = daily_history(end="2026-09-14")
        history.loc["2026-09-10", "Dividends"] = 1.0
        history.loc["2026-09-11", ["Close", "Dividends"]] = [float("nan"), 100.0]
        history.loc["2026-09-14", ["Close", "Dividends"]] = [float("nan"), float("nan")]
        result = self.analyze(history, "2026-09-11")
        self.assertEqual(result["PriceDate"], "2026-09-10")
        self.assertEqual(result["TTMCash"], 1.0)
        self.assertEqual(result["DividendCount"], 1)

    def test_special_payouts_are_included_without_annualizing_or_split_adjusting(self):
        history = daily_history()
        history["Adj Close"] = 20.0
        history["Stock Splits"] = 0.0
        history.loc["2026-06-11", "Stock Splits"] = 4.0
        history.loc["2026-06-11", "Dividends"] = 2.0
        history.loc["2026-06-12", "Dividends"] = 8.0
        original = history.copy()
        result = self.analyze(history)
        self.assertEqual(result["Price"], 80.0)
        self.assertEqual(result["TTMCash"], 10.0)
        self.assertEqual(result["YieldPercent"], 12.5)
        self.assertEqual(result["DividendCount"], 2)
        pd.testing.assert_frame_equal(history, original)

    def test_valid_full_window_without_payouts_is_zero(self):
        history = daily_history()
        history.loc["2025-09-11", "Dividends"] = 99.0
        result = self.analyze(history)
        self.assertEqual(result["TTMCash"], 0.0)
        self.assertEqual(result["YieldPercent"], 0.0)
        self.assertEqual(result["DividendCount"], 0)
        self.assertIsNone(result["LastExDate"])

    def test_missing_dividend_column_is_not_zero(self):
        with self.assertRaisesRegex(StockDataError, "BTI.*missing Dividends"):
            self.analyze(daily_history().drop(columns="Dividends"))

    def test_missing_close_is_explicit(self):
        with self.assertRaisesRegex(StockDataError, "BTI.*missing Close"):
            self.analyze(daily_history().drop(columns="Close"))

    def test_missing_nonfinite_negative_and_invalid_dividends_are_not_zero(self):
        for value in (None, float("nan"), float("inf"), -float("inf"), -0.1, "bad"):
            for day in ("2024-09-12", "2026-09-11"):
                with self.subTest(value=value, day=day):
                    history = daily_history().astype({"Dividends": object})
                    history.loc[day, "Dividends"] = value
                    with self.assertRaisesRegex(StockDataError, "BTI.*Dividends"):
                        self.analyze(history)

    def test_missing_nonfinite_nonpositive_and_invalid_closes_are_rejected(self):
        for value in (None, float("nan"), float("inf"), -float("inf"), 0, -1, "bad"):
            for day in ("2024-09-12", "2026-09-11"):
                with self.subTest(value=value, day=day):
                    history = daily_history().astype({"Close": object})
                    history.loc[day, "Close"] = value
                    with self.assertRaisesRegex(StockDataError, "BTI.*Close"):
                        self.analyze(history)

    def test_boolean_datetime_and_complex_columns_are_not_numeric_cash(self):
        for values in (True, 1 + 2j, pd.Timestamp("2026-01-01")):
            with self.subTest(values=values):
                history = daily_history()
                history["Dividends"] = values
                with self.assertRaisesRegex(StockDataError, "BTI.*Dividends"):
                    self.analyze(history)

    def test_sum_overflow_and_nonfinite_yield_are_rejected(self):
        history = daily_history()
        history.loc["2026-09-10":"2026-09-11", "Dividends"] = 1e308
        with self.assertRaisesRegex(StockDataError, "BTI.*non-finite"):
            self.analyze(history)
        history["Dividends"] = 0.0
        history.loc["2026-09-11", ["Close", "Dividends"]] = [1e-300, 1e100]
        with self.assertRaisesRegex(StockDataError, "BTI.*non-finite"):
            self.analyze(history)

    def test_empty_none_and_future_only_history_are_errors(self):
        for history in (pd.DataFrame(), None, daily_history("2026-09-14", "2026-09-15")):
            with self.subTest(history=type(history).__name__):
                with self.assertRaisesRegex(StockDataError, "BTI.*history"):
                    self.analyze(history)

    def test_stale_history_is_not_a_zero_yield(self):
        with self.assertRaisesRegex(StockDataError, "BTI.*stale.*2026-09-04"):
            self.analyze(daily_history(end="2026-09-04"))
        result = self.analyze(daily_history(end="2026-09-04"), "2026-09-11")
        self.assertEqual(result["PriceDate"], "2026-09-04")

    def test_full_year_coverage_requires_first_date_at_or_before_cutoff(self):
        with self.assertRaisesRegex(StockDataError, "BTI.*coverage.*2025-09-11"):
            self.analyze(daily_history(start="2025-09-12"))
        result = self.analyze(daily_history(start="2025-09-11"))
        self.assertEqual(result["TTMCash"], 0.0)

    def test_invalid_nat_and_numeric_timestamps_are_rejected(self):
        for value in ("not a date", pd.NaT, None, 1, float("nan")):
            with self.subTest(value=value):
                history = daily_history()
                dates = list(history.index)
                dates[0] = value
                history.index = pd.Index(dates, dtype=object)
                with self.assertRaisesRegex(StockDataError, "BTI.*invalid timestamp"):
                    self.analyze(history)

    def test_duplicate_dates_and_intraday_rows_are_rejected(self):
        history = daily_history()
        extra = history.iloc[[-1]].copy()
        for hours in (0, 1):
            with self.subTest(hours=hours):
                extra.index = history.index[-1:] + pd.Timedelta(hours=hours)
                with self.assertRaisesRegex(StockDataError, "BTI.*duplicate New York dates"):
                    self.analyze(pd.concat([history, extra]))

    def test_duplicate_columns_are_explicitly_rejected(self):
        history = daily_history()
        history = pd.concat([history, history[["Close"]]], axis=1)
        with self.assertRaisesRegex(StockDataError, "BTI.*duplicate columns"):
            self.analyze(history)

    def test_unsorted_history_is_sorted_before_choosing_price_and_last_ex_date(self):
        history = daily_history()
        history.loc["2026-09-11", "Dividends"] = 2.0
        self.assertEqual(self.analyze(history.iloc[::-1]), self.analyze(history))

    def test_as_of_requires_iso_calendar_date(self):
        for as_of in ("2026-9-12", "20260912", "2026-02-30", "2026-09-12T12:00Z", "", None):
            with self.subTest(as_of=as_of):
                with self.assertRaisesRegex(StockDataError, "BTI.*as_of"):
                    self.analyze(daily_history(), as_of)


class ADRDividendFetchTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(adr_dividend.yf, "Ticker")
        self.factory = patcher.start()
        self.addCleanup(patcher.stop)
        self.ticker = self.factory.return_value
        self.ticker.history.return_value = daily_history()
        self.ticker.get_history_metadata.return_value = {"currency": "USD", "exchangeName": "NYQ"}

    def test_api_requests_two_years_of_unadjusted_action_history(self):
        self.ticker.history.return_value.loc["2026-09-11", "Dividends"] = 4.4
        before = datetime.now(timezone.utc)
        result = get_adr_dividend("BTI", "2026-09-12")
        self.factory.assert_called_once_with("BTI")
        self.ticker.history.assert_called_once_with(
            start="2024-09-12", end="2026-09-12", interval="1d",
            actions=True, auto_adjust=False, raise_errors=True, timeout=15,
        )
        self.ticker.get_history_metadata.assert_called_once_with()
        self.assertEqual(set(result), {
            "Price", "TTMCash", "YieldPercent", "PriceDate", "WindowStart",
            "DividendCount", "LastExDate", "FetchedAt", "LiveSource",
        })
        self.assertAlmostEqual(result["YieldPercent"], 5.5)
        self.assertEqual(result["LiveSource"], "https://finance.yahoo.com/quote/BTI/history/")
        fetched = datetime.fromisoformat(result["FetchedAt"])
        self.assertEqual(fetched.tzinfo, timezone.utc)
        self.assertGreaterEqual(fetched, before)
        self.assertLessEqual(fetched, datetime.now(timezone.utc))

    def test_all_allowed_exchanges_are_accepted(self):
        for exchange in ("NYQ", "NMS", "NGM", "NCM"):
            with self.subTest(exchange=exchange):
                self.ticker.get_history_metadata.return_value["exchangeName"] = exchange
                self.assertEqual(get_adr_dividend("BTI", "2026-09-12")["Price"], 80.0)

    def test_non_usd_and_off_exchange_securities_are_rejected(self):
        for field, value, message in (
            ("currency", "GBP", "expected USD"),
            ("currency", "GBp", "expected USD"),
            ("currency", "EUR", "expected USD"),
            ("exchangeName", "PNK", "not a supported NYSE/Nasdaq"),
            ("exchangeName", "LSE", "not a supported NYSE/Nasdaq"),
            ("exchangeName", "ASE", "not a supported NYSE/Nasdaq"),
        ):
            with self.subTest(field=field, value=value):
                metadata = {"currency": "USD", "exchangeName": "NYQ", field: value}
                self.ticker.get_history_metadata.return_value = metadata
                with self.assertRaisesRegex(StockDataError, f"BTI.*{message}"):
                    get_adr_dividend("BTI", "2026-09-12")

    def test_missing_currency_or_exchange_is_explicit(self):
        for field in ("currency", "exchangeName"):
            for value in (None, "", "   ", [], 123):
                with self.subTest(field=field, value=value):
                    metadata = {"currency": "USD", "exchangeName": "NYQ", field: value}
                    self.ticker.get_history_metadata.return_value = metadata
                    with self.assertRaisesRegex(StockDataError, f"BTI.*missing {field}"):
                        get_adr_dividend("BTI", "2026-09-12")
            metadata = {"currency": "USD", "exchangeName": "NYQ"}
            del metadata[field]
            self.ticker.get_history_metadata.return_value = metadata
            with self.assertRaisesRegex(StockDataError, f"BTI.*missing {field}"):
                get_adr_dividend("BTI", "2026-09-12")

    def test_missing_or_invalid_metadata_is_not_accepted(self):
        for metadata in (None, [], "USD", {}):
            with self.subTest(metadata=metadata):
                self.ticker.get_history_metadata.return_value = metadata
                with self.assertRaisesRegex(StockDataError, "BTI.*metadata"):
                    get_adr_dividend("BTI", "2026-09-12")

    def test_preferred_and_class_b_symbols_are_passed_through_unchanged(self):
        for symbol in ("PBR-A", "AKO-B"):
            with self.subTest(symbol=symbol):
                self.factory.reset_mock()
                result = get_adr_dividend(symbol, "2026-09-12")
                self.factory.assert_called_once_with(symbol)
                self.assertEqual(result["LiveSource"], f"https://finance.yahoo.com/quote/{symbol}/history/")

    def test_fixed_universe_does_not_expand_or_replace_share_classes(self):
        for symbol in ("AAPL", "PBR.A", "AKO.B", "BTI.L", "ELP", "", None):
            with self.subTest(symbol=symbol):
                with self.assertRaisesRegex(StockDataError, "fixed 2026-09-11 ADR universe"):
                    get_adr_dividend(symbol, "2026-09-12")
        self.factory.assert_not_called()

    def test_invalid_as_of_does_not_make_network_request(self):
        with self.assertRaisesRegex(StockDataError, "BTI.*as_of"):
            get_adr_dividend("BTI", "tomorrow")
        self.factory.assert_not_called()

    def test_market_errors_propagate_as_symbol_specific_stock_data_errors(self):
        for method in (self.ticker.history, self.ticker.get_history_metadata):
            for error in (Timeout("timed out"), YFException("unavailable")):
                with self.subTest(method=method, error=type(error).__name__):
                    method.side_effect = error
                    with self.assertRaisesRegex(StockDataError, "BTI.*Yahoo daily history"):
                        get_adr_dividend("BTI", "2026-09-12")
                    method.side_effect = None

    def test_programming_errors_are_not_swallowed(self):
        self.ticker.history.side_effect = RuntimeError("programming failure")
        with self.assertRaisesRegex(RuntimeError, "programming failure"):
            get_adr_dividend("BTI", "2026-09-12")

    def test_empty_history_has_no_saved_research_fallback(self):
        self.ticker.history.return_value = pd.DataFrame()
        with self.assertRaisesRegex(StockDataError, "BTI.*no daily history"):
            get_adr_dividend("BTI", "2026-09-12")

    def test_dated_no_dividend_warning_does_not_override_live_cash(self):
        self.ticker.history.return_value.loc["2026-09-11", "Dividends"] = 2.0
        result = get_adr_dividend("PDD", "2026-09-12")
        self.assertEqual(result["TTMCash"], 2.0)
        self.assertEqual(result["YieldPercent"], 2.5)


if __name__ == "__main__":
    unittest.main()
