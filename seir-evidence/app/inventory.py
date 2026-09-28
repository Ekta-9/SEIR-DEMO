"""Lightweight component inventory: which top-level Java types exist at a snapshot.

This is an *interim* source of `Component` records so the evidence pipeline
works on real repositories before Member 4's AST parser is integrated. It
emits the same contract, so swapping in the real parser changes no callers.

Approach: Java requires a public top-level type to live in `<TypeName>.java`,
so the file stem is the type name; the package comes from the `package`
declaration (more reliable than guessing from the folder layout).
"""

import re
from pathlib import Path, PurePosixPath

from app.git_cli import run_git
from app.ids import NON_TYPE_JAVA_FILES, is_test_path, module_of
from app.schema import Component, ComponentKind

PACKAGE_PATTERN = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
KIND_KEYWORDS = {
    "@interface": ComponentKind.ANNOTATION,
    "interface": ComponentKind.INTERFACE,
    "enum": ComponentKind.ENUM,
    "record": ComponentKind.RECORD,
    "class": ComponentKind.CLASS,
}
# Strip comments first so "class" inside a Javadoc is not mistaken for a declaration.
COMMENT_PATTERN = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)


def detect_kind(source: str, type_name: str) -> ComponentKind:
    code = COMMENT_PATTERN.sub("", source)
    for keyword, kind in KIND_KEYWORDS.items():
        if re.search(rf"(?<![\w@]){re.escape(keyword)}\s+{re.escape(type_name)}\b", code):
            return kind
    return ComponentKind.CLASS


def count_loc(source: str) -> int:
    """Non-blank lines — a simple, reproducible size measure."""
    return sum(1 for line in source.splitlines() if line.strip())


def build_component(repo_id: str, snapshot: str, file_path: str, source: str) -> Component:
    type_name = PurePosixPath(file_path).stem
    match = PACKAGE_PATTERN.search(source)
    package = match.group(1) if match else ""
    return Component(
        component_id=f"{package}.{type_name}" if package else type_name,
        repo_id=repo_id,
        snapshot=snapshot,
        simple_name=type_name,
        package=package,
        kind=detect_kind(source, type_name),
        file_path=file_path,
        module=module_of(file_path),
        is_test=is_test_path(file_path),
        loc=count_loc(source),
    )


def list_components(repo_dir: Path, repo_id: str, snapshot: str) -> list[Component]:
    """All top-level Java types tracked by git at `snapshot` (must be checked out)."""
    tracked = run_git(repo_dir, "ls-files", "-z", "--", "*.java").split("\0")
    components: dict[str, Component] = {}
    for file_path in sorted(p for p in tracked if p):
        if PurePosixPath(file_path).name in NON_TYPE_JAVA_FILES:
            continue
        source = (repo_dir / file_path).read_text(encoding="utf-8", errors="replace")
        component = build_component(repo_id, snapshot, file_path, source)
        # Same FQCN in two modules (rare): keep the first, deterministic by path order.
        components.setdefault(component.component_id, component)
    return list(components.values())
