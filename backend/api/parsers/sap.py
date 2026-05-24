"""
SAP Fuel & Procurement Flat File Parser

Format rationale (documented in SOURCES.md):
  We handle the MB51 Material Document List flat file export — the report a
  sustainability team requests from their SAP BASIS team. It is semicolon-
  delimited with German locale settings: decimal comma, thousands period,
  dates as DD.MM.YYYY, and column headers that may arrive in German.

Movement types we ingest:
  201  Goods issue for cost center (direct consumption)
  261  Goods issue for production order (process fuel)
  262  Reversal of 261 — produces a negative quantity, we preserve the sign
       so it offsets the original entry in CO2e totals.

What we deliberately ignore:
  Goods receipts (101, 501), transfer postings (311/312), inventory
  adjustments (561/562) — none of these represent fuel consumed.
"""

import csv
import io
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import IO

from api.emission_factors import resolve_fuel_factor, normalize_unit_to_canonical, FACTOR_SOURCE

# German → English column header mappings for common SAP locale configs
HEADER_MAP = {
    "WERKS":    "plant_code",
    "WERK":     "plant_code",
    "MATNR":    "material_number",
    "MAKTX":    "material_description",
    "BTEXT":    "material_description",
    "BWART":    "movement_type",
    "MENGE":    "quantity",
    "QUANTITY": "quantity",
    "MEINS":    "unit",
    "UNIT":     "unit",
    "BUDAT":    "posting_date",
    "DATE":     "posting_date",
    "KOSTL":    "cost_center",
    "LGORT":    "storage_location",
    "WERKSNAME":"plant_name",
    "PLANT":    "plant_code",
    "MATERIAL": "material_number",
    "MOVEMENT TYPE": "movement_type",
    "POSTING DATE":  "posting_date",
    "COST CENTER":   "cost_center",
}

CONSUMPTION_MOVEMENT_TYPES = {"201", "261"}
REVERSAL_MOVEMENT_TYPES    = {"202", "262"}
ALL_VALID_MOVEMENT_TYPES   = CONSUMPTION_MOVEMENT_TYPES | REVERSAL_MOVEMENT_TYPES

REQUIRED_FIELDS = {"plant_code", "material_number", "material_description", "movement_type",
                   "quantity", "unit", "posting_date"}


def _parse_german_number(value: str) -> Decimal | None:
    """
    SAP German locale uses '.' as thousands separator and ',' as decimal.
    '1.500,75'  →  Decimal('1500.75')
    '2300'      →  Decimal('2300')
    '-200,00'   →  Decimal('-200.00')
    """
    try:
        cleaned = value.strip().replace(".", "").replace(",", ".")
        return Decimal(cleaned)
    except (InvalidOperation, AttributeError):
        return None


