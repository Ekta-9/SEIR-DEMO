"""Configuration evidence (Data & Evolution report §6): references to
components that live in configuration files instead of Java code.

Pipeline:  classify file -> strip comments -> find names -> resolve -> evidence

Files are read straight from git objects at any revision, so the same code
serves the live analysis (current snapshot) and the dataset (thousands of
historical snapshots). Files are scanned line by line rather than parsed:
templated values such as `${database}` make YAML/XML parsers fail, and line
scanning keeps exact line numbers. The trade-off is that we report the raw
line as context instead of a structured key path.
"""

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath

from app.git_cli import list_tree, read_blobs
from app.schema import Availability, EvidenceItem, Provenance, Source
from app.schema.evidence import FileLocation

EXTRACTION_METHOD = "config_files@0.1.0"
MAX_CONTEXT_CHARS = 160
MAX_COUNT_PROVENANCE_FILES = 20


class ConfigCategory(StrEnum):
    RUNTIME = "RUNTIME"  # read by the running application (Spring config, ServiceLoader, logging...)
    TEST = "TEST"  # test resources
    BUILD = "BUILD"  # build and static-analysis tooling (pom, checkstyle, spotbugs...)


class ReferenceKind(StrEnum):
    CLASS_NAME = "CLASS_NAME"  # fully qualified class name in a value/attribute
    BEAN_REFERENCE = "BEAN_REFERENCE"  # Spring XML ref="beanName"
    SERVICE_LOADER = "SERVICE_LOADER"  # implementation listed in META-INF/services/<iface>
    SERVICE_INTERFACE = "SERVICE_INTERFACE"  # the <iface> named by that file
    AUTO_CONFIGURATION = "AUTO_CONFIGURATION"  # spring.factories / *.imports


class Resolution(StrEnum):
    RESOLVED = "RESOLVED"  # maps to a component of this repository
    UNRESOLVED = "UNRESOLVED"  # looks like this repository's code but no such class: possibly stale
    EXTERNAL = "EXTERNAL"  # a library/framework class or bean


# ---- 1. classify files ------------------------------------------------------------

# Allow-lists, not deny-lists: 20 years of history contain every convention
# imaginable (Maven 1 `xdocs/`, Ant `build.xml`, IDE `.settings/`, CI files), and
# a deny-list mislabelled them all as runtime. A file is scanned only if it is
# somewhere an application or a build tool is known to read configuration from.
CONFIG_SUFFIXES = frozenset({".properties", ".yml", ".yaml", ".xml", ".factories", ".imports", ".gradle", ".kts"})
SERVICES_DIR = "META-INF/services/"
IGNORED_PATHS = re.compile(
    r"(^|/)[\w.-]*docs?/|(^|/)src/site/|(^|/)changes\.xml$"  # documentation (docs/, xdocs/, apidocs/...)
    r"|(^|/)messages[^/]*\.properties$"  # i18n text bundles
    r"|(^|/)(\.[\w-]+|target|node_modules)/"  # hidden tool folders (.github, .settings, .tanzu...) and outputs
)
RUNTIME_PATHS = re.compile(
    r"(^|/)src/main/(resources|webapp|config)/"  # where the running application reads its configuration
    r"|(^|/)(application|bootstrap)[\w-]*\.(ya?ml|properties)$"  # Spring Boot config files, wherever placed
    r"|(^|/)META-INF/(services/|spring\.factories$|spring/[^/]+\.imports$)"
)
BUILD_PATHS = re.compile(
    r"(^|/)(pom|build|maven|project)[\w-]*\.xml$"  # Maven 2+, Ant, Maven 1
    r"|(^|/)(project|default|build|sonar-project)\.properties$"
    r"|\.gradle(\.kts)?$|(^|/)gradle/wrapper/"
    r"|checkstyle|pmd|spotbugs|findbugs|(^|/)sb-excludes"
    r"|(^|/)src/(conf|assembly|main/assembly|release-tools)/"
)
TEST_PATHS = re.compile(r"(^|/)src/test/")


def classify_config_path(path: str) -> ConfigCategory | None:
    """Which category a file belongs to, or None if it is not scanned."""
    is_service_file = f"/{SERVICES_DIR}" in f"/{path}"
    suffix = PurePosixPath(path).suffix
    if not is_service_file and suffix not in CONFIG_SUFFIXES:
        return None
    if suffix == ".kts" and not path.endswith(".gradle.kts"):
        return None
    if IGNORED_PATHS.search(path):
        return None
    if BUILD_PATHS.search(path):
        return ConfigCategory.BUILD
    if TEST_PATHS.search(path):
        return ConfigCategory.TEST
    if RUNTIME_PATHS.search(path):
        return ConfigCategory.RUNTIME
    return None


