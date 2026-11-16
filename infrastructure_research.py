RESEARCH_AS_OF = "2026-09-06"
IBKR_EXCHANGE_SOURCE = "https://www.interactivebrokers.com/webrest/exchanges/"

# Venue-level evidence is not confirmation of an individual IBKR contract.
INFRASTRUCTURE_VENUES = {
    "": ("US exchanges", "NYSE / NASDAQ", "Supported venue", "ADR and account eligibility must be checked."),
    "MC": ("Spain", "BM", "Supported venue", ""),
    "PA": ("France", "SBF", "Supported venue", ""),
    "DE": ("Germany", "IBIS / FWB", "Supported venue", ""),
    "VI": ("Austria", "VSE", "Supported venue", ""),
    "SW": ("Switzerland", "EBS", "Supported venue", ""),
    "L": ("London", "LSE", "Supported venue", ""),
    "MI": ("Italy", "BVME", "Supported venue", ""),
    "TO": ("Canada", "TSE", "Supported venue", ""),
    "AX": ("Australia", "ASX", "Supported venue", ""),
    "SA": ("Brazil", "B3", "Supported venue", ""),
    "MX": ("Mexico", "MEXI", "Supported venue", ""),
    "WA": ("Poland", "WSE", "Supported venue", ""),
    "RO": ("Romania", "BVB", "Supported venue", ""),
    "JO": ("South Africa", "JSE", "Supported venue", ""),
    "SR": ("Saudi Arabia", "TADAWUL", "Supported venue", ""),
    "NS": ("India", "NSE", "Restricted venue", "IBKR's stock schedule restricts NSE stocks to Indian residents; do not assume general foreign-retail or NRI access."),
    "HK": ("Hong Kong", "SEHK", "Supported venue", ""),
    "KL": ("Malaysia", "BURSAMY", "Supported venue", ""),
    "TW": ("Taiwan", "TWSE", "Supported venue", ""),
    "TWO": ("Taiwan", "TPEX", "Supported venue", ""),
    "SI": ("Singapore", "SGX", "Supported venue", ""),
    "T": ("Japan", "TSEJ", "Supported venue", ""),
    "KS": ("South Korea", "KRX", "Supported venue", ""),
    "PR": ("Czechia", "PRA", "Supported venue", ""),
    "VS": ("Lithuania", "N.VILNIUS", "Supported venue", ""),
    "TL": ("Estonia", "N.TALLINN", "Supported venue", ""),
    "BR": ("Belgium", "ENEXT.BE", "Supported venue", ""),
    "LS": ("Portugal", "BVL", "Supported venue", ""),
    "AS": ("Netherlands", "AEB", "Supported venue", ""),
    "SN": ("Chile", "", "Unverified venue", "Santiago not found in the IBKR stock-venue list consulted."),
    "AT": ("Greece", "", "Unverified venue", "Athens not found in the IBKR stock-venue list consulted."),
    "IS": ("Turkey", "", "Unverified venue", "Borsa Istanbul not found in the IBKR stock-venue list consulted."),
    "QA": ("Qatar", "", "Unverified venue", "Qatar Exchange not found in the IBKR stock-venue list consulted."),
    "BK": ("Thailand", "", "Unverified venue", "Thailand's SET not found in the IBKR stock-venue list consulted."),
}


def infrastructure_listing_details(symbol: str) -> dict[str, str]:
    suffix = symbol.rpartition(".")[2] if "." in symbol else ""
    venue = INFRASTRUCTURE_VENUES.get(suffix)
    if venue is None:
        market, exchange, status, note = (
            "Unreviewed", "", "Unverified venue",
            "No venue-level access review is recorded for this listing.",
        )
    else:
        market, exchange, status, note = venue
    return {
        "ListingMarket": market,
        "IBKRExchange": exchange,
        "AccessStatus": status,
        "AccessNote": note,
        "AccessSource": (
            "https://www.interactivebrokers.com/en/pricing/commissions-stocks.php?region=asia-pacific"
            if suffix == "NS" else IBKR_EXCHANGE_SOURCE
        ),
    }


