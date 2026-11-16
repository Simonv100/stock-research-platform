import unittest
from unittest.mock import patch

import pandas as pd

from stock_chat import build_stock_context
from stock_data import (
    U_RECOVERY_MODEL_VERSION,
    U_SHAPE_NEAR_MISS,
    U_SHAPE_STRICT,
    analyze_etf_inflection,
    classify_u_recovery,
    get_etf_inflection_scan,
    get_inflection_scan,
    has_completed_intermediate_cycle,
)


def recovery_history(last_close=48.1):
    closes = (
        [100.0] * 120
        + [100.0 - step for step in range(80)]
        + [20.0 + (step % 20) * 0.2 for step in range(480)]
        + [24.0 + step * 0.26 for step in range(100)]
        + [50.0 - step * 0.1 for step in range(20)]
    )
    closes[-1] = last_close
    return pd.DataFrame({"Close": closes}, index=pd.bdate_range("2023-01-02", periods=len(closes)))


def intermediate_cycle_history():
    closes = (
        [100.0] * 120
        + [100.0 - step * 0.5 for step in range(80)]
        + [60.0 + step * 0.225 for step in range(160)]
        + [95.775 - step * 0.75 for step in range(100)]
        + [20.0] * 320
        + [21.0 + step * 0.18 for step in range(110)]
    )
    return pd.DataFrame({"Close": closes}, index=pd.bdate_range("2022-01-03", periods=len(closes)))


class IntermediateCycleTests(unittest.TestCase):
    def test_decline_recovery_and_duration_boundaries(self):
        def path(trough=75.0, rebound=93.75, elapsed=120):
            return pd.Series([100.0, trough] + [trough] * (elapsed - 1) + [rebound])

        self.assertTrue(has_completed_intermediate_cycle(path()))
        self.assertFalse(has_completed_intermediate_cycle(path(trough=75.0001)))
        self.assertFalse(has_completed_intermediate_cycle(path(rebound=93.7499)))
        self.assertFalse(has_completed_intermediate_cycle(path(elapsed=119)))
        self.assertFalse(has_completed_intermediate_cycle(pd.Series(dtype=float)))
        self.assertFalse(has_completed_intermediate_cycle(pd.Series([100.0])))
        self.assertFalse(has_completed_intermediate_cycle(pd.Series([100.0] * 150)))

    def test_lower_intermediate_trough_resets_the_recovery_clock(self):
        path = pd.Series([100.0, 75.0] + [75.0] * 130 + [60.0] + [60.0] * 118 + [90.0])
        self.assertFalse(has_completed_intermediate_cycle(path))
        self.assertTrue(has_completed_intermediate_cycle(pd.concat([path, pd.Series([90.0])], ignore_index=True)))

    def test_multi_cycle_path_is_near_only_without_changing_technical_measurements(self):
        history = intermediate_cycle_history()
        with patch("stock_data.has_completed_intermediate_cycle", return_value=False):
            old_match = analyze_etf_inflection(history)
        self.assertIsNotNone(old_match)
        self.assertEqual(old_match["ShapeMatch"], U_SHAPE_STRICT)
        self.assertIsNone(analyze_etf_inflection(history))
        near = analyze_etf_inflection(history, include_near_misses=True)
        self.assertEqual(near["ShapeMatch"], U_SHAPE_NEAR_MISS)
        self.assertEqual(near["ShapeMissCount"], 1)
        self.assertIn("Completed intermediate cycle", near["ShapeMissedRules"])
        for field in old_match.keys() - {"ShapeMatch", "ShapeMissCount", "ShapeMissedRules"}:
            self.assertEqual(old_match[field], near[field], field)

    def test_one_clean_recovery_does_not_become_an_intermediate_cycle(self):
        history = recovery_history()
        self.assertFalse(has_completed_intermediate_cycle(history["Close"].iloc[:history["Close"].argmin()]))
        self.assertEqual(analyze_etf_inflection(history)["ShapeMatch"], U_SHAPE_STRICT)


