"""Score the manual SZZ review (Data & Evolution report §10.4).

Fill `reviewer_verdict` in szz_review_sample.csv with correct / wrong / unsure, then:

    python -m scripts.evaluate_szz_review data/dataset/v1/szz_review_sample.csv

precision = correct / (correct + wrong); 'unsure' and empty rows are reported, not scored.
A 95 % Wilson interval is printed because 30 rows is a small sample.
"""

import argparse
import csv
import math
from collections import Counter

CORRECT, WRONG, UNSURE = "correct", "wrong", "unsure"
Z_95 = 1.96


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Confidence interval for a proportion that stays sensible for small n."""
    if n == 0:
        return 0.0, 0.0
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - margin), min(1.0, centre + margin)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_file")
    args = parser.parse_args()

    with open(args.csv_file, encoding="utf-8") as handle:
        verdicts = Counter(row["reviewer_verdict"].strip().lower() or "empty" for row in csv.DictReader(handle))

    judged = verdicts[CORRECT] + verdicts[WRONG]
    print(f"correct {verdicts[CORRECT]}, wrong {verdicts[WRONG]}, unsure {verdicts[UNSURE]}, "
          f"not reviewed {verdicts['empty']}")
    other = {k: v for k, v in verdicts.items() if k not in (CORRECT, WRONG, UNSURE, "empty")}
    if other:
        print(f"unrecognised verdicts (use correct/wrong/unsure): {other}")
    if judged == 0:
        print("SZZ precision: n/a (no correct/wrong verdicts yet)")
        return
    low, high = wilson_interval(verdicts[CORRECT], judged)
    print(f"SZZ precision: {verdicts[CORRECT] / judged:.0%} ({verdicts[CORRECT]}/{judged}), "
          f"95% CI {low:.0%}-{high:.0%}")


if __name__ == "__main__":
    main()
