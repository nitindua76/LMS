"""
Storage backend abstraction.

Selected by STORAGE_BACKEND env var:
  minio  (default) — MinIO / S3-compatible; requires MINIO_* env vars; runs in Docker Compose
  local            — local filesystem at STORAGE_LOCAL_PATH; signed URLs served by /api/content/download

Both backends expose identical signatures so callers never import a concrete class.
"""
import abc
import io
import time
from pathlib import Path
from typing import BinaryIO, Iterator


class StorageBackend(abc.ABC):
    @abc.abstractmethod
    def ensure_bucket(self) -> None: ...

    @abc.abstractmethod
    def upload_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...

    @abc.abstractmethod
    def upload_fileobj(self, key: str, fileobj: BinaryIO, content_type: str = "application/octet-stream") -> None: ...

    @abc.abstractmethod
    def download_bytes(self, key: str) -> bytes: ...

    @abc.abstractmethod
    def signed_url(self, key: str, expires: int = 3600) -> str: ...

    @abc.abstractmethod
    def list_keys(self, prefix: str) -> list[str]: ...


class MinIOBackend(StorageBackend):
    """S3-compatible backend (MinIO for on-prem, AWS S3 for cloud — same boto3 call)."""

    def _client(self):
        import boto3
        from botocore.config import Config
        from app.config import settings
        scheme = "https" if settings.MINIO_SECURE else "http"
        return boto3.client(
            "s3",
            endpoint_url=f"{scheme}://{settings.MINIO_ENDPOINT}",
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )

    def _bucket(self) -> str:
        from app.config import settings
        return settings.MINIO_BUCKET

    def ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError
        c = self._client()
        try:
            c.head_bucket(Bucket=self._bucket())
        except ClientError:
            c.create_bucket(Bucket=self._bucket())

    def upload_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._client().upload_fileobj(
            io.BytesIO(data), self._bucket(), key,
            ExtraArgs={"ContentType": content_type},
        )

    def upload_fileobj(self, key: str, fileobj: BinaryIO, content_type: str = "application/octet-stream") -> None:
        self._client().upload_fileobj(
            fileobj, self._bucket(), key,
            ExtraArgs={"ContentType": content_type},
        )

    def download_bytes(self, key: str) -> bytes:
        buf = io.BytesIO()
        self._client().download_fileobj(self._bucket(), key, buf)
        return buf.getvalue()

    def signed_url(self, key: str, expires: int = 3600) -> str:
        return self._client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket(), "Key": key},
            ExpiresIn=expires,
        )

    def list_keys(self, prefix: str) -> list[str]:
        resp = self._client().list_objects_v2(Bucket=self._bucket(), Prefix=prefix)
        return [o["Key"] for o in resp.get("Contents", [])]


class LocalBackend(StorageBackend):
    """
    Filesystem backend for dev environments without MinIO.

    Signed URLs are short-lived JWTs served by GET /api/content/download?token=…
    so the raw filesystem path is never revealed to the client.
    """

    @property
    def _root(self) -> Path:
        from app.config import settings
        return Path(settings.STORAGE_LOCAL_PATH)

    def ensure_bucket(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def upload_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        dest = self._root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def upload_fileobj(self, key: str, fileobj: BinaryIO, content_type: str = "application/octet-stream") -> None:
        import shutil
        dest = self._root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as out:
            shutil.copyfileobj(fileobj, out)

    def download_bytes(self, key: str) -> bytes:
        p = self._root / key
        if not p.exists():
            raise FileNotFoundError(f"Storage key not found: {key}")
        return p.read_bytes()

    def file_size(self, key: str) -> int:
        p = self._root / key
        if not p.exists():
            raise FileNotFoundError(f"Storage key not found: {key}")
        return p.stat().st_size

    DEFAULT_STREAM_CHUNK_SIZE = 1024 * 1024  # 1 MiB

    def iter_range(self, key: str, start: int, end: int, chunk_size: int = DEFAULT_STREAM_CHUNK_SIZE) -> Iterator[bytes]:
        """
        Stream the inclusive byte range [start, end] in fixed-size chunks — the
        server never holds more than one chunk in memory, regardless of how
        large the requested range is (including a "no Range header" request
        for the whole file, which is start=0, end=file_size-1). This is what
        makes both video seeking (206 Partial Content) and plain full-file
        playback avoid loading a multi-hundred-MB video into RAM per request.
        """
        p = self._root / key
        if not p.exists():
            raise FileNotFoundError(f"Storage key not found: {key}")
        remaining = end - start + 1
        with p.open("rb") as f:
            f.seek(start)
            while remaining > 0:
                chunk = f.read(min(chunk_size, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    def signed_url(self, key: str, expires: int = 3600) -> str:
        """Return a short-lived signed download URL handled by /api/content/download."""
        import jwt
        from app.config import settings
        exp = int(time.time()) + expires
        token = jwt.encode({"key": key, "exp": exp}, settings.JWT_SECRET, algorithm="HS256")
        return f"http://localhost:8000/api/content/download?token={token}"

    def list_keys(self, prefix: str) -> list[str]:
        root = self._root
        if not root.exists():
            return []
        return [
            str(p.relative_to(root)).replace("\\", "/")
            for p in root.rglob("*")
            if p.is_file() and str(p.relative_to(root)).replace("\\", "/").startswith(prefix)
        ]


def get_backend() -> StorageBackend:
    """Return the backend selected by STORAGE_BACKEND env var (default: minio)."""
    from app.config import settings
    name = getattr(settings, "STORAGE_BACKEND", "minio").lower()
    if name == "local":
        return LocalBackend()
    return MinIOBackend()


# ── Module-level convenience wrappers (callers import these, not the classes) ──

def ensure_bucket() -> None:
    get_backend().ensure_bucket()

def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    get_backend().upload_bytes(key, data, content_type)

def upload_fileobj(key: str, fileobj: BinaryIO, content_type: str = "application/octet-stream") -> None:
    get_backend().upload_fileobj(key, fileobj, content_type)

def download_bytes(key: str) -> bytes:
    return get_backend().download_bytes(key)

def signed_url(key: str, expires: int = 3600) -> str:
    return get_backend().signed_url(key, expires)

def list_keys(prefix: str) -> list[str]:
    return get_backend().list_keys(prefix)

def content_type_for(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "html": "text/html",
        "htm":  "text/html",
        "js":   "application/javascript",
        "css":  "text/css",
        "json": "application/json",
        "xml":  "application/xml",
        "swf":  "application/x-shockwave-flash",
        "gif":  "image/gif",
        "png":  "image/png",
        "jpg":  "image/jpeg",
        "jpeg": "image/jpeg",
        "svg":  "image/svg+xml",
        "pdf":  "application/pdf",
        "mp4":  "video/mp4",
        "webm": "video/webm",
        "woff": "font/woff",
        "woff2": "font/woff2",
        "ttf":  "font/ttf",
    }.get(ext, "application/octet-stream")
