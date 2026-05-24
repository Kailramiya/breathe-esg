# Tradeoffs

Three things I deliberately did not build, and why.

---

## 1. Prorating utility consumption across calendar month boundaries

**What it would do:** If a billing period runs Dec 22 – Jan 24 (34 days), prorate the consumption: assign 10/34 to December and 24/34 to January. This matters for month-by-month Scope 2 reporting and for aligning utility data with other monthly sources.

**Why I didn't build it:**
Prorating introduces a calculation that is invisible to the analyst and hard to audit. The raw row says "45,230 kWh from Jan 8 to Feb 6." If we silently split that into 4,087 kWh for January and 41,143 kWh for February, an auditor will ask why the numbers don't match the source — and the explanation requires understanding our proration algorithm.

The safer approach is to store the full billing period as-is (what I did), flag non-calendar-month periods for analyst awareness, and let the reporting layer aggregate by calendar month using the period_start/period_end dates. The analyst retains visibility and can decide whether to prorate.

**What I'd need to add it:** A clear proration method documented in MODEL.md, a `proration_method` field on the record (linear/actual days), and a UI indicator that a record is synthetic (a proration artefact, not a source row). Without all three, prorating silently introduces numbers that don't exist in any source document.

---

## 2. Scope 3 Category 1 procurement from SAP (purchased goods and services)

**What it would do:** Extract purchase order line items from SAP's MM module (transaction ME2M or the Purchasing Information System), map materials to spend categories, apply spend-based or average-data emission factors to calculate upstream Scope 3.

**Why I didn't build it:**
This is a fundamentally different data problem from Scope 1 fuel consumption. MB51 gives you quantity consumed; procurement data gives you purchase value. Spend-based Scope 3 requires:
- Mapping SAP material groups to NAICS/SIC spend categories
- Sourcing spend-based emission factors (EXIOBASE, EPA USEEIO)
- Handling multi-currency spend across different fiscal periods
- Deciding whether to use spend-based or supplier-specific factors

That's a prototype in its own right. Including a skeleton implementation would have been worse than excluding it cleanly — it would have looked complete without being correct.

**What I'd ask before building it:** Are they on SAP Spend Management? Do they want spend-based (easier, less accurate) or supplier-specific factors (requires supplier engagement)? What's the materiality threshold — do they want all procurement or only above-threshold categories?

---

## 3. Real-time SAP/Concur API integration (pull-based ingestion)

**What it would do:** Instead of file upload, periodically pull data directly from SAP's OData service or Concur's Expense v4 API on a schedule. New records appear automatically; analysts don't need to export and upload.

**Why I didn't build it:**
This is operationally correct but practically impossible to implement without client credentials. SAP OData requires RFC connection parameters and potentially VPN access. Concur's API requires OAuth2 client credentials provisioned by the enterprise Concur admin. Neither of these are available for a prototype.

More importantly, file upload is not just a prototype shortcut — it reflects how onboarding actually starts. A new client will send you a CSV export long before they're ready to grant API access. Building the file-based path first means the prototype is usable immediately, on real data.

**What I'd add for production:** A `DataConnection` model storing OAuth credentials or RFC parameters per tenant, a Celery task queue for scheduled pulls, and incremental sync logic (tracking `last_synced_at` to avoid re-importing records already seen). The `IngestionJob` model already has the right shape to track these pull-based jobs alongside upload-based ones.
