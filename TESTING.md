# Testing Guide — Breathe ESG Data Review Platform

This guide covers manual testing of every feature. Follow sections in order — each builds on the previous.

---

## Prerequisites

Both servers must be running before any test.

**Terminal 1 — Backend:**
```bash
cd backend
python manage.py migrate
python manage.py seed
python manage.py runserver
# Running at http://localhost:8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm install
npm run dev
# Running at http://localhost:5173
```

**Demo accounts created by `seed`:**

| Username | Password   | Role    | Can do                          |
|----------|------------|---------|----------------------------------|
| admin    | admin123   | Admin   | Everything                      |
| analyst  | analyst123 | Analyst | Review, approve, flag, reject   |

---

## 1. Authentication

### 1.1 Login — happy path
1. Open `http://localhost:5173/login`
2. Enter `admin` / `admin123` → click **Sign in**
3. **Expected:** Redirected to `/dashboard`. Header shows "Breathe ESG".

### 1.2 Login — wrong password
1. Enter `admin` / `wrongpassword` → click **Sign in**
2. **Expected:** Error message "Invalid username or password." Page stays on `/login`.

### 1.3 Protected route redirect
1. Clear browser storage: DevTools → Application → Local Storage → Clear All
2. Navigate directly to `http://localhost:5173/review`
3. **Expected:** Redirected to `/login`.

### 1.4 Sign out
1. Log in, then click **Sign out** in the header
2. **Expected:** Redirected to `/login`. Navigating back to `/dashboard` redirects to `/login` again.

### 1.5 Token refresh (API)
```bash
# Get tokens
curl -s -X POST http://localhost:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Response contains access + refresh tokens
# Use the refresh token:
curl -s -X POST http://localhost:8000/api/auth/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh":"<refresh_token>"}'

# Expected: new access token returned
```

---

## 2. Data Ingestion

Upload all three sample files from the `sample_data/` directory.

### 2.1 SAP — fuel export

**File:** `sample_data/sap_fuel_export.csv`

1. Go to **Ingest Data**
2. Under **SAP Fuel & Procurement**, click the upload zone → select `sap_fuel_export.csv`
3. Click **Upload & Ingest**
4. **Expected result card:**

| Metric   | Expected |
|----------|----------|
| Imported | 13       |
| Warnings | 1        |
| Errors   | 1        |

5. Click **1 parse error(s)** to expand
6. **Expected error:** Row 15 — `Unknown fuel type for material 'Unbekanntes Material'`

**Why these numbers:**
- 13 clean rows: diesel, petrol, natural gas, LPG across plants 1000/2000/3000 — all parsed with German number format (`1.500,000` → 1500) and DD.MM.YYYY dates
- 1 warning: Row 14, plant code `9999` — not in the PlantLookup table → suspicious flag set
- 1 error: Row 15 — material description "Unbekanntes Material" matches no fuel type in the emission factor table

### 2.2 SAP — API directly

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python -c "import sys,json; print(json.load(sys.stdin)['access'])")

