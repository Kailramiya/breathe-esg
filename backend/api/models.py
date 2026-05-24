import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser


class Tenant(models.Model):
    """
    An enterprise client company. Every piece of data is scoped to a tenant.
    Row-level isolation is enforced in viewset querysets, not at the DB layer —
    an acceptable tradeoff for a prototype (see TRADEOFFS.md).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    """
    Extends Django's AbstractUser to bind users to a tenant and assign roles.
    A user's tenant determines which records they can see — this is the primary
    multi-tenancy enforcement point.
    """
    ROLE_ANALYST = "analyst"
    ROLE_ADMIN = "admin"
    ROLE_CHOICES = [
        (ROLE_ANALYST, "Analyst"),
        (ROLE_ADMIN, "Admin"),
    ]

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="users", null=True, blank=True
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ANALYST)

    def __str__(self):
        return f"{self.username} ({self.tenant})"


class PlantLookup(models.Model):
    """
    Resolves SAP plant codes (WERKS) to human-readable site names and locations.
    Each client has their own plant codes, so this is tenant-scoped.
    Without this table, plant code '1000' is meaningless to an analyst.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="plants")
    plant_code = models.CharField(max_length=20)
    plant_name = models.CharField(max_length=255)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ("tenant", "plant_code")

    def __str__(self):
        return f"{self.plant_code} — {self.plant_name}"


class IngestionJob(models.Model):
    """
    One upload session. Created when a file is uploaded; tracks parse outcome.
    Storing the original file lets auditors verify we didn't alter the source.
    status transitions: pending → processing → completed | failed
    """
    SOURCE_SAP = "sap"
    SOURCE_UTILITY = "utility"
    SOURCE_TRAVEL = "travel"
    SOURCE_CHOICES = [
        (SOURCE_SAP, "SAP Fuel & Procurement"),
        (SOURCE_UTILITY, "Utility Electricity"),
        (SOURCE_TRAVEL, "Corporate Travel"),
    ]

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="jobs")
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    original_filename = models.CharField(max_length=255)
    raw_file = models.FileField(upload_to="uploads/", null=True, blank=True)
    row_count_total = models.IntegerField(default=0)
    row_count_ok = models.IntegerField(default=0)
    row_count_error = models.IntegerField(default=0)
    row_count_warning = models.IntegerField(default=0)
    error_summary = models.JSONField(default=list)
    ingested_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="jobs"
    )
    ingested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_source_type_display()} — {self.original_filename} ({self.status})"


