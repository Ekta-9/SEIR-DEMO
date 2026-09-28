"""Build the labelled risk dataset from the repositories in corpus.yaml.

Run from seir-evidence/:
    python -m scripts.build_dataset                 # repos with role 'dataset'
    python -m scripts.build_dataset --version v1
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import yaml

from app.config import PROJECT_ROOT, load_settings
from app.dataset.build import build_dataset

CORPUS_FILE = PROJECT_ROOT / "corpus.yaml"
DATASET_ROLE = "dataset"
HOLDOUT_ROLE = "holdout"


def load_corpus(path: Path) -> tuple[list[str], set[str]]:
    repos = yaml.safe_load(path.read_text(encoding="utf-8"))["repositories"]
    selected = [r for r in repos if DATASET_ROLE in r["roles"]]
    holdout = {r["repo_id"] for r in selected if HOLDOUT_ROLE in r["roles"]}
    return [r["url"] for r in selected], holdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", default="v1")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    urls, holdout = load_corpus(CORPUS_FILE)
    started = time.perf_counter()
    out_dir = build_dataset(urls, holdout, load_settings(), args.version)
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    print(f"\nbuilt in {time.perf_counter() - started:.0f}s -> {out_dir}")
    print((out_dir / "quality_report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