curl -s -X POST http://localhost:8000/api/ingest/sap/ \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sample_data/sap_fuel_export.csv" | python -m json.tool
```

**Expected response fields:**
```json
{
  "status": "completed",
  "row_count_ok": 13,
  "row_count_warning": 1,
  "row_count_error": 1,
  "error_summary": [
    { "row": 15, "errors": ["Unknown fuel type for material..."] }
  ]
}
```

### 2.3 Utility — electricity export

**File:** `sample_data/utility_electricity.csv`

1. Under **Utility Electricity**, upload `utility_electricity.csv`
2. **Expected result:**

| Metric   | Expected |
|----------|----------|
| Imported | 3        |
| Warnings | 6        |
| Errors   | 1        |

**Why:**
- 6 warnings: billing periods don't start on the 1st of the month (e.g. Jan 8, Dec 22) — real utility billing cycle mismatch, flagged so analyst is aware
- 1 error: Row 10 — missing consumption value (empty field for London server room meter)
- 3 ok: Birmingham Factory rows use calendar-month billing (Jan 1 → Feb 1) — no flag

### 2.4 Travel — Concur export

**File:** `sample_data/concur_travel_export.csv`

1. Under **Corporate Travel (Concur)**, upload `concur_travel_export.csv`
2. **Expected result:**

| Metric   | Expected |
|----------|----------|
| Imported | 4        |
| Warnings | 11       |
| Errors   | 1        |

**Why:**
- 11 warnings: flights where distance was calculated from airport codes (not provided), and hotel rows where nights count was assumed from the data
- 1 error: Row 17 — airport codes `XXX` / `YYY` are not in the airport lookup table and no distance provided → cannot calculate CO₂e
- 4 ok: rows where all fields were present and unambiguous

### 2.5 Wrong file type
1. Try uploading a `.pdf` or `.xlsx` to any source
2. **Expected:** File is sent to the parser; parser will likely return all rows as errors (unrecognised format). The job completes with `status: completed` but `row_count_ok: 0`.

### 2.6 Empty file
1. Create an empty `.csv` and upload it
2. **Expected:** Job completes with all counts at 0. No crash.

### 2.7 Duplicate upload
1. Upload `sap_fuel_export.csv` a second time
2. **Expected:** A second set of records is created (no deduplication — deduplication is a deliberate tradeoff, documented in TRADEOFFS.md). Job history shows two separate SAP jobs.

---

## 3. Review Queue

After uploading all three sample files, 38 records exist in `pending` status.

### 3.1 Default view
1. Go to **Review Queue**
2. **Expected:** Table shows all 38 records. Suspicious rows have a red background. Each row shows Scope badge, date, location, description, CO₂e, status badge.

### 3.2 Filter by status
1. Set **Status** filter to `pending`
2. **Expected:** 38 records (all pending after fresh upload)
3. After approving some records, set filter to `approved`
4. **Expected:** Only approved records shown

### 3.3 Filter by scope
1. Set **Scope** filter to `1`
2. **Expected:** Only SAP fuel records (14 total, including the 1 warning row)
3. Set to `2` → utility electricity records
4. Set to `3` → travel records (flights, hotels, ground)

### 3.4 Suspicious-only filter
1. Check **Suspicious only**
2. **Expected:** 18 records shown, all with ⚠ Suspicious badge

### 3.5 Combine filters
1. Set Scope = `1` AND Suspicious only = checked
2. **Expected:** Only Scope 1 suspicious records (plant 9999 row + any SAP rows with other flags)

### 3.6 Open review modal
1. Click any row in the table
2. **Expected:** Modal opens showing:
   - Record description and scope/status/suspicious badges
   - All key fields in a 2-column grid (Category, Date, Location, Source type, Original qty, Normalised qty, Factor, CO₂e)
   - Raw source row section (expandable JSON)
   - Suspicion flags section (if suspicious)
   - Review note textarea
   - Approve / Flag / Reject buttons
   - Audit trail at the bottom (should show 1 entry: "created")

### 3.7 Approve a record
1. Open any pending record → click **Approve**
2. **Expected:**
   - Modal closes
   - Row in table updates to show green "Approved" badge
   - Audit trail now has 2 entries: `created` → `approved`

### 3.8 Approve via API
```bash
# Get a record ID
RECORD_ID=$(curl -s http://localhost:8000/api/records/?page_size=1 \
  -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)['results'][0]['id'])")

curl -s -X POST "http://localhost:8000/api/records/$RECORD_ID/approve/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"note": "Verified against source invoice"}' | python -m json.tool

