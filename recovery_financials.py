"""Statement-based recovery checks; no prices, EBITDA proxies, or paid APIs.

The pure analyzer accepts Yahoo-style statements (line items in rows, period-end
dates in columns). Quarterly columns must be discrete quarters, not YTD flows;
annual columns must represent full fiscal years, not trailing or stub periods.
Ratios are fractions and monetary values are unscaled financial-reporting units.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Mapping
from urllib.parse import quote

import pandas as pd

from stock_data import (
    MARKET_DATA_EXCEPTIONS,
    StockDataError,
    get_company_info,
    get_statement_history,
)


PROFITABILITY_RULE = (
    "Pass requires operating margin (sum of operating income / sum of revenue) "
    "to increase AND free cash flow to increase, latest four complete quarters "
    "versus the prior four; negative but shrinking cash burn qualifies. "
    "If eight complete comparable quarters are unavailable, compare the latest "
    "full fiscal year with the prior full fiscal year, explicitly as a fallback. "
    "Equal values do not pass."
)
DELEVERAGING_RULE = (
    "Pass requires actual gross debt AND net debt to decline year over year "
    "AND latest-period free cash flow > 0. Use same-date debt and cash balances "
    "at the latest FCF period end and the comparable prior-year end "
    "(up to seven days' fiscal-calendar drift). Latest FCF is the sum of four "
    "complete quarters, or a full fiscal year if quarterly evidence is incomplete. "
    "Net debt is gross debt minus cash and cash equivalents; EBITDA improvement "
    "alone does not qualify. Equal debt or zero FCF does not pass."
)
FRESHNESS_RULE = (
    "Latest quarterly ends older than 200 days or fiscal-year ends older than "
    "550 days are Unknown; future ends are Unknown."
)
LIMITATIONS = (
    "Yahoo Finance/yfinance statements are provider data, not independently "
    "reconciled audited filings. Annual fallback is fiscal-year versus fiscal-year, "
    "not rolling TTM. Quarterly inputs must be discrete quarters and annual "
    "inputs full fiscal years; stub/YTD durations cannot be verified from end "
    "dates alone. Consecutive quarter ends must be 80-105 days apart, with "
    "corresponding year-ago ends within seven days of their anniversary. "
    "All flows must have matching income/cash-flow dates for profitability. "
    "Debt and cash must share both snapshot dates and the same line-item "
    "definition across years; missing debt components are not assumed zero. "
    "FCF uses reported Free Cash Flow when complete, otherwise operating cash "
    "flow minus absolute capital expenditure (negative outflows or positive "
    "spending magnitudes); missing capex is not zero. Net debt subtracts only "
    "cash and cash equivalents, not short-term investments. Cash restrictions, "
    "lease treatment, historical reporting-currency changes, restatements, "
    "acquisitions, asset sales, dilution/equity issuance, refinancing and debt "
    "maturities are not verified. Positive FCF alongside debt declines does not "
    "establish that operations funded repayment or that repayment is sustainable. "
    "Generic tests are not applicable to non-equity instruments, financial "
    "companies or REITs. "
    "An as-of date controls freshness, not historical filing availability; this "
    "is not a point-in-time backtest. " + FRESHNESS_RULE
)


def _date(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("as_of must be a valid date.")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.normalize()


def _statement(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None:
        return pd.DataFrame()
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Financial statements must be pandas DataFrames or None.")
    result = frame.copy()
    result.columns = pd.to_datetime(
        result.columns, errors="coerce", utc=True, format="mixed"
    ).tz_convert(None).normalize()
    return result.loc[:, result.columns.notna()]


def _dates(frame: pd.DataFrame) -> list[pd.Timestamp]:
    return sorted(set(frame.columns), reverse=True)


def _values(
    frame: pd.DataFrame, dates: list[pd.Timestamp], labels: tuple[str, ...]
) -> tuple[list[float], str] | None:
    for label in labels:
        if list(frame.index).count(label) != 1:
            continue
        if any(list(frame.columns).count(end) != 1 for end in dates):
            continue
        values = pd.to_numeric(frame.loc[label, dates], errors="coerce")
        if values.isna().any():
            continue
        numbers = [float(value) for value in values]
        if all(math.isfinite(value) for value in numbers):
            return numbers, label
    return None


def _year_apart(latest: pd.Timestamp, prior: pd.Timestamp) -> bool:
    return abs(((latest - pd.DateOffset(years=1)) - prior).days) <= 7


def _quarters(dates: list[pd.Timestamp]) -> bool:
    return all(
        80 <= (latest - prior).days <= 105
        for latest, prior in zip(dates, dates[1:])
    )


def _fcf(
    cashflow: pd.DataFrame, dates: list[pd.Timestamp]
) -> tuple[list[float], str] | None:
    reported = _values(cashflow, dates, ("Free Cash Flow",))
    if reported is not None:
        return reported
    operating = _values(
        cashflow, dates, ("Operating Cash Flow", "Total Cash From Operating Activities")
    )
    capex = _values(
        cashflow, dates, ("Capital Expenditure", "Capital Expenditure Reported")
    )
    if operating is None or capex is None:
        return None
    numbers = [cash - abs(spend) for cash, spend in zip(operating[0], capex[0])]
    if not all(math.isfinite(value) for value in numbers):
        return None
    return numbers, f"{operating[1]} minus absolute {capex[1]}"


def _profitability_period(
    income: pd.DataFrame, cashflow: pd.DataFrame, quarterly: bool
) -> tuple[dict[str, Any] | None, str]:
    count = 8 if quarterly else 2
    dates = sorted(set(income.columns) | set(cashflow.columns), reverse=True)[:count]
    if len(dates) < count:
        return None, f"Need {count} matching complete periods; found {len(dates)} dates."
    if quarterly:
        comparable = _quarters(dates) and all(
            _year_apart(dates[index], dates[index + 4]) for index in range(4)
        )
    else:
        comparable = _year_apart(dates[0], dates[1])
    if not comparable:
        return None, "Latest periods are not consecutive comparable quarters/fiscal years."
    revenue = _values(income, dates, ("Total Revenue", "Operating Revenue"))
    operating = _values(income, dates, ("Operating Income",))
    fcf = _fcf(cashflow, dates)
    if revenue is None or operating is None or fcf is None:
        return None, (
            "Latest periods lack matching dates or complete, finite revenue, "
            "Operating Income, and FCF (or operating cash flow plus capex); "
            "duplicate periods/line items are not used."
        )
    split = 4 if quarterly else 1
    totals = {
        "revenue_latest": sum(revenue[0][:split]),
        "revenue_prior": sum(revenue[0][split:]),
        "operating_latest": sum(operating[0][:split]),
        "operating_prior": sum(operating[0][split:]),
        "fcf_latest": sum(fcf[0][:split]),
        "fcf_prior": sum(fcf[0][split:]),
    }
    if (
        any(value < 0 for value in revenue[0])
        or totals["revenue_latest"] <= 0
        or totals["revenue_prior"] <= 0
        or not all(math.isfinite(value) for value in totals.values())
    ):
        return None, "Revenue must be nonnegative with positive period totals; totals must be finite."
    totals["margin_latest"] = totals["operating_latest"] / totals["revenue_latest"]
    totals["margin_prior"] = totals["operating_prior"] / totals["revenue_prior"]
    if not all(math.isfinite(totals[key]) for key in ("margin_latest", "margin_prior")):
        return None, "Operating margins are not finite."
    return {
        **totals,
        "dates": dates,
        "latest": dates[0],
        "prior": dates[split],
        "quarterly": quarterly,
        "fcf_basis": fcf[1],
    }, ""


def _debt_values(
    balance: pd.DataFrame, dates: list[pd.Timestamp]
) -> tuple[dict[str, Any] | None, str]:
    debt = _values(balance, dates, ("Total Debt",))
    if debt is None:
        for current_label, long_label in (
            (
                "Current Debt And Capital Lease Obligation",
                "Long Term Debt And Capital Lease Obligation",
            ),
            ("Current Debt", "Long Term Debt"),
        ):
            current = _values(balance, dates, (current_label,))
            long_term = _values(balance, dates, (long_label,))
            if current is not None and long_term is not None:
                if any(value < 0 for value in current[0] + long_term[0]):
                    continue
                debt = (
                    [short + long for short, long in zip(current[0], long_term[0])],
                    f"{current_label} + {long_label}",
                )
                break
    cash = _values(balance, dates, ("Cash And Cash Equivalents",))
    if debt is None or cash is None:
        return None, (
            "Both same-date snapshots need gross debt and cash and cash equivalents "
            "on a consistent basis; missing gross debt/components or cash is not zero."
        )
    if any(value < 0 or not math.isfinite(value) for value in debt[0] + cash[0]):
        return None, "Gross debt and cash balances must be finite and nonnegative."
    net = [gross - money for gross, money in zip(debt[0], cash[0])]
    return {
        "gross_latest": debt[0][0],
        "gross_prior": debt[0][1],
        "cash_latest": cash[0][0],
        "cash_prior": cash[0][1],
        "net_latest": net[0],
        "net_prior": net[1],
        "gross_basis": debt[1],
    }, ""


def _deleveraging_period(
    cashflow: pd.DataFrame, balance: pd.DataFrame, quarterly: bool
) -> tuple[dict[str, Any] | None, str]:
    count = 4 if quarterly else 1
    dates = _dates(cashflow)[:count]
    balance_dates = _dates(balance)
    if len(dates) < count or len(balance_dates) < 2:
        return None, f"Need {count} complete FCF periods and comparable year-ago balance snapshots."
    if dates[0] != balance_dates[0]:
        return None, "Latest cash-flow and balance-sheet ends do not match; no mismatched snapshots used."
    if quarterly:
        priors = [end for end in balance_dates[1:] if _year_apart(dates[0], end)]
        if not _quarters(dates) or len(priors) != 1:
            return None, "Need four consecutive quarters and one comparable year-ago balance snapshot."
        prior = priors[0]
    else:
        prior = balance_dates[1]
        if not _year_apart(dates[0], prior):
            return None, "Latest annual balance snapshots are not comparable consecutive fiscal years."
    fcf = _fcf(cashflow, dates)
    if fcf is None or not math.isfinite(sum(fcf[0])):
        return None, "Latest FCF periods are incomplete/nonfinite; missing capex or FCF is not zero."
    debt, reason = _debt_values(balance, [dates[0], prior])
    if debt is None:
        return None, reason
    return {
        **debt,
        "latest": dates[0],
        "prior": prior,
        "quarterly": quarterly,
        "fcf_latest": sum(fcf[0]),
        "fcf_basis": fcf[1],
    }, ""


def _unsuitable(info: Mapping[str, Any]) -> bool:
    quote_type = str(info.get("quoteType") or "").strip().upper()
    if quote_type and quote_type != "EQUITY":
        return True
    sector = str(info.get("sector") or "").casefold().strip()
    industry = str(info.get("industry") or "").casefold()
    return sector in {"financial", "financials", "financial services"} or any(
        word in industry
        for word in (
            "reit", "real estate investment trust", "banks", "banking", "insurance",
            "capital markets", "credit services", "asset management", "mortgage finance",
            "financial conglomerates",
        )
    )


def _freshness(period: dict[str, Any], as_of: pd.Timestamp) -> tuple[int, str]:
    age = (as_of - period["latest"]).days
    limit = 200 if period["quarterly"] else 550
    if age < 0:
        return age, "Statement end is in the future."
    if age > limit:
        return age, f"Latest statement end is stale ({age} days old; limit {limit} days)."
    return age, ""


def _amount(value: float, currency: str | None) -> str:
    return f"{currency or 'reporting-currency units'} {value:,.2f}"


def _basis(period: dict[str, Any], profitability: bool = False) -> str:
    if period["quarterly"]:
        return (
            "Latest four quarters vs prior four quarters"
            if profitability else "Quarterly YoY snapshots; latest four-quarter FCF"
        )
    return "Fiscal year vs prior fiscal year (fallback)"


def _empty_result(symbol: str, info: Mapping[str, Any], as_of: pd.Timestamp) -> dict[str, Any]:
    currency = str(info.get("financialCurrency") or "").strip().upper() or None
    base_url = f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}/" if symbol else None
    result: dict[str, Any] = {
        "ProfitabilityStatus": "Unknown",
        "ProfitabilityReason": "",
        "DeleveragingStatus": "Unknown",
        "DeleveragingReason": "",
        "FinancialSymbol": symbol or None,
        "FinancialCurrency": currency,
        "FinancialAsOf": as_of.date().isoformat(),
        "FinancialSource": "Yahoo Finance via yfinance financial statements",
        "FinancialSourceURL": base_url,
        "FinancialIncomeSourceURL": f"{base_url}financials/" if base_url else None,
        "FinancialCashFlowSourceURL": f"{base_url}cash-flow/" if base_url else None,
        "FinancialBalanceSourceURL": f"{base_url}balance-sheet/" if base_url else None,
        "FinancialSector": str(info.get("sector") or "").strip() or None,
        "FinancialIndustry": str(info.get("industry") or "").strip() or None,
        "FinancialQuoteType": str(info.get("quoteType") or "").strip().upper() or None,
        "FinancialLimitations": LIMITATIONS,
    }
    for key in (
        "FinancialPeriodBasis", "FinancialPeriodEnd", "FinancialPriorPeriodEnd",
        "FinancialLatestQuarterEnds", "FinancialPriorQuarterEnds",
        "FinancialStatementAgeDays", "FinancialFallbackReason",
        "OperatingRevenueLatest", "OperatingRevenuePrior",
        "OperatingIncomeLatest", "OperatingIncomePrior",
        "OperatingMarginLatest", "OperatingMarginPrior", "OperatingMarginChange",
        "FreeCashFlowLatest", "FreeCashFlowPrior", "FreeCashFlowChange", "FreeCashFlowBasis",
        "FinancialDebtPeriodBasis", "FinancialDebtPeriodEnd", "FinancialDebtPriorPeriodEnd",
        "FinancialDebtStatementAgeDays", "FinancialDebtFallbackReason",
        "GrossDebtLatest", "GrossDebtPrior", "GrossDebtChange", "GrossDebtBasis",
        "NetDebtLatest", "NetDebtPrior", "NetDebtChange", "NetDebtBasis",
        "FinancialCashLatest", "FinancialCashPrior",
        "FreeCashFlowDeleveragingLatest", "FreeCashFlowDeleveragingBasis",
    ):
        result[key] = None
    return result


def analyze_financial_recovery(
    income: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    balance: pd.DataFrame | None,
    *,
    annual_income: pd.DataFrame | None = None,
    annual_cashflow: pd.DataFrame | None = None,
    annual_balance: pd.DataFrame | None = None,
    info: Mapping[str, Any] | None = None,
    symbol: str = "",
    as_of: date | datetime | pd.Timestamp | str | None = None,
) -> dict[str, Any]:
    """Analyze quarterly statements with independent, explicit annual fallbacks.

    ``info`` supplies financialCurrency (never the quote/trading currency),
    sector and industry. A provided non-EQUITY quoteType is Not applicable;
    missing quoteType does not block these checks. Unknown reporting currency
    or sector classification prevents Pass/Fail. Dates alone cannot establish
    when a filing was available.
    Missing/nonfinite/ambiguous data stays Unknown, never an assumed zero.
    """
    info = info if info is not None else {}
    reference = _date(as_of if as_of is not None else pd.Timestamp.now(tz="UTC"))
    result = _empty_result(symbol.strip().upper(), info, reference)
    if _unsuitable(info):
        if result["FinancialQuoteType"] and result["FinancialQuoteType"] != "EQUITY":
            explanation = (
                f"Generic company recovery tests are Not applicable to quoteType "
                f"{result['FinancialQuoteType']}; these tests require an equity."
            )
        else:
            explanation = (
                "Generic operating-margin/FCF and corporate-debt tests are Not applicable "
                "to financial companies or REITs; use sector-specific measures."
            )
        result.update(
            ProfitabilityStatus="Not applicable",
            ProfitabilityReason=f"{explanation} {PROFITABILITY_RULE}",
            DeleveragingStatus="Not applicable",
            DeleveragingReason=f"{explanation} {DELEVERAGING_RULE}",
        )
        return result

    income, cashflow, balance = map(_statement, (income, cashflow, balance))
    annual_income, annual_cashflow, annual_balance = map(
        _statement, (annual_income, annual_cashflow, annual_balance)
    )
    metadata_reason = ""
    if not result["FinancialCurrency"]:
        metadata_reason = "Financial reporting currency is unavailable (quote currency is not substituted)."
    if not (result["FinancialSector"] or result["FinancialIndustry"]):
        metadata_reason += " Sector/industry classification is unavailable; generic-test suitability is unverified."
    metadata_reason = metadata_reason.strip()
    currency = result["FinancialCurrency"]

    profit, quarterly_reason = _profitability_period(income, cashflow, True)
    if profit is None:
        result["FinancialFallbackReason"] = quarterly_reason
        profit, annual_reason = _profitability_period(annual_income, annual_cashflow, False)
        if profit is None:
            result["ProfitabilityReason"] = (
                f"Quarterly evidence unavailable: {quarterly_reason} "
                f"Fiscal-year fallback unavailable: {annual_reason} "
                f"{metadata_reason} {PROFITABILITY_RULE} {FRESHNESS_RULE}"
            ).strip()
    if profit is not None:
        age, stale = _freshness(profit, reference)
        margin_change = profit["margin_latest"] - profit["margin_prior"]
        fcf_change = profit["fcf_latest"] - profit["fcf_prior"]
        result.update({
            "FinancialPeriodBasis": _basis(profit, profitability=True),
            "FinancialPeriodEnd": profit["latest"].date().isoformat(),
            "FinancialPriorPeriodEnd": profit["prior"].date().isoformat(),
            "FinancialStatementAgeDays": age,
            "OperatingRevenueLatest": profit["revenue_latest"],
            "OperatingRevenuePrior": profit["revenue_prior"],
            "OperatingIncomeLatest": profit["operating_latest"],
            "OperatingIncomePrior": profit["operating_prior"],
            "OperatingMarginLatest": profit["margin_latest"],
            "OperatingMarginPrior": profit["margin_prior"],
            "OperatingMarginChange": margin_change if math.isfinite(margin_change) else None,
            "FreeCashFlowLatest": profit["fcf_latest"],
            "FreeCashFlowPrior": profit["fcf_prior"],
            "FreeCashFlowChange": fcf_change if math.isfinite(fcf_change) else None,
            "FreeCashFlowBasis": profit["fcf_basis"],
        })
        if profit["quarterly"]:
            result["FinancialLatestQuarterEnds"] = ", ".join(
                end.date().isoformat() for end in reversed(profit["dates"][:4])
            )
            result["FinancialPriorQuarterEnds"] = ", ".join(
                end.date().isoformat() for end in reversed(profit["dates"][4:])
            )
        if not (stale or metadata_reason):
            result["ProfitabilityStatus"] = (
                "Pass" if profit["margin_latest"] > profit["margin_prior"]
                and profit["fcf_latest"] > profit["fcf_prior"] else "Fail"
            )
        fallback = (
            f" Quarterly evidence incomplete: {quarterly_reason}"
            if not profit["quarterly"] else ""
        )
        result["ProfitabilityReason"] = (
            f"{_basis(profit, profitability=True)} ending {result['FinancialPeriodEnd']} "
            f"versus {result['FinancialPriorPeriodEnd']}: operating margin "
            f"{profit['margin_prior']:.2%} -> {profit['margin_latest']:.2%}; "
            f"FCF {_amount(profit['fcf_prior'], currency)} -> "
            f"{_amount(profit['fcf_latest'], currency)} ({profit['fcf_basis']}). "
            f"{stale} {metadata_reason}{fallback} {PROFITABILITY_RULE} {FRESHNESS_RULE}"
        ).strip()

    debt, quarterly_reason = _deleveraging_period(cashflow, balance, True)
    if debt is None:
        result["FinancialDebtFallbackReason"] = quarterly_reason
        debt, annual_reason = _deleveraging_period(annual_cashflow, annual_balance, False)
        if debt is None:
            result["DeleveragingReason"] = (
                f"Quarterly evidence unavailable: {quarterly_reason} "
                f"Fiscal-year fallback unavailable: {annual_reason} "
                f"{metadata_reason} {DELEVERAGING_RULE} {FRESHNESS_RULE} "
                "Asset sales, dilution and debt maturities are not verified; "
                "cash-funded repayment cannot be established."
            ).strip()
    if debt is not None:
        age, stale = _freshness(debt, reference)
        net_change = debt["net_latest"] - debt["net_prior"]
        result.update({
            "FinancialDebtPeriodBasis": _basis(debt),
            "FinancialDebtPeriodEnd": debt["latest"].date().isoformat(),
            "FinancialDebtPriorPeriodEnd": debt["prior"].date().isoformat(),
            "FinancialDebtStatementAgeDays": age,
            "GrossDebtLatest": debt["gross_latest"],
            "GrossDebtPrior": debt["gross_prior"],
            "GrossDebtChange": debt["gross_latest"] - debt["gross_prior"],
            "GrossDebtBasis": debt["gross_basis"],
            "NetDebtLatest": debt["net_latest"],
            "NetDebtPrior": debt["net_prior"],
            "NetDebtChange": net_change if math.isfinite(net_change) else None,
            "NetDebtBasis": "Gross debt minus Cash And Cash Equivalents",
            "FinancialCashLatest": debt["cash_latest"],
            "FinancialCashPrior": debt["cash_prior"],
            "FreeCashFlowDeleveragingLatest": debt["fcf_latest"],
            "FreeCashFlowDeleveragingBasis": debt["fcf_basis"],
        })
        if not (stale or metadata_reason):
            result["DeleveragingStatus"] = (
                "Pass" if debt["gross_latest"] < debt["gross_prior"]
                and debt["net_latest"] < debt["net_prior"]
                and debt["fcf_latest"] > 0 else "Fail"
            )
        fallback = (
            f" Quarterly evidence incomplete: {quarterly_reason}"
            if not debt["quarterly"] else ""
        )
        result["DeleveragingReason"] = (
            f"{_basis(debt)}, {result['FinancialDebtPeriodEnd']} versus "
            f"{result['FinancialDebtPriorPeriodEnd']}: gross debt "
            f"{_amount(debt['gross_prior'], currency)} -> {_amount(debt['gross_latest'], currency)} "
            f"({debt['gross_basis']}); net debt {_amount(debt['net_prior'], currency)} "
            f"-> {_amount(debt['net_latest'], currency)}; latest FCF "
            f"{_amount(debt['fcf_latest'], currency)} ({debt['fcf_basis']}). "
            f"{stale} {metadata_reason}{fallback} {DELEVERAGING_RULE} {FRESHNESS_RULE} "
            "Positive FCF and debt declines do not prove cash-funded repayment; "
            "asset sales, dilution, refinancing and debt maturities are not verified."
        ).strip()
    return result


def get_financial_recovery(
    symbol: str, *, info: Mapping[str, Any] | None = None,
    statement_loader: Callable[[str, str, str], pd.DataFrame] | None = None,
) -> dict[str, Any]:
    """Fetch public Yahoo statements, reusing supplied metadata and raw loader.

    Metadata is fetched only when ``info`` is None. Non-equity instruments and
    unsuitable sectors return the analyzer's Not applicable result without
    fetching statements. Annual statements are requested only for checks whose
    quarterly evidence is incomplete.
    """
    cleaned_symbol = symbol.strip().upper()
    if not cleaned_symbol:
        raise ValueError("Enter a ticker symbol.")
    if info is None:
        info = get_company_info(cleaned_symbol)
    if _unsuitable(info):
        return analyze_financial_recovery(None, None, None, info=info, symbol=cleaned_symbol)
    loader = statement_loader if statement_loader is not None else get_statement_history
    try:
        income = loader(cleaned_symbol, "income", "quarterly")
        cashflow = loader(cleaned_symbol, "cashflow", "quarterly")
        balance = loader(cleaned_symbol, "balance", "quarterly")
        result = analyze_financial_recovery(
            income, cashflow, balance, info=info, symbol=cleaned_symbol
        )
        needs_profitability = result["FinancialPeriodBasis"] is None
        needs_deleveraging = result["FinancialDebtPeriodBasis"] is None
        if needs_profitability or needs_deleveraging:
            result = analyze_financial_recovery(
                income, cashflow, balance,
                annual_income=loader(cleaned_symbol, "income", "annual") if needs_profitability else None,
                annual_cashflow=loader(cleaned_symbol, "cashflow", "annual"),
                annual_balance=loader(cleaned_symbol, "balance", "annual") if needs_deleveraging else None,
                info=info,
                symbol=cleaned_symbol,
            )
    except MARKET_DATA_EXCEPTIONS as exc:
        raise StockDataError(
            f"Financial recovery statements for {cleaned_symbol} could not be loaded: {exc}"
        ) from exc
    return result
