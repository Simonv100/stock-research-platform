from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


ETF_ENTRY_REPLACEMENTS = {
    "Thematic ETFs|Aging & Health Innovation|EDOC": "Thematic ETFs|Aging & Health Innovation|HEAL",
}

ETF_RESEARCH_NOTES = {
    "BWET": {
        "ResearchNotes": (
            "BWET (Breakwave Tanker Shipping ETF) provides unlevered exposure to "
            "tanker freight futures for transporting crude oil. It is a futures-based "
            "commodity pool, not a portfolio of shipping-company shares like BOAT "
            "or direct crude oil price exposure. Freight futures can be highly volatile; "
            "roll effects and expenses can make returns differ from spot freight rates."
        ),
        "ResearchSource": "https://amplifyetfs.com/bwet/",
    },
    "HEAL": {
        "ResearchNotes": (
            "EDOC became HEAL (Global X HealthTech ETF) on April 1, 2025, with a "
            "new benchmark and broader healthtech mandate. Price history before "
            "2025-04-01 reflects the former telemedicine and digital-health strategy, "
            "not the current strategy."
        ),
        "ResearchSource": "https://www.globalxetfs.com/articles/why-healthtech-why-heal",
    },
}


GICS_SECTOR_ETFS = [
    ("Communication Services", "IXP", "iShares Global Comm Services ETF"),
    ("Consumer Discretionary", "RXI", "iShares Global Consumer Discretionary ETF"),
    ("Consumer Staples", "KXI", "iShares Global Consumer Staples ETF"),
    ("Energy", "IXC", "iShares Global Energy ETF"),
    ("Financials", "IXG", "iShares Global Financials ETF"),
    ("Health Care", "IXJ", "iShares Global Healthcare ETF"),
    ("Industrials", "EXI", "iShares Global Industrials ETF"),
    ("Information Technology", "IXN", "iShares Global Tech ETF"),
    ("Materials", "MXI", "iShares Global Materials ETF"),
    ("Real Estate", "REET", "iShares Global REIT ETF"),
    ("Utilities", "JXI", "iShares Global Utilities ETF"),
]

GICS_INDUSTRY_ETFS = [
    ("Communication Services", "Telecommunications", "IYZ", "iShares U.S. Telecommunications ETF"),
    ("Communication Services", "Media", "PBS", "Invesco Next Gen Media and Gaming ETF"),
    ("Communication Services", "Social media", "SOCL", "Global X Social Media ETF"),
    ("Consumer Discretionary", "Automobiles", "CARZ", "First Trust S-Network Future Vehicles & Technology ETF"),
    ("Consumer Discretionary", "Homebuilding", "ITB", "iShares U.S. Home Construction ETF"),
    ("Consumer Discretionary", "Retail", "XRT", "SPDR S&P Retail ETF"),
    ("Consumer Discretionary", "Leisure and entertainment", "PEJ", "Invesco Leisure and Entertainment ETF"),
    ("Consumer Staples", "Food and beverage", "PBJ", "Invesco Food & Beverage ETF"),
    ("Consumer Staples", "Agribusiness", "MOO", "VanEck Agribusiness ETF"),
    ("Energy", "Oil and gas exploration & production", "XOP", "SPDR S&P Oil & Gas Exploration & Production ETF"),
    ("Energy", "Oil services", "OIH", "VanEck Oil Services ETF"),
    ("Energy", "Midstream energy", "AMLP", "Alerian MLP ETF"),
    ("Financials", "Banks", "KBE", "SPDR S&P Bank ETF"),
    ("Financials", "Regional banks", "KRE", "SPDR S&P Regional Banking ETF"),
    ("Financials", "Insurance", "KIE", "SPDR S&P Insurance ETF"),
    ("Financials", "Capital markets", "IAI", "iShares U.S. Broker-Dealers & Securities Exchanges ETF"),
    ("Health Care", "Biotechnology", "IBB", "iShares Biotechnology ETF"),
    ("Health Care", "Pharmaceuticals", "IHE", "iShares U.S. Pharmaceuticals ETF"),
    ("Health Care", "Medical devices", "IHI", "iShares U.S. Medical Devices ETF"),
    ("Health Care", "Health care providers", "IHF", "iShares U.S. Healthcare Providers ETF"),
    ("Industrials", "Aerospace and defense", "ITA", "iShares U.S. Aerospace & Defense ETF"),
    ("Industrials", "Transportation", "IYT", "iShares U.S. Transportation ETF"),
    ("Industrials", "Infrastructure", "PAVE", "Global X U.S. Infrastructure Development ETF"),
    ("Information Technology", "Semiconductors", "SOXX", "iShares Semiconductor ETF"),
    ("Information Technology", "Software", "IGV", "iShares Expanded Tech-Software Sector ETF"),
    ("Information Technology", "Cybersecurity", "CIBR", "First Trust Nasdaq Cybersecurity ETF"),
    ("Materials", "Metals and mining", "XME", "SPDR S&P Metals & Mining ETF"),
    ("Materials", "Gold mining", "GDX", "VanEck Gold Miners ETF"),
    ("Materials", "Copper mining", "COPX", "Global X Copper Miners ETF"),
    ("Materials", "Timber and forestry", "WOOD", "iShares Global Timber & Forestry ETF"),
    ("Real Estate", "Equity REITs", "VNQ", "Vanguard Real Estate ETF"),
    ("Real Estate", "Residential real estate", "REZ", "iShares Residential and Multisector Real Estate ETF"),
    ("Real Estate", "Mortgage REITs", "REM", "iShares Mortgage Real Estate ETF"),
    ("Utilities", "Water", "PHO", "Invesco Water Resources ETF"),
    ("Utilities", "Clean and renewable power", "ICLN", "iShares Global Clean Energy ETF"),
]