def _parse_date(value: str) -> date | None:
    """
    Accept DD.MM.YYYY (German), YYYYMMDD (SAP internal), or YYYY-MM-DD (ISO).
    """
    value = value.strip()
    for fmt in ("%d.%m.%Y", "%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _normalise_headers(raw_headers: list[str]) -> dict[int, str]:
    """Map column indices to canonical English field names."""
    mapping = {}
    for idx, h in enumerate(raw_headers):
        canonical = HEADER_MAP.get(h.strip().upper())
        if canonical:
            mapping[idx] = canonical
    return mapping


def parse_sap_file(file_obj: IO, plant_lookup: dict) -> list[dict]:
    """
    Parse a SAP MB51 flat file.

    Args:
        file_obj:     file-like object (opened in text mode or bytes)
        plant_lookup: dict of {plant_code: plant_name} for this tenant

    Returns:
        List of result dicts, one per row:
        {
            "row_number": int,
            "raw_data":   dict,         # verbatim row
            "status":     "ok" | "error" | "warning",
            "errors":     [str],
            "record":     dict | None,  # normalized fields if status != error
        }
    """
    if isinstance(file_obj.read(0), bytes):
        file_obj = io.TextIOWrapper(file_obj, encoding="utf-8-sig", errors="replace")

    content = file_obj.read()
    # Detect delimiter: SAP exports are usually semicolon, but sometimes tab
    delimiter = ";" if content.count(";") > content.count("\t") else "\t"

    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    rows = list(reader)

    if not rows:
        return []

    header_map = _normalise_headers(rows[0])
    results = []

    for row_idx, row in enumerate(rows[1:], start=2):
        raw = {header_map.get(i, f"col_{i}"): v.strip() for i, v in enumerate(row) if v.strip()}
        result = {
            "row_number": row_idx,
            "raw_data": {header_map.get(i, f"col_{i}"): v.strip() for i, v in enumerate(row)},
            "status": "ok",
            "errors": [],
            "record": None,
        }

        # Skip rows where no data was mapped (blank lines, section headers)
        if not any(k in raw for k in ("plant_code", "material_number", "movement_type")):
            continue

        errors = []

        # Movement type filter — skip non-consumption types silently
        movement_type = raw.get("movement_type", "").strip()
        if movement_type not in ALL_VALID_MOVEMENT_TYPES:
            continue

        # Validate required fields
        for field in REQUIRED_FIELDS:
            if not raw.get(field):
                errors.append(f"Missing required field: {field}")

        if errors:
            result["status"] = "error"
            result["errors"] = errors
            results.append(result)
            continue

        # Parse quantity
        qty = _parse_german_number(raw["quantity"])
        if qty is None:
            result["status"] = "error"
            result["errors"] = [f"Cannot parse quantity: '{raw['quantity']}'"]
            results.append(result)
            continue

        # Reversals are negative — preserve sign
        if movement_type in REVERSAL_MOVEMENT_TYPES:
            qty = -abs(qty)

        # Parse date
        posting_date = _parse_date(raw["posting_date"])
        if posting_date is None:
            result["status"] = "error"
            result["errors"] = [f"Cannot parse date: '{raw['posting_date']}'"]
            results.append(result)
            continue

        unit = raw["unit"].upper().strip()
        mat_desc = raw.get("material_description", raw.get("material_number", ""))

        # Resolve fuel type and emission factor
        fuel_info = resolve_fuel_factor(mat_desc, unit)
        if fuel_info is None:
            result["status"] = "error"
            result["errors"] = [
                f"Unknown fuel type for material '{mat_desc}' — no emission factor found"
            ]
            results.append(result)
            continue

        canonical_unit = fuel_info["canonical_unit"]
        qty_normalized = normalize_unit_to_canonical(float(qty), unit, canonical_unit)
        if qty_normalized is None:
            result["status"] = "warning"
            result["errors"] = [
                f"Unit '{unit}' cannot be converted to '{canonical_unit}' for {mat_desc}; "
                "using original quantity — verify manually"
            ]
            qty_normalized = float(qty)
            canonical_unit = unit

        co2e_kg = round(qty_normalized * fuel_info["factor"], 4)

        # Resolve plant code to location name
        plant_code = raw["plant_code"].strip()
        location_resolved = plant_lookup.get(plant_code, "")

        # Suspicion checks
        suspicion_reasons = []
        if float(qty) == 0:
            suspicion_reasons.append("Zero quantity")
        if posting_date.year < 2020 or posting_date > date.today():
            suspicion_reasons.append(f"Posting date {posting_date} is outside expected range")
        if not location_resolved:
            suspicion_reasons.append(f"Plant code '{plant_code}' not in lookup table")
        if abs(co2e_kg) > 50_000:
            suspicion_reasons.append(f"CO2e {co2e_kg} kgCO2e is unusually large — verify quantity")

        result["record"] = {
            "source_type": "sap_fuel",
            "scope": "1",
            "category": "Stationary combustion",
            "activity_date": posting_date,
            "period_start": posting_date,
            "period_end": posting_date,
            "location_raw": plant_code,
            "location_resolved": location_resolved or plant_code,
            "description": f"{mat_desc} ({fuel_info['fuel_key']})",
            "quantity_original": str(qty),
            "unit_original": unit,
            "quantity_normalized": str(round(qty_normalized, 4)),
            "unit_normalized": canonical_unit,
            "emission_factor": str(fuel_info["factor"]),
            "emission_factor_source": FACTOR_SOURCE,
            "co2e_kg": str(co2e_kg),
            "is_suspicious": bool(suspicion_reasons),
            "suspicion_reasons": suspicion_reasons,
        }
        if suspicion_reasons:
            result["status"] = "warning"
        results.append(result)

    return results
