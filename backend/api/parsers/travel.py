"""
Corporate Travel CSV Parser (Concur SAP Standard Extract)

Format rationale (documented in SOURCES.md):
  Concur holds ~70% of the enterprise travel management market. Their "Expense
  Report Extract" or "Concur Analytics" export is what a sustainability team
  realistically sends us in week 1 of onboarding. The API exists but requires
  OAuth2 + enterprise client credentials — CSV is the pragmatic choice.

Expense types handled:
  Air      → Scope 3 Category 6 (Business Travel — Air)
  Hotel    → Scope 3 Category 6 (Business Travel — Hotel)
  Taxi/Car → Scope 3 Category 6 (Business Travel — Ground)

Expense types ignored:
  Train/Rail (different methodology, lower priority), Meals,
  Miscellaneous — see TRADEOFFS.md.

Key complexity: flights often only have origin/destination airport codes with
no distance column. We calculate great-circle distance via the haversine formula
using a built-in airport lat/lon table. If both codes are unknown, we flag the
row for manual review rather than silently dropping it.
"""

import csv
import io
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import IO

from api.emission_factors import (
    flight_distance_km,
    flight_co2e,
    HOTEL_FACTOR_ROOM_NIGHT,
    HOTEL_FACTOR_SOURCE,
    TAXI_FACTOR_KM,
    CAR_RENTAL_FACTOR_KM,
    TRAVEL_FACTOR_SOURCE,
)

HEADER_MAP = {
    "REPORT ID":        "report_id",
    "EXPENSE REPORT":   "report_id",
    "EMPLOYEE ID":      "employee_id",
    "EMPLOYEE":         "employee_id",
    "EMPLOYEE NAME":    "employee_name",
    "NAME":             "employee_name",
    "EXPENSE TYPE":     "expense_type",
    "TYPE":             "expense_type",
    "CATEGORY":         "expense_type",
    "TRAVEL DATE":      "travel_date",
    "DATE":             "travel_date",
    "TRANSACTION DATE": "travel_date",
    "ORIGIN":           "origin",
    "FROM":             "origin",
    "DEPARTURE":        "origin",
    "DESTINATION":      "destination",
    "TO":               "destination",
    "ARRIVAL":          "destination",
    "BOOKING CLASS":    "booking_class",
    "CLASS":            "booking_class",
    "CABIN CLASS":      "booking_class",
    "DISTANCE KM":      "distance_km",
    "DISTANCE":         "distance_km",
    "KM":               "distance_km",
    "NIGHTS":           "nights",
    "ROOM NIGHTS":      "nights",
    "VENDOR":           "vendor",
    "HOTEL":            "vendor",
    "AIRLINE":          "vendor",
    "AMOUNT":           "amount",
    "COST":             "amount",
    "CURRENCY":         "currency",
}

AIR_TYPES    = {"air", "flight", "airfare", "airline", "plane"}
HOTEL_TYPES  = {"hotel", "lodging", "accommodation", "motel"}
GROUND_TYPES = {"taxi", "cab", "uber", "lyft", "car rental", "rental car",
                "ground", "ground transport", "rideshare", "limo"}


def _parse_date(value: str) -> date | None:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value: str) -> float | None:
    try:
        return float(Decimal(value.strip().replace(",", "")))
    except (InvalidOperation, AttributeError, ValueError):
        return None


def _normalise_headers(raw_headers: list[str]) -> dict[int, str]:
    mapping = {}
    for idx, h in enumerate(raw_headers):
        canonical = HEADER_MAP.get(h.strip().upper())
        if canonical:
            mapping[idx] = canonical
    return mapping


def _classify_expense(expense_type: str) -> str | None:
    """Return 'air', 'hotel', 'ground', or None if not a travel expense."""
    et = expense_type.lower().strip()
    if any(t in et for t in AIR_TYPES):
        return "air"
    if any(t in et for t in HOTEL_TYPES):
        return "hotel"
    if any(t in et for t in GROUND_TYPES):
        return "ground"
    return None


