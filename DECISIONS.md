# Decisions

Every ambiguity I resolved, what I chose, and why.

---

## 1. SAP export format: flat file (MB51), not OData or IDoc

**What I researched:** SAP offers four ways to get data out — IDoc (XML message format), OData services (REST-ish API via SAP Gateway), BAPI function calls (RFC), and flat file exports from standard transactions (MB51, ME2M, etc.).

**What I chose:** SAP MB51 flat file export (semicolon-delimited, German locale).

**Why:**
- OData and BAPI require direct SAP system access (VPN, RFC credentials, BASIS team involvement). A sustainability team doing an initial data onboarding won't have this on day 1.
- IDoc XML is used for system-to-system EDI integration. It's not what a sustainability manager downloads from their SAP portal.
- Flat files from MB51 (Material Document List) or custom ABAP reports are exactly what an SAP consultant exports and emails over. This is the realistic week-1 handoff.
- Flat file also forces me to handle the hardest parts of SAP data: German number format (`1.500,75`), German column headers (WERKS, MATNR, MENGE), inconsistent date formats (DD.MM.YYYY vs YYYYMMDD), and movement type filtering.

**What I handle:** Movement types 261/201 (consumption) and 262/202 (reversals). Fuel materials: diesel, petrol, natural gas, LPG.

**What I ignore:** Goods receipts (101), transfer postings (311/312), inventory adjustments. These don't represent fuel consumed. I also don't handle procurement-level detail (Purchase Orders, invoices) — that's Scope 3 Category 1, which requires MM module data and is a separate, more complex integration.

**What I'd ask the PM:**
- Which SAP module are they on (ECC 6.0, S/4HANA)? Column structures differ.
- Do they have a custom ABAP report, or are they running standard MB51?
- What are their plant codes and what do they map to? (I need a PlantLookup seeded before data can be imported meaningfully.)
- Are quantities in SAP always in the same base unit, or do plants have different UoM configurations?

---

## 2. Utility format: portal CSV, not PDF or API

**What I researched:** Enterprise utilities in the UK (EDF, British Gas Business, E.ON, Octopus Energy for Business) offer three ways to get consumption data: PDF invoices (emailed monthly), portal CSV export (download from their web portal), and APIs (Green Button in the US; no unified standard in UK).

**What I chose:** Portal CSV export.

**Why:**
- PDF parsing is fragile for a prototype. Line-item positions shift between invoice versions, OCR errors on numbers are hard to detect, and multi-page bills with page-break tables are a known failure mode.
- Utility APIs in the UK are not standardised. EDF has a portal API but it requires per-account integration agreements. Green Button is US-specific and not universally adopted even there.
- Portal CSV is what a facilities manager actually does: logs into the utility portal, clicks "Download usage," gets a CSV. This is the realistic path for every client in the first six months.

**Key complexity I handle:**
- Billing periods that don't align with calendar months. An "January" bill might run Dec 22 – Jan 24. I store `period_start` and `period_end` verbatim and flag non-calendar-month starts for analyst review.
- Unit inconsistency: some meters report kWh, others MWh (large industrial sites). I normalise to kWh before applying the grid factor.

**What I deliberately don't handle:** Prorating consumption across calendar month boundaries. If a billing period spans two months, I record it as-is. See TRADEOFFS.md for why.

**What I'd ask the PM:**
- Which utility providers? Some portal CSVs have completely different column names.
- Do they have sub-metering (multiple meters per site, some for specific processes)? Should those be tagged differently?
- Are they on a renewable tariff? If so, the market-based Scope 2 factor is 0, not the UK grid average — this changes the calculation methodology significantly.

---

## 3. Travel format: Concur CSV, not API

**What I researched:** The main corporate travel platforms are SAP Concur (~70% enterprise market share), Navan (formerly TripActions), Amex GBT, and Egencia. Concur has a REST API (the Expense v4 API) with OAuth2 and scope-based access. Navan has an API as well. Both produce CSV exports from their analytics/reporting modules.

**What I chose:** Concur Expense Report Extract CSV.

