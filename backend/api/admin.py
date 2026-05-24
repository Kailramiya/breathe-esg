from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Tenant, User, IngestionJob, RawRecord, NormalizedRecord, AuditLog, PlantLookup


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "created_at"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Breathe ESG", {"fields": ("tenant", "role")}),
    )
    list_display = ["username", "email", "tenant", "role", "is_staff"]


@admin.register(PlantLookup)
class PlantLookupAdmin(admin.ModelAdmin):
    list_display = ["tenant", "plant_code", "plant_name", "city", "country"]
    list_filter = ["tenant"]


@admin.register(IngestionJob)
class IngestionJobAdmin(admin.ModelAdmin):
    list_display = ["original_filename", "source_type", "status", "tenant",
                    "row_count_total", "row_count_error", "ingested_at"]
    list_filter = ["status", "source_type", "tenant"]
    readonly_fields = ["id", "ingested_at", "completed_at"]


@admin.register(NormalizedRecord)
class NormalizedRecordAdmin(admin.ModelAdmin):
    list_display = ["source_type", "scope", "activity_date", "co2e_kg",
                    "review_status", "is_suspicious", "tenant"]
    list_filter = ["scope", "review_status", "source_type", "is_suspicious", "tenant"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["action", "record", "actor", "timestamp"]
    readonly_fields = ["id", "timestamp"]
