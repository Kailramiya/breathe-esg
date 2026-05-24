from datetime import datetime, timezone
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    IngestionJob, NormalizedRecord, RawRecord, AuditLog, PlantLookup, Tenant, User
)
from .serializers import (
    IngestionJobSerializer, NormalizedRecordSerializer,
    AuditLogSerializer, PlantLookupSerializer, UserSerializer,
)
from .parsers.sap import parse_sap_file
from .parsers.utility import parse_utility_file
from .parsers.travel import parse_travel_file


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class DashboardView(APIView):
    def get(self, request):
        tenant = request.user.tenant
        qs = NormalizedRecord.objects.filter(tenant=tenant)

        scope_totals = {}
        for scope in ("1", "2", "3"):
            agg = qs.filter(scope=scope).aggregate(total=Sum("co2e_kg"))
            scope_totals[f"scope_{scope}"] = round(float(agg["total"] or 0), 2)

        return Response({
            "total_co2e_kg": round(sum(scope_totals.values()), 2),
            "scope_totals": scope_totals,
            "pending_review": qs.filter(review_status="pending").count(),
            "flagged": qs.filter(review_status="flagged").count(),
            "suspicious": qs.filter(is_suspicious=True, review_status="pending").count(),
            "approved": qs.filter(review_status="approved").count(),
            "total_records": qs.count(),
            "recent_jobs": IngestionJobSerializer(
                IngestionJob.objects.filter(tenant=tenant).order_by("-ingested_at")[:5],
                many=True
            ).data,
        })