REGIONAL_MARKET_ETFS = [
    (
        "Africa",
        "Broad regional",
        "AFK",
        "VanEck Africa Index ETF",
        "Pan-Africa exposure, including companies listed in or deriving substantial revenue from Africa",
    ),
    (
        "Latin America",
        "Large-cap",
        "ILF",
        "iShares Latin America 40 ETF",
        "Forty large Latin American companies; includes Mexico as well as South America",
    ),
    (
        "Latin America",
        "Broad regional",
        "FLLA",
        "Franklin FTSE Latin America ETF",
        "Broad Latin American equity exposure; includes Mexico as well as South America",
    ),
    (
        "Latin America",
        "Factor tilted",
        "FLN",
        "First Trust Latin America AlphaDEX Fund",
        "Rules-based factor exposure to Latin America; includes Mexico as well as South America",
    ),
]

THEMATIC_ETFS = [
    ("Cybersecurity", "Cybersecurity", "CIBR", "First Trust NASDAQ Cybersecurity ETF", "Global"),
    ("AI & Robotics", "AI platforms", "AIQ", "Global X Artificial Intelligence & Technology ETF", "Global"),
    ("AI & Robotics", "Robotics and automation", "BOTZ", "Global X Robotics & Artificial Intelligence ETF", "Global"),
    ("AI & Robotics", "Autonomous systems", "ARKQ", "ARK Autonomous Technology & Robotics ETF", "Global"),
    ("Cloud & Digital Infrastructure", "Cloud software", "CLOU", "Global X Cloud Computing ETF", "Global"),
    ("Cloud & Digital Infrastructure", "Data centers", "DTCR", "Global X Data Center & Digital Infrastructure ETF", "Global"),
    ("Connected Economy", "Internet of Things", "SNSR", "Global X Internet of Things ETF", "Global"),
    ("Connected Economy", "5G infrastructure", "FIVG", "Defiance Next Gen Connectivity ETF", "Global"),
    ("Semiconductors", "Semiconductors", "SOXX", "iShares Semiconductor ETF", "United States"),
    ("Fintech & Blockchain", "Fintech platforms", "FINX", "Global X FinTech ETF", "Global"),
    ("Fintech & Blockchain", "Digital payments", "IPAY", "Amplify Digital Payments ETF", "Global"),
    ("Fintech & Blockchain", "Blockchain infrastructure", "BLOK", "Amplify Blockchain Technology ETF", "Global"),
    ("Clean Energy & Electrification", "Diversified renewables", "ICLN", "iShares Global Clean Energy ETF", "Global"),
    ("Clean Energy & Electrification", "Solar", "TAN", "Invesco Solar ETF", "Global"),
    ("Clean Energy & Electrification", "Wind", "FAN", "First Trust Global Wind Energy ETF", "Global"),
    ("Clean Energy & Electrification", "Smart grid", "GRID", "First Trust NASDAQ Clean Edge Smart Grid Infrastructure Index Fund", "Global"),
    ("Clean Energy & Electrification", "Hydrogen", "HYDR", "Global X Hydrogen ETF", "Global"),
    ("Climate Tech & Circular Economy", "Climate solutions", "CTEC", "Global X CleanTech ETF", "Global"),
    ("Nuclear Energy", "Uranium supply chain", "URA", "Global X Uranium ETF", "Global"),
    ("Nuclear Energy", "Nuclear power producers", "NLR", "VanEck Uranium and Nuclear ETF", "Global"),
    ("Batteries & Critical Materials", "Lithium and batteries", "LIT", "Global X Lithium & Battery Tech ETF", "Global"),
    ("Batteries & Critical Materials", "Rare earths and strategic metals", "REMX", "VanEck Rare Earth/Strategic Metals ETF", "Global"),
    ("Batteries & Critical Materials", "Copper", "COPX", "Global X Copper Miners ETF", "Global"),
    ("Specialty Materials", "Silver miners", "SIL", "Global X Silver Miners ETF", "Global"),
    ("Specialty Materials", "Diversified metals and mining", "PICK", "iShares MSCI Global Metals & Mining Producers ETF", "Global"),
    ("Water", "Water resources", "PHO", "Invesco Water Resources ETF", "United States"),
    ("Infrastructure & Industrial Modernization", "Infrastructure buildout", "PAVE", "Global X U.S. Infrastructure Development ETF", "United States"),
    ("Infrastructure & Industrial Modernization", "Global listed infrastructure", "NFRA", "FlexShares STOXX Global Broad Infrastructure Index Fund", "Global"),
    ("Space, Aerospace & Defense", "Space economy", "UFO", "Procure Space ETF", "Global"),
    ("Space, Aerospace & Defense", "Aerospace and defense", "ITA", "iShares U.S. Aerospace & Defense ETF", "United States"),
    ("Genomics & Biotech Innovation", "Genomics", "GNOM", "Global X Genomics & Biotechnology ETF", "Global"),
    ("Genomics & Biotech Innovation", "Genomics and immunology", "IDNA", "iShares Genomics Immunology and Healthcare ETF", "Global"),
    ("Genomics & Biotech Innovation", "Biotechnology", "XBI", "SPDR S&P Biotech ETF", "United States"),
    ("Aging & Health Innovation", "Aging population", "AGNG", "Global X Aging Population ETF", "Global"),
    ("Aging & Health Innovation", "Healthcare technology", "HTEC", "ROBO Global Healthcare Technology and Innovation ETF", "Global"),
    ("Aging & Health Innovation", "Digital health and AI-enabled care", "HEAL", "Global X HealthTech ETF", "Global"),
    ("Aging & Health Innovation", "Medical devices", "IHI", "iShares U.S. Medical Devices ETF", "United States"),
    ("Future Mobility", "EVs and autonomy", "DRIV", "Global X Autonomous & Electric Vehicles ETF", "Global"),
    ("Food & AgTech", "AgTech and food innovation", "KROP", "Global X AgTech & Food Innovation ETF", "Global"),
    ("Food & AgTech", "Agribusiness", "MOO", "VanEck Agribusiness ETF", "Global"),
    ("Digital Consumer", "E-commerce", "EBIZ", "Global X E-commerce ETF", "Global"),
    ("Digital Consumer", "Social media", "SOCL", "Global X Social Media ETF", "Global"),
    ("Digital Consumer", "Video games and esports", "HERO", "Global X Video Games & Esports ETF", "Global"),
    ("Digital Consumer", "Sports betting and iGaming", "BETZ", "Roundhill Sports Betting & iGaming ETF", "Global"),
    ("Digital Consumer", "Travel technology", "AWAY", "Amplify Travel Tech ETF", "Global"),
    ("Digital Consumer", "Millennial consumers", "MILN", "Global X Millennial Consumer ETF", "United States"),
    ("Alternative Consumer Trends", "Cannabis", "MJ", "Amplify Alternative Harvest ETF", "Global"),
    ("Alternative Consumer Trends", "Pet care", "PAWZ", "ProShares Pet Care ETF", "Global"),
    ("Housing & Real Assets", "Housing ecosystem", "HOMZ", "Hoya Capital Housing ETF", "United States"),
    ("Housing & Real Assets", "Home construction", "ITB", "iShares U.S. Home Construction ETF", "United States"),
    ("Housing & Real Assets", "Timber and forestry", "WOOD", "iShares Global Timber & Forestry ETF", "Global"),
    ("Emerging Digital Economies", "China internet", "KWEB", "KraneShares CSI China Internet ETF", "China"),
    ("Emerging Digital Economies", "Emerging-market internet", "EMQQ", "EMQQ Emerging Markets Internet & Ecommerce ETF", "Emerging markets"),
    ("Frontier Technology", "Metaverse platforms", "METV", "Roundhill Ball Metaverse ETF", "Global"),
    ("Frontier Technology", "3D printing", "PRNT", "ARK 3D Printing ETF", "Global"),
    ("Frontier Technology", "Quantum computing", "QTUM", "Defiance Quantum ETF", "Global"),
    ("Transportation", "Global shipping", "BOAT", "SonicShares Global Shipping ETF", "Global"),
    ("Transportation", "Airlines", "JETS", "U.S. Global Jets ETF", "Global"),
    ("Environmental Services", "Renewable infrastructure", "RNRG", "Global X Renewable Energy Producers ETF", "Global"),
    ("Environmental Services", "Environmental services", "EVX", "VanEck Environmental Services ETF", "Global"),
]

