"""Dated, curated product-company research; not an automated IP valuation model."""

from dataclasses import dataclass


IP_RESEARCH_AS_OF = "2026-09-25"
IP_RESEARCH_TIERS = (
    "Core research candidate",
    "More-confirmed recovery",
    "High-risk watchlist",
)
IP_RESEARCH_QUEUE_LABEL = "IP-backed turnaround candidates"

IP_EVALUATION_CHECKLIST = (
    (
        "Is the technology still commercially valuable?",
        "Identify paying users, qualified materials, installed systems, proprietary software "
        "or hard-to-replace processes. Patent counts and brand recognition alone are insufficient.",
    ),
    (
        "Is the setback repairable?",
        "Separate temporary demand, product or execution problems from permanent substitution "
        "and commoditization. Revenue and profit recovery need not already be visible.",
    ),
    (
        "Can shareholders survive until recovery?",
        "Check cash burn, debt maturities, covenants, capital spending and dilution. Do not "
        "count announced disposal proceeds as cash already received.",
    ),
    (
        "What concrete event could change the business?",
        "Look for customer adoption, a product launch, cost execution or completed deleveraging. "
        "Distinguish laboratory results and management targets from orders and realized cash flow.",
    ),
    (
        "Does the valuation leave room for disappointment?",
        "Use conservative operating economics, including R&D, capitalized IP costs and stock "
        "compensation. Do not assign a guaranteed patent-value floor or double-count assets being sold.",
    ),
    (
        "What would justify an entry, and invalidate the thesis?",
        "Review current prices for stabilization, a base or improving relative strength; do not "
        "infer cheapness from a large drawdown. Define milestones and exit reasons if adoption, "
        "cash conversion or funding deteriorate. An exact U-shape is not required.",
    ),
)


@dataclass(frozen=True)
class ResearchSource:
    label: str
    date: str
    url: str


@dataclass(frozen=True)
class IPTurnaroundCandidate:
    symbol: str
    name: str
    sector: str
    tier: str
    ip_case: str
    recovery_case: str
    financial_evidence: str
    risks: str
    watch_for: str
    sources: tuple[ResearchSource, ...]


