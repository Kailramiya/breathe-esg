"""
Utility Electricity CSV Parser

Format rationale (documented in SOURCES.md):
  We parse the CSV export from enterprise utility online portals (e.g. EDF,
  British Gas, E.ON). Most large UK enterprises have access to their utility
  provider's web portal, and the "Download usage data" button produces a
  semicolon- or comma-delimited CSV.

Key real-world complexities handled:
  1. Billing periods don't align with calendar months — a "January" bill might
     run Dec 22 – Jan 24. We store both period_start/period_end verbatim; we
     do NOT prorate across months (see TRADEOFFS.md).
  2. Units are inconsistent — some sites export kWh, some MWh, occasionally GJ.
     We normalise everything to kWh before applying the emission factor.
  3. Multiple meters per site — each row is one meter for one billing period.
     The site/account level is what the analyst sees in the dashboard.

Expected columns (flexible — header aliasing handles common variations):
  Account Number, Meter Serial, Site Name, Billing Period Start,
  Billing Period End, Consumption, Unit, Tariff Code, Cost (GBP)
"""

import csv
import io
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import IO

from api.emission_factors import (
    ELECTRICITY_FACTOR_KWH,
    ELECTRICITY_FACTOR_SOURCE,
    normalize_unit_to_canonical,
)

HEADER_MAP = {
    "ACCOUNT NUMBER":       "account_number",
    "ACCOUNT":              "account_number",
    "METER SERIAL":         "meter_id",
    "METER SERIAL NUMBER":  "meter_id",
    "METER ID":             "meter_id",
    "METER":                "meter_id",
    "SITE NAME":            "site_name",
    "SITE":                 "site_name",
    "LOCATION":             "site_name",
    "BILLING PERIOD START": "period_start",
    "PERIOD START":         "period_start",
    "START DATE":           "period_start",
    "FROM":                 "period_start",
    "BILLING PERIOD END":   "period_end",
    "PERIOD END":           "period_end",
    "END DATE":             "period_end",
    "TO":                   "period_end",
    "CONSUMPTION":          "consumption",
    "CONSUMPTION (KWH)":    "consumption",
    "USAGE":                "consumption",
    "ENERGY (KWH)":         "consumption",
    "UNIT":                 "unit",
    "UNITS":                "unit",
    "TARIFF CODE":          "tariff_code",
    "TARIFF":               "tariff_code",
    "COST (GBP)":           "cost_gbp",
    "COST":                 "cost_gbp",
    "AMOUNT":               "cost_gbp",
}

REQUIRED_FIELDS = {"site_name", "period_start", "period_end", "consumption", "unit"}


def _parse_date(value: str) -> date | None:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.strip().replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def _normalise_headers(raw_headers: list[str]) -> dict[int, str]:
    mapping = {}
    for idx, h in enumerate(raw_headers):
        canonical = HEADER_MAP.get(h.strip().upper())
        if canonical:
            mapping[idx] = canonical
    return mapping


def parse_utility_file(file_obj: IO) -> list[dict]:
    """
    Parse a utility portal CSV export.

    Returns list of result dicts per row, each with:
      row_number, raw_data, status, errors, record (or None on error)
    """
    if isinstance(file_obj.read(0), bytes):
        file_obj = io.TextIOWrapper(file_obj, encoding="utf-8-sig", errors="replace")

    content = file_obj.read()
    delimiter = ";" if content.count(";") > content.count(",") else ","
    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    rows = list(reader)

    if not rows:
        return []

    header_map = _normalise_headers(rows[0])
    results = []

    for row_idx, row in enumerate(rows[1:], start=2):
        raw = {header_map.get(i, f"col_{i}"): v.strip() for i, v in enumerate(row)}
        raw_verbatim = {header_map.get(i, f"col_{i}"): v.strip() for i, v in enumerate(row)}

        result = {
            "row_number": row_idx,
            "raw_data": raw_verbatim,
            "status": "ok",
            "errors": [],
            "record": None,
        }

        # Skip blank rows
        if not any(raw.get(f) for f in ("site_name", "meter_id", "consumption")):
            continue

        errors = []
        for field in REQUIRED_FIELDS:
            if not raw.get(field):
                errors.append(f"Missing required field: {field}")

        if errors:
            result["status"] = "error"
            result["errors"] = errors
            results.append(result)
            continue

        period_start = _parse_date(raw["period_start"])
        period_end   = _parse_date(raw["period_end"])
        if period_start is None:
            result["status"] = "error"
            result["errors"] = [f"Cannot parse period_start: '{raw['period_start']}'"]
            results.append(result)
            continue
        if period_end is None:
            result["status"] = "error"
            result["errors"] = [f"Cannot parse period_end: '{raw['period_end']}'"]
            results.append(result)
            continue

        consumption = _parse_decimal(raw["consumption"])
        if consumption is None:
            result["status"] = "error"
            result["errors"] = [f"Cannot parse consumption: '{raw['consumption']}'"]
            results.append(result)
            continue

        unit = raw["unit"].strip().upper()

        # Normalise to kWh
        consumption_kwh = normalize_unit_to_canonical(float(consumption), unit, "KWH")
        if consumption_kwh is None:
            result["status"] = "warning"
            result["errors"] = [
                f"Unit '{unit}' cannot be converted to kWh automatically; "
                "treating as kWh — verify manually"
            ]
            consumption_kwh = float(consumption)
            unit_normalised = unit
        else:
            unit_normalised = "kWh"

        co2e_kg = round(consumption_kwh * ELECTRICITY_FACTOR_KWH, 4)

        # Use midpoint of billing period as activity_date
        days = (period_end - period_start).days
        from datetime import timedelta
        activity_date = period_start + timedelta(days=days // 2)

        # Flag non-calendar billing periods for analyst awareness
        suspicion_reasons = []
        if period_start.day != 1:
            suspicion_reasons.append(
                f"Billing period starts on {period_start} (not calendar month start) — "
                "check if split billing is needed"
            )
        if consumption_kwh <= 0:
            suspicion_reasons.append("Zero or negative consumption")
        if consumption_kwh > 500_000:
            suspicion_reasons.append(
                f"Consumption {consumption_kwh} kWh is very high — verify meter reading"
            )

        meter_id   = raw.get("meter_id", "")
        tariff     = raw.get("tariff_code", "")
        site_name  = raw["site_name"]
        description = f"Meter {meter_id}" if meter_id else site_name
        if tariff:
            description += f" | Tariff {tariff}"

        result["record"] = {
            "source_type": "utility_electricity",
            "scope": "2",
            "category": "Purchased electricity",
            "activity_date": str(activity_date),
            "period_start": str(period_start),
            "period_end": str(period_end),
            "location_raw": site_name,
            "location_resolved": site_name,
            "description": description,
            "quantity_original": str(consumption),
            "unit_original": unit,
            "quantity_normalized": str(round(consumption_kwh, 4)),
            "unit_normalized": unit_normalised,
            "emission_factor": str(ELECTRICITY_FACTOR_KWH),
            "emission_factor_source": ELECTRICITY_FACTOR_SOURCE,
            "co2e_kg": str(co2e_kg),
            "is_suspicious": bool(suspicion_reasons),
            "suspicion_reasons": suspicion_reasons,
        }
        if suspicion_reasons:
            result["status"] = "warning"
        results.append(result)

    return results