COMMODITY_ETFS = [
    ("Broad commodities", "Diversified futures basket", "PDBC", "Invesco Optimum Yield Diversified Commodity Strategy No K-1 ETF"),
    ("Broad commodities", "Diversified futures basket", "DBC", "Invesco DB Commodity Index Tracking Fund"),
    ("Broad commodities", "S&P GSCI basket", "GSG", "iShares S&P GSCI Commodity-Indexed Trust"),
    ("Broad commodities", "Actively managed basket", "COMT", "iShares GSCI Commodity Dynamic Roll Strategy ETF"),
    ("Energy", "West Texas Intermediate crude oil", "USO", "United States Oil Fund"),
    ("Energy", "K-1-free crude oil futures", "OILK", "ProShares K-1 Free Crude Oil Strategy ETF"),
    ("Energy", "Brent crude oil", "BNO", "United States Brent Oil Fund"),
    ("Energy", "Natural gas", "UNG", "United States Natural Gas Fund"),
    ("Energy", "Gasoline", "UGA", "United States Gasoline Fund"),
    ("Energy", "Diversified energy futures", "DBE", "Invesco DB Energy Fund"),
    ("Precious metals", "Physical gold", "GLD", "SPDR Gold Shares"),
    ("Precious metals", "Lower-cost physical gold", "GLDM", "SPDR Gold MiniShares Trust"),
    ("Precious metals", "Physical silver", "SLV", "iShares Silver Trust"),
    ("Precious metals", "Alternative physical silver", "SIVR", "abrdn Physical Silver Shares ETF"),
    ("Precious metals", "Physical platinum", "PPLT", "abrdn Physical Platinum Shares ETF"),
    ("Precious metals", "Physical palladium", "PALL", "abrdn Physical Palladium Shares ETF"),
    ("Industrial metals", "Copper futures", "CPER", "United States Copper Index Fund"),
    ("Industrial metals", "Diversified base metals", "DBB", "Invesco DB Base Metals Fund"),
    ("Agriculture", "Diversified agriculture", "DBA", "Invesco DB Agriculture Fund"),
    ("Agriculture", "Corn", "CORN", "Teucrium Corn Fund"),
    ("Agriculture", "Wheat", "WEAT", "Teucrium Wheat Fund"),
    ("Agriculture", "Soybeans", "SOYB", "Teucrium Soybean Fund"),
    ("Agriculture", "Sugar", "CANE", "Teucrium Sugar Fund"),
    ("Agriculture", "Coffee", "COFF.L", "WisdomTree Coffee"),
    ("Agriculture", "Cocoa", "COCO.L", "WisdomTree Cocoa"),
    ("Freight", "Tanker freight futures", "BWET", "Breakwave Tanker Shipping ETF"),
]

