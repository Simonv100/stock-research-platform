import threading
import time
import unittest
from unittest.mock import patch

import pandas as pd

from scanner_loading import (
    CacheActivity,
    MAX_SCANNER_WORKERS,
    cache_market_data,
    load_symbol_batch,
    track_cache_activity,
)
from stock_data import StockDataError


class ObservableCacheTests(unittest.TestCase):
    def test_success_failure_and_none_are_cached_distinctly_and_copies_are_isolated(self):
        calls = []

        @cache_market_data(ttl=86400)
        def source(symbol):
            calls.append(symbol)
            if symbol == "FAIL":
                raise StockDataError("Provider temporarily unavailable")
            return None if symbol == "NONE" else {"symbol": symbol}

        source.clear()
        self.addCleanup(source.clear)
        stats = CacheActivity()
        with track_cache_activity(stats):
            first = source("GOOD")
            first["symbol"] = "changed"
            self.assertEqual(source("GOOD"), {"symbol": "GOOD"})
            self.assertIsNone(source("NONE"))
            self.assertIsNone(source("NONE"))
            for _ in range(2):
                with self.assertRaisesRegex(StockDataError, "Provider temporarily unavailable"):
                    source("FAIL")
        self.assertEqual(calls, ["GOOD", "NONE", "FAIL"])
        self.assertEqual(stats.counts(), (3, 3, 2))
        self.assertEqual(source._info.ttl, 86400)
        source.clear("FAIL")
        with self.assertRaises(StockDataError):
            source("FAIL")
        self.assertEqual(calls, ["GOOD", "NONE", "FAIL", "FAIL"])

    def test_unexpected_programming_errors_are_not_converted_to_missing_data(self):
        calls = []

        @cache_market_data(ttl=86400)
        def broken(symbol):
            calls.append(symbol)
            raise ValueError("Programming error")

        self.addCleanup(broken.clear)
        for _ in range(2):
            with self.assertRaisesRegex(ValueError, "Programming error"):
                broken("A")
        self.assertEqual(len(calls), 2)

    def test_different_functions_with_same_arguments_have_separate_cache_entries(self):
        @cache_market_data(ttl=86400)
        def first(symbol):
            return {"name": "first", "symbol": symbol}

        @cache_market_data(ttl=86400)
        def second(symbol):
            return {"name": "second", "symbol": symbol}

        self.addCleanup(first.clear)
        self.addCleanup(second.clear)
        self.assertEqual(first("A")["name"], "first")
        self.assertEqual(second("A")["name"], "second")

    def test_nested_cache_activity_counts_each_entry_and_single_flight_loads_once(self):
        calls = []

        @cache_market_data(ttl=86400)
        def raw(symbol):
            calls.append(symbol)
            time.sleep(0.02)
            return 10

        @cache_market_data(ttl=86400)
        def derived(symbol):
            return raw("SHARED") * 2

        raw.clear()
        derived.clear()
        self.addCleanup(raw.clear)
        self.addCleanup(derived.clear)
        batch = load_symbol_batch(["A", "B", "C", "D"], derived)
        self.assertEqual(calls, ["SHARED"])
        self.assertEqual(batch.progress.computed, 5)
        self.assertEqual(batch.progress.reused, 3)
        warm = load_symbol_batch(["D", "A"], derived)
        self.assertEqual(warm.progress.computed, 0)
        self.assertEqual(warm.progress.reused, 2)
        self.assertEqual(warm.values, {"D": 20, "A": 20})

    def test_expiry_and_global_refresh_clear_failures_as_well_as_successes(self):
        import streamlit as st
        from streamlit.runtime.caching import cache_utils

        calls = []

        @cache_market_data(ttl=86400)
        def source(symbol):
            calls.append(symbol)
            if symbol == "FAIL":
                raise StockDataError("Not available")
            return 1

        self.addCleanup(source.clear)
        with patch.object(cache_utils, "TTLCACHE_TIMER", return_value=0) as clock:
            source.clear()
            source("OK")
            with self.assertRaises(StockDataError):
                source("FAIL")
            clock.return_value = 23 * 3600
            source("OK")
            with self.assertRaises(StockDataError):
                source("FAIL")
            self.assertEqual(len(calls), 2)
            clock.return_value = 24 * 3600 + 1
            source("OK")
            with self.assertRaises(StockDataError):
                source("FAIL")
            self.assertEqual(len(calls), 4)
            st.cache_data.clear()
            source("OK")
            with self.assertRaises(StockDataError):
                source("FAIL")
            self.assertEqual(len(calls), 6)


