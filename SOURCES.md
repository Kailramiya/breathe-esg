# Sources

For each of the three data sources: what I researched, what I learned, what my sample data looks like and why, and what would break in a real deployment.

---

## 1. SAP — Fuel & Procurement

### What I researched
SAP's material management data can be accessed via four mechanisms:

- **IDoc** (Intermediate Document): XML-based message format, primarily used for EDI system-to-system integration. Sustainability teams don't get IDocs — BASIS teams set those up for ERP-to-ERP messaging.
- **OData service** (via SAP Gateway): REST-ish API, requires SAP Gateway configuration and RFC user setup. Available in S/4HANA more readily than ECC 6.0. Not realistic for week-1 onboarding.
- **BAPI** (Business API): RFC function calls from ABAP. Requires developer access. Most sustainability teams have none.
- **Flat file from standard transactions**: MB51 (Material Document List), ME2M (Purchase Orders), or custom ABAP reports. This is what sustainability managers actually get when they ask IT for "fuel data."

### What I learned
MB51 is the most common source for fuel consumption data. It shows goods movements — goods issues (261, 201) represent fuel consumed. The output depends on SAP locale settings:

- **German locale** (common in German-owned enterprises): decimal comma (`1.500,75` = 1500.75), thousands period, column headers in German (WERKS, MATNR, MENGE, MEINS, BUDAT)
- **English locale**: standard decimal point, English headers
- **Date formats**: DD.MM.YYYY in German locale, YYYYMMDD in SAP internal format, sometimes YYYY-MM-DD if someone exported via Excel
- **Units (MEINS)**: L (litres), KG (kilograms), M3 (cubic meters), G (grams), T (metric tonnes) — the same material can be measured in different units across plants
- **Movement types**: 261 = goods issue for production order (consumption), 201 = goods issue for cost center (direct), 262 = reversal of 261 (should offset the original), 101 = goods receipt (not consumption — must exclude)

### What my sample data looks like and why
`sap_fuel_export.csv` uses semicolons as delimiter with German locale settings, because that is the most common configuration in European enterprises and the hardest to parse correctly. I included:

- Diesel (DIESEL-001, "Diesel Kraftstoff") at plants 1000 and 2000 — most common fuel
- Petrol (PETROL-002, "Ottokraftstoff") at plant 3000 — second most common
- Natural gas (NGAS-001, "Erdgas") at all three plants — factory heating, large volumes in M3
- LPG (LPG-001, "Flüssiggas") at two plants — forklift trucks, measured in KG
- One reversal entry (-200,000 L at plant 1000) — movement type 261 with negative quantity; this is a corrected entry and should reduce the CO₂e total, not be excluded
- One entry with unknown plant code (9999) — triggers "plant code not in lookup" suspicion flag
- One entry with unknown material ("Unbekanntes Material") — parser cannot resolve fuel type, produces an error row

### What would break in a real deployment
1. **Column header variations**: A client on SAP S/4HANA with English locale will have completely different headers. Our HEADER_MAP covers common variants but is not exhaustive. We'd need to add a "column mapping" step in the upload UI where the analyst confirms which column is which.
2. **Material numbers vs descriptions**: We match on material description (MAKTX). If the client has non-standard material descriptions or the text field is in a different language, our fuel type resolution fails. Production needs a `MaterialFuelMapping` table (material number → fuel type) that the client configures once.
3. **Multi-plant, multi-currency**: Plant-level fuel prices vary. We only track consumption, not cost — so this doesn't affect our CO₂e calculation, but analysts may want cost data alongside.
4. **Reversal timing**: A reversal in the same export period is straightforward. A reversal in a later month's export (correcting a prior period) requires matching the reversal to its original entry across jobs. We currently don't do this matching.

---

## 2. Utility — Electricity

### What I researched
UK enterprise utility providers (EDF Business, British Gas Business, E.ON Next Business, Octopus Energy for Business) all have online portals. The portal CSV export is available on all of them, usually under "Download usage" or "Consumption history." I reviewed the typical column structure based on publicly documented portal export formats and EDF Business documentation.

PDF invoices: structured as letter-format bills, not data files. Even with pdfplumber, the extraction is fragile because invoice templates change with redesigns, multi-page tables break, and OCR errors on consumption figures are silent.

APIs: Green Button Connect (US standard) is not widely adopted in the UK. Some utilities have internal APIs (EDF has a portal API) but these require per-account provisioning and agreement, making them out of scope for an initial onboarding.

### What I learned
Key real-world characteristics of utility CSV exports:

- **Billing periods are not calendar months.** Meters are read on a cycle (every 28, 30, or 33 days depending on the utility and meter type). A "January" bill might run Jan 8 – Feb 6. This creates an alignment problem for monthly reporting.
- **Multiple meters per site.** A large office has separate meters for general power, HVAC, server rooms, and sometimes EV charging. Each is billed separately with its own meter ID.
- **Unit inconsistency.** Standard commercial meters report in kWh. Large industrial sites (factories) often have import meters that report in MWh or sometimes kVA demand + kWh consumption. Half-hourly metered sites (>100kW) have different billing structures.
- **Estimated vs actual reads.** Some rows are estimated readings (marked 'E' in the tariff notes). These should be flagged, not treated as actual consumption.