COUNTRY_MARKETS = [
    ("Developed", "Asia-Pacific", "Australia", "EWA", "iShares MSCI Australia ETF"),
    ("Developed", "Europe", "Austria", "EWO", "iShares MSCI Austria ETF"),
    ("Developed", "Europe", "Belgium", "EWK", "iShares MSCI Belgium ETF"),
    ("Developed", "Americas", "Canada", "EWC", "iShares MSCI Canada ETF"),
    ("Developed", "Europe", "Denmark", "EDEN", "iShares MSCI Denmark ETF"),
    ("Developed", "Europe", "Finland", "EFNL", "iShares MSCI Finland ETF"),
    ("Developed", "Europe", "France", "EWQ", "iShares MSCI France ETF"),
    ("Developed", "Europe", "Germany", "EWG", "iShares MSCI Germany ETF"),
    ("Developed", "Asia-Pacific", "Hong Kong", "EWH", "iShares MSCI Hong Kong ETF"),
    ("Developed", "Europe", "Ireland", "EIRL", "iShares MSCI Ireland ETF"),
    ("Developed", "Middle East & Africa", "Israel", "EIS", "iShares MSCI Israel ETF"),
    ("Developed", "Europe", "Italy", "EWI", "iShares MSCI Italy ETF"),
    ("Developed", "Asia-Pacific", "Japan", "EWJ", "iShares MSCI Japan ETF"),
    ("Developed", "Europe", "Netherlands", "EWN", "iShares MSCI Netherlands ETF"),
    ("Developed", "Asia-Pacific", "New Zealand", "ENZL", "iShares MSCI New Zealand ETF"),
    ("Developed", "Europe", "Norway", "ENOR", "iShares MSCI Norway ETF"),
    ("Developed", "Europe", "Portugal", None, None),
    ("Developed", "Asia-Pacific", "Singapore", "EWS", "iShares MSCI Singapore ETF"),
    ("Developed", "Europe", "Spain", "EWP", "iShares MSCI Spain ETF"),
    ("Developed", "Europe", "Sweden", "EWD", "iShares MSCI Sweden ETF"),
    ("Developed", "Europe", "Switzerland", "EWL", "iShares MSCI Switzerland ETF"),
    ("Developed", "Europe", "United Kingdom", "EWU", "iShares MSCI United Kingdom ETF"),
    (
        "Developed",
        "Americas",
        "United States",
        "ITOT",
        "iShares Core S&P Total U.S. Stock Market ETF",
    ),
    ("Emerging", "Americas", "Brazil", "EWZ", "iShares MSCI Brazil ETF"),
    ("Emerging", "Americas", "Chile", "ECH", "iShares MSCI Chile ETF"),
    ("Emerging", "Asia-Pacific", "China", "MCHI", "iShares MSCI China ETF"),
    ("Emerging", "Americas", "Colombia", "COLO", "Global X MSCI Colombia ETF"),
    ("Emerging", "Europe", "Czech Republic", None, None),
    ("Emerging", "Middle East & Africa", "Egypt", None, None),
    ("Emerging", "Europe", "Greece", "GREK", "Global X MSCI Greece ETF"),
    ("Emerging", "Europe", "Hungary", None, None),
    ("Emerging", "Asia-Pacific", "India", "INDA", "iShares MSCI India ETF"),
    ("Emerging", "Asia-Pacific", "Indonesia", "EIDO", "iShares MSCI Indonesia ETF"),
    ("Emerging", "Asia-Pacific", "South Korea", "EWY", "iShares MSCI South Korea ETF"),
    ("Emerging", "Middle East & Africa", "Kuwait", "KWT", "iShares MSCI Kuwait ETF"),
    ("Emerging", "Asia-Pacific", "Malaysia", "EWM", "iShares MSCI Malaysia ETF"),
    ("Emerging", "Americas", "Mexico", "EWW", "iShares MSCI Mexico ETF"),
    ("Emerging", "Americas", "Peru", "EPU", "iShares MSCI Peru and Global Exposure ETF"),
    ("Emerging", "Asia-Pacific", "Philippines", "EPHE", "iShares MSCI Philippines ETF"),
    ("Emerging", "Europe", "Poland", "EPOL", "iShares MSCI Poland ETF"),
    ("Emerging", "Middle East & Africa", "Qatar", "QAT", "iShares MSCI Qatar ETF"),
    ("Emerging", "Middle East & Africa", "Saudi Arabia", "KSA", "iShares MSCI Saudi Arabia ETF"),
    ("Emerging", "Middle East & Africa", "South Africa", "EZA", "iShares MSCI South Africa ETF"),
    ("Emerging", "Asia-Pacific", "Taiwan", "EWT", "iShares MSCI Taiwan ETF"),
    ("Emerging", "Asia-Pacific", "Thailand", "THD", "iShares MSCI Thailand ETF"),
    ("Emerging", "Europe", "Turkey", "TUR", "iShares MSCI Turkey ETF"),
    ("Emerging", "Middle East & Africa", "United Arab Emirates", "UAE", "iShares MSCI UAE ETF"),
    ("Frontier", "Middle East & Africa", "Bahrain", None, None),
    ("Frontier", "Asia-Pacific", "Bangladesh", None, None),
    ("Frontier", "Middle East & Africa", "Benin", None, None),
    ("Frontier", "Middle East & Africa", "Botswana", None, None),
    ("Frontier", "Middle East & Africa", "Burkina Faso", None, None),
    ("Frontier", "Middle East & Africa", "Côte d'Ivoire", None, None),
    ("Frontier", "Europe", "Croatia", None, None),
    ("Frontier", "Europe", "Estonia", None, None),
    ("Frontier", "Middle East & Africa", "Ghana", None, None),
    ("Frontier", "Middle East & Africa", "Guinea-Bissau", None, None),
    ("Frontier", "Europe", "Iceland", None, None),
    ("Frontier", "Middle East & Africa", "Jordan", None, None),
    ("Frontier", "Asia-Pacific", "Kazakhstan", None, None),
    ("Frontier", "Middle East & Africa", "Kenya", None, None),
    ("Frontier", "Europe", "Lithuania", None, None),
    ("Frontier", "Middle East & Africa", "Mali", None, None),
    ("Frontier", "Middle East & Africa", "Mauritius", None, None),
    ("Frontier", "Middle East & Africa", "Morocco", None, None),
    ("Frontier", "Middle East & Africa", "Niger", None, None),
    ("Frontier", "Middle East & Africa", "Nigeria", None, None),
    ("Frontier", "Middle East & Africa", "Oman", None, None),
    ("Frontier", "Asia-Pacific", "Pakistan", None, None),
    ("Frontier", "Europe", "Romania", None, None),
    ("Frontier", "Middle East & Africa", "Senegal", None, None),
    ("Frontier", "Europe", "Serbia", None, None),
    ("Frontier", "Europe", "Slovenia", None, None),
    ("Frontier", "Asia-Pacific", "Sri Lanka", None, None),
    ("Frontier", "Middle East & Africa", "Togo", None, None),
    ("Frontier", "Middle East & Africa", "Tunisia", None, None),
    ("Frontier", "Asia-Pacific", "Vietnam", "VNM", "VanEck Vietnam ETF"),
    ("Standalone", "Americas", "Argentina", "ARGT", "Global X MSCI Argentina ETF"),
    ("Standalone", "Europe", "Bosnia and Herzegovina", None, None),
    ("Standalone", "Europe", "Bulgaria", None, None),
    ("Standalone", "Americas", "Jamaica", None, None),
    ("Standalone", "Middle East & Africa", "Lebanon", None, None),
    ("Standalone", "Europe", "Malta", None, None),
    ("Standalone", "Middle East & Africa", "Palestine", None, None),
    ("Standalone", "Americas", "Panama", None, None),
    ("Standalone", "Europe", "Russia", None, None),
    ("Standalone", "Americas", "Trinidad and Tobago", None, None),
    ("Standalone", "Europe", "Ukraine", None, None),
    ("Standalone", "Middle East & Africa", "Zimbabwe", None, None),
]

