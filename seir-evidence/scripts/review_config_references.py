"""Export configuration references for manual review (Data & Evolution report §6.2).

Rows come from two sources:
  seir        every reference SEIR resolved or flagged UNRESOLVED -> measures precision
  broad_scan  lines in the same files where a component's simple name or bean
              name appears but SEIR reported nothing for that component
              -> candidate misses, measures recall

Fill `is_real_reference` with yes / no / unsure, then run
`python -m scripts.evaluate_config_review <csv>`.

Run from seir-evidence/:
    python -m scripts.review_config_references https://github.com/spring-projects/spring-petclinic --ref 7080682d3e2a
"""

import argparse
import csv
import re

from app.collectors.config_files import (
    ComponentResolver,
    Resolution,
    classify_config_path,
    default_bean_name,
    package_of,
    scan_revision,
    strip_comments,
)
from app.collectors.git_history import GitHistoryIndex
from app.collectors.git_log import read_history
from app.config import load_settings
from app.git_cli import list_tree, read_blobs
from app.inventory import list_components
from app.repo_fetcher import fetch_repository

FIELDS = ["source", "path", "line", "token", "category", "kind", "seir_resolution", "seir_component",
          "context", "is_real_reference", "reviewer_note"]
MIN_NAME_LENGTH = 4  # shorter simple names ("Pet", "Vet") are too noisy for a broad text search


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url")
    parser.add_argument("--ref")
    args = parser.parse_args()

    settings = load_settings()
    checkout = fetch_repository(args.url, settings, args.ref)
    components = list_components(checkout.path, checkout.repo_id, checkout.snapshot)
    component_ids = [c.component_id for c in components]
    index = GitHistoryIndex.build(read_history(checkout.path, checkout.snapshot),
                                  {c.file_path: c.component_id for c in components}, settings)
    resolver = ComponentResolver(component_ids, {package_of(c) for c in index.component_ids})
    scan = scan_revision(checkout.path, checkout.snapshot, resolver)

    rows = []
    reported = set()  # (path, line, component) SEIR already covers
    for ref in scan.references:
        if ref.resolution is Resolution.EXTERNAL:
            continue
        reported.add((ref.path, ref.line, ref.component_id))
        rows.append({"source": "seir", "path": ref.path, "line": ref.line, "token": ref.token,
                     "category": ref.category, "kind": ref.kind, "seir_resolution": ref.resolution,
                     "seir_component": ref.component_id or "", "context": ref.context})

    # Broad, independent text search for candidate misses. Several classes can
    # share a simple name (lang3.Functions / lang3.function.Functions), so a
    # name maps to *all* of them; a line is a candidate miss only if SEIR
    # reported none of them there.
    names: dict[str, set[str]] = {}
    for component_id in component_ids:
        simple = component_id.rsplit(".", 1)[-1]
        if len(simple) >= MIN_NAME_LENGTH:
            names.setdefault(simple, set()).add(component_id)
            names.setdefault(default_bean_name(simple), set()).add(component_id)
    pattern = re.compile(r"\b(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)) + r")\b")
    tree = {p: b for p, b in list_tree(checkout.path, checkout.snapshot).items() if classify_config_path(p)}
    contents = read_blobs(checkout.path, sorted(set(tree.values())))
    for path, blob in sorted(tree.items()):
        text = strip_comments(path, contents.get(blob, ""))
        for number, line in enumerate(text.splitlines(), start=1):
            for match in pattern.finditer(line):
                candidates = names[match.group(1)]
                if any((path, number, c) in reported for c in candidates):
                    continue
                reported.update((path, number, c) for c in candidates)
                rows.append({"source": "broad_scan", "path": path, "line": number, "token": match.group(1),
                             "category": classify_config_path(path), "kind": "", "seir_resolution": "",
                             "seir_component": " | ".join(sorted(candidates)), "context": line.strip()[:160]})

    out_dir = settings.data_dir / checkout.repo_id.replace("/", "__") / checkout.snapshot[:12]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "config_review.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({**row, "is_real_reference": "", "reviewer_note": ""} for row in rows)
    seir_rows = sum(r["source"] == "seir" for r in rows)
    print(f"{checkout.repo_id}@{checkout.snapshot[:12]}: {seir_rows} SEIR references, "
          f"{len(rows) - seir_rows} broad-scan candidates -> {out}")


if __name__ == "__main__":
    main()
