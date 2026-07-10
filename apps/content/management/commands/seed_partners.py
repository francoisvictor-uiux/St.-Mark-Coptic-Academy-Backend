"""Seed the real homepage partners with their logos (idempotent).

Ships the five partner logos alongside this command (``partner_logos/``),
re-encodes each through the same pipeline as an admin upload (EXIF-stripped,
capped), stores it as a MediaAsset, and publishes a Partner row for it.

Re-running is safe: partners are keyed by ``name_en`` and skipped if already
present, so a super admin can edit them in the dashboard without the seed
clobbering their changes.
"""

from pathlib import Path

from django.core.files.base import File
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.content.models import MediaAsset, Partner
from apps.content.services import process_image

LOGO_DIR = Path(__file__).resolve().parent / "partner_logos"

# (name_ar, name_en, logo filename, external url). Order → sort_order.
PARTNERS = [
    ("معهد الدراسات القبطية", "Institute of Coptic Studies", "partner-1.png", ""),
    ("الكلية الإكليريكية", "Clerical College", "partner-2.jpg", ""),
    ("جامعة طنطا", "Tanta University", "partner-3.png", ""),
    ("الكلية الإكليريكية بالإسكندرية", "Clerical College of Alexandria", "partner-4.png", ""),
    (
        "الكلية اللاهوتية القبطية الأرثوذكسية",
        "Coptic Orthodox Theological College",
        "partner-5.png",
        "",
    ),
]


class Command(BaseCommand):
    help = "Seed the real homepage partners with their logos (idempotent)."

    def _make_asset(self, filename: str, alt_ar: str, alt_en: str) -> MediaAsset:
        path = LOGO_DIR / filename
        with path.open("rb") as fh:
            content, width, height, mime, _ = process_image(File(fh, name=filename))
        return MediaAsset.objects.create(
            file=content,
            original_name=filename,
            mime=mime,
            size_bytes=content.size,
            width=width,
            height=height,
            alt_ar=alt_ar,
            alt_en=alt_en,
        )

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        for order, (name_ar, name_en, filename, url) in enumerate(PARTNERS):
            if Partner.objects.filter(name_en=name_en).exists():
                continue
            asset = self._make_asset(filename, name_ar, name_en)
            Partner.objects.create(
                name_ar=name_ar,
                name_en=name_en,
                logo=asset,
                url=url,
                sort_order=order,
                is_published=True,
            )
            created += 1
        self.stdout.write(
            self.style.SUCCESS(f"Partners seeded ({created} new, {len(PARTNERS)} total).")
        )
