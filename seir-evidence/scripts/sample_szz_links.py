"""Export a random sample of SZZ links (change -> later bug fix) for manual review.

Report §10.4 / §22 ask for a manually verified sample of ground truth. Open the
CSV, read each pair of commits, and fill `reviewer_verdict` with
`correct` / `wrong` / `unsure`; the precision of SZZ is correct / (correct + wrong).

Run from seir-evidence/:
    python -m scripts.sample_szz_links --version v1 --sample 30
"""

import argparse
import csv
import json
import random

from app.config import load_settings
from app.git_cli import run_git
from app.repo_fetcher import local_path_for

DEFAULT_SAMPLE = 30
DEFAULT_SEED = 7
GITHUB_COMMIT_URL = "https://github.com/{repo}/commit/{sha}"


def subject(repo_dir, sha: str) -> str:
    return run_git(repo_dir, "show", "-s", "--format=%s", sha).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", default="v1")
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    settings = load_settings()
    dataset_dir = settings.data_dir / "dataset" / args.version
    links = []
    with (dataset_dir / "change_cases.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            case = json.loads(line)
            links.extend((case, fix) for fix in case["fix_commit_shas"])

    rows = []
    for case, fix in random.Random(args.seed).sample(links, min(args.sample, len(links))):
        repo_dir = local_path_for(case["repo_id"], settings)
        rows.append({
            "component": case["target_component_id"],
            "change_subject": subject(repo_dir, case["commit_sha"]),
            "fix_subject": subject(repo_dir, fix),
            "change_url": GITHUB_COMMIT_URL.format(repo=case["repo_id"], sha=case["commit_sha"]),
            "fix_url": GITHUB_COMMIT_URL.format(repo=case["repo_id"], sha=fix),
            "reviewer_verdict": "",
            "reviewer_note": "",
        })

    out = dataset_dir / "szz_review_sample.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(links)} SZZ links in total; wrote {len(rows)} for review -> {out}")


if __name__ == "__main__":
    main()
