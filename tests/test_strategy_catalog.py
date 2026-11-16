import unittest

from strategy_catalog import (
    FASHION_COMPANIES,
    INFRASTRUCTURE_COMPANIES,
    STAR_PRINCIPLE_COMPANIES,
    STAR_PRINCIPLE_NEAR_MISSES,
    STAR_PRINCIPLE_RESEARCH_REVIEWS,
    star_principle_catalog,
)


class StrategyCatalogTests(unittest.TestCase):
    def test_infrastructure_catalog_covers_regions_and_asset_types(self) -> None:
        self.assertEqual(
            {company["Region"] for company in INFRASTRUCTURE_COMPANIES},
            {
                "Canada",
                "Developed Asia-Pacific",
                "Emerging Asia",
                "Emerging Europe",
                "Europe",
                "Latin America",
                "Middle East and Africa",
                "US",
            },
        )
        self.assertGreaterEqual(len(INFRASTRUCTURE_COMPANIES), 100)
        symbols = [company["Symbol"] for company in INFRASTRUCTURE_COMPANIES]
        self.assertEqual(len(symbols), len(set(symbols)))
        self.assertIn("CIG", symbols)
        types = {company["Type"] for company in INFRASTRUCTURE_COMPANIES}
        self.assertIn("Airports", types)
        self.assertIn("Regulated water", types)
        self.assertTrue(
            all(company["Source"].startswith("https://") for company in INFRASTRUCTURE_COMPANIES)
        )

    def test_infrastructure_includes_african_and_baltic_exposure_without_duplicate_lines(self):
        companies = {company["Symbol"]: company for company in INFRASTRUCTURE_COMPANIES}
        for symbol in ("TKG.JO", "VOD.JO", "MTN.JO", "HTWS.L", "AAF.L", "GND.JO"):
            self.assertEqual(companies[symbol]["Region"], "Middle East and Africa")
        for symbol in ("CEZ.PR", "IGN1L.VS", "TSM1T.TL", "TVE1T.TL", "VEON"):
            self.assertIn(symbol, companies)
        self.assertEqual(companies["ENB"]["Region"], "Canada")
        self.assertNotIn("ASURB.MX", companies)
        self.assertNotIn("GAPB.MX", companies)
        self.assertNotIn("IHS", companies)

    def test_fashion_catalog_has_unique_symbols_and_both_regions(self) -> None:
        symbols = [company["Symbol"] for company in FASHION_COMPANIES]
        self.assertEqual(len(symbols), len(set(symbols)))
        self.assertEqual(
            {company["Region"] for company in FASHION_COMPANIES},
            {"Europe", "US"},
        )
        self.assertTrue(all(company["SearchTerm"] for company in FASHION_COMPANIES))

    def test_fashion_catalog_includes_requested_apparel_retail_stocks(self) -> None:
        requested_symbols = {
            "AEO", "AKA", "ANF", "BKE", "BOOT", "BRIA", "BURL", "CAL",
            "CATO", "CRI", "CTRN", "CURV", "DBGI", "DLTH", "DXLG",
            "GAP", "GCO", "JEM", "JILL", "LE",
            "LULU", "LVLU", "MYSZ", "REF", "RENT", "ROST", "SFIX",
            "SHOE", "TJX", "TLYS", "URBN", "VSXY", "ZUMZ",
        }
        companies = {company["Symbol"]: company for company in FASHION_COMPANIES}
        self.assertTrue(requested_symbols.issubset(companies))
        for symbol in requested_symbols:
            with self.subTest(symbol=symbol):
                self.assertEqual(companies[symbol]["Region"], "US")
                self.assertTrue(companies[symbol]["Name"])
                self.assertTrue(companies[symbol]["SearchTerm"])
        self.assertNotIn("VSCO", companies)
        self.assertNotIn("SCVL", companies)

    def test_fashion_catalog_includes_requested_footwear_accessory_stocks(self) -> None:
        requested_symbols = {
            "BIRK", "CROX", "DBI", "DECK", "FMFC", "FOSL", "NKE",
            "ONON", "RCKY", "SHOO", "VRA", "WEYS", "WWW",
        }
        companies = {company["Symbol"]: company for company in FASHION_COMPANIES}
        self.assertTrue(requested_symbols.issubset(companies))
        for symbol in requested_symbols:
            with self.subTest(symbol=symbol):
                self.assertTrue(companies[symbol]["Name"])
                self.assertTrue(companies[symbol]["SearchTerm"])

    def test_star_catalog_never_promotes_incomplete_evidence(self) -> None:
        for company in STAR_PRINCIPLE_COMPANIES:
            self.assertGreaterEqual(company["GrowthRate"], 0.10)
            self.assertTrue(company["LeadershipEvidence"])
            self.assertTrue(company["GrowthSource"].startswith("https://"))
        self.assertEqual(STAR_PRINCIPLE_NEAR_MISSES[0]["Symbol"], "ASML.AS")
        self.assertGreaterEqual(len(STAR_PRINCIPLE_NEAR_MISSES), 9)
        symbols = [company["Symbol"] for company in STAR_PRINCIPLE_NEAR_MISSES]
        self.assertEqual(len(symbols), len(set(symbols)))
        self.assertIn(
            "No exact",
            STAR_PRINCIPLE_NEAR_MISSES[0]["MissingEvidence"],
        )

    def test_researched_star_records_have_sources_and_explicit_conclusions(self) -> None:
        rows = star_principle_catalog()
        symbols = [row["Symbol"] for row in rows]
        self.assertEqual(len(symbols), len(set(symbols)))
        self.assertEqual(
            {row["Symbol"] for row in STAR_PRINCIPLE_RESEARCH_REVIEWS},
            {"ANET", "CDNS", "SNPS", "FTNT", "FICO", "VRSK",
             "ASM.AS", "BESI.AS", "DSY.PA", "HLMA.L"},
        )
        for row in STAR_PRINCIPLE_RESEARCH_REVIEWS:
            with self.subTest(symbol=row["Symbol"]):
                self.assertIn(row["ReviewStatus"], {
                    "Evidence-qualified", "Near miss", "Does not meet", "Insufficient evidence",
                })
                self.assertEqual(row["EvidenceAsOf"], "2026-09-06")
                self.assertTrue(row["LeadershipSource"].startswith("https://"))
                self.assertTrue(row["GrowthEvidence"])
                if row["GrowthRate"] is not None:
                    self.assertTrue(row["GrowthSource"].startswith("https://"))
                    self.assertTrue(row["GrowthPeriod"])
                if row["ReviewStatus"] == "Evidence-qualified":
                    self.assertGreaterEqual(row["GrowthRate"], 0.10)
                    self.assertTrue(row["LeadershipEvidence"])
                else:
                    self.assertTrue(row["MissingEvidence"])


if __name__ == "__main__":
    unittest.main()
