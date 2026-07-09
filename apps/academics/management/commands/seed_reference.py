"""Seed dioceses, churches, and programs (idempotent). Spec M3 reference data."""

from django.core.management.base import BaseCommand

from apps.academics.models import Church, Diocese, Program

DIOCESES = [
    # (name_ar, name_en, country_code, [(church_ar, church_en, city), ...])
    (
        "إيبارشية القاهرة",
        "Diocese of Cairo",
        "EG",
        [
            ("كنيسة القديس مارمرقس - العباسية", "St. Mark Church - Abbassia", "القاهرة"),
            ("كنيسة العذراء مريم - الزيتون", "St. Mary Church - Zeitoun", "القاهرة"),
        ],
    ),
    (
        "إيبارشية الإسكندرية",
        "Diocese of Alexandria",
        "EG",
        [
            ("كنيسة القديس مارمرقس - محطة الرمل", "St. Mark Church - Raml Station", "الإسكندرية"),
        ],
    ),
    (
        "إيبارشية أمريكا الشمالية",
        "Diocese of North America",
        "US",
        [
            ("كنيسة القديس مارمرقس - جيرسي سيتي", "St. Mark Church - Jersey City", "Jersey City"),
        ],
    ),
]

PROGRAMS = [
    ("taree2-elmalakoot", "طريق الملكوت", "Path of the Kingdom"),
    ("coptic-language", "اللغة القبطية", "Coptic Language"),
    ("church-history", "تاريخ الكنيسة", "Church History"),
]


class Command(BaseCommand):
    help = "Seed reference data: dioceses, churches, programs (idempotent)."

    def handle(self, *args, **options):
        created = 0
        for name_ar, name_en, country, churches in DIOCESES:
            diocese, was_created = Diocese.objects.get_or_create(
                name_en=name_en, defaults={"name_ar": name_ar, "country_code": country}
            )
            created += was_created
            for church_ar, church_en, city in churches:
                _, was_created = Church.objects.get_or_create(
                    diocese=diocese,
                    name_en=church_en,
                    defaults={"name_ar": church_ar, "city": city},
                )
                created += was_created
        for slug, name_ar, name_en in PROGRAMS:
            _, was_created = Program.objects.get_or_create(
                slug=slug,
                defaults={"name_ar": name_ar, "name_en": name_en, "is_published": True},
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(f"Seeded reference data ({created} new rows)."))
