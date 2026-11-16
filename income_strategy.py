"""Pure composition of infrastructure screens and ADR trailing-cash evidence."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite, nan
from numbers import Integral
from typing import Any

import pandas as pd


INCOME_EVIDENCE_FIELDS = frozenset({
    "IncomeStrategies", "InfrastructureMember", "ADRMember",
    "InfrastructureStatus", "InfrastructureReason", "ADRStatus", "ADRReason",
    "InfrastructureYieldPercent", "ADRYieldPercent",
    "InfrastructurePriceDate", "InfrastructureCurrency", "IncomeIncludedVia",
    "DividendCoverageRatio", "CoverageBasis", "DistanceToFiveYearHigh",
    "ExclusionReason", "Source", "AccessStatus",
})

_ADR_METADATA = ("Country", "Overview", "ResearchNotes", "ResearchSource")
_ADR_DETAILS = (
    "Price", "TTMCash", "PriceDate", "WindowStart", "DividendCount",
    "LastExDate", "FetchedAt", "LiveSource",
)
_COLUMNS = (
    "Symbol", "Ticker", "Name", "IncomeStrategies",
    "InfrastructureMember", "ADRMember", "InfrastructureStatus",
    "InfrastructureReason", "ADRStatus", "ADRReason",
    "InfrastructureYieldPercent", "ADRYieldPercent", "IncomeIncludedVia",
    "InfrastructurePriceDate", "InfrastructureCurrency",
    "Region", "Type", "MarketStructure", "Source",
    "ListingMarket", "AccessStatus", "AccessNote", "AccessSource", "IBKRExchange",
    "DividendCoverageRatio", "CoverageBasis", "DistanceToFiveYearHigh",
    "ExclusionReason",
    *_ADR_METADATA, *_ADR_DETAILS,
)
_STRATEGIES = ("All income candidates", "Infrastructure", "ADRs")
_SORTS = {
    "Company": "Name",
    "Infrastructure forward yield": "InfrastructureYieldPercent",
    "ADR TTM yield": "ADRYieldPercent",
}


def _number(value: Any) -> float:
    if pd.api.types.is_bool(value):
        return nan
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return nan
    return result if isfinite(result) else nan


def _text(value: Any, fallback: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _index_rows(rows: list[dict], label: str) -> dict[str, dict]:
    indexed = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"{label} must contain mapping rows.")
        symbol = _text(row.get("Symbol")).upper()
        if not symbol:
            raise ValueError(f"{label} contains a missing or invalid Symbol.")
        if symbol in indexed:
            raise ValueError(f"{label} contains duplicate Symbol {symbol}.")
        indexed[symbol] = {**row, "Symbol": symbol}
    return indexed


def _responses(catalog: dict, rows: list[dict], errors: list[dict], label: str):
    values = _index_rows(rows, f"{label} rows")
    failures = _index_rows(errors, f"{label} errors")
    outside = (values.keys() | failures.keys()) - catalog.keys()
    if outside:
        raise ValueError(f"{label} response outside catalog: {', '.join(sorted(outside))}.")
    conflicts = values.keys() & failures.keys()
    if conflicts:
        raise ValueError(
            f"{label} has duplicate responses in rows and errors: "
            f"{', '.join(sorted(conflicts))}."
        )
    return values, failures


def _infrastructure_assessment(
    catalog: dict, row: dict | None, error: dict | None,
) -> tuple[str, str]:
    access = _text(catalog.get("AccessStatus"))
    note = _text(catalog.get("AccessNote"))
    if access not in ("Supported venue", "Restricted venue"):
        reason = f"{access or 'Unverified venue'}: {note or 'Venue access has not been verified.'}"
        if error is not None:
            reason += f" {_text(error.get('Error'), 'Infrastructure data unavailable.')}"
        return "Not screened", reason

    disclosure = f" Restricted venue: {note or 'Account-specific access requires verification.'}" \
        if access == "Restricted venue" else ""
    if error is not None:
        return "Unavailable", _text(error.get("Error"), "Infrastructure data unavailable.") + disclosure
    if row is None:
        return "Unavailable", "Unknown: no infrastructure assessment returned." + disclosure

    values = (
        _number(row.get("DividendYield")),
        _number(row.get("DividendCoverageRatio")),
        _number(row.get("DistanceToFiveYearHigh")),
    )
    unavailable = []
    failures = []
    for value, missing_reason, fails, failure_reason in (
        (values[0], "Forward yield unavailable", values[0] <= 4.0, "Forward yield must exceed 4%"),
        (values[1], "Payout / coverage unavailable", values[1] > 0.80, "Payout / coverage exceeds 80%"),
        (values[2], "Five-year price distance unavailable", values[2] > -0.05,
         "Price is less than 5% below five-year high"),
    ):
        if not isfinite(value):
            unavailable.append(missing_reason)
        elif fails:
            failures.append(failure_reason)
    if unavailable or failures:
        reasons = [_text(row.get("ExclusionReason"))]
        reasons.extend(reason for reason in unavailable + failures if reason not in reasons[0])
        return (
            "Unavailable" if unavailable else "Fail",
            "; ".join(reason for reason in reasons if reason) + disclosure,
        )
    return "Pass", "Meets infrastructure financial criteria." + disclosure


def build_income_candidates(
    infrastructure_catalog: list[dict],
    infrastructure_rows: list[dict],
    infrastructure_errors: list[dict],
    adr_catalog: pd.DataFrame,
    adr_rows: list[dict],
    adr_errors: list[dict],
) -> pd.DataFrame:
    """Union catalog listings, never issuers, retaining unavailable rows for audit.

    Catalog metadata is authoritative. Infrastructure supplies the shared Name;
    ADR supplies its display Ticker (e.g. PBR.A), never the join key. Only the two
    original yield fields are renamed, to explicit percentage-point columns;
    the redundant generic Qualifies flag is omitted from the combined output.
    Unknown/non-finite yields remain NaN. Infrastructure assessment uses the
    original >4%, <=80%, <=-5% rules and requires all three finite metrics.
    IncomeIncludedVia is blank until a view is selected by the filter function.
    """
    if not isinstance(adr_catalog, pd.DataFrame):
        raise ValueError("ADR catalog must be a DataFrame.")
    if adr_catalog.columns.duplicated().any():
        raise ValueError("ADR catalog contains duplicate columns.")
    if len(adr_catalog) and "Symbol" not in adr_catalog.columns:
        raise ValueError("ADR catalog is missing Symbol.")
    infrastructure = _index_rows(infrastructure_catalog, "Infrastructure catalog")
    adrs = _index_rows(adr_catalog.to_dict("records"), "ADR catalog")
    infrastructure_data, infrastructure_failures = _responses(
        infrastructure, infrastructure_rows, infrastructure_errors, "Infrastructure",
    )
    adr_data, adr_failures = _responses(adrs, adr_rows, adr_errors, "ADR")

    records = []
    for symbol in dict.fromkeys([*infrastructure, *adrs]):
        infra_member, adr_member = symbol in infrastructure, symbol in adrs
        infra_catalog_row, adr_catalog_row = infrastructure.get(symbol, {}), adrs.get(symbol, {})
        infra_row, adr_row = infrastructure_data.get(symbol), adr_data.get(symbol)
        record = dict.fromkeys(_COLUMNS)
        # Project ADR fields explicitly so they cannot replace infrastructure evidence.
        record.update(infra_row or {})
        record.update(infra_catalog_row)
        record.pop("DividendYield", None)
        record.pop("YieldPercent", None)
        record.pop("Qualifies", None)
        if adr_member:
            record.update({field: adr_catalog_row.get(field) for field in _ADR_METADATA})
        if adr_row is not None:
            record.update({field: adr_row.get(field) for field in _ADR_DETAILS})
        record.update({
            "Symbol": symbol,
            "Ticker": _text(adr_catalog_row.get("Ticker"), symbol).upper(),
            "Name": _text(infra_catalog_row.get("Name"), _text(adr_catalog_row.get("Name"), symbol)),
            "IncomeStrategies": (
                "Infrastructure + ADR" if infra_member and adr_member
                else "Infrastructure" if infra_member else "ADR"
            ),
            "InfrastructureMember": infra_member,
            "ADRMember": adr_member,
            "InfrastructureYieldPercent": _number((infra_row or {}).get("DividendYield")),
            "ADRYieldPercent": _number((adr_row or {}).get("YieldPercent")),
            "IncomeIncludedVia": "",
        })
        if infra_member:
            status, reason = _infrastructure_assessment(
                infra_catalog_row, infra_row, infrastructure_failures.get(symbol),
            )
        else:
            status, reason = "Not in strategy", "Not in the infrastructure strategy."
        record["InfrastructureStatus"], record["InfrastructureReason"] = status, reason

        if not adr_member:
            status, reason = "Not in strategy", "Not in the ADR strategy."
        elif symbol in adr_failures:
            status, reason = "Unavailable", _text(
                adr_failures[symbol].get("Error"), "ADR dividend data unavailable.",
            )
        elif adr_row is None:
            status, reason = "Unavailable", "Unknown: no ADR dividend data returned."
        elif not isfinite(record["ADRYieldPercent"]) or record["ADRYieldPercent"] < 0:
            status, reason = "Unavailable", "ADR trailing cash yield unavailable or invalid."
        else:
            status, reason = "Available", "ADR trailing cash yield available."
        record["ADRStatus"], record["ADRReason"] = status, reason
        records.append(record)

    extra_columns = dict.fromkeys(
        field for record in records for field in record if field not in _COLUMNS
    )
    result = pd.DataFrame.from_records(records, columns=[*_COLUMNS, *extra_columns])
    return result.astype({
        "InfrastructureMember": bool, "ADRMember": bool,
        "InfrastructureYieldPercent": float, "ADRYieldPercent": float,
    })


def filter_income_candidates(
    frame: pd.DataFrame,
    *,
    strategy: str = "All income candidates",
    infrastructure_region: str = "All regions",
    adr_country: str = "All countries",
    minimum_adr_yield: float = 0.0,
    show_excluded_infrastructure: bool = False,
    sort_by: str = "Company",
    limit: int | None = None,
) -> pd.DataFrame:
    """Select the OR of eligible legs; geography and yield never cross legs.

    Excluded infrastructure is review evidence, not an eligible infrastructure
    leg. An overlap admitted through ADR alone therefore says ADR even when
    infrastructure review is enabled. Limits must be positive integers or None.
    Active region/country options come from corresponding catalog members in
    frame. Retained selectors on inactive or empty legs cannot exclude the other
    leg, including when a scoped catalog could not be loaded.
    """
    if not isinstance(strategy, str) or strategy not in _STRATEGIES:
        raise ValueError(f"Unsupported income strategy: {strategy!r}.")
    if not isinstance(sort_by, str) or sort_by not in _SORTS:
        raise ValueError(f"Unsupported income sort: {sort_by!r}.")
    minimum = _number(minimum_adr_yield)
    if not isfinite(minimum) or minimum < 0:
        raise ValueError("minimum_adr_yield must be a finite non-negative number.")
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, Integral) or limit <= 0
    ):
        raise ValueError("limit must be a positive integer or None.")
    if not pd.api.types.is_bool(show_excluded_infrastructure):
        raise ValueError("show_excluded_infrastructure must be a boolean.")
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Income candidates must be a DataFrame.")
    if frame.columns.duplicated().any():
        raise ValueError("Income candidates contain duplicate columns.")
    missing = set(_COLUMNS).difference(frame.columns)
    if missing and not frame.empty:
        raise ValueError(f"Income candidates are missing columns: {', '.join(sorted(missing))}.")
    extras = [field for field in frame.columns if field not in _COLUMNS]
    working = frame.reindex(columns=[*_COLUMNS, *extras]).copy()
    working = working.reset_index(drop=True)
    if working.empty:
        working = working.astype({
            "InfrastructureMember": bool, "ADRMember": bool,
            "InfrastructureYieldPercent": float, "ADRYieldPercent": float,
        })
    symbols = [_text(value).upper() for value in working["Symbol"]]
    if any(not value for value in symbols) or len(set(symbols)) != len(symbols):
        raise ValueError("Income candidates require unique, non-empty Symbols.")
    working["Symbol"] = pd.Series(symbols, index=working.index, dtype=object)

    infra_scope = working["InfrastructureMember"].eq(True) & (strategy != "ADRs")
    adr_scope = working["ADRMember"].eq(True) & (strategy != "Infrastructure")
    for selection, all_option, field, scope in (
        (infrastructure_region, "All regions", "Region", infra_scope),
        (adr_country, "All countries", "Country", adr_scope),
    ):
        choices = working.loc[scope, field].dropna().tolist()
        if (
            not isinstance(selection, str) or not selection.strip()
            or (scope.any() and selection != all_option and selection not in choices)
        ):
            raise ValueError(f"Unsupported {field} option: {selection!r}.")
    if infrastructure_region != "All regions":
        infra_scope &= working["Region"].eq(infrastructure_region)
    if adr_country != "All countries":
        adr_scope &= working["Country"].eq(adr_country)
    infrastructure_yield = working["InfrastructureYieldPercent"].map(_number)
    adr_yield = working["ADRYieldPercent"].map(_number)
    infra_pass = (
        infra_scope & working["InfrastructureStatus"].eq("Pass")
        & infrastructure_yield.gt(4.0)
    )
    adr_pass = adr_scope & working["ADRStatus"].eq("Available") & adr_yield.ge(minimum)
    infra_review = (
        infra_scope & show_excluded_infrastructure
        & working["InfrastructureStatus"].isin(("Fail", "Unavailable", "Not screened"))
    )
    working["IncomeIncludedVia"] = pd.Series("", index=working.index, dtype=object)
    working.loc[infra_review, "IncomeIncludedVia"] = "Infrastructure review only"
    working.loc[infra_pass, "IncomeIncludedVia"] = "Infrastructure"
    working.loc[adr_pass, "IncomeIncludedVia"] = "ADR"
    working.loc[infra_pass & adr_pass, "IncomeIncludedVia"] = "Infrastructure + ADR"
    selected = working.loc[infra_pass | adr_pass | infra_review].copy()

    primary = (
        selected["Name"].fillna("").astype(str).str.casefold()
        if sort_by == "Company" else selected[_SORTS[sort_by]].map(_number)
    )
    sort_keys = pd.DataFrame({
        "primary": primary,
        "ticker": selected["Ticker"].fillna("").astype(str).str.upper(),
        "symbol": selected["Symbol"],
    })
    ordered = sort_keys.sort_values(
        ["primary", "ticker", "symbol"],
        ascending=[sort_by == "Company", True, True], na_position="last", kind="stable",
    ).index
    return selected.loc[ordered].iloc[:limit].reset_index(drop=True)