GICS_PROXY_BY_CODE = {
    "101010": ("OIH", "VanEck Oil Services ETF", "Industry"),
    "10102020": ("XOP", "SPDR S&P Oil & Gas Exploration & Production ETF", "Sub-industry"),
    "10102040": ("AMLP", "Alerian MLP ETF", "Sub-industry"),
    "151040": ("XME", "SPDR S&P Metals & Mining ETF", "Industry"),
    "15104025": ("COPX", "Global X Copper Miners ETF", "Sub-industry"),
    "15104030": ("GDX", "VanEck Gold Miners ETF", "Sub-industry"),
    "15105010": ("WOOD", "iShares Global Timber & Forestry ETF", "Sub-industry"),
    "20101010": ("ITA", "iShares U.S. Aerospace & Defense ETF", "Sub-industry"),
    "2030": ("IYT", "iShares U.S. Transportation ETF", "Industry group"),
    "25102010": ("CARZ", "First Trust S-Network Future Vehicles & Technology ETF", "Sub-industry"),
    "25201030": ("ITB", "iShares U.S. Home Construction ETF", "Sub-industry"),
    "253010": ("PEJ", "Invesco Leisure and Entertainment ETF", "Industry"),
    "2550": ("XRT", "SPDR S&P Retail ETF", "Industry group"),
    "3020": ("PBJ", "Invesco Food & Beverage ETF", "Industry group"),
    "30202010": ("MOO", "VanEck Agribusiness ETF", "Sub-industry"),
    "35101010": ("IHI", "iShares U.S. Medical Devices ETF", "Sub-industry"),
    "351020": ("IHF", "iShares U.S. Healthcare Providers ETF", "Industry"),
    "35201010": ("IBB", "iShares Biotechnology ETF", "Sub-industry"),
    "35202010": ("IHE", "iShares U.S. Pharmaceuticals ETF", "Sub-industry"),
    "40101010": ("KBE", "SPDR S&P Bank ETF", "Sub-industry"),
    "40101015": ("KRE", "SPDR S&P Regional Banking ETF", "Sub-industry"),
    "402030": ("IAI", "iShares U.S. Broker-Dealers & Securities Exchanges ETF", "Industry"),
    "40204010": ("REM", "iShares Mortgage Real Estate ETF", "Sub-industry"),
    "403010": ("KIE", "SPDR S&P Insurance ETF", "Industry"),
    "451030": ("IGV", "iShares Expanded Tech-Software Sector ETF", "Industry"),
    "453010": ("SOXX", "iShares Semiconductor ETF", "Industry"),
    "5010": ("IYZ", "iShares U.S. Telecommunications ETF", "Industry group"),
    "502010": ("PBS", "Invesco Next Gen Media and Gaming ETF", "Industry"),
    "50203010": ("SOCL", "Global X Social Media ETF", "Sub-industry"),
    "55104010": ("PHO", "Invesco Water Resources ETF", "Sub-industry"),
    "55105020": ("ICLN", "iShares Global Clean Energy ETF", "Sub-industry"),
    "6010": ("VNQ", "Vanguard Real Estate ETF", "Industry group"),
    "601060": ("REZ", "iShares Residential and Multisector Real Estate ETF", "Industry"),
}


