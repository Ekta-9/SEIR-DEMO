"""Risk labelling rules — labels@1.0 (approved 2026-09-28, before any training).

These thresholds are *part of the label definition*, not tuning knobs, which is
why they live here as versioned constants rather than in config.py. Changing
any of them means a new LABEL_RULE_VERSION and regenerating the dataset.

    HIGH   : the change later required a bug fix (SZZ), or it spread to
             >= HIGH_SPREAD_MIN other production components
    MEDIUM : it spread to 1 .. HIGH_SPREAD_MIN-1 other production components
    LOW    : it spread to no other production component and caused no bug
"""

from app.schema import RiskClass

LABEL_RULE_VERSION = "labels@1.0"
HIGH_SPREAD_MIN = 4
MEDIUM_SPREAD_MIN = 1


def assign_label(spread: int, caused_bug_fix: bool) -> RiskClass:
    if spread < 0:
        raise ValueError("spread cannot be negative")
    if caused_bug_fix or spread >= HIGH_SPREAD_MIN:
        return RiskClass.HIGH
    if spread >= MEDIUM_SPREAD_MIN:
        return RiskClass.MEDIUM
    return RiskClass.LOW