class IngestView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    SOURCE_PARSERS = {
        "sap":     parse_sap_file,
        "utility": parse_utility_file,
        "travel":  parse_travel_file,
    }

    def post(self, request, source_type):
        if source_type not in self.SOURCE_PARSERS:
            return Response(
                {"error": f"Unknown source type '{source_type}'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

        tenant = request.user.tenant
        job = IngestionJob.objects.create(
            tenant=tenant,
            source_type=source_type,
            status=IngestionJob.STATUS_PROCESSING,
            original_filename=file_obj.name,
            raw_file=file_obj,
            ingested_by=request.user,
        )

        try:
            file_obj.seek(0)
            plant_lookup = {}
            if source_type == "sap":
                plant_lookup = {
                    p.plant_code: p.plant_name
                    for p in PlantLookup.objects.filter(tenant=tenant)
                }
                results = parse_sap_file(file_obj, plant_lookup)
            elif source_type == "utility":
                results = parse_utility_file(file_obj)
            else:
                results = parse_travel_file(file_obj)

            ok = error = warning = 0
            errors_summary = []

            with transaction.atomic():
                for r in results:
                    if not r.get("raw_data"):
                        continue

                    raw_rec = RawRecord.objects.create(
                        job=job,
                        tenant=tenant,
                        row_number=r["row_number"],
                        raw_data=r["raw_data"],
                        parse_status=r["status"],
                        parse_errors=r["errors"],
                    )

                    if r["status"] == "error":
                        error += 1
                        errors_summary.append({
                            "row": r["row_number"],
                            "errors": r["errors"],
                        })
                        continue

                    rec_data = r.get("record")
                    if not rec_data:
                        continue

                    norm = NormalizedRecord.objects.create(
                        tenant=tenant,
                        raw_record=raw_rec,
                        source_job=job,
                        source_type=rec_data["source_type"],
                        scope=rec_data["scope"],
                        category=rec_data["category"],
                        activity_date=rec_data["activity_date"],
                        period_start=rec_data.get("period_start"),
                        period_end=rec_data.get("period_end"),
                        location_raw=rec_data.get("location_raw", ""),
                        location_resolved=rec_data.get("location_resolved", ""),
                        description=rec_data.get("description", ""),
                        employee_id=rec_data.get("employee_id", ""),
                        quantity_original=Decimal(rec_data["quantity_original"]),
                        unit_original=rec_data["unit_original"],
                        quantity_normalized=Decimal(rec_data["quantity_normalized"]),
                        unit_normalized=rec_data["unit_normalized"],
                        emission_factor=Decimal(rec_data["emission_factor"]),
                        emission_factor_source=rec_data["emission_factor_source"],
                        co2e_kg=Decimal(rec_data["co2e_kg"]),
                        is_suspicious=rec_data.get("is_suspicious", False),
                        suspicion_reasons=rec_data.get("suspicion_reasons", []),
                        review_status=NormalizedRecord.STATUS_PENDING,
                    )
                    AuditLog.objects.create(
                        tenant=tenant,
                        record=norm,
                        actor=request.user,
                        action=AuditLog.ACTION_CREATED,
                        before={},
                        after={
                            "source_type": norm.source_type,
                            "scope": norm.scope,
                            "co2e_kg": str(norm.co2e_kg),
                            "emission_factor_source": norm.emission_factor_source,
                            "job_id": str(job.id),
                            "row_number": r["row_number"],
                        },
                    )
                    if r["status"] == "warning":
                        warning += 1
                    else:
                        ok += 1

            job.status = IngestionJob.STATUS_COMPLETED
            job.row_count_total = ok + warning + error
            job.row_count_ok = ok
            job.row_count_error = error
            job.row_count_warning = warning
            job.error_summary = errors_summary
            job.completed_at = datetime.now(timezone.utc)
            job.save()

        except Exception as exc:
            job.status = IngestionJob.STATUS_FAILED
            job.error_summary = [{"error": str(exc)}]
            job.save()
            return Response(
                {"error": str(exc), "job_id": str(job.id)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(IngestionJobSerializer(job).data, status=status.HTTP_201_CREATED)


class JobViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = IngestionJobSerializer

    def get_queryset(self):
        return IngestionJob.objects.filter(
            tenant=self.request.user.tenant
        ).order_by("-ingested_at")


class RecordViewSet(viewsets.ModelViewSet):
    serializer_class = NormalizedRecordSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = NormalizedRecord.objects.filter(tenant=self.request.user.tenant)
        params = self.request.query_params

        if scope := params.get("scope"):
            qs = qs.filter(scope=scope)
        if review_status := params.get("status"):
            qs = qs.filter(review_status=review_status)
        if source_type := params.get("source_type"):
            qs = qs.filter(source_type=source_type)
        if suspicious := params.get("suspicious"):
            qs = qs.filter(is_suspicious=suspicious.lower() == "true")
        if job_id := params.get("job"):
            qs = qs.filter(source_job_id=job_id)

        return qs.select_related("raw_record", "reviewed_by", "source_job")

    def partial_update(self, request, *args, **kwargs):
        record = self.get_object()
        if record.is_locked:
            return Response(
                {"error": "Record is locked and cannot be edited."},
                status=status.HTTP_403_FORBIDDEN,
            )

        allowed = {"quantity_original", "unit_original", "quantity_normalized",
                   "unit_normalized", "description", "location_resolved", "review_note"}
        updates = {k: v for k, v in request.data.items() if k in allowed}

        if not updates:
            return Response({"error": "No editable fields provided."}, status=status.HTTP_400_BAD_REQUEST)

        # Snapshot before edit
        if not record.is_edited:
            record.original_values = {
                "quantity_original": str(record.quantity_original),
                "unit_original": record.unit_original,
                "quantity_normalized": str(record.quantity_normalized),
                "unit_normalized": record.unit_normalized,
                "description": record.description,
                "location_resolved": record.location_resolved,
            }

        before = {k: str(getattr(record, k, "")) for k in updates}
        for k, v in updates.items():
            setattr(record, k, v)

        # Recalculate co2e if quantity/unit changed
        if "quantity_normalized" in updates:
            try:
                new_co2e = float(Decimal(updates["quantity_normalized"])) * float(record.emission_factor)
                record.co2e_kg = Decimal(str(round(new_co2e, 4)))
            except Exception:
                pass

        record.is_edited = True
        record.save()

        AuditLog.objects.create(
            tenant=request.user.tenant,
            record=record,
            actor=request.user,
            action=AuditLog.ACTION_EDITED,
            before=before,
            after={k: str(getattr(record, k, "")) for k in updates},
            note=request.data.get("note", ""),
        )

        return Response(NormalizedRecordSerializer(record).data)

    def _review_action(self, request, pk, action_name, new_status):
        record = self.get_object()
        if record.is_locked:
            return Response({"error": "Record is locked."}, status=status.HTTP_403_FORBIDDEN)

        before = {"review_status": record.review_status}
        record.review_status = new_status
        record.reviewed_by = request.user
        record.reviewed_at = datetime.now(timezone.utc)
        record.review_note = request.data.get("note", "")
        record.save()

        AuditLog.objects.create(
            tenant=request.user.tenant,
            record=record,
            actor=request.user,
            action=action_name,
            before=before,
            after={"review_status": new_status},
            note=record.review_note,
        )
        return Response(NormalizedRecordSerializer(record).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._review_action(request, pk, AuditLog.ACTION_APPROVED, NormalizedRecord.STATUS_APPROVED)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._review_action(request, pk, AuditLog.ACTION_REJECTED, NormalizedRecord.STATUS_REJECTED)

    @action(detail=True, methods=["post"])
    def flag(self, request, pk=None):
        return self._review_action(request, pk, AuditLog.ACTION_FLAGGED, NormalizedRecord.STATUS_FLAGGED)

    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        record = self.get_object()
        if record.review_status != NormalizedRecord.STATUS_APPROVED:
            return Response(
                {"error": "Only approved records can be locked."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        record.is_locked = True
        record.locked_at = datetime.now(timezone.utc)
        record.locked_by = request.user
        record.save()
        AuditLog.objects.create(
            tenant=request.user.tenant,
            record=record,
            actor=request.user,
            action=AuditLog.ACTION_LOCKED,
            before={},
            after={"is_locked": True},
        )
        return Response(NormalizedRecordSerializer(record).data)

    @action(detail=True, methods=["get"])
    def audit_trail(self, request, pk=None):
        record = self.get_object()
        logs = AuditLog.objects.filter(record=record).order_by("timestamp")
        return Response(AuditLogSerializer(logs, many=True).data)

    @action(detail=False, methods=["post"])
    def bulk_approve(self, request):
        ids = request.data.get("ids", [])
        if not ids:
            return Response({"error": "No IDs provided."}, status=status.HTTP_400_BAD_REQUEST)

        records = NormalizedRecord.objects.filter(
            tenant=request.user.tenant, id__in=ids, is_locked=False
        )
        now = datetime.now(timezone.utc)
        updated = 0
        for record in records:
            before = {"review_status": record.review_status}
            record.review_status = NormalizedRecord.STATUS_APPROVED
            record.reviewed_by = request.user
            record.reviewed_at = now
            record.save()
            AuditLog.objects.create(
                tenant=request.user.tenant,
                record=record,
                actor=request.user,
                action=AuditLog.ACTION_APPROVED,
                before=before,
                after={"review_status": "approved"},
                note="Bulk approval",
            )
            updated += 1

        return Response({"approved": updated})
