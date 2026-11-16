import copy
from pathlib import Path
import unittest

import pandas as pd
from pandas.testing import assert_frame_equal

from income_strategy import (
    INCOME_EVIDENCE_FIELDS,
    build_income_candidates,
    filter_income_candidates,
)


def infrastructure(symbol="CIG", *, name=None, region="Latin America", access="Supported venue"):
    return {
        "Symbol": symbol, "Name": name or f"Network {symbol}", "Region": region,
        "Type": "Electricity network", "MarketStructure": "Regulated network",
        "Source": "https://example.com/infrastructure",
        "ListingMarket": "Reviewed exchange", "AccessStatus": access,
        "AccessNote": "Check account permissions.",
        "AccessSource": "https://example.com/access", "IBKRExchange": "NYSE",
    }


def infrastructure_result(catalog_row, **overrides):
    return {
        **catalog_row, "DividendYield": 5.0, "DividendCoverageRatio": 0.70,
        "CoverageBasis": "Earnings payout ratio", "DistanceToFiveYearHigh": -0.10,
        "Qualifies": True, "ExclusionReason": "",
        "InfrastructurePriceDate": "2026-09-11", "InfrastructureCurrency": "USD",
        **overrides,
    }


def adr(symbol="CIG", *, ticker=None, name=None, country="Brazil"):
    return {
        "Symbol": symbol, "Ticker": ticker or symbol, "Name": name or f"ADR {symbol}",
        "Country": country, "Overview": "ADR business overview",
        "ResearchNotes": "Dated research, not live evidence.",
        "ResearchSource": "https://example.com/adr",
    }


def adr_result(symbol="CIG", yield_percent=6.0, **overrides):
    return {
        "Symbol": symbol, "Price": 50.0, "TTMCash": 3.0, "YieldPercent": yield_percent,
        "PriceDate": "2026-09-14", "WindowStart": "2025-09-14",
        "DividendCount": 4, "LastExDate": "2026-06-10",
        "FetchedAt": "2026-09-15T20:00:00+00:00",
        "LiveSource": "https://example.com/live", **overrides,
    }


def build(infra=(), infra_rows=(), infra_errors=(), adrs=(), adr_rows=(), adr_errors=()):
    return build_income_candidates(
        list(infra), list(infra_rows), list(infra_errors),
        pd.DataFrame(list(adrs)), list(adr_rows), list(adr_errors),
    )


