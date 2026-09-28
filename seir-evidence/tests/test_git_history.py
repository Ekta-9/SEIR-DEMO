from datetime import datetime, timedelta, timezone

import pytest

from app.collectors.git_history import GitHistoryIndex, build_git_evidence
from app.collectors.git_log import parse_log, read_history
from app.config import Settings
from app.inventory import list_components
from app.schema import Availability
from tests.git_repo_builder import GitRepoBuilder, java

T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
PKG = "com.shop"
SRC = "src/main/java/com/shop"


def day(n: int) -> datetime:
    return T0 + timedelta(days=n)


def index_for(repo: GitRepoBuilder, settings: Settings | None = None) -> GitHistoryIndex:
    settings = settings or Settings()
    snapshot = repo.git("rev-parse", "HEAD")
    components = list_components(repo.path, "acme/shop", snapshot)
    path_to_component = {c.file_path: c.component_id for c in components}
    return GitHistoryIndex.build(read_history(repo.path, snapshot), path_to_component, settings)


@pytest.fixture
def repo(tmp_path) -> GitRepoBuilder:
    return GitRepoBuilder(tmp_path / "repo")


# ---- parser -------------------------------------------------------------------

def test_parse_log_handles_rename_tokens():
    header = "\x1f".join(["a" * 40, "1700000000", "Alice@X", "b" * 40 + " " + "c" * 40, "Fix NPE\x1fodd"])
    raw = "\x1e" + header + "\0\n3\t1\t\0old/A.java\0new/A.java\0" + "2\t0\tB.java\0"
    [commit] = parse_log(raw)
    assert commit.author == "alice@x"
    assert commit.parent == "b" * 40  # first parent only
    assert commit.subject == "Fix NPE\x1fodd"  # separator inside the subject survives
    assert [(f.old_path, f.path, f.added, f.deleted) for f in commit.files] == [
        ("old/A.java", "new/A.java", 3, 1), (None, "B.java", 2, 0),
    ]


# ---- features -------------------------------------------------------------------

def test_counts_authors_and_churn(repo):
    repo.write(f"{SRC}/Pay.java", java(PKG, "Pay"))
    repo.commit("add", day(0), "alice@test")
    repo.write(f"{SRC}/Pay.java", java(PKG, "Pay", "  int x;\n  int y;\n"))
    repo.commit("edit", day(10), "bob@test")

    f = index_for(repo).features(f"{PKG}.Pay", day(20))
    assert f.historical_commit_count == 2
    assert f.unique_contributors == 2
    assert f.lines_added == 4 + 2  # 4-line new file, then 2 added lines
    assert f.days_since_last_change == 10


def test_as_of_excludes_the_future(repo):
    """Leakage guard: commits at or after the cutoff must be invisible."""
    repo.write(f"{SRC}/Pay.java", java(PKG, "Pay"))
    repo.commit("add", day(0))
    repo.write(f"{SRC}/Pay.java", java(PKG, "Pay", "  int x;\n"))
    repo.commit("future edit", day(30))

    index = index_for(repo)
    assert index.features(f"{PKG}.Pay", day(30)).historical_commit_count == 1  # exclusive cutoff
    assert index.features(f"{PKG}.Pay", day(30) + timedelta(seconds=1)).historical_commit_count == 2


def test_recent_window(repo):
    repo.write(f"{SRC}/Pay.java", java(PKG, "Pay"))
    repo.commit("old", day(0))
    repo.write(f"{SRC}/Pay.java", java(PKG, "Pay", "  int x;\n"))
    repo.commit("recent", day(200))

    f = index_for(repo, Settings(recent_window_days=90)).features(f"{PKG}.Pay", day(210))
    assert f.recent_commit_count == 1
    assert f.historical_commit_count == 2


def test_rename_keeps_history(repo):
    repo.write("src/main/java/com/shop/web/Vet.java", java("com.shop.web", "Vet", "  int a;\n  int b;\n  int c;\n"))
    repo.commit("add", day(0))
    repo.move("src/main/java/com/shop/web/Vet.java", "src/main/java/com/shop/vet/Vet.java")
    repo.write("src/main/java/com/shop/vet/Vet.java", java("com.shop.vet", "Vet", "  int a;\n  int b;\n  int c;\n"))
    repo.commit("move", day(1))

    assert index_for(repo).features("com.shop.vet.Vet", day(2)).historical_commit_count == 2