# Expected: record JSON with review_status: "approved"
```

### 3.9 Reject a record
1. Open a pending record → click **Reject**
2. **Expected:** Status changes to red "Rejected" badge
3. Try approving a rejected record → click **Approve**
4. **Expected:** Works — review status moves back to approved (no restriction on re-review of unlocked records)

### 3.10 Flag a record
1. Open a pending record → click **Flag**
2. **Expected:** Status changes to orange "Flagged — Needs Attention" badge
3. Dashboard's **Flagged** counter increments by 1

### 3.11 Add a review note
1. Open any record, type "Checked against plant fuel log — correct" in the note box
2. Click **Approve**
3. Re-open the same record → expand audit trail
4. **Expected:** Audit log entry shows `action: approved` with the note text

### 3.12 Edit quantity
1. Open any record (not locked)
2. Change the value in **Correct normalised quantity** input to a different number
3. Click **Save edit**
4. **Expected:**
   - Modal closes, record reloads
   - `quantity_normalized` is updated
   - `co2e_kg` is recalculated automatically (new qty × emission factor)
   - `is_edited: true` on the record
   - Audit trail has an `edited` entry with before/after values
   - `original_values` field stores the pre-edit snapshot

### 3.13 Edit — verify CO₂e recalculation
1. Open a diesel SAP record. Note `emission_factor` (should be `2.51839`)
2. Note current `quantity_normalized` (e.g. `1500`) and `co2e_kg` (e.g. `3777.585`)
3. Edit `quantity_normalized` to `2000`
4. **Expected:** `co2e_kg` becomes `2000 × 2.51839 = 5036.78`

### 3.14 Bulk approve
1. Check the checkbox on 5 pending records
2. Click **Approve 5 selected** (top-right of table)
3. **Expected:** All 5 records show "Approved" badge. Button disappears.

### 3.15 Lock a record (API only)
```bash
# First approve the record
curl -s -X POST "http://localhost:8000/api/records/$RECORD_ID/approve/" \
  -H "Authorization: Bearer $TOKEN" -d '{}'

# Then lock it
curl -s -X POST "http://localhost:8000/api/records/$RECORD_ID/lock/" \
  -H "Authorization: Bearer $TOKEN" -d '{}'

# Expected: is_locked: true, locked_at: <timestamp>
```

1. Re-open the locked record in the UI
2. **Expected:** Approve/Flag/Reject buttons are hidden. Grey "This record is locked for audit." message shown.

### 3.16 Edit a locked record (should fail)
```bash
curl -s -X PATCH "http://localhost:8000/api/records/$RECORD_ID/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"quantity_normalized": "9999"}'

# Expected: 403 Forbidden {"error": "Record is locked and cannot be edited."}
```

### 3.17 Lock a non-approved record (should fail)
```bash
# Get a pending record
PENDING_ID=$(curl -s "http://localhost:8000/api/records/?status=pending&page_size=1" \
  -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)['results'][0]['id'])")

curl -s -X POST "http://localhost:8000/api/records/$PENDING_ID/lock/" \
  -H "Authorization: Bearer $TOKEN" -d '{}'

# Expected: 400 Bad Request {"error": "Only approved records can be locked."}
```

---

## 4. Audit Trail

The audit chain runs: `IngestionJob → RawRecord → NormalizedRecord → AuditLog[]`.

### 4.1 Verify creation entry
```bash
curl -s "http://localhost:8000/api/records/$RECORD_ID/audit_trail/" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool

# Expected: first entry has action: "created", before: {}, after contains source_type, scope, co2e_kg, job_id, row_number
```

### 4.2 Full lifecycle audit trail
1. Take a record through the full lifecycle: create → edit → flag → approve → lock
2. Fetch its audit trail
3. **Expected:** 5 entries in chronological order:
   ```
   created   (by admin, at ingestion time)
   edited    (before/after for quantity_normalized)
   flagged   (before: pending, after: flagged)
   approved  (before: flagged, after: approved)
   locked    (after: {is_locked: true})
   ```

### 4.3 Raw source data preserved
1. Open any record modal → expand **Raw source row**
2. **Expected:** JSON shows the exact column values from the original CSV file — no normalisation, no transformation

### 4.4 Check RawRecord via admin
1. Open `http://localhost:8000/admin/` → log in with admin/admin123
2. Go to **Raw records**
3. **Expected:** One RawRecord per data row (including error rows). `raw_data` field contains verbatim CSV row as JSON. `parse_status` is `ok`, `warning`, or `error`.

---

## 5. Dashboard

### 5.1 Scope totals after full upload
After uploading all three sample files:

| Metric         | Expected value         |
|----------------|------------------------|
| Total CO₂e     | ~195,447 kg (~195 t)   |
| Scope 1        | ~42,584 kgCO₂e         |
| Scope 2        | ~148,662 kgCO₂e        |
| Scope 3        | ~4,200 kgCO₂e          |
| Pending review | 38                     |
| Suspicious     | 18                     |

### 5.2 Totals update after approval
1. Note current Scope 1 CO₂e total
2. Reject a Scope 1 record (rejection does not remove from CO₂e total — rejected records are still counted)
3. **Expected:** CO₂e totals unchanged (rejection is a review state, not a deletion)

