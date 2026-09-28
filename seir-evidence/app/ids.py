"""Identifier helpers shared by all collectors.

IDs are *deterministic*: the same inputs always produce the same ID. That is
what makes "run the analysis twice, get identical output" (report §5.4)
possible, and lets the explainer cite evidence IDs that stay stable.
"""

import hashlib
from pathlib import PurePosixPath

# Standard Maven/Gradle source roots, plus the older Apache 'src/java' layout.
DEFAULT_SOURCE_ROOTS: tuple[str, ...] = (
    "src/main/java/",
    "src/test/java/",
    "src/java/",
    "src/test/",
)
TEST_SOURCE_ROOTS: tuple[str, ...] = ("src/test/java/", "src/test/")

# Java files that do not declare a type (package docs / module descriptor).
NON_TYPE_JAVA_FILES = frozenset({"package-info.java", "module-info.java"})

EVIDENCE_ID_PREFIX = "ev_"
EVIDENCE_ID_HASH_LENGTH = 16


def to_posix(path: str) -> str:
    """Normalize Windows separators so paths compare equally on every OS."""
    return path.replace("\\", "/")


def path_to_component_id(path: str, source_roots: tuple[str, ...] = DEFAULT_SOURCE_ROOTS) -> str | None:
    """Best-effort fallback: derive a FQCN from a .java path.

    The authoritative mapping is Member 4's `Component.file_path`; use this
    only for files that no longer exist at the analyzed snapshot (e.g. old
    history). Returns None when no known source root is found.
    """
    posix = to_posix(path)
    if not posix.endswith(".java") or PurePosixPath(posix).name in NON_TYPE_JAVA_FILES:
        return None
    for root in source_roots:
        marker = f"/{root}" if not posix.startswith(root) else root
        index = posix.find(marker)
        if index == -1:
            continue
        relative = posix[index + len(marker):]
        return str(PurePosixPath(relative).with_suffix("")).replace("/", ".")
    return None


def module_of(path: str, source_roots: tuple[str, ...] = DEFAULT_SOURCE_ROOTS) -> str | None:
    """Return the build module prefix ('payment-service') or None for root."""
    posix = to_posix(path)
    for root in source_roots:
        index = posix.find(f"/{root}")
        if index > 0:
            return posix[:index]
    return None


def is_test_path(path: str) -> bool:
    posix = to_posix(path)
    return any(posix.startswith(root) or f"/{root}" in posix for root in TEST_SOURCE_ROOTS)


def make_evidence_id(*parts: object) -> str:
    """Hash the identifying fields of an evidence item into a short stable ID."""
    key = "|".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:EVIDENCE_ID_HASH_LENGTH]
    return f"{EVIDENCE_ID_PREFIX}{digest}"
