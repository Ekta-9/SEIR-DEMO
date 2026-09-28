"""Analyze a real GitHub repository and write evidence JSON to data/.

Run from seir-evidence/:
    python -m scripts.run_analysis https://github.com/spring-projects/spring-petclinic
"""

import argparse
import time

from app.config import load_settings
from app.pipeline import analyze_repository
from app.repo_fetcher import fetch_repository

PREVIEW_ROWS = 10


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="GitHub repository URL")
    parser.add_argument("--ref", help="branch, tag or SHA (default: remote default branch)")
    args = parser.parse_args()

    settings = load_settings()
    started = time.perf_counter()
    checkout = fetch_repository(args.url, settings, args.ref)
    fetched = time.perf_counter()
    result = analyze_repository(checkout, settings)
    analyzed = time.perf_counter()

    out_dir = settings.data_dir / checkout.repo_id.replace("/", "__") / checkout.snapshot[:12]
    result.write(out_dir)

    print(f"repo      {checkout.repo_id} @ {checkout.snapshot}")
    for key, value in result.stats.items():
        print(f"{key:<24}{value}")
    print(f"fetch time              {fetched - started:.1f}s")
    print(f"analysis time           {analyzed - fetched:.1f}s")
    print(f"output                  {out_dir}")

    by_type = {}
    for item in result.evidence:
        by_type.setdefault(item.component_id, {})[item.evidence_type] = item.value
    busiest = sorted(by_type.items(), key=lambda kv: -(kv[1].get("historical_commit_count") or 0))
    print(f"\nMost-changed components (top {PREVIEW_ROWS}):")
    print(f"{'component':<70}{'commits':>8}{'recent':>8}{'authors':>8}{'days':>7}{'cochg':>7}")
    for component_id, v in busiest[:PREVIEW_ROWS]:
        print(f"{component_id[-69:]:<70}{v['historical_commit_count']!s:>8}{v['recent_commit_count']!s:>8}"
              f"{v['unique_contributors']!s:>8}{v['days_since_last_change']!s:>7}{v['co_change_count']!s:>7}")


if __name__ == "__main__":
    main()
