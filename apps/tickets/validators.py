from pathlib import Path

from django.core.exceptions import ValidationError

ALLOWED_EXTENSIONS = ("png", "jpg", "jpeg", "pdf", "docx")
MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_FILES_PER_UPLOAD = 5


def file_extension(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


def validate_attachment(uploaded) -> None:
    if file_extension(uploaded.name) not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValidationError(
            f"Tệp “{uploaded.name}” sai định dạng. Chỉ cho phép: {allowed}.",
            code="invalid_extension",
        )
    if uploaded.size > MAX_FILE_SIZE:
        raise ValidationError(f"Tệp “{uploaded.name}” vượt quá 5 MB.", code="file_too_large")