def parse_travel_file(file_obj: IO) -> list[dict]:
    """
    Parse a Concur-style travel expense CSV.

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
        if not any(raw.get(f) for f in ("expense_type", "travel_date", "employee_id")):
            continue

        if not raw.get("expense_type"):
            result["status"] = "error"
            result["errors"] = ["Missing expense_type"]
            results.append(result)
            continue

        category = _classify_expense(raw["expense_type"])
        if category is None:
            # Not a travel expense type we handle — skip silently
            continue

        if not raw.get("travel_date"):
            result["status"] = "error"
            result["errors"] = ["Missing travel_date"]
            results.append(result)
            continue

        travel_date = _parse_date(raw["travel_date"])
        if travel_date is None:
            result["status"] = "error"
            result["errors"] = [f"Cannot parse travel_date: '{raw['travel_date']}'"]
            results.append(result)
            continue

        suspicion_reasons = []

        # ------------------------------------------------------------------ #
        # FLIGHT
        # ------------------------------------------------------------------ #
        if category == "air":
            origin = raw.get("origin", "").upper().strip()
            dest   = raw.get("destination", "").upper().strip()
            booking_class = raw.get("booking_class", "economy").lower().strip() or "economy"

            # Try explicit distance first, fall back to haversine
            dist_raw = _parse_decimal(raw.get("distance_km", ""))
            if dist_raw and dist_raw > 0:
                distance_km = dist_raw
                dist_source = "provided"
            elif origin and dest:
                distance_km = flight_distance_km(origin, dest)
                dist_source = "calculated"
            else:
                distance_km = None
                dist_source = None

            if distance_km is None:
                result["status"] = "error"
                result["errors"] = [
                    f"Cannot determine flight distance: origin='{origin}' dest='{dest}' "
                    "are not in the airport lookup table and no distance_km provided"
                ]
                results.append(result)
                continue

            co2e_kg, factor = flight_co2e(distance_km, booking_class)
            co2e_kg = round(co2e_kg, 4)

            if dist_source == "calculated":
                suspicion_reasons.append(
                    f"Distance calculated from airport codes ({origin}→{dest}), not provided by source"
                )
            if booking_class not in ("economy", "business", "first"):
                suspicion_reasons.append(
                    f"Booking class '{booking_class}' not recognised; defaulted to economy"
                )

            route = f"{origin}→{dest}" if (origin and dest) else raw.get("vendor", "Unknown route")
            result["record"] = {
                "source_type": "travel_flight",
                "scope": "3",
                "category": "Business travel — air",
                "activity_date": str(travel_date),
                "period_start": str(travel_date),
                "period_end": str(travel_date),
                "location_raw": f"{origin} → {dest}",
                "location_resolved": f"{origin} → {dest}",
                "description": f"Flight {route} ({booking_class})",
                "employee_id": raw.get("employee_id", ""),
                "quantity_original": str(round(distance_km, 1)),
                "unit_original": "km",
                "quantity_normalized": str(round(distance_km, 1)),
                "unit_normalized": "PKM",
                "emission_factor": str(round(factor, 6)),
                "emission_factor_source": TRAVEL_FACTOR_SOURCE,
                "co2e_kg": str(co2e_kg),
                "is_suspicious": bool(suspicion_reasons),
                "suspicion_reasons": suspicion_reasons,
            }

        # ------------------------------------------------------------------ #
        # HOTEL
        # ------------------------------------------------------------------ #
        elif category == "hotel":
            nights_raw = _parse_decimal(raw.get("nights", ""))
            if nights_raw is None or nights_raw <= 0:
                # Try to infer 1 night from a single-date row
                nights_raw = 1.0
                suspicion_reasons.append(
                    "Nights not provided; assumed 1 — verify with booking confirmation"
                )

            co2e_kg = round(nights_raw * HOTEL_FACTOR_ROOM_NIGHT, 4)
            city = raw.get("destination", raw.get("origin", raw.get("vendor", "Unknown")))

            result["record"] = {
                "source_type": "travel_hotel",
                "scope": "3",
                "category": "Business travel — hotel",
                "activity_date": str(travel_date),
                "period_start": str(travel_date),
                "period_end": str(travel_date),
                "location_raw": city,
                "location_resolved": city,
                "description": f"Hotel — {raw.get('vendor', city)} ({int(nights_raw)} night(s))",
                "employee_id": raw.get("employee_id", ""),
                "quantity_original": str(nights_raw),
                "unit_original": "nights",
                "quantity_normalized": str(nights_raw),
                "unit_normalized": "room-night",
                "emission_factor": str(HOTEL_FACTOR_ROOM_NIGHT),
                "emission_factor_source": HOTEL_FACTOR_SOURCE,
                "co2e_kg": str(co2e_kg),
                "is_suspicious": bool(suspicion_reasons),
                "suspicion_reasons": suspicion_reasons,
            }

        # ------------------------------------------------------------------ #
        # GROUND TRANSPORT
        # ------------------------------------------------------------------ #
        elif category == "ground":
            dist_km = _parse_decimal(raw.get("distance_km", ""))
            vendor = raw.get("vendor", raw.get("expense_type", "ground transport")).lower()

            is_rental = any(t in vendor for t in ("rental", "car rental", "hire"))
            factor = CAR_RENTAL_FACTOR_KM if is_rental else TAXI_FACTOR_KM

            if dist_km and dist_km > 0:
                co2e_kg = round(dist_km * factor, 4)
                qty_orig = str(dist_km)
                unit_orig = "km"
                qty_norm = str(dist_km)
                unit_norm = "km"
            else:
                # No distance — use cost as a proxy note but flag for analyst
                co2e_kg = 0.0
                qty_orig = "0"
                unit_orig = "km"
                qty_norm = "0"
                unit_norm = "km"
                suspicion_reasons.append(
                    "No distance provided for ground transport — CO2e is 0; "
                    "analyst must enter distance manually"
                )

            result["record"] = {
                "source_type": "travel_ground",
                "scope": "3",
                "category": "Business travel — ground transport",
                "activity_date": str(travel_date),
                "period_start": str(travel_date),
                "period_end": str(travel_date),
                "location_raw": raw.get("origin", ""),
                "location_resolved": raw.get("origin", ""),
                "description": f"{raw.get('vendor', 'Ground transport')}",
                "employee_id": raw.get("employee_id", ""),
                "quantity_original": qty_orig,
                "unit_original": unit_orig,
                "quantity_normalized": qty_norm,
                "unit_normalized": unit_norm,
                "emission_factor": str(factor),
                "emission_factor_source": TRAVEL_FACTOR_SOURCE,
                "co2e_kg": str(co2e_kg),
                "is_suspicious": bool(suspicion_reasons),
                "suspicion_reasons": suspicion_reasons,
            }

        if suspicion_reasons and result["status"] == "ok":
            result["status"] = "warning"
        results.append(result)

    return results
