"""Shared deterministic serialization and bounded package access."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_PACKAGE_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 10_000


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def check_package(archive: ZipFile) -> None:
    members = archive.infolist()
    if len(members) > MAX_MEMBERS:
        raise ValueError(f"Package exceeds {MAX_MEMBERS} members")
    seen: set[str] = set()
    total = 0
    for member in members:
        name = member.filename.replace("\\", "/")
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or ":" in name
            or "\x00" in name
            or name.casefold() in seen
        ):
            raise ValueError(f"Unsafe or duplicate package member: {name!r}")
        seen.add(name.casefold())
        if member.flag_bits & 1:
            raise ValueError(f"Encrypted package member is unsupported: {name!r}")
        if member.file_size > MAX_MEMBER_BYTES:
            raise ValueError(f"Package member exceeds size limit: {name!r}")
        total += member.file_size
        if total > MAX_PACKAGE_BYTES:
            raise ValueError("Package exceeds total uncompressed size limit")


def copy_member(archive: ZipFile, name: str, destination: Path) -> None:
    """Copy only to a caller-chosen path, never a path taken from the archive."""
    with archive.open(name) as source, destination.open("wb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)
