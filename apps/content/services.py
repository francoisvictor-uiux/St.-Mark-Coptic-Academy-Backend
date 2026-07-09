"""Content processing: image re-encode + EXIF strip, HTML sanitization.

Spec Part 4 §5.6: uploads validated by content (not extension), re-encoded,
EXIF stripped. Editor HTML is sanitized server-side regardless of the client.
"""

import io
import secrets

import nh3
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

from apps.common.errors import ApiError

MAX_DIMENSION = 2400
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB before re-encode

ALLOWED_TAGS = {
    "p", "h2", "h3", "strong", "em", "u", "s", "a", "ul", "ol", "li",
    "blockquote", "img", "br", "hr", "figure", "figcaption",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
}


def sanitize_html(html: str) -> str:
    """Whitelist-sanitize editor output. Never trust the client."""
    if not html:
        return ""
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        link_rel="noopener noreferrer",
        url_schemes={"http", "https", "mailto"},
    )


def _invalid_image_error():
    return ApiError(
        "invalid_image",
        "الملف ليس صورة صالحة — المسموح JPG وPNG وWebP",
        "The file is not a valid image — JPG, PNG and WebP are allowed",
        status_code=400,
    )


def process_image(uploaded_file, max_dimension: int = MAX_DIMENSION):
    """Validate by magic bytes, re-encode (strips EXIF), cap dimensions.

    Returns (django_file, width, height, mime, ext).
    """
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        raise ApiError(
            "file_too_large",
            "حجم الصورة يتجاوز ١٠ ميجابايت",
            "Image exceeds the 10MB limit",
            status_code=400,
        )
    try:
        image = Image.open(uploaded_file)
        image.load()
    except (UnidentifiedImageError, OSError):
        raise _invalid_image_error()

    if image.format not in ("JPEG", "PNG", "WEBP"):
        raise _invalid_image_error()

    if max(image.size) > max_dimension:
        image.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

    # Re-encode drops EXIF/GPS. Keep alpha where the source had it.
    has_alpha = image.mode in ("RGBA", "LA", "P") and (
        image.mode != "P" or "transparency" in image.info
    )
    buffer = io.BytesIO()
    if has_alpha:
        image.convert("RGBA").save(buffer, format="WEBP", quality=88)
        mime, ext = "image/webp", "webp"
    else:
        image.convert("RGB").save(buffer, format="JPEG", quality=88, optimize=True)
        mime, ext = "image/jpeg", "jpg"

    name = f"{secrets.token_hex(8)}.{ext}"
    return ContentFile(buffer.getvalue(), name=name), image.width, image.height, mime, ext
