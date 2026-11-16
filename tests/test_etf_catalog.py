import unittest

from etf_catalog import ETF_ENTRY_REPLACEMENTS, etf_catalog, filter_etfs


class EtfCatalogTests(unittest.TestCase):
    def test_catalog_covers_all_eleven_gics_sectors(self) -> None:
        sectors = filter_etfs(etf_catalog(), "Global sectors")

        self.assertEqual(len(sectors), 11)
        self.assertEqual(len({row["Category"] for row in sectors}), 11)
        self.assertTrue(all(row["Taxonomy"] == "GICS sector" for row in sectors))

    def test_catalog_has_broad_country_coverage(self) -> None:
        countries = filter_etfs(etf_catalog(), "Country markets")

        self.assertGreaterEqual(len(countries), 85)
        self.assertTrue(
            {"Americas", "Europe", "Middle East & Africa", "Asia-Pacific"}.issubset(
                {row["Region"] for row in countries}
            )
        )
        symbols = [row["Symbol"] for row in countries if row["Symbol"]]
        self.assertEqual(len(set(symbols)), len(symbols))
        self.assertGreaterEqual(
            len(
                [
                    row
                    for row in countries
                    if row["Market group"] == "Frontier"
                ]
            ),
            25,
        )

    def test_bulgaria_remains_standalone_until_2027(self) -> None:
        bulgaria = next(
            row
            for row in filter_etfs(etf_catalog(), "Country markets")
            if row["Country"] == "Bulgaria"
        )

        self.assertEqual(bulgaria["Market group"], "Standalone")

    def test_filter_etfs_combines_market_group_and_region(self) -> None:
        rows = filter_etfs(
            etf_catalog(),
            "Country markets",
            market_group="Developed",
            region="Europe",
        )

        self.assertTrue(rows)
        self.assertTrue(
            all(
                row["Market group"] == "Developed" and row["Region"] == "Europe"
                for row in rows
            )
        )

    def test_industry_exposures_link_to_gics_parent_sectors(self) -> None:
        rows = filter_etfs(
            etf_catalog(),
            "Industry exposures",
            parent_sector="Information Technology",
        )

        self.assertGreaterEqual(len(rows), 3)
        self.assertEqual(
            {"Semiconductors", "Software", "Cybersecurity"},
            {row["Category"] for row in rows},
        )
        self.assertTrue(
            all(row["Parent sector"] == "Information Technology" for row in rows)
        )

    def test_regional_markets_include_africa_and_latin_america(self) -> None:
        rows = filter_etfs(etf_catalog(), "Regional markets")

        self.assertEqual(
            {"AFK", "ILF", "FLLA", "FLN"},
            {row["Symbol"] for row in rows},
        )
        self.assertEqual(
            {"Africa", "Latin America"},
            {row["Region"] for row in rows},
        )
        self.assertEqual(len({row["Entry ID"] for row in rows}), len(rows))

    def test_thematic_catalog_has_at_least_fifty_funds(self) -> None:
        rows = filter_etfs(etf_catalog(), "Thematic ETFs")

        self.assertGreaterEqual(len(rows), 50)
        self.assertGreaterEqual(len({row["Category"] for row in rows}), 15)
        self.assertGreaterEqual(len({row["Category"] for row in rows}), 25)
        self.assertEqual(
            len({(row["Category"], row["Market group"]) for row in rows}),
            len(rows),
        )
        self.assertEqual(
            {row["Symbol"] for row in rows if row["Category"] == "Cybersecurity"},
            {"CIBR"},
        )
        self.assertTrue(
            {
                "Internet of Things",
                "Quantum computing",
                "Uranium supply chain",
                "Sports betting and iGaming",
                "Pet care",
                "Global shipping",
            }.issubset({row["Market group"] for row in rows})
        )
        self.assertEqual(len({row["Entry ID"] for row in rows}), len(rows))

    def test_commodity_catalog_covers_major_groups_and_unique_funds(self) -> None:
        rows = filter_etfs(etf_catalog(), "Commodity ETFs")

        self.assertGreaterEqual(len(rows), 20)
        self.assertTrue(
            {
                "Broad commodities",
                "Energy",
                "Precious metals",
                "Industrial metals",
                "Agriculture",
            }.issubset({row["Category"] for row in rows})
        )
        self.assertEqual(len({row["Symbol"] for row in rows}), len(rows))
        self.assertTrue(
            {"PDBC", "USO", "GLD", "CPER", "DBA", "COFF.L"}.issubset(
                {row["Symbol"] for row in rows}
            )
        )

    def test_healthtech_uses_current_heal_listing_and_discloses_the_mandate_change(self) -> None:
        rows = filter_etfs(etf_catalog(), "Thematic ETFs")
        self.assertNotIn("EDOC", {row["Symbol"] for row in etf_catalog()})
        heal = next(row for row in rows if row["Symbol"] == "HEAL")
        self.assertEqual(heal["Fund"], "Global X HealthTech ETF")
        self.assertEqual(heal["Market group"], "Digital health and AI-enabled care")
        self.assertIn("2025-04-01", heal["ResearchNotes"])
        self.assertIn("former", heal["ResearchNotes"])
        self.assertEqual(
            heal["ResearchSource"], "https://www.globalxetfs.com/articles/why-healthtech-why-heal",
        )
        self.assertEqual(
            ETF_ENTRY_REPLACEMENTS["Thematic ETFs|Aging & Health Innovation|EDOC"],
            heal["Entry ID"],
        )

    def test_bwet_is_a_unique_freight_futures_entry_not_a_shipping_equity_proxy(self) -> None:
        rows = etf_catalog()
        matches = [row for row in rows if row["Symbol"] == "BWET"]
        self.assertEqual(len(matches), 1)
        bwet = matches[0]
        self.assertEqual(bwet["Universe"], "Commodity ETFs")
        self.assertEqual(bwet["Category"], "Freight")
        self.assertEqual(bwet["Market group"], "Tanker freight futures")
        self.assertEqual(bwet["Fund"], "Breakwave Tanker Shipping ETF")
        self.assertEqual(bwet["Entry ID"], "Commodity ETFs|Freight|BWET")
        self.assertEqual(bwet["Taxonomy"], "Commodity exchange-traded exposure")
        self.assertIn("not a portfolio of shipping-company shares", bwet["ResearchNotes"])
        self.assertIn("volatile", bwet["ResearchNotes"])
        self.assertEqual(bwet["ResearchSource"], "https://amplifyetfs.com/bwet/")
        self.assertIn("BWET", {row["Symbol"] for row in filter_etfs(rows, "Commodity ETFs")})
        self.assertEqual(next(row for row in rows if row["Symbol"] == "BOAT")["Universe"], "Thematic ETFs")

    def test_colombia_uses_active_successor_ticker(self) -> None:
        colombia = next(
            row
            for row in filter_etfs(etf_catalog(), "Country markets")
            if row["Country"] == "Colombia"
        )

        self.assertEqual(colombia["Symbol"], "COLO")

    def test_united_states_uses_total_market_proxy(self) -> None:
        united_states = next(
            row
            for row in filter_etfs(etf_catalog(), "Country markets")
            if row["Country"] == "United States"
        )

        self.assertEqual(united_states["Symbol"], "ITOT")

    def test_full_gics_hierarchy_has_official_level_counts(self) -> None:
        rows = filter_etfs(etf_catalog(), "Full GICS hierarchy")

        self.assertEqual(len(rows), 163)
        self.assertEqual(len({row["Parent sector"] for row in rows}), 11)
        self.assertEqual(len({row["Industry group"] for row in rows}), 25)
        self.assertEqual(len({row["Industry"] for row in rows}), 74)
        self.assertTrue(any(row["Symbol"] is None for row in rows))

    def test_full_gics_hierarchy_filters_to_subindustries(self) -> None:
        rows = filter_etfs(
            etf_catalog(),
            "Full GICS hierarchy",
            parent_sector="Information Technology",
            industry_group="Software & Services",
            industry="Software",
        )

        self.assertEqual(
            {"Application Software", "Systems Software"},
            {row["Sub-industry"] for row in rows},
        )


if __name__ == "__main__":
    unittest.main()
