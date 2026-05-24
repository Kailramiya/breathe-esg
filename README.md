# Breathe ESG — Data Ingestion & Review Platform

Django REST + React prototype for ingesting, normalising, and reviewing ESG emissions data from SAP, utility portals, and corporate travel systems.

---

## Demo credentials

| Role    | Username | Password    |
|---------|----------|-------------|
| Admin   | admin    | admin123    |
| Analyst | analyst  | analyst123  |

---

## Local setup

### Backend

```bash
cd backend
pip install -r requirements.txt   # installs Django, DRF, simplejwt, etc.
python manage.py migrate
python manage.py seed             # creates demo tenant, users, plant lookups
python manage.py runserver
```

Backend runs on `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173`. The Vite proxy forwards `/api` requests to Django.

---

## Testing guide

### Step 1 — Start both servers

Terminal 1 (backend):
```bash
cd backend && python manage.py runserver
```

Terminal 2 (frontend):
```bash
cd frontend && npm run dev
```

Open `http://localhost:5173/login` → log in as `admin / admin123`.

### Step 2 — Upload sample files (Ingest page)

| File | Source type | Expected result |
|------|-------------|-----------------|
| `sample_data/sap_fuel_export.csv` | SAP | 13 ok, 1 warning (plant 9999 not in lookup), 1 error (unknown material — no emission factor) |
| `sample_data/utility_electricity.csv` | Utility | 3 ok, 6 warnings (non-calendar billing periods flagged), 1 error (missing consumption value) |
| `sample_data/concur_travel_export.csv` | Travel | 4 ok, 11 warnings (distance calculated from airport codes / nights assumed), 1 error (unknown IATA codes XXX/YYY) |

Total: **38 records** created across Scope 1/2/3. All start as `pending`. 18 flagged as suspicious.

Each upload shows a result card with OK / Warning / Error counts. Errors are expandable with the row number and reason.

### Step 3 — Review queue

- Filter by **Status = pending** to see all unreviewed records
- Filter by **Suspicious only** to see flagged anomalies:
  - SAP row with plant code `9999` (not in lookup table)
  - SAP row with reversal entry (negative CO₂e)
  - Utility row with non-calendar billing period
  - Travel flight with distance calculated from airport codes
- Click any row → review modal shows:
  - Raw source data (exactly as it arrived in the file)
  - Normalised quantity + unit + emission factor source
  - Suspicion flags with explanations
  - Approve / Flag / Reject buttons
  - Full audit trail

### Step 4 — Analyst actions

- **Approve**: sets `review_status = approved`, writes AuditLog entry
- **Reject**: sets `review_status = rejected`, analyst must add a note
- **Flag**: marks for follow-up without blocking the record
- **Edit quantity**: corrects a value; recalculates CO₂e; snapshots original values in `original_values`; writes AuditLog
- **Bulk approve**: select multiple pending rows → approve in one click
- **Lock** (via API): freezes an approved record — no further edits possible

### Step 5 — Dashboard

After uploading all three files, the dashboard shows:
- Total CO₂e in tonnes split by Scope 1 / 2 / 3
- Pending review count, flagged count, suspicious count
- Recent job history with row counts

---

## Deployment (Render)

### Backend (Web Service)

- **Build command:** `pip install -r requirements.txt && python manage.py migrate && python manage.py seed`
- **Start command:** `gunicorn breathe.wsgi`
- **Environment variables:**
  ```
  SECRET_KEY=<random string>
  DEBUG=False
  ALLOWED_HOSTS=your-backend.onrender.com
  DATABASE_URL=<provided by Render PostgreSQL addon>
  CORS_ALLOWED_ORIGINS=https://your-frontend.onrender.com
  ```

### Frontend (Static Site)

- **Build command:** `npm install && npm run build`
- **Publish directory:** `dist`
- **Environment variables:**
  ```
  VITE_API_URL=https://your-backend.onrender.com/api
  ```

---

## Project structure

```
breathe-esg/
├── backend/
│   ├── api/
│   │   ├── models.py          # data model (see MODEL.md)
│   │   ├── views.py           # ingest, review, dashboard endpoints
│   │   ├── serializers.py
│   │   ├── emission_factors.py  # DEFRA 2023 constants
│   │   └── parsers/
│   │       ├── sap.py         # MB51 flat file parser
│   │       ├── utility.py     # utility portal CSV parser
│   │       └── travel.py      # Concur expense extract parser
│   └── breathe/               # Django project settings
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.jsx  # CO₂e summary + recent jobs
│       │   ├── Ingest.jsx     # file upload per source type
│       │   ├── Review.jsx     # analyst review queue
│       │   └── Jobs.jsx       # ingestion job history
│       └── components/
├── sample_data/               # realistic test files
├── MODEL.md                   # data model and design rationale
├── DECISIONS.md               # every ambiguity resolved
├── TRADEOFFS.md               # three things not built and why
└── SOURCES.md                 # research on each data source
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/token/` | Obtain JWT |
| POST | `/api/auth/token/refresh/` | Refresh JWT |
| GET | `/api/auth/me/` | Current user |
| GET | `/api/dashboard/` | CO₂e summary + recent jobs |
| POST | `/api/ingest/sap/` | Upload SAP flat file |
| POST | `/api/ingest/utility/` | Upload utility CSV |
| POST | `/api/ingest/travel/` | Upload travel CSV |
| GET | `/api/records/` | List records (filterable) |
| PATCH | `/api/records/{id}/` | Edit a record |
| POST | `/api/records/{id}/approve/` | Approve |
| POST | `/api/records/{id}/reject/` | Reject |
| POST | `/api/records/{id}/flag/` | Flag |
| POST | `/api/records/{id}/lock/` | Lock for audit |
| GET | `/api/records/{id}/audit_trail/` | Full audit trail |
| POST | `/api/records/bulk_approve/` | Approve multiple records |
| GET | `/api/jobs/` | List ingestion jobs |
