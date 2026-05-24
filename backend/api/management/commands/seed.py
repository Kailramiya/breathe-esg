"""
Creates demo tenant, users, plant lookups, and sample ingestion data.
Run: python manage.py seed
"""
from django.core.management.base import BaseCommand
from api.models import Tenant, User, PlantLookup


class Command(BaseCommand):
    help = "Seed database with demo tenant and users"

    def handle(self, *args, **options):
        tenant, created = Tenant.objects.get_or_create(
            slug="acme-manufacturing",
            defaults={"name": "ACME Manufacturing Ltd"},
        )
        self.stdout.write(f"Tenant: {tenant.name} ({'created' if created else 'exists'})")

        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@acme.com",
                "tenant": tenant,
                "role": User.ROLE_ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            admin.set_password("admin123")
            admin.save()
        self.stdout.write(f"Admin user: admin / admin123 ({'created' if created else 'exists'})")

        analyst, created = User.objects.get_or_create(
            username="analyst",
            defaults={
                "email": "analyst@acme.com",
                "tenant": tenant,
                "role": User.ROLE_ANALYST,
            },
        )
        if created:
            analyst.set_password("analyst123")
            analyst.save()
        self.stdout.write(f"Analyst user: analyst / analyst123 ({'created' if created else 'exists'})")

        plants = [
            ("1000", "London HQ",         "London",     "UK"),
            ("2000", "Manchester Plant",  "Manchester", "UK"),
            ("3000", "Birmingham Factory","Birmingham", "UK"),
        ]
        for code, name, city, country in plants:
            PlantLookup.objects.get_or_create(
                tenant=tenant, plant_code=code,
                defaults={"plant_name": name, "city": city, "country": country},
            )
        self.stdout.write("Plant lookups seeded.")
        self.stdout.write(self.style.SUCCESS("Seed complete. Upload sample_data/ files via the UI."))