def gics_hierarchy() -> list[dict[str, Any]]:
    taxonomy_path = Path(__file__).parent / "data" / "gics_taxonomy.csv"
    with taxonomy_path.open(encoding="utf-8-sig", newline="") as source:
        taxonomy = list(csv.DictReader(source))

    rows = []
    for item in taxonomy:
        proxy = next(
            (
                GICS_PROXY_BY_CODE[code]
                for code in (
                    item["sub_industry_code"],
                    item["industry_code"],
                    item["industry_group_code"],
                )
                if code in GICS_PROXY_BY_CODE
            ),
            None,
        )
        symbol, fund, proxy_level = proxy if proxy else (None, None, None)
        rows.append(
            {
                "Universe": "Full GICS hierarchy",
                "Market group": "GICS March 2023",
                "Region": (
                    "Global proxy"
                    if symbol in {"MOO", "WOOD", "ICLN"}
                    else "Primarily US proxy" if symbol else "No ETF proxy"
                ),
                "Category": item["sub_industry_name"],
                "Country": None,
                "Parent sector": item["sector_name"],
                "Industry group": item["industry_group_name"],
                "Industry": item["industry_name"],
                "Sub-industry": item["sub_industry_name"],
                "Taxonomy code": item["sub_industry_code"],
                "Symbol": symbol,
                "Fund": fund,
                "Taxonomy": "GICS sub-industry",
                "Proxy level": proxy_level,
            }
        )
    return rows