class IncomeCompositionTests(unittest.TestCase):
    def test_overlap_retains_separate_yields_details_and_catalog_authority(self):
        catalog = infrastructure()
        data = infrastructure_result(
            catalog, Value="infrastructure value", Source="wrong provider source",
            Name="wrong provider name",
        )
        trailing = adr_result(Value="ADR must not overwrite", Name="provider ADR name")
        row = build([catalog], [data], adrs=[adr()], adr_rows=[trailing]).iloc[0]
        self.assertEqual(row["IncomeStrategies"], "Infrastructure + ADR")
        self.assertTrue(row["InfrastructureMember"])
        self.assertTrue(row["ADRMember"])
        self.assertEqual(row["InfrastructureStatus"], "Pass")
        self.assertEqual(row["ADRStatus"], "Available")
        self.assertEqual(row["InfrastructureYieldPercent"], 5.0)
        self.assertEqual(row["ADRYieldPercent"], 6.0)
        self.assertEqual(row["Name"], catalog["Name"])
        self.assertEqual(row["Source"], catalog["Source"])
        self.assertEqual(row["Value"], "infrastructure value")
        self.assertEqual(row["InfrastructurePriceDate"], "2026-09-11")
        self.assertEqual(row["InfrastructureCurrency"], "USD")
        for field in ("DividendCoverageRatio", "CoverageBasis", "DistanceToFiveYearHigh",
                      "ExclusionReason"):
            self.assertEqual(row[field], data[field])
        for field in ("MarketStructure", "ListingMarket", "AccessStatus", "AccessNote",
                      "AccessSource", "IBKRExchange", "Region", "Type"):
            self.assertEqual(row[field], catalog[field])
        for field in ("Price", "TTMCash", "PriceDate", "WindowStart", "DividendCount",
                      "LastExDate", "FetchedAt", "LiveSource"):
            self.assertEqual(row[field], trailing[field])
        self.assertEqual(row["Country"], "Brazil")
        self.assertEqual(row["Overview"], adr()["Overview"])
        for field in ("Yield", "YieldPercent", "DividendYield", "Qualifies", "Rank"):
            self.assertNotIn(field, row.index)
        self.assertEqual(row["IncomeIncludedVia"], "")

    def test_canonical_symbols_preserve_listings_and_share_classes(self):
        infra = [
            infrastructure(" ng.l ", name="National Grid"),
            infrastructure("cig", name="Cemig"),
        ]
        adrs = [
            adr("NGG", name="National Grid"), adr(" CIG ", name="Cemig"),
            adr("pbr", name="Petrobras"), adr("pbr-a", ticker="PBR.A", name="Petrobras"),
            adr("AKO-B", ticker="AKO.B"),
        ]
        frame = build(infra, adrs=adrs).set_index("Symbol")
        self.assertEqual(list(frame.index), ["NG.L", "CIG", "NGG", "PBR", "PBR-A", "AKO-B"])
        self.assertEqual(frame.loc["PBR-A", "Ticker"], "PBR.A")
        self.assertEqual(frame.loc["AKO-B", "Ticker"], "AKO.B")
        self.assertEqual(frame.loc["CIG", "IncomeStrategies"], "Infrastructure + ADR")
        self.assertEqual(frame.loc["NG.L", "IncomeStrategies"], "Infrastructure")
        self.assertEqual(frame.loc["NGG", "IncomeStrategies"], "ADR")

    def test_provider_symbols_are_canonicalized_without_changing_catalog_identity(self):
        catalog = infrastructure()
        frame = build(
            [catalog], [infrastructure_result(catalog, Symbol=" cig ")],
            adrs=[adr()], adr_rows=[adr_result("cIg")],
        )
        self.assertEqual(frame["Symbol"].tolist(), ["CIG"])
        self.assertEqual(frame.iloc[0]["InfrastructureStatus"], "Pass")
        self.assertEqual(frame.iloc[0]["ADRStatus"], "Available")

    def test_real_catalogs_have_exact_six_overlaps_and_no_issuer_deduplication(self):
        from infrastructure_research import infrastructure_listing_details
        from strategy_catalog import INFRASTRUCTURE_COMPANIES

        infra = [
            {**item, **infrastructure_listing_details(item["Symbol"])}
            for item in INFRASTRUCTURE_COMPANIES
        ]
        catalog_path = Path(__file__).resolve().parents[1] / "data" / "adr_catalog.csv"
        adrs = pd.read_csv(catalog_path)
        result = build_income_candidates(infra, [], [], adrs, [], [])
        overlaps = result.loc[result["InfrastructureMember"] & result["ADRMember"], "Symbol"]
        self.assertEqual(set(overlaps), {"AMX", "ASR", "CIG", "OMAB", "PAC", "SBS"})
        self.assertEqual(len(result), len(infra) + len(adrs) - 6)
        self.assertEqual(result["Symbol"].nunique(), len(result))
        self.assertTrue({"NG.L", "NGG", "PBR", "PBR-A"}.issubset(result["Symbol"]))

    def test_missing_responses_are_unknown_not_zero_or_failed(self):
        row = build([infrastructure()], adrs=[adr()]).iloc[0]
        for leg in ("Infrastructure", "ADR"):
            self.assertEqual(row[f"{leg}Status"], "Unavailable")
            self.assertIn("Unknown", row[f"{leg}Reason"])
            self.assertTrue(pd.isna(row[f"{leg}YieldPercent"]))
        self.assertNotIn("Qualifies", row.index)
        self.assertTrue(pd.isna(row["InfrastructurePriceDate"]))
        self.assertTrue(filter_income_candidates(build([infrastructure()], adrs=[adr()])).empty)

    def test_errors_preserve_each_leg_without_erasing_other_success(self):
        catalog = infrastructure()
        frame = build(
            [catalog], infra_errors=[{"Symbol": " cig ", "Error": "No infrastructure history"}],
            adrs=[adr()], adr_rows=[adr_result()],
        )
        row = frame.iloc[0]
        self.assertEqual(row["InfrastructureReason"], "No infrastructure history")
        self.assertEqual(row["InfrastructureStatus"], "Unavailable")
        self.assertEqual(filter_income_candidates(frame).iloc[0]["IncomeIncludedVia"], "ADR")
        frame = build(
            [catalog], [infrastructure_result(catalog)], adrs=[adr()],
            adr_errors=[{"Symbol": "CIG", "Error": "ADR refresh failed"}],
        )
        self.assertEqual(frame.iloc[0]["ADRReason"], "ADR refresh failed")
        self.assertEqual(filter_income_candidates(frame).iloc[0]["IncomeIncludedVia"], "Infrastructure")
        self.assertTrue(pd.isna(frame.iloc[0]["ADRYieldPercent"]))

    def test_infrastructure_boundaries_match_original_rules(self):
        catalog = infrastructure()
        cases = (
            ({"DividendYield": 4.0}, "Fail", "exceed 4%"),
            ({"DividendYield": 4.000001}, "Pass", "Meets"),
            ({"DividendCoverageRatio": 0.80}, "Pass", "Meets"),
            ({"DividendCoverageRatio": 0.800001}, "Fail", "exceeds 80%"),
            ({"DistanceToFiveYearHigh": -0.05}, "Pass", "Meets"),
            ({"DistanceToFiveYearHigh": -0.049999}, "Fail", "less than 5%"),
            ({"DividendYield": 0.0}, "Fail", "exceed 4%"),
        )
        for metrics, status, reason in cases:
            with self.subTest(metrics=metrics):
                row = build([catalog], [infrastructure_result(catalog, **metrics)]).iloc[0]
                self.assertEqual(row["InfrastructureStatus"], status)
                self.assertIn(reason, row["InfrastructureReason"])

    def test_all_missing_or_nonfinite_infrastructure_metrics_are_unavailable(self):
        catalog = infrastructure()
        for metric in ("DividendYield", "DividendCoverageRatio", "DistanceToFiveYearHigh"):
            for value in (None, pd.NA, float("nan"), float("inf"), -float("inf"), "", "bad", True):
                with self.subTest(metric=metric, value=value):
                    result = infrastructure_result(catalog, **{metric: value})
                    frame = build([catalog], [result])
                    self.assertEqual(frame.iloc[0]["InfrastructureStatus"], "Unavailable")
                    self.assertIn("unavailable", frame.iloc[0]["InfrastructureReason"])
                    self.assertTrue(filter_income_candidates(frame).empty)
        data = infrastructure_result(catalog)
        for metric in ("DividendYield", "DividendCoverageRatio", "DistanceToFiveYearHigh"):
            del data[metric]
        self.assertEqual(build([catalog], [data]).iloc[0]["InfrastructureStatus"], "Unavailable")

    def test_unavailable_reason_retains_original_exclusion_evidence(self):
        catalog = infrastructure()
        data = infrastructure_result(
            catalog, DividendYield=None, Qualifies=False,
            ExclusionReason="Forward yield unavailable; Provider incomplete",
        )
        row = build([catalog], [data]).iloc[0]
        self.assertEqual(row["InfrastructureStatus"], "Unavailable")
        self.assertEqual(row["InfrastructureReason"], data["ExclusionReason"])
        self.assertNotIn("Qualifies", row.index)

    def test_unverified_venue_never_screens_even_with_passing_data(self):
        for access in ("Unverified venue", "", None):
            with self.subTest(access=access):
                catalog = infrastructure("UNKNOWN.XX", access=access)
                data = infrastructure_result(catalog, AccessStatus="Supported venue")
                frame = build([catalog], [data])
                self.assertEqual(frame.iloc[0]["InfrastructureStatus"], "Not screened")
                self.assertEqual(frame.iloc[0]["InfrastructureYieldPercent"], 5.0)
                self.assertTrue(filter_income_candidates(frame).empty)
                reviewed = filter_income_candidates(frame, show_excluded_infrastructure=True)
                self.assertEqual(reviewed.iloc[0]["IncomeIncludedVia"], "Infrastructure review only")

    def test_unverified_venue_error_retains_access_and_provider_disclosures(self):
        catalog = infrastructure("UNKNOWN.XX", access="Unverified venue")
        frame = build([catalog], infra_errors=[{"Symbol": "UNKNOWN.XX", "Error": "No data"}])
        self.assertEqual(frame.iloc[0]["InfrastructureStatus"], "Not screened")
        self.assertIn("No data", frame.iloc[0]["InfrastructureReason"])
        self.assertIn(catalog["AccessNote"], frame.iloc[0]["InfrastructureReason"])

    def test_restricted_venue_is_evaluated_with_disclosure(self):
        catalog = infrastructure("TEST.NS", access="Restricted venue")
        for yield_percent, status in ((5.0, "Pass"), (4.0, "Fail"), (None, "Unavailable")):
            with self.subTest(status=status):
                data = infrastructure_result(catalog, DividendYield=yield_percent)
                row = build([catalog], [data]).iloc[0]
                self.assertEqual(row["InfrastructureStatus"], status)
                self.assertIn("Restricted venue", row["InfrastructureReason"])
                self.assertIn(catalog["AccessNote"], row["InfrastructureReason"])

    def test_adr_zero_is_available_but_missing_invalid_or_nonfinite_yields_are_not(self):
        for value in (None, pd.NA, float("nan"), float("inf"), -float("inf"), -0.1, "bad", True):
            with self.subTest(value=value):
                frame = build(adrs=[adr()], adr_rows=[adr_result(yield_percent=value)])
                self.assertEqual(frame.iloc[0]["ADRStatus"], "Unavailable")
                self.assertTrue(filter_income_candidates(frame).empty)
        frame = build(adrs=[adr()], adr_rows=[adr_result(yield_percent=0.0, TTMCash=0.0)])
        self.assertEqual(frame.iloc[0]["ADRStatus"], "Available")
        self.assertEqual(len(filter_income_candidates(frame)), 1)
        self.assertTrue(filter_income_candidates(frame, minimum_adr_yield=0.000001).empty)
        data = adr_result()
        del data["YieldPercent"]
        self.assertEqual(build(adrs=[adr()], adr_rows=[data]).iloc[0]["ADRStatus"], "Unavailable")

    def test_empty_sides_have_stable_schema_and_absent_membership_status(self):
        empty = build()
        frames = (
            (build([infrastructure()]), "Infrastructure"),
            (build(adrs=[adr()]), "ADR"),
        )
        self.assertTrue(empty.empty)
        for frame, member in frames:
            self.assertEqual(frame.columns.tolist(), empty.columns.tolist())
            absent = "ADR" if member == "Infrastructure" else "Infrastructure"
            self.assertFalse(frame.iloc[0][f"{absent}Member"])
            self.assertEqual(frame.iloc[0][f"{absent}Status"], "Not in strategy")
            self.assertTrue(pd.isna(frame.iloc[0][f"{absent}YieldPercent"]))
        for field in ("InfrastructureMember", "ADRMember"):
            self.assertEqual(empty[field].dtype, bool)
        for field in ("InfrastructureYieldPercent", "ADRYieldPercent"):
            self.assertEqual(empty[field].dtype, float)
        filtered = filter_income_candidates(empty)
        self.assertTrue(filtered.empty)
        assert_frame_equal(filtered, empty)
        self.assertTrue(filter_income_candidates(pd.DataFrame()).empty)
        self.assertIsInstance(INCOME_EVIDENCE_FIELDS, frozenset)
        self.assertTrue(INCOME_EVIDENCE_FIELDS.issubset(empty.columns))
        self.assertTrue({
            "DividendCoverageRatio", "CoverageBasis", "DistanceToFiveYearHigh",
            "ExclusionReason", "Source", "AccessStatus",
        }.issubset(INCOME_EVIDENCE_FIELDS))
        for field in ("Qualifies", "YieldPercent", "DividendYield"):
            self.assertNotIn(field, empty.columns)
            self.assertNotIn(field, INCOME_EVIDENCE_FIELDS)

    def test_duplicates_are_rejected_in_each_catalog_rows_and_errors(self):
        infra = infrastructure()
        cases = (
            {"infra": [infra, {**infra, "Symbol": " cig "}]},
            {"adrs": [adr(), adr("cig")]},
            {"infra": [infra], "infra_rows": [infrastructure_result(infra)] * 2},
            {"infra": [infra], "infra_errors": [{"Symbol": "CIG", "Error": "bad"}] * 2},
            {"adrs": [adr()], "adr_rows": [adr_result(), adr_result("cig")]},
            {"adrs": [adr()], "adr_errors": [{"Symbol": "CIG", "Error": "bad"}] * 2},
            {"infra": [infra], "infra_rows": [infrastructure_result(infra)],
             "infra_errors": [{"Symbol": "CIG", "Error": "bad"}]},
            {"adrs": [adr()], "adr_rows": [adr_result()],
             "adr_errors": [{"Symbol": "CIG", "Error": "bad"}]},
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    build(**arguments)

    def test_outside_catalog_responses_are_rejected_even_if_in_other_strategy(self):
        cases = (
            {"infra_rows": [infrastructure_result(infrastructure())], "adrs": [adr()]},
            {"infra_errors": [{"Symbol": "CIG", "Error": "bad"}], "adrs": [adr()]},
            {"adr_rows": [adr_result()], "infra": [infrastructure()]},
            {"adr_errors": [{"Symbol": "CIG", "Error": "bad"}], "infra": [infrastructure()]},
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(ValueError, "outside catalog"):
                    build(**arguments)

    def test_missing_or_invalid_symbols_are_rejected(self):
        for value in (None, pd.NA, 7, "", "  "):
            for side in ("infra", "adrs"):
                with self.subTest(value=value, side=side):
                    with self.assertRaisesRegex(ValueError, "Symbol"):
                        build(**{side: [{"Symbol": value}]})
        for catalog in (pd.DataFrame([{"Name": "Missing symbol"}]), pd.DataFrame(index=[0])):
            with self.subTest(catalog=catalog):
                with self.assertRaisesRegex(ValueError, "Symbol"):
                    build_income_candidates([], [], [], catalog, [], [])

    def test_composition_does_not_mutate_inputs(self):
        infra = [infrastructure()]
        infra_rows = [infrastructure_result(infra[0])]
        adrs = pd.DataFrame([adr()])
        adr_rows = [adr_result()]
        saved = copy.deepcopy((infra, infra_rows, adr_rows))
        saved_catalog = adrs.copy(deep=True)
        result = build_income_candidates(infra, infra_rows, [], adrs, adr_rows, [])
        result.loc[0, "Name"] = "Changed"
        self.assertEqual((infra, infra_rows, adr_rows), saved)
        assert_frame_equal(adrs, saved_catalog)


class IncomeFilterTests(unittest.TestCase):
    def setUp(self):
        self.infra = [
            infrastructure("BOTH", name="Alpha", region="Europe"),
            infrastructure("INFRA", name="Beta", region="Europe"),
            infrastructure("FAIL", name="Gamma", region="Africa"),
            infrastructure("UNKNOWN", name="Delta", region="Africa"),
            infrastructure("UNVERIFIED.XX", name="Epsilon", region="Africa", access="Unverified venue"),
            infrastructure("REVIEW", name="Eta", region="Africa"),
        ]
        self.adrs = [
            adr("BOTH", country="UK"), adr("FAIL", country="Brazil"),
            adr("ADR", name="Zeta", country="Brazil"), adr("NOADR", country="UK"),
        ]
        rows = [
            infrastructure_result(self.infra[0]),
            infrastructure_result(self.infra[1], DividendYield=7.0),
            infrastructure_result(self.infra[2], DividendYield=3.0, Qualifies=False),
            infrastructure_result(self.infra[5], DividendYield=4.0, Qualifies=False),
        ]
        self.frame = build(
            self.infra, rows, adrs=self.adrs,
            adr_rows=[adr_result("BOTH", 1.0), adr_result("FAIL", 8.0), adr_result("ADR", 0.0)],
            adr_errors=[{"Symbol": "NOADR", "Error": "ADR history unavailable"}],
        )

    def selected(self, **options):
        return filter_income_candidates(self.frame, **options).set_index("Symbol")

    def test_default_union_is_or_not_intersection_and_exposes_active_legs(self):
        selected = self.selected()
        self.assertEqual(set(selected.index), {"BOTH", "INFRA", "FAIL", "ADR"})
        self.assertEqual(selected.loc["BOTH", "IncomeIncludedVia"], "Infrastructure + ADR")
        self.assertEqual(selected.loc["INFRA", "IncomeIncludedVia"], "Infrastructure")
        self.assertEqual(selected.loc["FAIL", "IncomeIncludedVia"], "ADR")
        self.assertEqual(selected.loc["FAIL", "InfrastructureStatus"], "Fail")
        self.assertEqual(selected.loc["ADR", "IncomeIncludedVia"], "ADR")

    def test_strategy_selectors_never_borrow_other_legs(self):
        self.assertEqual(set(self.selected(strategy="Infrastructure").index), {"BOTH", "INFRA"})
        adrs = self.selected(strategy="ADRs")
        self.assertEqual(set(adrs.index), {"BOTH", "FAIL", "ADR"})
        self.assertTrue(adrs["IncomeIncludedVia"].eq("ADR").all())
        self.assertNotIn("FAIL", self.selected(strategy="Infrastructure").index)
        self.assertNotIn("NOADR", self.selected(strategy="ADRs", show_excluded_infrastructure=True).index)

    def test_country_and_region_apply_only_to_their_own_leg(self):
        selected = self.selected(infrastructure_region="Africa", adr_country="UK")
        self.assertEqual(set(selected.index), {"BOTH"})
        self.assertEqual(selected.loc["BOTH", "IncomeIncludedVia"], "ADR")
        selected = self.selected(adr_country="Brazil")
        self.assertEqual(set(selected.index), {"BOTH", "INFRA", "FAIL", "ADR"})
        self.assertEqual(selected.loc["BOTH", "IncomeIncludedVia"], "Infrastructure")
        selected = self.selected(infrastructure_region="Europe")
        self.assertIn("FAIL", selected.index)
        self.assertIn("ADR", selected.index)
        self.assertEqual(set(self.selected(strategy="Infrastructure", adr_country="Brazil").index),
                         {"BOTH", "INFRA"})
        self.assertEqual(set(self.selected(strategy="ADRs", infrastructure_region="Africa").index),
                         {"BOTH", "FAIL", "ADR"})

    def test_adr_minimum_boundary_is_inclusive_and_cannot_remove_infrastructure(self):
        selected = self.selected(minimum_adr_yield=8.0)
        self.assertEqual(set(selected.index), {"BOTH", "INFRA", "FAIL"})
        self.assertEqual(selected.loc["BOTH", "IncomeIncludedVia"], "Infrastructure")
        self.assertEqual(set(self.selected(minimum_adr_yield=8.000001).index), {"BOTH", "INFRA"})
        selected = self.selected(strategy="Infrastructure", minimum_adr_yield=1000.0)
        self.assertEqual(set(selected.index), {"BOTH", "INFRA"})
        self.assertTrue(self.selected(strategy="ADRs", minimum_adr_yield=8.000001).empty)

    def test_review_rows_include_all_exclusion_states_but_do_not_claim_pass(self):
        selected = self.selected(show_excluded_infrastructure=True)
        self.assertEqual(set(selected.index),
                         {"BOTH", "INFRA", "FAIL", "UNKNOWN", "UNVERIFIED.XX", "REVIEW", "ADR"})
        for symbol in ("UNKNOWN", "UNVERIFIED.XX", "REVIEW"):
            self.assertEqual(selected.loc[symbol, "IncomeIncludedVia"], "Infrastructure review only")
        self.assertEqual(selected.loc["FAIL", "IncomeIncludedVia"], "ADR")
        self.assertEqual(selected.loc["UNKNOWN", "InfrastructureStatus"], "Unavailable")
        self.assertTrue(pd.isna(selected.loc["UNKNOWN", "InfrastructureYieldPercent"]))
        self.assertEqual(selected.loc["UNVERIFIED.XX", "InfrastructureStatus"], "Not screened")
        self.assertEqual(selected.loc["REVIEW", "InfrastructureStatus"], "Fail")
        selected = self.selected(strategy="Infrastructure", show_excluded_infrastructure=True)
        self.assertEqual(selected.loc["FAIL", "IncomeIncludedVia"], "Infrastructure review only")
        self.assertNotIn("ADR", selected.index)

    def test_review_still_obeys_only_active_infrastructure_region(self):
        selected = self.selected(
            infrastructure_region="Europe", adr_country="Brazil",
            minimum_adr_yield=9.0, show_excluded_infrastructure=True,
        )
        self.assertEqual(set(selected.index), {"BOTH", "INFRA"})
        selected = self.selected(
            infrastructure_region="Africa", adr_country="UK",
            minimum_adr_yield=9.0, show_excluded_infrastructure=True,
        )
        self.assertEqual(set(selected.index), {"FAIL", "UNKNOWN", "UNVERIFIED.XX", "REVIEW"})
        self.assertTrue(selected["IncomeIncludedVia"].eq("Infrastructure review only").all())

    def test_retained_selectors_on_inactive_or_missing_legs_do_not_block_other_leg(self):
        selected = self.selected(strategy="Infrastructure", adr_country="Previously selected country")
        self.assertEqual(set(selected.index), {"BOTH", "INFRA"})
        selected = self.selected(strategy="ADRs", infrastructure_region="Previously selected region")
        self.assertEqual(set(selected.index), {"BOTH", "FAIL", "ADR"})
        infra = infrastructure("NETWORK", region="Europe")
        infrastructure_only = build([infra], [infrastructure_result(infra)])
        selected = filter_income_candidates(
            infrastructure_only, adr_country="Previously selected country",
        )
        self.assertEqual(selected["Symbol"].tolist(), ["NETWORK"])
        adr_only = build(adrs=[adr()], adr_rows=[adr_result()])
        selected = filter_income_candidates(
            adr_only, infrastructure_region="Previously selected region",
        )
        self.assertEqual(selected["Symbol"].tolist(), ["CIG"])
        selected = filter_income_candidates(
            build(), infrastructure_region="Previously selected region",
            adr_country="Previously selected country",
        )
        assert_frame_equal(selected, build())

    def test_selected_leg_labels_are_recomputed_on_every_filter_call(self):
        selected = filter_income_candidates(self.frame)
        selected = filter_income_candidates(selected, strategy="ADRs", minimum_adr_yield=1.0)
        self.assertTrue(selected["IncomeIncludedVia"].eq("ADR").all())
        self.assertEqual(set(selected["Symbol"]), {"BOTH", "FAIL"})

    def test_sorting_is_stable_with_missing_yields_last_and_ticker_symbol_ties(self):
        catalogs = [
            adr("ZZ", ticker="TIE", name="same"), adr("AA", ticker="TIE", name="Same"),
            adr("BB", name="alpha"), adr("CC", name="zeta"),
        ]
        frame = build(
            [infrastructure("II", name="same")], [infrastructure_result(infrastructure("II"))],
            adrs=catalogs,
            adr_rows=[adr_result("ZZ", 4.0), adr_result("AA", 4.0),
                      adr_result("BB", 4.0), adr_result("CC", 9.0)],
        )
        for _ in range(2):
            company = filter_income_candidates(frame)
            self.assertEqual(company["Symbol"].tolist(), ["BB", "II", "AA", "ZZ", "CC"])
            trailing = filter_income_candidates(frame, sort_by="ADR TTM yield")
            self.assertEqual(trailing["Symbol"].tolist(), ["CC", "BB", "AA", "ZZ", "II"])
            forward = filter_income_candidates(frame, sort_by="Infrastructure forward yield")
            self.assertEqual(forward["Symbol"].tolist(), ["II", "BB", "CC", "AA", "ZZ"])
            frame = frame.iloc[::-1].copy()

    def test_numeric_yield_sort_is_not_lexical_and_forward_ties_use_ticker(self):
        catalogs = [infrastructure("Z"), infrastructure("A"), infrastructure("B")]
        frame = build(catalogs, [
            infrastructure_result(catalogs[0], DividendYield="9"),
            infrastructure_result(catalogs[1], DividendYield="9"),
            infrastructure_result(catalogs[2], DividendYield="10"),
        ])
        sorted_frame = filter_income_candidates(frame, sort_by="Infrastructure forward yield")
        self.assertEqual(sorted_frame["Symbol"].tolist(), ["B", "A", "Z"])

    def test_nonfinite_or_missing_yields_cannot_be_admitted_by_forged_pass_status(self):
        for field, strategy in (("InfrastructureYieldPercent", "Infrastructure"),
                                ("ADRYieldPercent", "ADRs")):
            for value in (None, float("nan"), float("inf"), -float("inf"), pd.NA, True):
                with self.subTest(field=field, value=value):
                    frame = self.frame.copy()
                    frame[field] = pd.Series([value] * len(frame), dtype=object)
                    self.assertTrue(filter_income_candidates(frame, strategy=strategy).empty)

    def test_limit_is_applied_after_union_filter_and_sort(self):
        frame = filter_income_candidates(self.frame, sort_by="ADR TTM yield", limit=2)
        self.assertEqual(frame["Symbol"].tolist(), ["FAIL", "BOTH"])
        self.assertEqual(frame["Symbol"].nunique(), 2)
        frame = filter_income_candidates(
            self.frame, strategy="Infrastructure", sort_by="Infrastructure forward yield", limit=1,
        )
        self.assertEqual(frame["Symbol"].tolist(), ["INFRA"])
        self.assertEqual(len(filter_income_candidates(self.frame, limit=100)), 4)

    def test_no_implicit_result_limit(self):
        catalogs = [adr(f"A{index:03d}") for index in range(150)]
        rows = [adr_result(item["Symbol"]) for item in catalogs]
        self.assertEqual(len(filter_income_candidates(build(adrs=catalogs, adr_rows=rows))), 150)

    def test_invalid_options_raise_explicit_value_errors_even_on_empty_frame(self):
        cases = (
            {"strategy": "ADR"}, {"strategy": None}, {"strategy": []},
            {"sort_by": "Yield"}, {"sort_by": None}, {"sort_by": []},
            {"infrastructure_region": None}, {"adr_country": []},
            {"infrastructure_region": ""}, {"adr_country": "   "},
            {"minimum_adr_yield": -0.01}, {"minimum_adr_yield": float("nan")},
            {"minimum_adr_yield": float("inf")}, {"minimum_adr_yield": -float("inf")},
            {"minimum_adr_yield": None}, {"minimum_adr_yield": "bad"}, {"minimum_adr_yield": True},
            {"limit": 0}, {"limit": -1}, {"limit": 1.0}, {"limit": True},
            {"limit": "10"}, {"limit": float("nan")}, {"limit": float("inf")},
            {"show_excluded_infrastructure": "False"}, {"show_excluded_infrastructure": 1},
        )
        for frame in (self.frame, build()):
            for options in cases:
                with self.subTest(options=options, empty=frame.empty):
                    with self.assertRaises(ValueError):
                        filter_income_candidates(frame, **options)

    def test_unsupported_active_geographic_options_raise_value_errors(self):
        for options in ({"infrastructure_region": "Atlantis"}, {"adr_country": "Atlantis"}):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    filter_income_candidates(self.frame, **options)

    def test_filter_rejects_duplicate_symbols_and_does_not_silently_drop_evidence(self):
        duplicate = pd.concat([self.frame, self.frame.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "unique"):
            filter_income_candidates(duplicate)

    def test_filter_does_not_mutate_input_or_leak_temporary_sort_fields(self):
        saved = self.frame.copy(deep=True)
        result = filter_income_candidates(
            self.frame, minimum_adr_yield=8.0, show_excluded_infrastructure=True,
            sort_by="ADR TTM yield",
        )
        assert_frame_equal(self.frame, saved)
        self.assertEqual(result.columns.tolist(), self.frame.columns.tolist())
        result.loc[0, "Name"] = "Changed"
        assert_frame_equal(self.frame, saved)

    def test_extra_infrastructure_evidence_and_order_survive_filtering(self):
        catalog = infrastructure()
        frame = build([catalog], [infrastructure_result(catalog, Value="original", ExtraEvidence="retained")])
        result = filter_income_candidates(frame)
        self.assertEqual(result.columns.tolist(), frame.columns.tolist())
        self.assertEqual(result.iloc[0]["Value"], "original")
        self.assertEqual(result.iloc[0]["ExtraEvidence"], "retained")


if __name__ == "__main__":
    unittest.main()
