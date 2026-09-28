from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.collectors.git_history import GitHistoryIndex
from app.collectors.git_log import read_history
from app.config import Settings
from app.dataset.cases import BULK_COMMIT, CENSORED, COSMETIC_COMMIT, NEW_COMPONENT, mine_cases
from app.dataset.features import ACTION_FEATURE, git_feature_row
from app.dataset.labels import assign_label
from app.dataset.splits import HOLDOUT, TEST, TRAIN, VALIDATION, assign_splits
from app.dataset.szz import faulty_lines, find_bug_inducing, to_ranges
from app.inventory import list_components
from app.schema import ChangeAction, RiskClass
from tests.git_repo_builder import GitRepoBuilder, java

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
PKG, SRC, TEST_SRC = "com.shop", "src/main/java/com/shop", "src/test/java/com/shop"
FAR_FUTURE = T0 + timedelta(days=10_000)


def day(n: int) -> datetime:
    return T0 + timedelta(days=n)


def build(repo: GitRepoBuilder, settings: Settings):
    snapshot = repo.git("rev-parse", "HEAD")
    comps = list_components(repo.path, "acme/shop", snapshot)
    p2c = {c.file_path: c.component_id for c in comps}
    commits = read_history(repo.path, snapshot)
    return commits, GitHistoryIndex.build(commits, p2c, settings), p2c


@pytest.fixture
def repo(tmp_path) -> GitRepoBuilder:
    return GitRepoBuilder(tmp_path / "repo")


# ---- labels ---------------------------------------------------------------------

@pytest.mark.parametrize(("spread", "bug", "expected"), [
    (0, False, RiskClass.LOW),
    (1, False, RiskClass.MEDIUM),
    (3, False, RiskClass.MEDIUM),
    (4, False, RiskClass.HIGH),
    (0, True, RiskClass.HIGH),
])
def test_label_rules(spread, bug, expected):
    assert assign_label(spread, bug) is expected


# ---- SZZ helpers ------------------------------------------------------------------

def test_faulty_lines_skip_comments_blank_and_imports():
    diff = "\n".join([
        "--- a/X.java", "+++ b/X.java",
        "@@ -10,4 +10,1 @@",
        "-    int x = 1;",  # line 10: code -> faulty
        "-    // old comment",  # line 11: skipped
        "-",  # line 12: blank, skipped
        "-import java.util.List;",  # line 13: skipped
        "+    int x = 2;",
        "@@ -30 +27,0 @@",
        "-    return x;",  # line 30: code -> faulty
    ])
    assert faulty_lines(diff) == [10, 30]


def test_to_ranges():
    assert to_ranges([9, 3, 4, 5, 4]) == [(3, 5), (9, 9)]


# ---- mining + SZZ end to end on a real git repo ----------------------------------------