class UShapeClassificationTests(unittest.TestCase):
    def setUp(self):
        self.metrics = {
            "PriorDecline": -0.5, "RecoveryProgress": 0.3, "DistanceToPeak": -0.3,
            "LowAge": 200, "BaseSpan": 300, "BaseDays": 150,
            "20DReturn": 0.1, "60DReturn": 0.05, "OneYearReturn": 0.2,
            "HigherLow": 0.1, "MA50Slope20D": 0.04, "VsMA50": 0.1,
        }

    def classify(self, **changes):
        return classify_u_recovery(
            {**self.metrics, **changes}, completed_earlier_cycle=False, failed_late_recovery=False,
        )

    def test_strict_match_is_not_a_near_miss(self):
        result = self.classify()
        self.assertEqual(result["ShapeMatch"], U_SHAPE_STRICT)
        self.assertEqual(result["ShapeMissCount"], 0)
        self.assertIn("all strict rules met", result["ShapeMissedRules"])

    def test_each_relaxed_boundary_can_only_produce_a_labeled_near_miss(self):
        for field, value, label in (
            ("LowAge", 45, "Age of low"),
            ("BaseSpan", 90, "Base span"),
            ("BaseDays", 40, "Days in low zone"),
            ("20DReturn", -0.15, "20-day return"),
            ("60DReturn", -0.08, "60-day return"),
            ("HigherLow", -0.08, "Recent vs. prior low"),
            ("MA50Slope20D", -0.02, "50-day MA slope"),
            ("VsMA50", -0.03, "Price vs. 50-day MA"),
        ):
            with self.subTest(field=field):
                result = self.classify(**{field: value})
                self.assertEqual(result["ShapeMatch"], U_SHAPE_NEAR_MISS)
                self.assertEqual(result["ShapeMissCount"], 1)
                self.assertIn(label, result["ShapeMissedRules"])
                self.assertIn("needs", result["ShapeMissedRules"])
                self.assertIsNone(self.classify(**{field: value - 0.0001}))

    def test_exact_strict_boundaries_and_strictly_positive_ma_rules(self):
        result = self.classify(
            LowAge=60, BaseSpan=120, BaseDays=50,
            PriorDecline=-0.15, RecoveryProgress=0.05, DistanceToPeak=-0.10,
            **{"20DReturn": -0.1, "60DReturn": -0.03, "OneYearReturn": 0, "HigherLow": -0.03},
        )
        self.assertEqual(result["ShapeMatch"], U_SHAPE_STRICT)
        self.assertEqual(self.classify(RecoveryProgress=0.75)["ShapeMatch"], U_SHAPE_STRICT)
        result = self.classify(MA50Slope20D=0, VsMA50=0)
        self.assertEqual(result["ShapeMatch"], U_SHAPE_NEAR_MISS)
        self.assertEqual(result["ShapeMissCount"], 2)

    def test_two_misses_allowed_but_three_rejected(self):
        result = self.classify(BaseSpan=100, BaseDays=45)
        self.assertEqual(result["ShapeMissCount"], 2)
        self.assertIn("Base span", result["ShapeMissedRules"])
        self.assertIn("Days in low zone", result["ShapeMissedRules"])
        self.assertIsNone(self.classify(BaseSpan=100, BaseDays=45, VsMA50=-0.01))

    def test_hard_shape_and_cycle_guards_are_never_relaxed(self):
        for field, value in (
            ("PriorDecline", -0.149), ("RecoveryProgress", 0.049),
            ("RecoveryProgress", 0.751), ("DistanceToPeak", -0.099), ("OneYearReturn", -0.0001),
        ):
            with self.subTest(field=field, value=value):
                self.assertIsNone(self.classify(**{field: value}))
        for completed, failed in ((True, False), (False, True), (True, True)):
            with self.subTest(completed=completed, failed=failed):
                self.assertIsNone(classify_u_recovery(
                    self.metrics, completed_earlier_cycle=completed, failed_late_recovery=failed,
                ))

    def test_existing_recent_reversal_exception_is_preserved(self):
        result = self.classify(LowAge=100, **{"60DReturn": 0.08, "OneYearReturn": -0.5})
        self.assertEqual(result["ShapeMatch"], U_SHAPE_STRICT)
        near = self.classify(LowAge=100, VsMA50=-0.01, **{"60DReturn": 0.08, "OneYearReturn": -0.5})
        self.assertEqual(near["ShapeMatch"], U_SHAPE_NEAR_MISS)
        self.assertIsNone(self.classify(LowAge=181, **{"60DReturn": 0.08, "OneYearReturn": -0.5}))

    def test_invalid_numeric_measurements_are_not_near_misses(self):
        for field in self.metrics:
            for value in (None, float("nan"), float("inf"), float("-inf")):
                with self.subTest(field=field, value=value):
                    self.assertIsNone(self.classify(**{field: value}))

    def test_intermediate_cycle_counts_as_one_miss_and_preserves_hard_guards(self):
        def classify(**changes):
            return classify_u_recovery(
                {**self.metrics, **changes}, completed_earlier_cycle=False,
                failed_late_recovery=False, completed_intermediate_cycle=True,
            )

        near = classify()
        self.assertEqual(near["ShapeMatch"], U_SHAPE_NEAR_MISS)
        self.assertEqual(near["ShapeMissCount"], 1)
        self.assertEqual(classify(BaseSpan=100)["ShapeMissCount"], 2)
        self.assertIsNone(classify(BaseSpan=100, BaseDays=45))
        self.assertIsNone(classify(BaseSpan=89))
        self.assertIsNone(classify(RecoveryProgress=0.76))
        for completed, failed in ((True, False), (False, True)):
            self.assertIsNone(classify_u_recovery(
                self.metrics, completed_earlier_cycle=completed, failed_late_recovery=failed,
                completed_intermediate_cycle=True,
            ))