### 5.3 Quick actions
1. Click **Review pending (38)** → should navigate to `/review?status=pending`
2. Click **Upload new data** → should navigate to `/ingest`

### 5.4 Recent jobs panel
- Shows last 5 ingestion jobs
- Each row shows filename, source type, status badge, ok/error counts, and date
- **Expected after 3 uploads:** SAP, Utility, Travel jobs all visible

---

## 6. Job History

### 6.1 All jobs listed
1. Go to **Job History**
2. **Expected:** 3 jobs shown (one per upload), most recent first

### 6.2 Expand errors
1. Click the SAP job row
2. **Expected:** Red section shows 1 error: "Row 15: Unknown fuel type..."
3. Click a job with no errors (e.g. Birmingham Factory utility rows only)
4. **Expected:** Green "All rows parsed successfully." message

### 6.3 Status badges
- Completed jobs → green "completed" badge
- If you kill the server mid-upload and restart, the stuck job will have status "processing" — shown with blue badge

---

## 7. API — Edge Cases

### 7.1 Missing auth header
```bash
curl -s http://localhost:8000/api/records/
# Expected: 401 Unauthorized
```

### 7.2 Ingest unknown source type
```bash
curl -s -X POST http://localhost:8000/api/ingest/unknown/ \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sample_data/sap_fuel_export.csv"
# Expected: 400 {"error": "Unknown source type 'unknown'"}
```

### 7.3 Ingest without file
```bash
curl -s -X POST http://localhost:8000/api/ingest/sap/ \
  -H "Authorization: Bearer $TOKEN"
# Expected: 400 {"error": "No file provided"}
```

### 7.4 Bulk approve with empty list
```bash
curl -s -X POST http://localhost:8000/api/records/bulk_approve/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ids": []}'
# Expected: 400 {"error": "No ids provided."}
```

### 7.5 Record filtering
```bash
# Filter by scope
curl -s "http://localhost:8000/api/records/?scope=1" -H "Authorization: Bearer $TOKEN"

# Filter by review status
curl -s "http://localhost:8000/api/records/?status=pending" -H "Authorization: Bearer $TOKEN"

# Filter suspicious only
curl -s "http://localhost:8000/api/records/?suspicious=true" -H "Authorization: Bearer $TOKEN"

# Filter by job ID (from job history)
curl -s "http://localhost:8000/api/records/?job=<job-uuid>" -H "Authorization: Bearer $TOKEN"
```

---

## 8. Emission Factor Verification

Cross-check a few calculated CO₂e values against DEFRA 2023 manually.

### 8.1 Diesel (Scope 1)
Find the diesel record for plant 1000, Jan 1 2024 (1,500 L):
- Factor: `2.51839 kgCO₂e/L`
- Expected CO₂e: `1500 × 2.51839 = 3,777.585 kgCO₂e`

### 8.2 Electricity — Birmingham Factory (Scope 2)
Row: 185,000 kWh, Jan 1–Feb 1:
- Factor: `0.20493 kgCO₂e/kWh` (UK grid 2023)
- Expected CO₂e: `185,000 × 0.20493 = 37,912.05 kgCO₂e`

### 8.3 LHR→JFK flight (Scope 3)
Economy, long-haul:
- Great-circle distance: ~5,570 km (calculated by haversine)
- Factor: `0.15302 kgCO₂e/PKM` (long-haul economy, includes RFI 1.891)
- Expected CO₂e: `5570 × 0.15302 ≈ 852.32 kgCO₂e`

### 8.4 Hotel — New York, 3 nights (Scope 3)
- Factor: `31.0 kgCO₂e/room-night`
- Expected CO₂e: `3 × 31.0 = 93.0 kgCO₂e`

To verify via API:
```bash
# Get all scope 1 records and check co2e_kg values
curl -s "http://localhost:8000/api/records/?scope=1" \
  -H "Authorization: Bearer $TOKEN" | python -c "
import sys, json
data = json.load(sys.stdin)
for r in data.get('results', []):
    print(f\"{r['description']:50s} | {r['quantity_normalized']} {r['unit_normalized']} | {r['co2e_kg']} kgCO2e\")
"
```

---

## 9. Multi-tenancy

### 9.1 Tenant isolation
The seed command creates one tenant (ACME Manufacturing). To test isolation:

```bash
# Via Django admin — create a second tenant and user
python manage.py shell -c "
from api.models import Tenant, User
t2 = Tenant.objects.create(name='Acme Corp 2', slug='acme-2')
u2 = User.objects.create_user('analyst2', password='analyst2', tenant=t2, role='analyst')
"

# Log in as analyst2 and check records
TOKEN2=$(curl -s -X POST http://localhost:8000/api/auth/token/ \
  -d '{"username":"analyst2","password":"analyst2"}' \
  -H "Content-Type: application/json" | python -c "import sys,json; print(json.load(sys.stdin)['access'])")

curl -s http://localhost:8000/api/records/ -H "Authorization: Bearer $TOKEN2"
# Expected: empty results list — analyst2 cannot see ACME Manufacturing's records
```

---

## 10. Sample Data — What Each Row Tests

### SAP (`sap_fuel_export.csv`)

| Row | What it tests |
|-----|---------------|
| 1–2 | Diesel, plant 1000, standard parse |
| 3 | Diesel, plant 2000, German decimal `2.200,500` |
| 4 | Petrol ("Ottokraftstoff") — alias matching |
| 5–7 | Natural gas ("Erdgas") in M3 — unit conversion path |
| 8–9 | LPG ("Flüssiggas") in KG — third fuel type |
| 10 | Negative quantity reversal entry — negative CO₂e preserved |
| 11–13 | February entries — second month, same logic |
| 14 | Plant code `9999` — suspicion flag (not in lookup table) |
| 15 | "Unbekanntes Material" — error path, no emission factor |

### Utility (`utility_electricity.csv`)

| Row | What it tests |
|-----|---------------|
| 1–2 | London HQ, two meters, same billing period Jan 8–Feb 6 |
| 3 | London HQ, February billing period |
| 4 | Manchester, kWh, non-calendar period (Dec 22–Jan 24) |
| 5 | Manchester, MWh unit → converted to kWh (×1000) |
| 6 | Manchester, February |
| 7–8 | Birmingham Factory, calendar month, high consumption |
| 9 | Birmingham, February |
| 10 | Missing consumption — error row |

### Travel (`concur_travel_export.csv`)

| Row | What it tests |
|-----|---------------|
| 1 | LHR→JFK Economy — long-haul, distance from airport codes |
| 2 | Hotel NYC 3 nights — room-night factor |
| 3 | Taxi JFK — ground transport, no distance (CO₂e = 0, flagged) |
| 4 | JFK→LHR Economy — return leg |
| 5 | LHR→CDG Business — short-haul, business class factor |
| 6 | Hotel Paris 2 nights |
| 7 | Taxi CDG — ground, no distance |
| 8 | CDG→LHR Business — return, short-haul |
| 9 | LHR→DXB Economy — medium long-haul |
| 10 | Hotel Dubai 4 nights |
| 11 | DXB→LHR Economy — return |
| 12 | MAN→AMS Economy — short-haul from Manchester |
| 13 | Hotel Amsterdam 1 night |
| 14 | AMS→MAN Economy — return |
| 15 | Car Rental Birmingham — no distance, CO₂e = 0, flagged |
| 16 | XXX→YYY — unknown IATA codes, parse error |

---

## 11. Deployment Smoke Test (Render)

After deploying using `render.yaml`:

1. Visit `https://breathe-esg-backend.onrender.com/api/auth/token/` — should return 405 (GET not allowed), confirming Django is running
2. POST credentials → get token
3. Visit frontend URL → login page loads
4. Upload all three sample files via the UI
5. Verify dashboard shows expected CO₂e totals
6. Check job history — all three jobs show `completed`
7. Approve one record, verify audit trail via API

---

## Known Limitations (by design — see TRADEOFFS.md)

| Limitation | Behaviour |
|------------|-----------|
| Duplicate uploads not detected | Uploading the same file twice doubles the records |
| No proration of utility billing periods | Non-calendar billing periods are stored as-is and flagged |
| Scope 3 procurement (SAP MM) not implemented | Only Scope 1 fuel and Scope 3 travel are handled |
| Ground transport without distance | CO₂e recorded as 0, analyst must correct manually |
| Hotel factors UK-only | All hotels use DEFRA UK average regardless of country |
| No PDF/API ingestion | File upload only; real-time API pull not implemented |
