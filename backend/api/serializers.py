from rest_framework import serializers
from .models import Tenant, User, IngestionJob, RawRecord, NormalizedRecord, AuditLog, PlantLookup


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "created_at"]


class UserSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "tenant", "tenant_name"]


class IngestionJobSerializer(serializers.ModelSerializer):
    ingested_by_username = serializers.CharField(source="ingested_by.username", read_only=True)
    source_type_display  = serializers.CharField(source="get_source_type_display", read_only=True)

    class Meta:
        model = IngestionJob
        fields = [
            "id", "source_type", "source_type_display", "status",
            "original_filename", "row_count_total", "row_count_ok",
            "row_count_error", "row_count_warning", "error_summary",
            "ingested_by_username", "ingested_at", "completed_at",
        ]


class RawRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawRecord
        fields = ["id", "row_number", "raw_data", "parse_status", "parse_errors"]


class NormalizedRecordSerializer(serializers.ModelSerializer):
    scope_display       = serializers.CharField(source="get_scope_display", read_only=True)
    source_type_display = serializers.CharField(source="get_source_type_display", read_only=True)
    review_status_display = serializers.CharField(source="get_review_status_display", read_only=True)
    reviewed_by_username  = serializers.CharField(source="reviewed_by.username", read_only=True)
    raw_data = serializers.SerializerMethodField()

    def get_raw_data(self, obj):
        if obj.raw_record:
            return obj.raw_record.raw_data
        return None

    class Meta:
        model = NormalizedRecord
        fields = [
            "id", "source_type", "source_type_display",
            "scope", "scope_display", "category",
            "activity_date", "period_start", "period_end",
            "location_raw", "location_resolved",
            "description", "employee_id",
            "quantity_original", "unit_original",
            "quantity_normalized", "unit_normalized",
            "emission_factor", "emission_factor_source", "co2e_kg",
            "review_status", "review_status_display",
            "reviewed_by_username", "reviewed_at", "review_note",
            "is_suspicious", "suspicion_reasons",
            "is_edited", "original_values",
            "is_locked", "locked_at",
            "created_at", "updated_at",
            "raw_data",
        ]
        read_only_fields = [
            "id", "source_type", "scope", "category",
            "emission_factor", "emission_factor_source",
            "is_locked", "locked_at", "locked_by",
            "created_at", "updated_at",
        ]


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True)
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "actor_username", "action", "action_display",
                  "before", "after", "note", "timestamp"]


class PlantLookupSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantLookup
        fields = ["id", "plant_code", "plant_name", "city", "country"]
