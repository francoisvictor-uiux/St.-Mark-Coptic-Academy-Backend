"""Bilingual transactional email sending (spec Part 4 §4).

Templates live in templates/emails/<name>.html + .txt — Arabic-primary (RTL)
with English secondary, inline styles only. Synchronous for now; swap to a
queue (Celery) before launch per spec §4.
"""

import logging

from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

SUBJECTS = {
    "verify_email": "رمز تفعيل حسابك — أكاديمية القديس مارمرقس | Your verification code",
    "welcome": "أهلاً بك في أكاديمية القديس مارمرقس | Welcome to St. Mark Coptic Academy",
    "reset_code": "رمز استعادة كلمة المرور — أكاديمية القديس مارمرقس | Password reset code",
    "password_changed": "تم تغيير كلمة المرور — أكاديمية القديس مارمرقس | Your password was changed",
    "admin_invitation": "دعوة للانضمام لفريق الأكاديمية — أكاديمية القديس مارمرقس | Team invitation",
    "account_suspended": "بخصوص حسابك — أكاديمية القديس مارمرقس | About your account",
    "registration_received": "استلمنا طلب تسجيلك — أكاديمية القديس مارمرقس | We received your registration",
    "activation_link": "تم قبول حسابك — فعّل حسابك | Your account is approved — activate it",
}


def _log_send(to_email: str, template: str, subject: str, error: str = ""):
    """Record the attempt in email_log — a logging failure must never block a send."""
    from .models import EmailLog, EmailStatus

    try:
        EmailLog.objects.create(
            to_email=to_email,
            template=template,
            subject=subject[:255],
            status=EmailStatus.FAILED if error else EmailStatus.SENT,
            error=error,
        )
    except Exception:
        logger.exception("email_log write failed: template=%s to=%s", template, to_email)


def send_templated(to_email: str, template: str, context: dict, subject: str | None = None) -> bool:
    """Render and send one branded email. Returns False on failure (logged).

    `subject` overrides the catalog — newsletters set it per issue.
    Every attempt lands in the email_log table (recipient, template,
    subject, time, sent/failed) — bodies are never stored.
    """
    final_subject = subject or SUBJECTS.get(
        template, "أكاديمية القديس مارمرقس | St. Mark Coptic Academy"
    )
    try:
        text_body = render_to_string(f"emails/{template}.txt", context)
        html_body = render_to_string(f"emails/{template}.html", context)
        # Bounded connection so a slow or misconfigured mail server can never
        # hang (or crash) the request that triggered the email. Email is
        # best-effort — a failure here must never block registration/login.
        connection = get_connection(timeout=10)
        message = EmailMultiAlternatives(
            subject=final_subject, body=text_body, to=[to_email], connection=connection
        )
        message.attach_alternative(html_body, "text/html")
        message.send()
        _log_send(to_email, template, final_subject)
        return True
    except Exception as exc:
        import traceback
        print(f"\n[EMAIL ERROR] template={template} to={to_email}")
        print(traceback.format_exc())
        logger.exception("email send failed: template=%s to=%s", template, to_email)
        _log_send(to_email, template, final_subject, error=f"{type(exc).__name__}: {exc}")
        return False