def etf_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {
            "Universe": "Global sectors",
            "Market group": "Global",
            "Region": "Global",
            "Category": sector,
            "Country": None,
            "Parent sector": sector,
            "Industry group": None,
            "Industry": None,
            "Sub-industry": None,
            "Taxonomy code": None,
            "Symbol": symbol,
            "Fund": fund,
            "Taxonomy": "GICS sector",
            "Proxy level": "Sector",
        }
        for sector, symbol, fund in GICS_SECTOR_ETFS
    ]
    rows.extend(
        {
            "Universe": "Thematic ETFs",
            "Market group": subtheme,
            "Region": scope,
            "Category": theme,
            "Country": None,
            "Parent sector": None,
            "Industry group": None,
            "Industry": None,
            "Sub-industry": None,
            "Taxonomy code": None,
            "Symbol": symbol,
            "Fund": fund,
            "Taxonomy": "Thematic equity exposure",
            "Proxy level": subtheme,
        }
        for theme, subtheme, symbol, fund, scope in THEMATIC_ETFS
    )
    rows.extend(
        {
            "Universe": "Commodity ETFs",
            "Market group": exposure,
            "Region": "Global",
            "Category": group,
            "Country": None,
            "Parent sector": None,
            "Industry group": None,
            "Industry": None,
            "Sub-industry": None,
            "Taxonomy code": None,
            "Symbol": symbol,
            "Fund": fund,
            "Taxonomy": "Commodity exchange-traded exposure",
            "Proxy level": exposure,
        }
        for group, exposure, symbol, fund in COMMODITY_ETFS
    )
    rows.extend(
        {
            "Universe": "Regional markets",
            "Market group": style,
            "Region": region,
            "Category": region,
            "Country": None,
            "Parent sector": None,
            "Industry group": None,
            "Industry": None,
            "Sub-industry": None,
            "Taxonomy code": None,
            "Symbol": symbol,
            "Fund": fund,
            "Taxonomy": "Regional equity exposure",
            "Proxy level": scope,
        }
        for region, style, symbol, fund, scope in REGIONAL_MARKET_ETFS
    )
    rows.extend(
        {
            "Universe": "Industry exposures",
            "Market group": "Primarily US",
            "Region": "United States" if symbol not in {"MOO", "WOOD", "ICLN"} else "Global",
            "Category": industry,
            "Country": None,
            "Parent sector": sector,
            "Industry group": None,
            "Industry": industry,
            "Sub-industry": None,
            "Taxonomy code": None,
            "Symbol": symbol,
            "Fund": fund,
            "Taxonomy": "GICS-aligned industry exposure",
            "Proxy level": "Industry exposure",
        }
        for sector, industry, symbol, fund in GICS_INDUSTRY_ETFS
    )
    rows.extend(
        {
            "Universe": "Country markets",
            "Market group": market_group,
            "Region": region,
            "Category": country,
            "Country": country,
            "Parent sector": None,
            "Industry group": None,
            "Industry": None,
            "Sub-industry": None,
            "Taxonomy code": None,
            "Symbol": symbol,
            "Fund": fund,
            "Taxonomy": "MSCI-style country market classification",
            "Proxy level": "Country" if symbol else None,
        }
        for market_group, region, country, symbol, fund in COUNTRY_MARKETS
    )
    rows.extend(gics_hierarchy())
    for row in rows:
        row.update(ETF_RESEARCH_NOTES.get(row["Symbol"], {}))
        identity = (
            row["Taxonomy code"]
            or row["Country"]
            or f"{row['Category']}|{row['Symbol'] or 'none'}"
        )
        row["Entry ID"] = f"{row['Universe']}|{identity}"
    return rows


def filter_etfs(
    catalog: list[dict[str, Any]],
    universe: str,
    market_group: str | None = None,
    region: str | None = None,
    parent_sector: str | None = None,
    industry_group: str | None = None,
    industry: str | None = None,
) -> list[dict[str, Any]]:
    rows = [row for row in catalog if row["Universe"] == universe]
    if market_group and market_group != "All":
        rows = [row for row in rows if row["Market group"] == market_group]
    if region and region != "All":
        rows = [row for row in rows if row["Region"] == region]
    if parent_sector and parent_sector != "All":
        rows = [row for row in rows if row["Parent sector"] == parent_sector]
    if industry_group and industry_group != "All":
        rows = [row for row in rows if row["Industry group"] == industry_group]
    if industry and industry != "All":
        rows = [row for row in rows if row["Industry"] == industry]
    return rows
