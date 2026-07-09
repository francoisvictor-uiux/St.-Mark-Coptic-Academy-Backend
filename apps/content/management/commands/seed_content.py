"""Seed starter content categories (idempotent)."""

from django.core.management.base import BaseCommand

from apps.content.models import Category

CATEGORIES = [
    ("theology", "لاهوت", "Theology"),
    ("church-history", "تاريخ كنسي", "Church History"),
    ("spirituality", "روحانيات", "Spirituality"),
    ("coptic-studies", "دراسات قبطية", "Coptic Studies"),
]


class Command(BaseCommand):
    help = "Seed starter content categories (idempotent)."

    def handle(self, *args, **options):
        created = 0
        for slug, name_ar, name_en in CATEGORIES:
            _, was_new = Category.objects.get_or_create(
                slug=slug, defaults={"name_ar": name_ar, "name_en": name_en}
            )
            created += was_new
        self.stdout.write(self.style.SUCCESS(f"Content seeded ({created} new categories)."))