def test_edit_on_parallel_branch_after_rename_is_attributed(repo):
    """The DAG case found in spring-petclinic: a side branch edits the old path
    (dated after the rename on main), then gets merged."""
    body = "".join(f"  int f{i};\n" for i in range(10))
    repo.write("src/main/java/com/shop/web/Vet.java", java("com.shop.web", "Vet", body))
    repo.commit("add", day(0))
    repo.git("checkout", "-q", "-b", "side")
    repo.git("checkout", "-q", "main")
    repo.move("src/main/java/com/shop/web/Vet.java", "src/main/java/com/shop/vet/Vet.java")
    repo.write("src/main/java/com/shop/vet/Vet.java", java("com.shop.vet", "Vet", body))
    repo.commit("rename on main", day(1))
    repo.git("checkout", "-q", "side")
    repo.write("src/main/java/com/shop/web/Vet.java", java("com.shop.web", "Vet", body + "  int extra;\n"))
    side_edit = repo.commit("edit old path on side branch", day(2))
    repo.git("checkout", "-q", "main")
    repo.git("merge", "-q", "-X", "theirs", "--no-edit", "side",
             env={"GIT_AUTHOR_DATE": day(3).isoformat(), "GIT_COMMITTER_DATE": day(3).isoformat()})

    touches = index_for(repo).features("com.shop.vet.Vet", day(4)).touches
    assert side_edit in {t.sha for t in touches}


def test_side_branch_commits_are_not_pruned(repo):
    """With a pathspec, git log prunes side branches whose merge result equals
    main ("history simplification"). The commits still happened, so they count."""
    repo.write(f"{SRC}/Pay.java", java(PKG, "Pay"))
    repo.commit("add", day(0))
    repo.git("checkout", "-q", "-b", "side")
    repo.write(f"{SRC}/Pay.java", java(PKG, "Pay", "  int tried;\n"))
    side_edit = repo.commit("experiment on side branch", day(1))
    repo.git("checkout", "-q", "main")
    stamp = {"GIT_AUTHOR_DATE": day(2).isoformat(), "GIT_COMMITTER_DATE": day(2).isoformat()}
    repo.git("merge", "-q", "-s", "ours", "--no-edit", "side", env=stamp)  # result == main

    touches = index_for(repo).features(f"{PKG}.Pay", day(3)).touches
    assert side_edit in {t.sha for t in touches}


def test_bulk_commits_count_but_do_not_create_co_change(repo):
    for i in range(5):
        repo.write(f"{SRC}/C{i}.java", java(PKG, f"C{i}"))
    repo.commit("bulk import", day(0))
    for n in range(2):  # A and B change together twice
        repo.write(f"{SRC}/C0.java", java(PKG, "C0", f"  int v{n};\n"))
        repo.write(f"{SRC}/C1.java", java(PKG, "C1", f"  int v{n};\n"))
        repo.commit(f"pair {n}", day(1 + n))

    index = index_for(repo, Settings(bulk_commit_file_threshold=3, co_change_min_support=2))
    c0 = index.features(f"{PKG}.C0", day(10))
    assert c0.historical_commit_count == 3  # bulk import still counts as a change
    assert dict(c0.partners) == {f"{PKG}.C1": 2}  # C2..C4 only co-occurred in the bulk commit


def test_deleted_partner_is_not_counted(repo):
    repo.write(f"{SRC}/A.java", java(PKG, "A"))
    repo.write(f"{SRC}/Gone.java", java(PKG, "Gone"))
    repo.commit("add", day(0))
    for n in range(2):
        repo.write(f"{SRC}/A.java", java(PKG, "A", f"  int v{n};\n"))
        repo.write(f"{SRC}/Gone.java", java(PKG, "Gone", f"  int v{n};\n"))
        repo.commit(f"together {n}", day(1 + n))
    (repo.path / SRC / "Gone.java").unlink()
    repo.commit("delete Gone", day(5))

    index = index_for(repo, Settings(co_change_min_support=2))
    assert f"{PKG}.Gone" in index.features(f"{PKG}.A", day(4)).partners  # alive before deletion
    assert f"{PKG}.Gone" not in index.features(f"{PKG}.A", day(6)).partners  # gone after


def test_evidence_is_unknown_without_history(repo):
    repo.write(f"{SRC}/Pay.java", java(PKG, "Pay"))
    snapshot = repo.commit("add", day(10))

    items = build_git_evidence(index_for(repo), [f"{PKG}.Pay"], "acme/shop", snapshot, day(5), Settings())
    assert items and all(i.availability is Availability.UNKNOWN and i.value is None for i in items)