INFRASTRUCTURE_RESEARCH_GAPS = [
    {"Name": "KazTransOil", "Local symbol": "KZTO", "Market": "Kazakhstan / KASE", "Reason": "Oil-pipeline operator; KASE not found in IBKR stock venues, no supported foreign line or usable Yahoo history verified.", "Source": "https://kase.kz/en/listing/issuers/KZTO/"},
    {"Name": "KEGOC", "Local symbol": "KEGC", "Market": "Kazakhstan / KASE", "Reason": "National transmission grid; local access and usable Yahoo history not verified.", "Source": "https://kase.kz/en/listing/issuers/KEGC/"},
    {"Name": "Kazakhtelecom", "Local symbol": "KZTK", "Market": "Kazakhstan / KASE", "Reason": "Incumbent telecom; no supported current cross-listing or usable Yahoo history verified.", "Source": "https://kase.kz/en/listing/issuers/KZTK/"},
    {"Name": "Kcell", "Local symbol": "KCEL", "Market": "Kazakhstan / KASE", "Reason": "Mobile network; no supported current cross-listing verified.", "Source": "https://kase.kz/en/listing/issuers/KCEL/"},
    {"Name": "MTN Nigeria", "Local symbol": "MTNN", "Market": "Nigeria / NGX", "Reason": "NGX not found in IBKR stock venues. MTN.JO offers parent-company exposure.", "Source": "https://www.mtn.ng/investors/"},
    {"Name": "Safaricom", "Local symbol": "SCOM", "Market": "Kenya / Nairobi", "Reason": "Nairobi not found in IBKR stock venues; the IBKR NSE identifier is India, not Kenya.", "Source": IBKR_EXCHANGE_SOURCE},
    {"Name": "Kenya Power", "Local symbol": "KPLC", "Market": "Kenya / Nairobi", "Reason": "Distribution-network candidate; local equity access and a foreign listing not verified.", "Source": IBKR_EXCHANGE_SOURCE},
    {"Name": "Marsa Maroc", "Local symbol": "MSA", "Market": "Morocco / Casablanca", "Reason": "Port-terminal candidate; Casablanca not found in IBKR stock venues.", "Source": IBKR_EXCHANGE_SOURCE},
    {"Name": "Maroc Telecom", "Local symbol": "IAM", "Market": "Morocco / Casablanca", "Reason": "Local venue not found; any foreign line requires separate contract and liquidity verification.", "Source": IBKR_EXCHANGE_SOURCE},
    {"Name": "Telecom Egypt", "Local symbol": "ETEL", "Market": "Egypt / EGX", "Reason": "EGX not found in IBKR stock venues; an active, liquid foreign line was not verified.", "Source": IBKR_EXCHANGE_SOURCE},
    {"Name": "Alexandria Container and Cargo Handling", "Local symbol": "ALCN", "Market": "Egypt / EGX", "Reason": "Port-terminal candidate; local venue and supported foreign listing not verified.", "Source": IBKR_EXCHANGE_SOURCE},
    {"Name": "Sonatel", "Local symbol": "SNTS", "Market": "West Africa / BRVM", "Reason": "Incumbent telecom; BRVM not found in IBKR stock venues.", "Source": IBKR_EXCHANGE_SOURCE},
    {"Name": "Compagnie Ivoirienne d'Electricite", "Local symbol": "CIEC", "Market": "West Africa / BRVM", "Reason": "Electricity concession; BRVM access not verified.", "Source": IBKR_EXCHANGE_SOURCE},
    {"Name": "SODECI", "Local symbol": "SDCC", "Market": "West Africa / BRVM", "Reason": "Water concession; BRVM access not verified.", "Source": IBKR_EXCHANGE_SOURCE},
    {"Name": "MTN Ghana", "Local symbol": "MTNGH", "Market": "Ghana", "Reason": "Local venue not found in IBKR list; MTN.JO offers parent exposure.", "Source": "https://mtn.com.gh/investors/"},
    {"Name": "Mobile Telecommunications", "Local symbol": "MTC", "Market": "Namibia", "Reason": "Local venue not found in IBKR list; no supported foreign line verified.", "Source": "https://www.mtc.com.na/investors"},
    {"Name": "Botswana Telecommunications", "Local symbol": "BTCL", "Market": "Botswana", "Reason": "Local venue not found in IBKR list; no supported foreign line verified.", "Source": IBKR_EXCHANGE_SOURCE},
    {"Name": "Vodacom Tanzania", "Local symbol": "VODA", "Market": "Tanzania", "Reason": "Local venue not found; VOD.JO offers parent-company exposure.", "Source": "https://vodacom.co.tz/about-us"},
    {"Name": "MTN Uganda", "Local symbol": "MTNU", "Market": "Uganda", "Reason": "Local venue not found; MTN.JO offers parent-company exposure.", "Source": IBKR_EXCHANGE_SOURCE},
    {"Name": "MTN Rwanda", "Local symbol": "MTNR", "Market": "Rwanda", "Reason": "Local venue not found; MTN.JO offers parent-company exposure.", "Source": IBKR_EXCHANGE_SOURCE},
    {"Name": "IHS Holding", "Local symbol": "IHS", "Market": "NYSE / pan-Africa", "Reason": "MTN acquisition proposal contemplates delisting; excluded from the continuing-issuer universe pending transaction outcome.", "Source": "https://www.mtn.com/mtn-group-announces-proposed-acquisition-of-ihs-towers/"},
    {"Name": "Abu Dhabi National Energy Company", "Local symbol": "TAQA", "Market": "UAE / ADX", "Reason": "Regulated utility networks; ADX is an IBKR stock venue, but a usable Yahoo symbol/history was not verified.", "Source": "https://www.taqa.com/about-us/"},
    {"Name": "Tabreed", "Local symbol": "TABREED", "Market": "UAE", "Reason": "District-cooling networks; Yahoo symbol/history and exact listing route require verification.", "Source": "https://tabreed.ae/en/what-we-do"},
    {"Name": "AD Ports Group", "Local symbol": "ADPORTS", "Market": "UAE / ADX", "Reason": "Ports and economic zones; ADX is supported, but usable Yahoo symbol/history was not verified.", "Source": "https://www.adportsgroup.com/en/about-us"},
    {"Name": "Dubai Electricity and Water Authority", "Local symbol": "DEWA", "Market": "UAE / DFM", "Reason": "Monopoly utility; DFM is an IBKR stock venue, but the attempted Yahoo symbol had no usable history.", "Source": "https://www.dewa.gov.ae/"},
    {"Name": "Salik", "Local symbol": "SALIK", "Market": "UAE / DFM", "Reason": "Exclusive Dubai toll-gate operator; supported venue, but a usable Yahoo symbol/history was not verified.", "Source": "https://www.salik.ae/"},
    {"Name": "Empower", "Local symbol": "EMPOWER", "Market": "UAE / DFM", "Reason": "District-cooling network; supported venue, but a usable Yahoo symbol/history was not verified.", "Source": "https://www.empower.ae/"},
]
