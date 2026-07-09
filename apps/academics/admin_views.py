"""Program management APIs (module: programs)."""

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import audit
from apps.common.errors import ApiError
from apps.content.models import MediaAsset
from apps.content.serializers import MediaSerializer
from apps.rbac.permissions import HasPermission

from .models import Program


class ProgramAdminSerializer(serializers.ModelSerializer):
    cover = MediaSerializer(read_only=True)
    cover_id = serializers.PrimaryKeyRelatedField(
        source="cover", queryset=MediaAsset.objects.all(),
        required=False, allow_null=True, default=None, write_only=True,
    )

    class Meta:
        model = Program
        fields = [
            "id", "slug", "name_ar", "name_en", "description_ar", "description_en",
            "duration_ar", "duration_en", "enrollment_status", "cover", "cover_id",
            "sort_order", "is_published", "created_at",
        ]
        read_only_fields = ["slug", "sort_order"]


class ProgramListCreateView(APIView):
    permission_classes = [HasPermission("programs.view")]

    def get(self, request):
        programs = Program.objects.select_related("cover").all()
        return Response({"programs": ProgramAdminSerializer(programs, many=True).data})

    def post(self, request):
        if not HasPermission("programs.create")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية", "Missing programs.create", status_code=403)
        serializer = ProgramAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from apps.content.serializers import unique_slug

        last = Program.objects.order_by("-sort_order").first()
        program = serializer.save(
            slug=unique_slug(Program, serializer.validated_data.get("name_en", ""),
                             serializer.validated_data["name_ar"]),
            sort_order=(last.sort_order + 1) if last else 1,
        )
        audit(request, "program.created", module="programs", target=program)
        return Response(ProgramAdminSerializer(program).data, status=status.HTTP_201_CREATED)


class ProgramDetailView(APIView):
    permission_classes = [HasPermission("programs.edit")]

    def _get(self, program_id):
        program = Program.objects.filter(id=program_id).first()
        if program is None:
            raise ApiError("not_found", "البرنامج غير موجود", "Program not found", status_code=404)
        return program

    def patch(self, request, program_id):
        program = self._get(program_id)
        if "is_published" in request.data and not HasPermission("programs.publish")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية النشر", "Missing programs.publish", status_code=403)
        serializer = ProgramAdminSerializer(program, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit(request, "program.updated", module="programs", target=program)
        return Response(serializer.data)

    def delete(self, request, program_id):
        if not HasPermission("programs.delete")().has_permission(request, self):
            raise ApiError("forbidden", "ليست لديك صلاحية", "Missing programs.delete", status_code=403)
        program = self._get(program_id)
        audit(request, "program.deleted", module="programs", target=program)
        program.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProgramReorderView(APIView):
    permission_classes = [HasPermission("programs.edit")]

    def put(self, request):
        ordered_ids = request.data.get("ordered_ids", [])
        if not isinstance(ordered_ids, list):
            raise ApiError("invalid_payload", "حمولة غير صالحة", "ordered_ids must be a list", status_code=400)
        for position, program_id in enumerate(ordered_ids, start=1):
            Program.objects.filter(id=program_id).update(sort_order=position)
        audit(request, "program.reordered", module="programs")
        programs = Program.objects.select_related("cover").all()
        return Response({"programs": ProgramAdminSerializer(programs, many=True).data})
