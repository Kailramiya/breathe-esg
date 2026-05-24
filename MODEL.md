# Data Model

## Overview

The model is built around a single central question: **can an auditor reconstruct exactly what happened to every number?** That means preserving the raw source row, recording every edit, and snapshotting the emission factor at the time the record was created so that updating a factor table never retroactively changes an approved figure.

---

## Entities

### Tenant
Represents a client company. Every other table has a `tenant` foreign key. This is the primary multi-tenancy boundary — all viewset querysets filter by `request.user.tenant`.

```
Tenant
  id          UUID (PK)
  name        str
  slug        str (unique)
  created_at  datetime
```

### User
Extends Django's AbstractUser. Bound to a Tenant and assigned a role (`analyst` or `admin`). The tenant FK is where multi-tenancy is enforced at query time.

```
User (extends AbstractUser)
  tenant  FK → Tenant
  role    enum [analyst, admin]
```

### PlantLookup
SAP plant codes (e.g. `1000`, `2000`) are meaningless to an analyst without a lookup table. This table is tenant-scoped because each client has their own plant code namespace.

```
PlantLookup
  tenant      FK → Tenant
  plant_code  str   (e.g. "1000")
  plant_name  str   (e.g. "London HQ")
  city        str
  country     str
  UNIQUE (tenant, plant_code)
```

### IngestionJob
One row per file upload. Tracks parse outcome (row counts, error list) and stores the original file. Storing the raw file means an auditor can always go back to the exact bytes we received.

```
IngestionJob
  id                UUID (PK)
  tenant            FK → Tenant
  source_type       enum [sap, utility, travel]
  status            enum [pending, processing, completed, failed]
  original_filename str
  raw_file          FileField
  row_count_total   int
  row_count_ok      int
  row_count_error   int
  row_count_warning int
  error_summary     JSON   (list of {row, errors})
  ingested_by       FK → User
  ingested_at       datetime
  completed_at      datetime?
```

### RawRecord
**Immutable.** One row per source row. `raw_data` stores the exact parsed row as JSON — nothing is ever normalised or inferred here. `parse_status` explains why a row couldn't be normalised. This separation means a failed row doesn't disappear; it can be inspected and re-queued manually.

```
RawRecord
  id            UUID (PK)
  job           FK → IngestionJob
  tenant        FK → Tenant
  row_number    int
  raw_data      JSON   (verbatim row)
  parse_status  enum [ok, error, warning]
  parse_errors  JSON   (list of strings)
```

### NormalizedRecord
The central table. Contains the cleaned, unit-converted, emission-calculated record that analysts review and sign off.

**Key design choices:**

1. **`quantity_original` / `unit_original`** — verbatim from the source. Never changes.
2. **`quantity_normalized` / `unit_normalized`** — after unit conversion. This is what analysts can correct.
3. **`co2e_kg`** — always in kg CO₂e. Recalculated when `quantity_normalized` is edited.
4. **`emission_factor` + `emission_factor_source`** — snapshotted at creation time. Changing the factor table in code does not retroactively alter this record. This is load-bearing for audit.
5. **`is_edited` + `original_values`** — if an analyst corrects a value, we snapshot the pre-edit state here. The full edit history is in `AuditLog`.
6. **`review_status`** — the workflow state: `pending → approved | rejected | flagged`.
7. **`is_locked`** — once set, the record is frozen. No further edits or review changes. Lock is applied when a batch is submitted to auditors.
8. **`raw_record`** — OneToOne back to the original row. Analysts can always see what the source said.

```
NormalizedRecord
  id                    UUID (PK)
  tenant                FK → Tenant
  raw_record            FK → RawRecord (OneToOne, nullable)
  source_type           enum [sap_fuel, sap_procurement, utility_electricity,
                              travel_flight, travel_hotel, travel_ground]
  source_job            FK → IngestionJob
  scope                 enum [1, 2, 3]
  category              str   (e.g. "Stationary combustion")
  activity_date         date
  period_start          date?
  period_end            date?
  location_raw          str   (plant code, site name, city)
  location_resolved     str   (after PlantLookup resolution)
  description           str   (fuel type, meter ID, flight route…)
  employee_id           str   (travel records)
  quantity_original     decimal
  unit_original         str   (L, M3, kWh, km, night…)
  quantity_normalized   decimal
  unit_normalized       str   (consistent per source type)
  emission_factor       decimal  (kgCO₂e per unit_normalized)
  emission_factor_source str   (e.g. "DEFRA_2023")
  co2e_kg               decimal
  review_status         enum [pending, approved, rejected, flagged]
  reviewed_by           FK → User?
  reviewed_at           datetime?
  review_note           str
  is_suspicious         bool
  suspicion_reasons     JSON  (list of strings)
  is_edited             bool
  original_values       JSON  (snapshot before first edit)
  is_locked             bool
  locked_at             datetime?
  locked_by             FK → User?
  created_at            datetime
  updated_at            datetime

  INDEXES: (tenant, review_status), (tenant, scope),
           (tenant, activity_date), (tenant, is_suspicious)
```

### AuditLog
Append-only. Every state change on a NormalizedRecord — creation, edit, approve, reject, flag, lock — writes one row here with `before` and `after` JSON snapshots. This table is never updated, only inserted. It provides a complete reconstruction of a record's history.

```
AuditLog
  id          UUID (PK)
  tenant      FK → Tenant
  record      FK → NormalizedRecord
  actor       FK → User
  action      enum [created, edited, approved, rejected, flagged, locked]
  before      JSON
  after       JSON
  note        str
  timestamp   datetime (auto)
```

---

## Scope Categorisation

| Source type           | GHG Scope | Category                          |
|-----------------------|-----------|-----------------------------------|
| `sap_fuel`            | Scope 1   | Stationary combustion             |
| `sap_procurement`     | Scope 3   | Purchased goods & services        |
| `utility_electricity` | Scope 2   | Purchased electricity             |
| `travel_flight`       | Scope 3   | Business travel — air             |
| `travel_hotel`        | Scope 3   | Business travel — hotel           |
| `travel_ground`       | Scope 3   | Business travel — ground transport|

---

## Unit Normalisation

| Source        | Original units          | Normalised unit | Notes                                        |
|---------------|-------------------------|-----------------|----------------------------------------------|
| SAP fuel      | L, M3, KG (varies)      | L / M3 / KG     | Normalised to canonical unit for that fuel   |
| Utility       | kWh, MWh, GJ            | kWh             | MWh × 1000, GJ × 277.778                    |
| Travel flight | km (or derived)         | PKM             | Great-circle distance if not provided        |
| Travel hotel  | nights                  | room-night      | 1 assumed if missing                         |
| Travel ground | km (if provided)        | km              | CO₂e = 0 + flag if distance missing          |

---

## Multi-tenancy

Shared schema with a `tenant` FK on every table. Isolation is enforced in DRF viewset `get_queryset()` methods — every query filters by `request.user.tenant`. This is a deliberate simplification; see TRADEOFFS.md for what a production deployment would use instead.

---

## Audit Trail

The audit chain is:

```
IngestionJob (file received, when, by whom)
  └── RawRecord (verbatim row, parse outcome)
        └── NormalizedRecord (cleaned record, emission calc)
              └── AuditLog[] (every state change, append-only)
```

An auditor can answer:
- "Where did this number come from?" → `raw_record.raw_data`
- "Who changed it and when?" → `AuditLog`
- "What emission factor was used?" → `emission_factor` + `emission_factor_source` on the record
- "Was it approved before or after the edit?" → `AuditLog` timestamps
- "Was the original file altered?" → `IngestionJob.raw_file` (stored verbatim)
