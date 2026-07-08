"""
Server-side validation for admin-uploaded content files (video/PDF).

Enforces, independent of what the client claims:
  - a hard size cap, checked while streaming (never trust Content-Length alone)
  - the file's actual bytes match the declared content type (magic-byte sniff),
    so a renamed .exe can't masquerade as a PDF
  - the storage key is derived from a sanitized filename (no path traversal)
"""
import re
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Optional

from app.models.course import ContentType

CHUNK_SIZE = 1024 * 1024  # 1 MiB
_SPOOL_THRESHOLD = 8 * 1024 * 1024  # spill to disk past 8MiB so large uploads don't sit fully in RAM


class UploadValidationError(Exception):
    """Raised for any client-caused upload rejection (too large, wrong type, bad name)."""


def sanitize_filename(filename: str) -> str:
    """Strip any path components and unsafe characters — never trust the client's path."""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    name = name.lstrip(".")  # no leading dot (hidden files / relative-path tricks)
    if not name:
        raise UploadValidationError("Filename is empty or invalid after sanitization")
    return name[:255]


def _sniff_video(head: bytes) -> bool:
    # MP4/MOV: 'ftyp' box at byte offset 4. WebM/MKV: EBML header. Ogg: 'OggS'.
    return head[4:8] == b"ftyp" or head[:4] == b"\x1a\x45\xdf\xa3" or head[:4] == b"OggS"


def _sniff_pdf(head: bytes) -> bool:
    return head[:5] == b"%PDF-"


_SNIFFERS = {
    ContentType.video: (_sniff_video, "a recognizable video container (mp4/webm/ogg)"),
    ContentType.pdf: (_sniff_pdf, "a valid PDF (must start with %PDF-)"),
}

_MAX_MB_SETTING_BY_TYPE = {
    ContentType.video: "MAX_VIDEO_UPLOAD_MB",
    ContentType.pdf: "MAX_PDF_UPLOAD_MB",
}


def stream_validate_and_spool(fileobj: BinaryIO, declared_type: ContentType) -> SpooledTemporaryFile:
    """
    Read `fileobj` in chunks into a spooled buffer (spills to disk past 8MiB, so a
    large upload never sits fully in process memory), enforcing the size cap for
    `declared_type` as we go and sniffing the first chunk's magic bytes against
    what the content type claims to be. Raises UploadValidationError on any
    violation. Returns the buffer rewound to position 0, ready to hand to the
    storage backend.
    """
    from app.config import settings

    if declared_type not in _SNIFFERS:
        raise UploadValidationError(f"Direct upload is not supported for content type '{declared_type.value}'")

    max_bytes = getattr(settings, _MAX_MB_SETTING_BY_TYPE[declared_type]) * 1024 * 1024
    sniffer, expected_desc = _SNIFFERS[declared_type]

    buf = SpooledTemporaryFile(max_size=_SPOOL_THRESHOLD)
    total = 0
    first_chunk: Optional[bytes] = None

    while True:
        chunk = fileobj.read(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadValidationError(
                f"File exceeds the {max_bytes // (1024 * 1024)}MB limit for {declared_type.value} uploads"
            )
        if first_chunk is None:
            first_chunk = chunk
        buf.write(chunk)

    if total == 0:
        raise UploadValidationError("Uploaded file is empty")

    if not sniffer(first_chunk or b""):
        raise UploadValidationError(
            f"File content does not look like {expected_desc} — check the file matches the selected content type"
        )

    buf.seek(0)
    return buf