class ScannerBatchTests(unittest.TestCase):
    def test_concurrency_is_bounded_order_is_stable_and_progress_is_on_main_thread(self):
        lock = threading.Lock()
        barrier = threading.Barrier(MAX_SCANNER_WORKERS)
        active = 0
        maximum = 0
        main_thread = threading.get_ident()
        snapshots = []

        def load(symbol):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            barrier.wait(timeout=3)
            with lock:
                active -= 1
            if symbol == "2":
                raise StockDataError("No data")
            return symbol

        def progress(state):
            self.assertEqual(threading.get_ident(), main_thread)
            snapshots.append(state)

        batch = load_symbol_batch(["3", "1", "2", "0", "1"], load, progress)
        self.assertEqual(maximum, MAX_SCANNER_WORKERS)
        self.assertEqual(list(batch.values), ["3", "1", "0"])
        self.assertEqual(batch.errors, {"2": "No data"})
        self.assertEqual(snapshots[0].completed, 0)
        self.assertEqual(snapshots[-1].completed, 4)
        self.assertEqual(snapshots[-1].total, 4)

    def test_fully_warm_batches_make_zero_provider_calls(self):
        calls = []

        @cache_market_data(ttl=86400)
        def source(symbol):
            calls.append(symbol)
            return pd.DataFrame({"value": [len(symbol)]})

        source.clear()
        self.addCleanup(source.clear)
        symbols = [str(index) for index in range(100)]
        first = load_symbol_batch(symbols, source)
        self.assertEqual(len(calls), 100)
        self.assertEqual(first.progress.computed, 100)
        second = load_symbol_batch(symbols[::-1], source)
        third = load_symbol_batch(symbols[:20], source)
        self.assertEqual(len(calls), 100)
        self.assertEqual(second.progress.computed, 0)
        self.assertEqual(second.progress.reused, 100)
        self.assertEqual(third.progress.computed, 0)

    def test_empty_batch_and_unexpected_loader_errors_are_explicit(self):
        batch = load_symbol_batch([], lambda _: self.fail("No request should occur"))
        self.assertEqual(batch.values, {})
        self.assertEqual(batch.progress.total, 0)
        with self.assertRaisesRegex(ValueError, "broken"):
            load_symbol_batch(["A"], lambda _: (_ for _ in ()).throw(ValueError("broken")))

    def test_interrupted_progress_cancels_obsolete_queued_loads(self):
        calls = []

        def load(symbol):
            calls.append(symbol)
            time.sleep(0.02)
            return symbol

        def interrupted(state):
            if state.completed:
                raise RuntimeError("new rerun")

        with self.assertRaisesRegex(RuntimeError, "new rerun"):
            load_symbol_batch([str(index) for index in range(80)], load, interrupted)
        self.assertLess(len(calls), 80)


class SharedAppStatementCacheTests(unittest.TestCase):
    def test_progress_ui_reports_cache_hits_and_explicit_unavailable_rows(self):
        from streamlit.testing.v1 import AppTest
        import app

        @cache_market_data(ttl=86400)
        def source(symbol):
            if symbol == "BAD":
                raise StockDataError("Feed unavailable")
            return {"symbol": symbol}

        source.clear()
        self.addCleanup(source.clear)
        script = (
            "from app import load_scanner_data, cached_info\n"
            "batch = load_scanner_data(['GOOD', 'BAD'], cached_info, 'Test metadata')\n"
        )
        with patch.object(app, "cached_info", source):
            ui = AppTest.from_string(script).run()
            self.assertFalse(ui.exception)
            self.assertTrue(any("2/2 processed" in item.value for item in ui.caption))
            self.assertTrue(any("2 entries loaded/computed" in item.value for item in ui.caption))
            self.assertTrue(any("Failed market requests" in item.value for item in ui.warning))
            ui.run()
            self.assertFalse(ui.exception)
            self.assertTrue(any("2 cached entries reused" in item.value for item in ui.caption))
            self.assertTrue(any("0 entries loaded/computed" in item.value for item in ui.caption))
            self.assertTrue(ui.warning)

    def test_revenue_buybacks_share_count_and_recovery_reuse_raw_statements(self):
        import app
        from tests.test_recovery_financials import statements

        income, cashflow, balance = statements()
        latest = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize() - pd.offsets.QuarterEnd()
        for frame in (income, cashflow, balance):
            frame.columns = pd.date_range(end=latest, periods=len(frame.columns), freq="QE")[::-1]
        cashflow.loc["Net Common Stock Issuance"] = -20.0
        cashflow.loc["Common Stock Dividend Paid"] = -10.0
        balance.loc["Ordinary Shares Number"] = 1000.0
        frames = {"income": income, "cashflow": cashflow, "balance": balance}
        caches = (
            app.cached_statement_history, app.cached_financial_history, app.cached_sec_quarterly_revenue,
            app.cached_stock_revenue_growth, app.cached_cashflow_history, app.cached_share_count_history,
            app.cached_net_buyback_assessment, app.cached_financial_recovery, app.cached_shareholder_yield,
        )
        for cache in caches:
            cache.clear()
            self.addCleanup(cache.clear)
        info = {"currency": "USD", "financialCurrency": "USD", "marketCap": 1000,
                "quoteType": "EQUITY", "sector": "Technology"}
        with (
            patch.object(app, "cached_info", return_value=info),
            patch.object(app, "get_sec_quarterly_revenue", return_value=pd.DataFrame(columns=["Period", "Revenue"])) as sec,
            patch.object(app, "get_statement_history",
                         side_effect=lambda symbol, statement, frequency: frames[statement]) as source,
        ):
            app.cached_financial_history("EX", "quarterly")
            app.cached_stock_revenue_growth("EX", app.REVENUE_MODEL_VERSION)
            app.cached_net_buyback_assessment("EX")
            app.cached_shareholder_yield("EX", 1000)
            app.cached_share_count_history("EX", "quarterly")
            app.cached_financial_recovery("EX", app.RECOVERY_MODEL_VERSION)
            calls = [call.args for call in source.call_args_list]
            self.assertEqual(calls.count(("EX", "income", "quarterly")), 1)
            self.assertEqual(calls.count(("EX", "cashflow", "quarterly")), 1)
            self.assertEqual(calls.count(("EX", "balance", "quarterly")), 1)
            self.assertEqual(len(calls), len(set(calls)))
            sec.assert_called_once_with("EX")
            count = source.call_count
            app.cached_stock_revenue_growth("EX", app.REVENUE_MODEL_VERSION)
            app.cached_financial_recovery("EX", app.RECOVERY_MODEL_VERSION)
            self.assertEqual(source.call_count, count)


if __name__ == "__main__":
    unittest.main()