def test_mining_labels_and_szz(repo):
    good = "  int total(int a, int b) {\n    return a + b;\n  }\n"
    repo.write(f"{SRC}/Calc.java", java(PKG, "Calc", good))
    repo.write(f"{SRC}/Report.java", java(PKG, "Report"))
    repo.commit("add classes", day(0))

    # A change that introduces a bug in Calc and also touches Report + a test.
    buggy = "  int total(int a, int b) {\n    return a - b;\n  }\n"
    repo.write(f"{SRC}/Calc.java", java(PKG, "Calc", buggy))
    repo.write(f"{SRC}/Report.java", java(PKG, "Report", "  int n;\n"))
    repo.write(f"{TEST_SRC}/CalcTest.java", java(PKG, "CalcTest"))
    bad_change = repo.commit("Refactor total calculation", day(10))

    repo.write(f"{SRC}/Calc.java", java(PKG, "Calc", good))
    repo.commit("Fix wrong sign in Calc.total", day(20))

    repo.write(f"{SRC}/Report.java", java(PKG, "Report", "  int n;\n  int m;\n"))
    repo.commit("Fix javadoc", day(30))  # cosmetic -> excluded

    settings = Settings(censor_days=180, co_change_min_support=1)
    commits, index, p2c = build(repo, settings)
    cases, excluded = mine_cases(commits, index, p2c, "acme/shop", FAR_FUTURE, set(), settings)

    by_key = {(c.commit_sha, c.target_component_id): c for c in cases}
    calc = by_key[(bad_change, f"{PKG}.Calc")]
    assert calc.impacted == (f"{PKG}.Report",)  # the test class is not "impact"
    assert calc.impacted_test_count == 1
    assert calc.action is ChangeAction.MODIFY
    assert excluded[COSMETIC_COMMIT] == 1
    assert excluded[NEW_COMPONENT] == 2  # both classes were created in the first commit

    inducing, fixes_traced = find_bug_inducing(repo.path, commits, p2c, settings)
    assert fixes_traced == 1
    assert (bad_change, f"{PKG}.Calc") in inducing  # SZZ blames the refactor
    assert (bad_change, f"{PKG}.Report") not in inducing  # Report's lines were not the bug

    row = git_feature_row(index, calc, settings)
    assert row["git_historical_commit_count"] == 1  # only the creating commit; not the change itself
    assert row[ACTION_FEATURE] == 0


def test_bulk_and_censored_commits_are_excluded(repo):
    for i in range(4):
        repo.write(f"{SRC}/C{i}.java", java(PKG, f"C{i}"))
    repo.commit("add", day(0))
    for i in range(4):
        repo.write(f"{SRC}/C{i}.java", java(PKG, f"C{i}", "  int x;\n"))
    repo.commit("touch everything", day(1))
    repo.write(f"{SRC}/C0.java", java(PKG, "C0", "  int y;\n"))
    repo.commit("recent edit", day(100))

    settings = Settings(bulk_commit_file_threshold=3)
    commits, index, p2c = build(repo, settings)
    cases, excluded = mine_cases(commits, index, p2c, "acme/shop", day(50), set(), settings)
    assert cases == []
    assert excluded[BULK_COMMIT] == 4
    assert excluded[CENSORED] == 1


def test_deletion_case(repo):
    repo.write(f"{SRC}/Old.java", java(PKG, "Old"))
    repo.write(f"{SRC}/User.java", java(PKG, "User"))
    repo.commit("add", day(0))
    (repo.path / SRC / "Old.java").unlink()
    repo.write(f"{SRC}/User.java", java(PKG, "User", "  int replaced;\n"))
    removal = repo.commit("Remove Old", day(5))

    settings = Settings()
    commits, index, p2c = build(repo, settings)
    cases, _ = mine_cases(commits, index, p2c, "acme/shop", FAR_FUTURE, set(), settings)
    old = next(c for c in cases if c.target_component_id == f"{PKG}.Old")
    assert old.commit_sha == removal
    assert old.action is ChangeAction.DELETE
    assert old.impacted == (f"{PKG}.User",)


# ---- splits ------------------------------------------------------------------------------

def test_splits_are_chronological_and_keep_commits_together():
    times = [day(i) for i in range(20)]
    df = pd.DataFrame({
        "repo_id": ["a/a"] * 20 + ["a/a"] + ["b/b"] * 3,
        "as_of": times + [times[-1]] + times[:3],  # a second case sharing the last commit time
    })
    split = assign_splits(df, {"b/b"}, 0.7, 0.15)
    a = df.assign(split=split)[df["repo_id"] == "a/a"]
    assert a.loc[a["split"] == TRAIN, "as_of"].max() < a.loc[a["split"] == VALIDATION, "as_of"].min()
    assert a.loc[a["split"] == VALIDATION, "as_of"].max() < a.loc[a["split"] == TEST, "as_of"].min()
    assert split.iloc[19] == split.iloc[20]  # same commit time -> same split
    assert (split[df["repo_id"] == "b/b"] == HOLDOUT).all()