class UShapeHistoryAndScanTests(unittest.TestCase):
    def test_real_measurements_keep_strict_default_and_opt_in_near_misses(self):
        strict = analyze_etf_inflection(recovery_history())
        self.assertEqual(strict["ShapeMatch"], U_SHAPE_STRICT)
        self.assertEqual(strict["Score"], 14)
        self.assertEqual(strict, analyze_etf_inflection(recovery_history(), include_near_misses=True))
        self.assertIsNone(analyze_etf_inflection(recovery_history(46)))
        near = analyze_etf_inflection(recovery_history(46), include_near_misses=True)
        self.assertEqual(near["ShapeMatch"], U_SHAPE_NEAR_MISS)
        self.assertEqual(near["ShapeMissCount"], 1)
        self.assertLess(near["VsMA50"], 0)
        self.assertIn("Price vs. 50-day MA", near["ShapeMissedRules"])
        self.assertIsNone(analyze_etf_inflection(recovery_history(40), include_near_misses=True))

    def test_short_invalid_and_persistent_decline_histories_remain_excluded(self):
        short = recovery_history().tail(499)
        self.assertIsNone(analyze_etf_inflection(short, include_near_misses=True))
        for value in (0, -1, float("inf")):
            history = recovery_history()
            history.iloc[-1, 0] = value
            with self.subTest(value=value):
                self.assertIsNone(analyze_etf_inflection(history, include_near_misses=True))
        falling = recovery_history()
        falling["Close"] = [1000 - index for index in range(len(falling))]
        self.assertIsNone(analyze_etf_inflection(falling, include_near_misses=True))

    def test_batched_scan_and_etf_wrapper_keep_groups_disjoint_and_deduplicate_symbols(self):
        downloaded = pd.concat({"AAA": recovery_history(), "BBB": recovery_history(46)}, axis=1)
        with patch("stock_data.yf.download", return_value=downloaded) as download:
            strict = get_inflection_scan(["BBB", "AAA", "AAA"])
            combined = get_inflection_scan(["AAA", "BBB"], include_near_misses=True)
            etfs = get_etf_inflection_scan(["AAA", "BBB"], include_near_misses=True)
        self.assertEqual(strict["Symbol"].tolist(), ["AAA"])
        self.assertEqual(set(combined["Symbol"]), {"AAA", "BBB"})
        self.assertEqual(combined["Symbol"].nunique(), len(combined))
        self.assertEqual(combined.set_index("Symbol").loc["BBB", "ShapeMatch"], U_SHAPE_NEAR_MISS)
        pd.testing.assert_frame_equal(combined, etfs)
        self.assertEqual(download.call_args_list[0].args[0], ["AAA", "BBB"])

    def test_empty_scan_schema_and_single_ticker_response(self):
        empty = get_inflection_scan([], include_near_misses=True)
        self.assertTrue({"ShapeMatch", "ShapeMissCount", "ShapeMissedRules", "VsMA50"}.issubset(empty.columns))
        with patch("stock_data.yf.download", return_value=recovery_history(46)):
            near = get_inflection_scan(["BBB"], include_near_misses=True)
        self.assertEqual(near["ShapeMatch"].tolist(), [U_SHAPE_NEAR_MISS])

    def test_both_cache_wrappers_cache_the_union_without_ui_mode_in_cache_key(self):
        import app
        for cache, loader_name in (
            (app.cached_stock_inflection_scan, "get_inflection_scan"),
            (app.cached_inflection_scan, "get_etf_inflection_scan"),
        ):
            with self.subTest(loader=loader_name):
                cache.clear()
                self.addCleanup(cache.clear)
                with patch.object(app, loader_name, return_value=pd.DataFrame()) as loader:
                    cache(("AAA",), U_RECOVERY_MODEL_VERSION)
                    cache(("AAA",), U_RECOVERY_MODEL_VERSION)
                loader.assert_called_once_with(["AAA"], include_near_misses=True)
                self.assertEqual(cache._info.ttl, 86400)
                for old_version in ("u-recovery-v8", "u-recovery-v9-independent-shapes"):
                    with self.assertRaises(ValueError):
                        cache(("AAA",), old_version)

    def test_chat_context_keeps_shape_classification_and_missed_rules(self):
        near = analyze_etf_inflection(recovery_history(46), include_near_misses=True)
        context = build_stock_context("BBB", "Example", {}, pd.DataFrame(), {"research_view": near})
        evidence = context["sections"]["research_view"]
        self.assertEqual(evidence["ShapeMatch"], U_SHAPE_NEAR_MISS)
        self.assertEqual(evidence["ShapeMissCount"], 1)
        self.assertIn("Price vs. 50-day MA", evidence["ShapeMissedRules"])

    def test_intermediate_cycle_reason_is_kept_in_scan_schema_and_chat(self):
        history = intermediate_cycle_history()
        with patch("stock_data.yf.download", return_value=history):
            self.assertTrue(get_inflection_scan(["MULTI"]).empty)
            scan = get_etf_inflection_scan(["MULTI"], include_near_misses=True)
        self.assertEqual(scan.iloc[0]["ShapeMatch"], U_SHAPE_NEAR_MISS)
        context = build_stock_context("MULTI", "Example", {}, pd.DataFrame(), {"research_view": scan.iloc[0].to_dict()})
        self.assertIn("Completed intermediate cycle", context["sections"]["research_view"]["ShapeMissedRules"])


if __name__ == "__main__":
    unittest.main()