**Why:**
- Concur's API requires OAuth2 client credentials that must be provisioned by the enterprise's Concur admin. This is not something a client hands over on day 1.
- The Concur Analytics export is a standard CSV that sustainability teams already pull monthly. It's the format they're familiar with.
- CSV forces me to handle the hardest part of travel data: airport codes without distances. I built the haversine calculation specifically because Concur expense rows only have IATA origin/destination with no distance field.

**Key complexity I handle:**
- Flights with no distance column: calculate great-circle distance from IATA codes using a haversine formula with a built-in airport lat/lon table (35 airports covering most common corporate routes).
- Booking class affects emission factor significantly. Economy LHR→JFK: 0.25397 kgCO₂e/PKM. Business LHR→JFK: 0.42849 kgCO₂e/PKM — 69% more.
- Short-haul vs long-haul threshold (3,700 km) follows DEFRA 2023 methodology.
- Ground transport without distance: flag as zero CO₂e pending analyst input, rather than silently dropping the row.

**What I ignore:** Rail/train (different methodology, requires journey-level data), meal expenses, rental car fuel consumption detail (approximated as average car).

**What I'd ask the PM:**
- Is this actually Concur, or one of the other platforms? Column names vary.
- Do expense reports include the booking class field, or is it always missing? If missing, we default to economy across the board.
- Should hotel stays use a UK-specific factor or a destination-country factor? DEFRA publishes UK-only; the GHGP requires origin-country factors for international travel.

---

## 4. Multi-tenancy: shared schema with tenant FK

**What I chose:** All tables have a `tenant` FK. DRF viewsets filter every queryset by `request.user.tenant`.

**Why:** Row-level security (PostgreSQL RLS) or separate schemas per tenant are more robust but significantly more complex to implement and migrate. For a prototype with a small number of analysts reviewing data in a supervised context, shared-schema with application-level filtering is sufficient. The isolation guarantee is: "you cannot see another tenant's data through the UI." What it doesn't guarantee: an SQL error or a missing queryset filter would leak data. That's acceptable for a prototype, explicitly not for production.

**What I'd change for production:** Add PostgreSQL row-level security policies on the critical tables (NormalizedRecord, RawRecord, AuditLog) so that even a filter bug in the application layer can't leak across tenants.

---

## 5. Emission factors: DEFRA 2023, hardcoded, snapshotted at record creation

**What I chose:** DEFRA 2023 Greenhouse Gas Reporting Conversion Factors, stored as constants in `emission_factors.py`. The factor value and source string are written to each `NormalizedRecord` at creation time.

**Why the hardcoding:**
- DEFRA publishes annual factors as a static spreadsheet. They don't have an API.
- Hardcoded factors are version-controlled, transparent, and easy to audit. A database-stored factor table adds a UI and migration complexity for no gain at this scale.
- The key guarantee is that the factor is snapshotted on the record. If DEFRA releases 2024 factors and we update the code, previously approved records still show the 2023 factor they were calculated with.

**What I'd change for production:**
- Store factors in the database with `valid_from` / `valid_to` date ranges.
- Add a recalculation job that flags records whose factor is superseded.
- Support market-based vs location-based Scope 2 factors.

---

## 6. Authentication: JWT, no SSO

**What I chose:** JWT via `djangorestframework-simplejwt`. 8-hour access token, 7-day refresh.

**Why:** SSO (SAML, OIDC) is what an enterprise client would actually use, but it requires their IdP credentials and integration setup. For a prototype with a demo tenant, username/password + JWT is the right call. Access token expiry at 8 hours means a full working day without re-login; refresh token handles the overnight case.

---

## 7. Suspicious detection: rule-based, not statistical

**What I chose:** Four deterministic rules per source type:
- Zero or negative quantity
- Date outside expected range (pre-2020 or future)
- Plant code not in lookup table
- CO₂e above absolute threshold (50,000 kg for fuel; 500,000 kWh for electricity)

**Why not statistical (z-score, IQR):** Statistical outlier detection requires a baseline dataset. On first ingestion, there's no baseline. Rule-based flags work on the first file uploaded and produce human-readable explanations ("Plant code '9999' not in lookup table") rather than opaque scores. Analysts can act on them immediately.

**What I'd add with more time:** After N ingestion jobs, compute a rolling mean and standard deviation per source type and add a statistical flag for records > 3σ from the mean.