# ---- 2. strip comments (keeping line numbers) --------------------------------------------

XML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
C_STYLE_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)


def _blank_keep_newlines(match: re.Match) -> str:
    return "\n" * match.group(0).count("\n")


def strip_comments(path: str, text: str) -> str:
    suffix = PurePosixPath(path).suffix
    if suffix == ".xml":
        return XML_COMMENT.sub(_blank_keep_newlines, text)
    if suffix in {".gradle", ".kts"}:
        return C_STYLE_COMMENT.sub(_blank_keep_newlines, text)
    lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("#", "!")):
            lines.append("")
        elif suffix in {".yml", ".yaml"} and " #" in line:
            lines.append(line.split(" #", 1)[0])  # inline YAML comment
        else:
            lines.append(line)
    return "\n".join(lines)


# ---- 3. find names ------------------------------------------------------------------------

# package segments start lowercase (Java convention), the class segment uppercase;
# nested classes appear as Outer$Inner or Outer.Inner.
FQCN_PATTERN = re.compile(r"(?<![\w$.])((?:[a-z_][a-z0-9_]*\.)+[A-Z][\w$]*(?:\.[A-Z][\w$]*)*)(?![\w$])")
BEAN_REFERENCE_PATTERN = re.compile(r"(?<![\w-])(?:[\w:.-]*-ref|ref|bean|depends-on)\s*=\s*\"([A-Za-z_]\w*)\"")


@dataclass(frozen=True)
class RawToken:
    text: str
    line: int | None  # None for names taken from the file name itself
    kind: ReferenceKind
    context: str


def _content_kind(path: str) -> ReferenceKind:
    if f"/{SERVICES_DIR}" in f"/{path}":
        return ReferenceKind.SERVICE_LOADER
    if path.endswith((".factories", ".imports")):
        return ReferenceKind.AUTO_CONFIGURATION
    return ReferenceKind.CLASS_NAME


def scan_text(path: str, text: str) -> list[RawToken]:
    tokens: list[RawToken] = []
    if f"/{SERVICES_DIR}" in f"/{path}":
        interface = PurePosixPath(path).name
        if FQCN_PATTERN.fullmatch(interface):
            tokens.append(RawToken(interface, None, ReferenceKind.SERVICE_INTERFACE, path))

    kind = _content_kind(path)
    is_xml = path.endswith(".xml")
    for number, line in enumerate(strip_comments(path, text).splitlines(), start=1):
        context = line.strip()[:MAX_CONTEXT_CHARS]
        for match in FQCN_PATTERN.finditer(line):
            tokens.append(RawToken(match.group(1), number, kind, context))
        if is_xml:
            for match in BEAN_REFERENCE_PATTERN.finditer(line):
                tokens.append(RawToken(match.group(1), number, ReferenceKind.BEAN_REFERENCE, context))
    return tokens


# ---- 4. resolve names to components --------------------------------------------------------

def package_of(name: str) -> str:
    """'org.x.Foo$Bar' -> 'org.x' (leading lowercase segments)."""
    parts = []
    for part in name.split("."):
        if part[:1].isupper():
            break
        parts.append(part)
    return ".".join(parts)


def default_bean_name(simple_name: str) -> str:
    """Spring's default bean name (java.beans.Introspector.decapitalize)."""
    if len(simple_name) > 1 and simple_name[:2].isupper():
        return simple_name
    return simple_name[:1].lower() + simple_name[1:]


class ComponentResolver:
    """Maps names found in configuration to the components that exist at one snapshot.

    `known_packages` should include packages of classes that *used to* exist, so a
    reference to a deleted class is reported as UNRESOLVED (possibly stale)
    rather than silently treated as a library class.
    """

    def __init__(self, component_ids: Iterable[str], known_packages: Iterable[str] = ()):
        self.component_ids = set(component_ids)
        self.packages = {package_of(c) for c in self.component_ids} | set(known_packages)
        bean_counts = Counter(default_bean_name(c.rsplit(".", 1)[-1]) for c in self.component_ids)
        self.beans = {
            default_bean_name(c.rsplit(".", 1)[-1]): c
            for c in self.component_ids
            if bean_counts[default_bean_name(c.rsplit(".", 1)[-1])] == 1  # only unambiguous names
        }

    def resolve(self, token: RawToken) -> tuple[Resolution, str | None]:
        if token.kind is ReferenceKind.BEAN_REFERENCE:
            component = self.beans.get(token.text)
            return (Resolution.RESOLVED, component) if component else (Resolution.EXTERNAL, None)

        parts = token.text.split("$", 1)[0].split(".")
        while len(parts) > 1 and parts[-1][:1].isupper():  # Outer.Inner -> Outer
            candidate = ".".join(parts)
            if candidate in self.component_ids:
                return Resolution.RESOLVED, candidate
            parts.pop()
        package = package_of(token.text)
        internal = any(package == p or package.startswith(f"{p}.") for p in self.packages if p)
        return (Resolution.UNRESOLVED if internal else Resolution.EXTERNAL), None