### What my sample data looks like and why
`utility_electricity.csv` reflects three real sites with different characteristics:

- **London HQ** (ACC-001234): Two meters (general office + separate circuit), billing period Jan 8 – Feb 6 (not calendar month), moderate consumption
- **Manchester Plant** (ACC-005678): One meter in kWh, one in MWh — to test unit conversion. Non-calendar billing period starts Dec 22, straddling the year boundary
- **Birmingham Factory** (ACC-009012): High consumption (185,000 kWh/month) — a large industrial site. Calendar-month billing because they're on a half-hourly metered contract
- One row with missing consumption (London server room MTR-LDN-B005) — tests error handling for empty consumption field

### What would break in a real deployment
1. **Provider-specific column names.** EDF's CSV uses different headers than British Gas. We'd need a per-provider column mapping or a more aggressive fuzzy header matcher.
2. **Estimated readings.** If the utility marks a row as estimated, that affects the CO₂e figure. We should flag estimated rows separately from actual reads.
3. **Reactive power / demand charges.** Some bills include kVAr (reactive power) alongside kWh. Our parser would see these as extra rows with an unrecognised unit and error out.
4. **Market-based Scope 2.** If the client has a renewable electricity contract (REGO certificates), the market-based Scope 2 factor is 0, not 0.20493. We'd need a `tariff_type` field and the ability to override the emission factor at the site level.
5. **Half-hourly data.** Large sites have half-hourly metered data (48 rows per day per meter). Our parser handles one row per billing period; HH data would require aggregation before import.

---

## 3. Corporate Travel — Concur

### What I researched
SAP Concur holds approximately 70% of the enterprise travel management market. I reviewed Concur's public API documentation (Expense v4, Travel v3), their standard expense report extract format, and the GHG Protocol's guidance on Scope 3 Category 6 (Business Travel).

Concur's Expense Report Extract is a CSV available from Concur Analytics or via a custom extract in the Expense module. The columns vary by configuration but the core fields are consistent. I also reviewed DEFRA 2023 conversion factors specifically for flights, including their treatment of Radiative Forcing Index (RFI = 1.891 for flights, included in DEFRA's PKM factors).

### What I learned
Real-world complexity of travel expense data:

- **Flights often have no distance.** Concur records origin and destination airport codes (IATA) but the distance field is not always populated. It depends on how the booking was made (GDS vs direct) and the Concur configuration.
- **Airport codes are not always IATA.** Some exports use city names, some use full airport names, some use internal booking codes. Matching to lat/lon requires a lookup table.
- **Booking class matters significantly.** Business class LHR→JFK emits 2.8× more CO₂e per passenger than economy (DEFRA 2023: 0.42849 vs 0.15302 kgCO₂e/PKM). If booking class is missing, we must decide whether to default to economy (under-count) or require the field (block import).
- **Hotel stays are often single-date rows.** Concur records the first night of a hotel stay on one expense line, not a per-night breakdown. The `Nights` field is often absent.
- **Ground transport rarely has distance.** Taxi/Uber expenses have a cost and a vendor but no km field. We can't calculate CO₂e without distance.

### What my sample data looks like and why
`concur_travel_export.csv` is modelled on a real Concur expense extract, covering four employee trips:

- **EMP-101 (Jane Smith) — LHR→JFK round trip (long-haul economy):** No distance field; parser calculates haversine distance (~5,570 km). Tests airport code lookup and long-haul factor selection.
- **EMP-205 (John Doe) — LHR→CDG round trip (short-haul business):** Short haul (<3,700 km), business class. Tests class-based factor selection. CO₂e is higher than economy despite shorter distance.
- **EMP-317 (Priya Patel) — LHR→DXB round trip (long-haul economy):** Medium long-haul (~5,500 km). Hotel row has a formatting anomaly (nights field in wrong column) to test robustness.
- **EMP-422 (David Lee) — car rental with no distance:** CO₂e recorded as 0 with a suspicion flag. Tests the ground-transport-without-distance path.
- **Last row — unknown airport codes (XXX, YYY):** Cannot calculate distance, produces a parse error. Tests the failure path for unrecognised codes.

### What would break in a real deployment
1. **Non-Concur platforms.** Navan (TripActions), Amex GBT, and Egencia have different column names and conventions. Each would need its own adapter.
2. **Airport codes outside our lookup table.** We have 35 airports. A client that flies to regional airports (e.g. BRS, NCL, ABZ) would get parse errors on those routes. Production needs the full OurAirports dataset (~10,000 airports).
3. **Multi-leg journeys.** Concur sometimes records a connection as two separate rows (LHR→AMS, AMS→JFK). Our parser treats each row independently — we'd double-count the RFI for a connecting flight vs the correct single long-haul factor.
4. **Currency conversion.** Travel costs are in the booking currency. We store them but don't convert. Spend-based analysis would need FX rates.
5. **Hotel country-specific factors.** DEFRA only publishes UK hotel factors. A client with significant international travel should use destination-country factors (available from GHGP Scope 3 tools or EXIOBASE). We default to the UK average for all hotels.
