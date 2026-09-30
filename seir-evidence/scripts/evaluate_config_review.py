"""Compute configuration-extraction metrics from reviewed CSVs (report §6.3).

    precision          = resolved references judged real / resolved references judged
    recall             = real references SEIR resolved / all real references found
                         (SEIR-resolved + real broad-scan misses)
    unresolved rate    = UNRESOLVED / (RESOLVED + UNRESOLVED)
    false-reference    = resolved references judged not real / resolved references judged

Rows marked 'unsure' or left empty are excluded and counted.

Run from seir-evidence/:
    python -m scripts.evaluate_config_review data/<repo>/<snapshot>/config_review.csv [more.csv ...]
"""

import argparse
import csv
from collections import Counter

YES, NO = "yes", "no"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_files", nargs="+")
    args = parser.parse_args()

    counts = Counter()
    for path in args.csv_files:
        with open(path, encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                verdict = row["is_real_reference"].strip().lower()
                if row["source"] == "seir":
                    counts[f"seir_{row['seir_resolution']}"] += 1
                if verdict not in (YES, NO):
                    counts["not_judged"] += 1
                    continue
                if row["source"] == "seir" and row["seir_resolution"] == "RESOLVED":
                    counts[f"resolved_{verdict}"] += 1
                elif row["source"] == "broad_scan":
                    counts[f"missed_{verdict}"] += 1

    judged = counts["resolved_yes"] + counts["resolved_no"]
    real = counts["resolved_yes"] + counts["missed_yes"]
    found = counts["seir_RESOLVED"] + counts["seir_UNRESOLVED"]
    ratio = lambda a, b: f"{a / b:.1%} ({a}/{b})" if b else "n/a (no judged rows)"
    print(f"precision            {ratio(counts['resolved_yes'], judged)}")
    print(f"recall               {ratio(counts['resolved_yes'], real)}")
    print(f"false-reference rate {ratio(counts['resolved_no'], judged)}")
    print(f"unresolved rate      {ratio(counts['seir_UNRESOLVED'], found)}")
    print(f"not judged / unsure  {counts['not_judged']}")


if __name__ == "__main__":
    main()
