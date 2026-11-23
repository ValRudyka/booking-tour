"""Tour photo files (ТЗ form 4.6.2.1, field 18): validation, storage on disk, cleanup.

Files live in settings.upload_dir/tours/<tour_id>/<random>.jpg|png and are served publicly at
/uploads/tours/... (only the tours subfolder is mounted, see main.py).
The database keeps only the relative path. The type is detected from the first bytes of the
file (its "magic number"), not from the name or the Content-Type header, which the client controls.
"""
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from app.config import settings
from app.services.errors import DomainError

CHUNK = 64 * 1024
SIGNATURES = {
    b"\xff\xd8\xff": "jpg",               # JPEG
    b"\x89PNG\r\n\x1a\n": "png",          # PNG
}


def detect_extension(head: bytes) -> str | None:
    for signature, ext in SIGNATURES.items():
        if head.startswith(signature):
            return ext
    return None


def absolute(relative_path: str) -> Path:
    return Path(settings.upload_dir) / relative_path


def save_tour_image(tour_id: int, source: BinaryIO, filename: str | None) -> str:
    """Copy an uploaded stream to disk in chunks, enforcing type and size. Returns the relative path."""
    head = source.read(CHUNK)
    ext = detect_extension(head)
    if ext is None:
        raise DomainError(f"Файл «{filename or 'без назви'}»: дозволені лише зображення JPG або PNG", 422)

    limit = settings.max_image_mb * 1024 * 1024
    relative = f"tours/{tour_id}/{uuid.uuid4().hex}.{ext}"
    target = absolute(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with target.open("wb") as out:
            chunk = head
            while chunk:
                size += len(chunk)
                if size > limit:  # stop reading as soon as the limit is passed
                    raise DomainError(f"Файл «{filename or 'без назви'}» більший за "
                                      f"{settings.max_image_mb} МБ", 413)
                out.write(chunk)
                chunk = source.read(CHUNK)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return relative


def copy_tour_image(relative_path: str, new_tour_id: int) -> str:
    """Physical copy for a copied tour, so deleting a photo of one tour never breaks the other."""
    ext = Path(relative_path).suffix
    relative = f"tours/{new_tour_id}/{uuid.uuid4().hex}{ext}"
    target = absolute(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(absolute(relative_path), target)
    return relative


def remove_files(relative_paths: list[str]) -> None:
    for path in relative_paths:
        absolute(path).unlink(missing_ok=True)
