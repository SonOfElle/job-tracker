"""Filesystem helpers for CV storage."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import BinaryIO

DATA_DIR = Path(os.getenv("DATA_DIR", "data")).resolve()
CV_SUBDIR = "cvs"
MAX_CV_BYTES = 10 * 1024 * 1024  # 10 MB

# Allow letters, digits, dot, dash, underscore. Everything else becomes _.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str, fallback: str = "cv.pdf") -> str:
    """Return a filename that is safe to use on disk.

    Takes only the final path component (defeats path traversal via slashes),
    replaces unsafe characters, strips leading/trailing dots and underscores,
    and caps length. Empty results fall back to `fallback`.
    """
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _UNSAFE.sub("_", base).strip("._") or fallback
    return cleaned[:255]


def cv_dir(application_id: int) -> Path:
    return DATA_DIR / CV_SUBDIR / str(application_id)


def cv_relative_path(application_id: int, filename: str) -> str:
    """The value stored in Application.cv_path — relative to DATA_DIR."""
    return f"{CV_SUBDIR}/{application_id}/{filename}"


def cv_full_path(cv_path: str) -> Path:
    """Resolve a stored cv_path back to an absolute filesystem path."""
    return DATA_DIR / cv_path


def save_cv(application_id: int, filename: str, source: BinaryIO) -> tuple[str, int]:
    """Write an uploaded file to disk under the application's CV directory.

    Returns (relative_path, bytes_written). Raises ValueError if the file
    exceeds MAX_CV_BYTES.
    """
    directory = cv_dir(application_id)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename

    written = 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = source.read(64 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_CV_BYTES:
                    raise ValueError(
                        f"CV exceeds {MAX_CV_BYTES // (1024 * 1024)} MB limit"
                    )
                out.write(chunk)
    except Exception:
        # Clean up the partial file on any failure.
        target.unlink(missing_ok=True)
        raise

    return cv_relative_path(application_id, filename), written


def delete_cv_file(cv_path: str) -> None:
    """Remove the file at the given stored path. Silent if already gone."""
    full = cv_full_path(cv_path)
    full.unlink(missing_ok=True)
    # Remove the per-application directory if it's now empty.
    try:
        full.parent.rmdir()
    except OSError:
        pass  # Non-empty or already gone.