"""Stable-code, bilingual API error envelope (spec Part 4 §3).

Every error response body is:
    {"error": {"code": "...", "message_ar": "...", "message_en": "...", "fields": {...}}}
"""

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler as drf_exception_handler


class ApiError(APIException):
    """Raise anywhere in a view with a stable code + bilingual messages."""

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, code, message_ar, message_en, *, status_code=None, fields=None, headers=None):
        self.code = code
        self.message_ar = message_ar
        self.message_en = message_en
        self.fields = fields or {}
        self.headers = headers or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(detail=message_en)


def _envelope(code, message_ar, message_en, fields=None):
    return {
        "error": {
            "code": code,
            "message_ar": message_ar,
            "message_en": message_en,
            "fields": fields or {},
        }
    }


_GENERIC = {
    401: ("unauthorized", "يجب تسجيل الدخول أولاً", "Authentication required"),
    403: ("forbidden", "ليست لديك صلاحية لهذا الإجراء", "You do not have permission to perform this action"),
    404: ("not_found", "العنصر غير موجود", "Not found"),
    405: ("method_not_allowed", "طريقة الطلب غير مسموح بها", "Method not allowed"),
    429: ("rate_limited", "محاولات كثيرة، حاول لاحقاً", "Too many requests, try again later"),
}


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    # Audit denied attempts on admin endpoints (spec Part 4 §5.8) — an
    # authenticated caller probing beyond their permissions is a signal.
    if response.status_code == 403:
        request = context.get("request")
        if (
            request is not None
            and request.path.startswith("/api/v1/admin/")
            and getattr(request, "user", None) is not None
            and request.user.is_authenticated
        ):
            from apps.audit.services import audit  # local import — avoid cycles

            audit(request, "auth.permission_denied", module="audit",
                  target_label=request.path)

    if isinstance(exc, ApiError):
        response.data = _envelope(exc.code, exc.message_ar, exc.message_en, exc.fields)
        for key, value in exc.headers.items():
            response[key] = value
        return response

    if isinstance(exc, ValidationError):
        fields = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": exc.detail}
        response.data = _envelope(
            "validation_error",
            "بعض الحقول غير صالحة",
            "Some fields are invalid",
            fields,
        )
        return response

    code, message_ar, message_en = _GENERIC.get(
        response.status_code, ("error", "حدث خطأ ما", "Something went wrong")
    )
    response.data = _envelope(code, message_ar, message_en)
    return response