class RawRecord(models.Model):
    """
    An immutable snapshot of a single row as it arrived from the source file.
    raw_data stores the original row as JSON so nothing is ever lost.
    parse_errors explains why a row couldn't be normalized (missing unit, unknown
    plant code, etc.). This is separate from NormalizedRecord so that a failed
    parse doesn't lose the source data — an analyst can manually correct and
    re-queue if needed.
    """
    PARSE_OK = "ok"
    PARSE_ERROR = "error"
    PARSE_WARNING = "warning"
    PARSE_STATUS_CHOICES = [
        (PARSE_OK, "OK"),
        (PARSE_ERROR, "Error"),
        (PARSE_WARNING, "Warning"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(IngestionJob, on_delete=models.CASCADE, related_name="raw_records")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="raw_records")
    row_number = models.IntegerField()
    raw_data = models.JSONField()
    parse_status = models.CharField(max_length=10, choices=PARSE_STATUS_CHOICES, default=PARSE_OK)
    parse_errors = models.JSONField(default=list)

    class Meta:
        ordering = ["job", "row_number"]

    def __str__(self):
        return f"Row {self.row_number} of {self.job}"


class NormalizedRecord(models.Model):
    """
    The clean, unit-normalized, emission-calculated record that analysts review.

    Design principles:
    - raw_record links back to the exact source row (immutable audit chain)
    - quantity_original / unit_original are preserved verbatim from the source
    - quantity_normalized + unit_normalized are the post-conversion values
    - co2e_kg is always the final calculated figure in kg CO2e
    - emission_factor and emission_factor_source are snapshotted at creation time
      so that changing the factor table never retroactively alters approved records
    - is_edited + original_values allow analysts to correct bad data while
      maintaining an audit trail of what was changed
    - review_status drives the analyst dashboard workflow
    - is_locked = True means the record has been signed off and is frozen for audit
    """

    # --- Source type (more granular than IngestionJob.source_type) ---
    SOURCE_SAP_FUEL = "sap_fuel"
    SOURCE_SAP_PROCUREMENT = "sap_procurement"
    SOURCE_UTILITY_ELECTRICITY = "utility_electricity"
    SOURCE_TRAVEL_FLIGHT = "travel_flight"
    SOURCE_TRAVEL_HOTEL = "travel_hotel"
    SOURCE_TRAVEL_GROUND = "travel_ground"
    SOURCE_TYPE_CHOICES = [
        (SOURCE_SAP_FUEL, "SAP — Fuel Combustion"),
        (SOURCE_SAP_PROCUREMENT, "SAP — Procurement"),
        (SOURCE_UTILITY_ELECTRICITY, "Utility — Electricity"),
        (SOURCE_TRAVEL_FLIGHT, "Travel — Flight"),
        (SOURCE_TRAVEL_HOTEL, "Travel — Hotel"),
        (SOURCE_TRAVEL_GROUND, "Travel — Ground Transport"),
    ]

    # --- GHG Protocol scope ---
    SCOPE_1 = "1"
    SCOPE_2 = "2"
    SCOPE_3 = "3"
    SCOPE_CHOICES = [
        (SCOPE_1, "Scope 1 — Direct"),
        (SCOPE_2, "Scope 2 — Purchased Energy"),
        (SCOPE_3, "Scope 3 — Value Chain"),
    ]

    # --- Review status ---
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_FLAGGED = "flagged"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending Review"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_FLAGGED, "Flagged — Needs Attention"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="records")
    raw_record = models.OneToOneField(
        RawRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="normalized"
    )
    source_type = models.CharField(max_length=30, choices=SOURCE_TYPE_CHOICES)
    source_job = models.ForeignKey(
        IngestionJob, on_delete=models.CASCADE, related_name="normalized_records"
    )

    # --- GHG scope + category ---
    scope = models.CharField(max_length=1, choices=SCOPE_CHOICES)
    category = models.CharField(max_length=100)  # e.g. "Stationary combustion", "Purchased electricity"

    # --- Activity period ---
    activity_date = models.DateField()
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    # --- Location / site ---
    location_raw = models.CharField(max_length=255, blank=True)   # plant code, site name, city
    location_resolved = models.CharField(max_length=255, blank=True)  # after PlantLookup resolution

    # --- Activity description ---
    description = models.CharField(max_length=500, blank=True)    # fuel type, meter ID, route, etc.
    employee_id = models.CharField(max_length=100, blank=True)    # travel records

    # --- Quantity as ingested (verbatim) ---
    quantity_original = models.DecimalField(max_digits=18, decimal_places=4)
    unit_original = models.CharField(max_length=20)               # L, M3, kWh, MWh, PKM, night, km

    # --- Quantity after unit normalization ---
    quantity_normalized = models.DecimalField(max_digits=18, decimal_places=4)
    unit_normalized = models.CharField(max_length=20)             # L, kWh, PKM, night, km (consistent per scope)

    # --- Emission calculation ---
    emission_factor = models.DecimalField(max_digits=12, decimal_places=6)    # kgCO2e per unit_normalized
    emission_factor_source = models.CharField(max_length=100)     # e.g. "DEFRA_2023", "EPA_2023"
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=4)

    # --- Analyst review ---
    review_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_records"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    # --- Suspicious activity flags ---
    is_suspicious = models.BooleanField(default=False)
    suspicion_reasons = models.JSONField(default=list)

    # --- Edit tracking ---
    # If an analyst corrects a value (e.g. wrong unit, typo in quantity), we store
    # what the record looked like before so the audit trail is complete.
    is_edited = models.BooleanField(default=False)
    original_values = models.JSONField(default=dict)  # snapshot of fields before first edit

    # --- Audit lock ---
    # Once locked, the record cannot be edited or re-reviewed. Lock is set
    # when a batch is submitted to auditors.
    is_locked = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="locked_records"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activity_date", "scope", "source_type"]
        indexes = [
            models.Index(fields=["tenant", "review_status"]),
            models.Index(fields=["tenant", "scope"]),
            models.Index(fields=["tenant", "activity_date"]),
            models.Index(fields=["tenant", "is_suspicious"]),
        ]

    def __str__(self):
        return f"{self.get_source_type_display()} | {self.activity_date} | {self.co2e_kg} kgCO2e"


class AuditLog(models.Model):
    """
    Append-only log of every state change on a NormalizedRecord.
    Never delete entries from this table. before/after store the full
    field snapshot so any version of a record can be reconstructed.
    """
    ACTION_CREATED = "created"
    ACTION_EDITED = "edited"
    ACTION_APPROVED = "approved"
    ACTION_REJECTED = "rejected"
    ACTION_FLAGGED = "flagged"
    ACTION_LOCKED = "locked"
    ACTION_CHOICES = [
        (ACTION_CREATED, "Created"),
        (ACTION_EDITED, "Edited"),
        (ACTION_APPROVED, "Approved"),
        (ACTION_REJECTED, "Rejected"),
        (ACTION_FLAGGED, "Flagged"),
        (ACTION_LOCKED, "Locked for Audit"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="audit_logs")
    record = models.ForeignKey(
        NormalizedRecord, on_delete=models.CASCADE, related_name="audit_logs"
    )
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="audit_logs")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    note = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.action} on {self.record_id} by {self.actor} at {self.timestamp}"