# ---- 5. scan a snapshot --------------------------------------------------------------------

@dataclass(frozen=True)
class ConfigReference:
    path: str
    line: int | None
    category: ConfigCategory
    kind: ReferenceKind
    token: str
    resolution: Resolution
    component_id: str | None
    context: str


@dataclass
class ConfigScan:
    revision: str
    references: list[ConfigReference] = field(default_factory=list)
    files_scanned: Counter = field(default_factory=Counter)  # category -> file count

    def resolved(self) -> list[ConfigReference]:
        return [r for r in self.references if r.resolution is Resolution.RESOLVED]

    def stats(self) -> dict:
        return {
            "files_scanned": {str(k): v for k, v in self.files_scanned.items()},
            "references": {str(k): v for k, v in Counter(r.resolution for r in self.references).items()},
            "resolved_by_category": {str(k): v for k, v in Counter(r.category for r in self.resolved()).items()},
        }


TokenCache = dict[tuple[str, str], list[RawToken]]  # (path, blob sha) -> tokens


def scan_revision(repo_dir: Path, revision: str, resolver: ComponentResolver,
                  cache: TokenCache | None = None, timeout: int = 600) -> ConfigScan:
    """Scan every configuration file at `revision` (no checkout needed).

    `cache` lets many historical revisions share work: a file whose content
    (blob) did not change is never re-read or re-scanned.
    """
    cache = {} if cache is None else cache
    files = {}
    for path, blob in list_tree(repo_dir, revision, timeout=timeout).items():
        category = classify_config_path(path)
        if category:
            files[path] = (blob, category)

    missing = sorted({blob for path, (blob, _) in files.items() if (path, blob) not in cache})
    contents = read_blobs(repo_dir, missing, timeout=timeout)
    for path, (blob, _) in files.items():
        if (path, blob) not in cache:
            cache[(path, blob)] = scan_text(path, contents.get(blob, ""))

    scan = ConfigScan(revision=revision)
    seen = set()
    for path in sorted(files):
        blob, category = files[path]
        scan.files_scanned[category] += 1
        for token in cache[(path, blob)]:
            resolution, component = resolver.resolve(token)
            key = (path, token.line, token.text, token.kind)
            if key in seen:
                continue
            seen.add(key)
            scan.references.append(ConfigReference(
                path=path, line=token.line, category=category, kind=token.kind, token=token.text,
                resolution=resolution, component_id=component, context=token.context,
            ))
    return scan


# ---- 6. evidence ----------------------------------------------------------------------------

def build_config_evidence(scan: ConfigScan, component_ids: list[str], repo_id: str, snapshot: str,
                          as_of: datetime) -> list[EvidenceItem]:
    """One `config_reference` per resolved reference, plus a RUNTIME
    `config_reference_count` for every component (0 is a real, measured 0)."""
    by_component: dict[str, list[ConfigReference]] = {}
    for ref in scan.resolved():
        by_component.setdefault(ref.component_id, []).append(ref)

    total_files = sum(scan.files_scanned.values())
    scanned_note = ", ".join(f"{n} {c}" for c, n in sorted(scan.files_scanned.items())) or "none"
    common = dict(repo_id=repo_id, snapshot=snapshot, source=Source.CONFIG, as_of=as_of,
                  availability=Availability.AVAILABLE, extraction_method=EXTRACTION_METHOD)
    items: list[EvidenceItem] = []
    for component_id in component_ids:
        refs = by_component.get(component_id, [])
        seen_locations = set()
        for ref in refs:
            location = (ref.path, ref.line)
            if location in seen_locations:
                continue  # two names on one line pointing at the same component
            seen_locations.add(location)
            items.append(EvidenceItem(
                component_id=component_id, evidence_type="config_reference", value=str(ref.category),
                provenance=Provenance(files=[FileLocation(path=ref.path, line=ref.line)],
                                      note=f"{ref.kind}: {ref.context}"),
                **common,
            ))
        runtime = sorted({(r.path, r.line or 0) for r in refs if r.category is ConfigCategory.RUNTIME})
        items.append(EvidenceItem(
            component_id=component_id, evidence_type="config_reference_count", value=len(runtime),
            unit="references",
            provenance=Provenance(
                files=[FileLocation(path=p, line=line or None) for p, line in runtime[:MAX_COUNT_PROVENANCE_FILES]],
                note=f"{len(runtime)} RUNTIME configuration references; scanned {total_files} "
                     f"configuration files ({scanned_note})",
            ),
            **common,
        ))
    return items
