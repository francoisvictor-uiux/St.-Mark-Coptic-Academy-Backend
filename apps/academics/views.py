from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.students.models import EducationLevel, Gender

from .models import Church, Diocese, Program


class RegistrationOptionsView(APIView):
    """Public reference data for the registration wizard (spec Part 4 §3 META)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @method_decorator(cache_page(60 * 5))
    def get(self, request):
        dioceses = [
            {
                "id": str(d.id),
                "name_ar": d.name_ar,
                "name_en": d.name_en,
                "country_code": d.country_code,
            }
            for d in Diocese.objects.filter(is_active=True)
        ]
        churches = [
            {
                "id": str(c.id),
                "diocese_id": str(c.diocese_id),
                "name_ar": c.name_ar,
                "name_en": c.name_en,
                "city": c.city,
            }
            for c in Church.objects.filter(is_active=True, is_user_submitted=False)
        ]
        programs = [
            {"id": str(p.id), "slug": p.slug, "name_ar": p.name_ar, "name_en": p.name_en}
            for p in Program.objects.filter(is_published=True)
        ]
        return Response(
            {
                "dioceses": dioceses,
                "churches": churches,
                "programs": programs,
                "genders": [{"value": v, "label_ar": l} for v, l in Gender.choices],
                "education_levels": [
                    {"value": v, "label_ar": l} for v, l in EducationLevel.choices
                ],
            }
        )
