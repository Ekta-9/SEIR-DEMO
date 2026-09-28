"""Phase 2 verification (Data & Evolution report §5.3–5.5).

1. Accuracy: for a random sample of components, recompute commit count,
   last-change date, contributors and churn with an *independent* method —
   `git log --follow` on the single file - and compare with SEIR's output.
2. Repeatability: run the pipeline twice and check the evidence is identical.
3. Writes a CSV sample for manual hand-checking.

Run from seir-evidence/ (after scripts.run_analysis has cloned the repo):
    python -m scripts.verify_git_history https://github.com/spring-projects/spring-petclinic --sample 15
"""

import argparse
import csv
import hashlib
import json
import random
from datetime import datetime, timezone

from app.config import load_settings
from app.git_cli import run_git
from app.pipeline import analyze_repository
from app.repo_fetcher import fetch_repository

COMPARED_FEATURES = ("historical_commit_count", "unique_contributors", "lines_added", "lines_deleted")
DEFAULT_SAMPLE_SIZE = 15
DEFAULT_SEED = 42


def oracle(repo_dir, snapshot: str, file_path: str, as_of: datetime) -> dict:
    """Independent recomputation using git's own per-file rename following."""
    raw = run_git(repo_dir, "log", snapshot, "--follow", "--full-history", "--no-merges", "-M", "--numstat",
                  "--format=@%H\t%ct\t%aE", "--", file_path)
    shas, authors, times, added, deleted = set(), set(), [], 0, 0
    current_included = False
    for line in raw.splitlines():
        if line.startswith("@"):
            sha, ct, email = line[1:].split("\t")
            timestamp = datetime.fromtimestamp(int(ct), tz=timezone.utc)
            current_included = timestamp < as_of
            if current_included:
                shas.add(sha)
                authors.add(email.strip().lower())
                times.append(timestamp)
        elif line.strip() and current_included:
            a, d, *_ = line.split("\t")
            added += 0 if a == "-" else int(a)
            deleted += 0 if d == "-" else int(d)
    days = int((as_of - max(times)).total_seconds() // 86_400) if times else None
    return {
        "historical_commit_count": len(shas),
        "unique_contributors": len(authors),
        "lines_added": added,
        "lines_deleted": deleted,
        "days_since_last_change": days,
    }


def oracle_followed_copy(repo_dir, snapshot: str, file_path: str) -> bool:
    """`git log --follow` can jump into a *different* file it thinks was copied
    (status Cxx). When that happens the oracle is wrong, not SEIR."""
    raw = run_git(repo_dir, "log", snapshot, "--follow", "--full-history", "--no-merges", "-M", "--name-status",
                  "--format=", "--", file_path)
    return any(line.startswith("C") for line in raw.splitlines())


def lower_bound_violations(checkout, result, values, path_of) -> list[tuple[str, int, int]]:
    """Every commit touching a file's *current* path must be counted (no guessing
    involved), so SEIR's count can never be lower than a plain `git log -- path`."""
    violations = []
    for component_id, path in path_of.items():
        plain = len(run_git(checkout.path, "log", checkout.snapshot, "--full-history", "--no-merges",
                            f"--until={int(result.as_of.timestamp())}", "--format=%H", "--", path).split())
        ours = values[component_id]["historical_commit_count"]
        if ours is not None and ours < plain:
            violations.append((component_id, ours, plain))
    return violations


def fingerprint(result) -> str:
    payload = json.dumps([e.model_dump(mode="json") for e in result.evidence], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url")
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    settings = load_settings()
    checkout = fetch_repository(args.url, settings)
    first = analyze_repository(checkout, settings)
    second = analyze_repository(checkout, settings)

    values = {}
    for item in first.evidence:
        values.setdefault(item.component_id, {})[item.evidence_type] = item.value
    path_of = {c.component_id: c.file_path for c in first.components}

    sample = random.Random(args.seed).sample(sorted(values), min(args.sample, len(values)))
    rows, matches, checks = [], 0, 0
    clean_matches, clean_checks = 0, 0
    print(f"{'component':<60}{'feature':<26}{'seir':>8}{'oracle':>8}")
    for component_id in sample:
        path = path_of[component_id]
        expected = oracle(checkout.path, checkout.snapshot, path, first.as_of)
        copy_followed = oracle_followed_copy(checkout.path, checkout.snapshot, path)
        row = {"component_id": component_id, "file_path": path, "oracle_followed_copy": copy_followed}
        for feature in (*COMPARED_FEATURES, "days_since_last_change"):
            ours, theirs = values[component_id][feature], expected[feature]
            agree = ours == theirs
            checks += 1
            matches += agree
            if not copy_followed:
                clean_checks += 1
                clean_matches += agree
            row[f"seir_{feature}"], row[f"oracle_{feature}"] = ours, theirs
            if not agree:
                reason = "oracle followed a copy" if copy_followed else "MISMATCH"
                print(f"{component_id[-59:]:<60}{feature:<26}{ours!s:>8}{theirs!s:>8}  {reason}")
        rows.append(row)

    out_dir = settings.data_dir / checkout.repo_id.replace("/", "__") / checkout.snapshot[:12]
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "git_verification_sample.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    below = lower_bound_violations(checkout, first, values, path_of)
    for component_id, ours, plain in below:
        print(f"BELOW LOWER BOUND {component_id}: seir={ours} plain git log={plain}")

    repeatable = fingerprint(first) == fingerprint(second)
    print(f"\nlower-bound check    {len(path_of) - len(below)}/{len(path_of)} components OK")
    print(f"sampled components   {len(sample)}")
    print(f"feature agreement    {matches}/{checks} ({matches / checks:.1%}) - all sampled")
    if clean_checks:
        print(f"                     {clean_matches}/{clean_checks} ({clean_matches / clean_checks:.1%})"
              f" - excluding components where the oracle followed a copy")
    print(f"repeatable output    {'YES' if repeatable else 'NO'}")
    print(f"hand-check CSV       {csv_path}")


if __name__ == "__main__":
    main()