IP_TURNAROUND_CANDIDATES = (
    IPTurnaroundCandidate(
        symbol="SSYS",
        name="Stratasys",
        sector="Industrial additive manufacturing",
        tier="Core research candidate",
        ip_case=(
            "Industrial printing platforms, qualified materials, software and application "
            "engineering support an installed base with repeat consumables demand. This is "
            "not exclusive ownership of 3D printing; foundational patents have expired."
        ),
        recovery_case=(
            "Record consumables sales and aerospace/defence demand could improve a stagnant "
            "equipment business. A September announcement described deployment across more "
            "than 20 GM facilities, without disclosing a contract value."
        ),
        financial_evidence=(
            "Q2 2026 revenue was $137.6m versus $138.1m a year earlier; consumables reached "
            "$66.3m and aerospace/defence revenue grew 17%. June 30 cash, equivalents and "
            "short-term deposits were $212.5m, with no debt. Q2 operating cash outflow was $18.7m."
        ),
        risks=(
            "The positive full-year operating-cash-flow expectation was withdrawn; management "
            "instead expected positive operating cash flow in H2. The pending $42.5m cash "
            "acquisition of Markforged reduces liquidity and adds integration risk. Lower-cost "
            "printers can erode differentiation in less demanding applications."
        ),
        watch_for=(
            "Repeat consumables demand, actual H2 cash conversion after capital spending, "
            "customer deployments and acquisition closing/integration. Do not treat the June "
            "cash balance as permanently surplus or adjusted EBITDA as free cash flow."
        ),
        sources=(
            ResearchSource(
                "Q2 results and cash-flow outlook", "2026-08-13",
                "https://investors.stratasys.com/news-events/press-releases/detail/989/"
                "stratasys-releases-second-quarter-2026-financial-results",
            ),
            ResearchSource(
                "GM deployment announcement", "2026-09-14",
                "https://investors.stratasys.com/news-events/press-releases/detail/993/"
                "stratasys-additive-manufacturing-solutions-to-roll-out",
            ),
            ResearchSource(
                "Pending Markforged acquisition", "2026-05-27",
                "https://investors.stratasys.com/news-events/press-releases/detail/984/"
                "stratasys-to-acquire-markforged-inc-expanding-aerospace",
            ),
        ),
    ),
    IPTurnaroundCandidate(
        symbol="GN.CO",
        name="GN Store Nord",
        sector="Audio and enterprise peripherals",
        tier="Core research candidate",
        ip_case=(
            "The retained Jabra and SteelSeries businesses combine audio hardware, "
            "sound-processing algorithms, adaptive noise cancellation and device-management "
            "software. The thesis is product differentiation, not royalty collection."
        ),
        recovery_case=(
            "Evolve3 and gaming-product adoption, operational repair and deleveraging could "
            "support a reset. GN agreed to sell its Hearing business to Amplifon for approximately "
            "DKK12.6bn cash plus 56m Amplifon shares, with closing expected by year-end 2026."
        ),
        financial_evidence=(
            "Q2 2026 continuing revenue was DKK2,171m, down 4% organically; adjusted EBITA "
            "margin was 5.1%. June group net interest-bearing debt was DKK9,566m and adjusted "
            "leverage 4.4x, before the disposal. These are DKK figures, not US dollars."
        ),
        risks=(
            "The Hearing business and its hearing-product IP leave GN on completion. Do not "
            "count both the proceeds and continued ownership of those assets. Closing and "
            "separation remained pending; DKK750m carve-out/right-sizing cash costs were "
            "estimated across 2026-27. Planned savings largely offset stranded costs."
        ),
        watch_for=(
            "Regulatory approval, completed disposal and actual debt repayment; Evolve3 "
            "sell-through, working-capital improvement and retained-business margins excluding "
            "tariff refunds. Announced proceeds are not cash already on the balance sheet."
        ),
        sources=(
            ResearchSource(
                "Q2 report: continuing business, debt and separation", "2026-08-19",
                "https://www.gn.com/-/media/Files/Financial-Download-Center/2026/Q2/"
                "GN-Interim-Report-Q2-2026.pdf",
            ),
            ResearchSource(
                "Hearing disposal agreement", "2026-03-16",
                "https://www.gn.com/Newsroom/Announcement?id=3256006&lang=en&date=20260316"
                "&title=gn-store-nord-a-s-enters-into-agreement-to-sell-its-hearing-business"
                "-to-amplifon-s-p-a-for-dkk-17-0-billion",
            ),
            ResearchSource(
                "Jabra Evolve3 product announcement", "2026-01-21",
                "https://www.gn.com/Newsroom/News/2026/January/Jabra-reinforces-headset-leadership",
            ),
        ),
    ),
    IPTurnaroundCandidate(
        symbol="OLED",
        name="Universal Display",
        sector="Display materials and technology",
        tier="Core research candidate",
        ip_case=(
            "Proprietary OLED emitting materials and device architectures combine a physical "
            "materials business with technology licensing. The research question is whether "
            "commercially useful technology remains valuable through a demand setback."
        ),
        recovery_case=(
            "Broader OLED adoption and new technology could support future demand. OLEDX, "
            "announced in August, is a laboratory-stage architecture opportunity; it is not "
            "evidence of material commercial orders or a completed earnings recovery."
        ),
        financial_evidence=(
            "Q2 2026 revenue fell to $152.2m from $171.8m; net income remained positive at "
            "$49.4m, or $1.06 per share versus $1.41. June cash and short-term investments "
            "totalled approximately $471.3m. Management expected 2026 revenue around the "
            "lower end of its previous $630-670m range."
        ),
        risks=(
            "Demand and earnings were still weakening. Apparent Q2 royalty growth included "
            "a favourable $16.3m year-over-year change in catch-up adjustments, rather than "
            "clean volume-led growth. New architectures require customer adoption; competition "
            "and contract economics can erode the value of existing technology."
        ),
        watch_for=(
            "Material volumes, underlying royalties excluding catch-ups, customer qualification "
            "and commercial adoption. Review current prices for stabilization rather than "
            "assuming a large historical drawdown establishes an entry."
        ),
        sources=(
            ResearchSource(
                "Q2 results, guidance and balance sheet", "2026-07-30",
                "https://ir.oled.com/newsroom/press-releases/press-release-details/2026/"
                "Universal-Display-Corporation-Announces-Second-Quarter-2026-Financial-Results/default.aspx",
            ),
            ResearchSource(
                "OLEDX research architecture", "2026-08-19",
                "https://ir.oled.com/newsroom/press-releases/press-release-details/2026/"
                "Universal-Display-Corporation-Unveils-OLEDX-A-Breakthrough-Technology-Platform"
                "-for-Driving-a-New-Era-of-OLED-Efficiency-and-Performance/default.aspx",
            ),
        ),
    ),
    IPTurnaroundCandidate(
        symbol="KLIC",
        name="Kulicke & Soffa",
        sector="Semiconductor manufacturing equipment",
        tier="More-confirmed recovery",
        ip_case=(
            "Precision bonding and advanced-packaging systems rely on process know-how, "
            "yield and throughput. Fluxless thermocompression bonding is a concrete technology "
            "route into advanced logic, high-bandwidth memory and co-packaged optics."
        ),
        recovery_case=(
            "An equipment-cycle recovery and advanced-packaging adoption provide operating "
            "confirmation. This is a technology-transition comparison, not an undiscovered "
            "business whose recovery has yet to begin."
        ),
        financial_evidence=(
            "Fiscal Q3 ended July 4, 2026: revenue $330.4m versus $148.4m a year earlier, "
            "GAAP net income $57.4m and operating cash flow $45.2m. Cash and short-term "
            "investments were approximately $516.6m. Q4 revenue guidance was $375m +/- $20m."
        ),
        risks=(
            "Semiconductor-equipment demand is cyclical and competing assembly approaches "
            "may limit adoption. Nine-month operating cash flow was only $46.6m versus $105.0m "
            "previously as receivables and inventories increased. A strong quarter is not "
            "proof that cash conversion or demand is durable."
        ),
        watch_for=(
            "Customer adoption, orders, working-capital conversion and capacity execution. "
            "Assess a current pullback against sustainable earnings, not peak-cycle forecasts."
        ),
        sources=(
            ResearchSource(
                "Fiscal Q3 results and Q4 guidance", "2026-08-05",
                "https://investor.kns.com/2026-08-05-Kulicke-Soffa-Reports-Third-Quarter-2026-Results",
            ),
            ResearchSource(
                "Advanced-packaging technology announcement", "2026-09-01",
                "https://investor.kns.com/2026-09-01-Kulicke-Soffa-Advances-AI-Infrastructure"
                "-Through-Co-Packaged-Optics-CPO-and-Advanced-Packaging-Leadership",
            ),
        ),
    ),
    IPTurnaroundCandidate(
        symbol="PACB",
        name="PacBio",
        sector="Life-science instruments",
        tier="High-risk watchlist",
        ip_case=(
            "HiFi long-read sequencing instruments, SMRT consumables and analysis software "
            "form a genuine product platform. Valuable technology does not by itself ensure "
            "that current equity holders benefit from commercialization."
        ),
        recovery_case=(
            "New chemistry, consumables adoption, a large sequencing project and cost "
            "reductions could improve economics. A larger contribution from the Basecamp "
            "project was expected in 2027, not immediately."
        ),
        financial_evidence=(
            "Q2 2026 revenue was $39.0m versus $39.8m, with a GAAP net loss of $44.7m. "
            "Cash and investments were $236.9m, down from $276.0m in March. Debt principal "
            "was $641m: $200m due in 2029 and $441m in 2030."
        ),
        risks=(
            "Cash-flow breakeven was delayed to 2028 and full-year revenue guidance was cut. "
            "Management said existing resources could fund its plan, but adoption or cost "
            "misses could require further financing and dilution. This is not a claim of "
            "imminent insolvency, nor a low-risk balance sheet."
        ),
        watch_for=(
            "Quarterly cash burn versus the funding plan, realized cost savings, reagent "
            "adoption and sequencing-project revenue. Keep this separate from the core "
            "research candidates until financing and execution risks are better resolved."
        ),
        sources=(
            ResearchSource(
                "Q2 results and revised revenue outlook", "2026-08-05",
                "https://investor.pacificbiosciences.com/news-releases/news-release-details/"
                "pacbio-announces-second-quarter-2026-financial-results",
            ),
            ResearchSource(
                "Prepared remarks: funding and breakeven assumptions", "2026-08-05",
                "https://investor.pacificbiosciences.com/static-files/"
                "bda38067-d3f4-4c0e-bf02-4db571716fdd",
            ),
            ResearchSource(
                "Q2 filing: debt and liquidity", "2026-08-06",
                "https://investor.pacificbiosciences.com/node/16671/html",
            ),
        ),
    ),
)
