"""Secret paths like ``prod/billing/DB_PASSWORD`` and the folder prefixes that contain them.

A folder is not stored. It exists while some secret path starts with it. The root folder is ``""``.
"""

import re

SEPARATOR = "/"
ROOT = ""

_FOLDER_PART = re.compile(r"\A[A-Za-z0-9_.-]+\Z")
_LEAF = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")


def normalize_path(path: str) -> str:
    """Stripped secret path. Raises ValueError when a part is empty or not allowed."""
    cleaned = path.strip()
    if not cleaned:
        raise ValueError("name is empty")
    *folders, leaf = cleaned.split(SEPARATOR)
    for part in folders:
        _check_folder_part(part, cleaned)
    if not _LEAF.fullmatch(leaf):
        raise ValueError(f'invalid name "{leaf}" in "{cleaned}": use letters, digits, and _, not starting with a digit')
    return cleaned


def normalize_prefix(prefix: str) -> str:
    """Folder prefix without outer slashes. ``""`` and ``"/"`` are the root. Raises ValueError for a bad part."""
    cleaned = prefix.strip().strip(SEPARATOR)
    if not cleaned:
        return ROOT
    for part in cleaned.split(SEPARATOR):
        _check_folder_part(part, cleaned)
    return cleaned


def join(folder: str, name: str) -> str:
    """Path of name inside folder."""
    return f"{folder}{SEPARATOR}{name}" if folder else name


def short_name(path: str) -> str:
    """Last part of the path: the name an app sees."""
    return path.rsplit(SEPARATOR, 1)[-1]


def folder_of(path: str) -> str:
    """Folder that holds the path, or the root."""
    head, _, _ = path.rpartition(SEPARATOR)
    return head


def covers(prefix: str, path: str) -> bool:
    """Whether the path is inside the folder prefix, at any depth."""
    return prefix == ROOT or path.startswith(prefix + SEPARATOR)


def folders(paths: list[str]) -> list[str]:
    """Every folder that holds at least one of the paths, sorted. The root is not included."""
    found: set[str] = set()
    for path in paths:
        folder = folder_of(path)
        while folder:
            found.add(folder)
            folder = folder_of(folder)
    return sorted(found)


def prefix_label(prefix: str) -> str:
    """``prod/billing/*`` for a prefix, ``/*`` for the root."""
    return f"{prefix}{SEPARATOR}*" if prefix else f"{SEPARATOR}*"


def _check_folder_part(part: str, whole: str) -> None:
    if not part:
        raise ValueError(f'empty folder in "{whole}"')
    if part in (".", "..") or not _FOLDER_PART.fullmatch(part):
        raise ValueError(f'invalid folder "{part}" in "{whole}": use letters, digits, and _ . -')
