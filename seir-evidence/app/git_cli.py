"""Thin wrapper around the `git` command line.

We call git directly (instead of GitPython/PyDriller) because a single
`git log --numstat` pass is orders of magnitude faster than per-commit diffs,
and every command here can be copy-pasted into a terminal to reproduce a result.
"""

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def run_git(repo_dir: Path | None, *args: str, timeout: int = 600) -> str:
    command = ["git", *args] if repo_dir is None else ["git", "-C", str(repo_dir), *args]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git timed out after {timeout}s: {' '.join(command)}") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise GitError(f"{' '.join(command)} failed: {stderr}")
    # Commit messages/author names can contain any bytes; never crash on them.
    return completed.stdout.decode("utf-8", errors="replace")


def list_tree(repo_dir: Path, revision: str, timeout: int = 600) -> dict[str, str]:
    """Every file at `revision` -> its blob SHA (content fingerprint), without checking it out."""
    raw = run_git(repo_dir, "ls-tree", "-r", "-z", revision, timeout=timeout)
    tree = {}
    for entry in raw.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        _mode, kind, blob = meta.split()
        if kind == "blob":
            tree[path] = blob
    return tree


def read_blobs(repo_dir: Path, blobs: list[str], timeout: int = 600) -> dict[str, str]:
    """Read many file contents in ONE `git cat-file --batch` call (blob SHA -> text)."""
    if not blobs:
        return {}
    completed = subprocess.run(
        ["git", "-C", str(repo_dir), "cat-file", "--batch"],
        input="\n".join(blobs).encode() + b"\n", capture_output=True, timeout=timeout, check=False,
    )
    if completed.returncode != 0:
        raise GitError(f"git cat-file --batch failed: {completed.stderr.decode(errors='replace')}")
    out, contents, position = completed.stdout, {}, 0
    for blob in blobs:
        header_end = out.index(b"\n", position)
        header = out[position:header_end].decode()
        if header.endswith("missing"):
            position = header_end + 1
            continue
        size = int(header.split()[2])  # "<sha> blob <size>"
        start = header_end + 1
        contents[blob] = out[start:start + size].decode("utf-8", errors="replace")
        position = start + size + 1  # content is followed by a newline
    return contents


def run_git_piped(repo_dir: Path, producer: list[str], consumer: list[str], timeout: int = 600) -> str:
    """`git <producer> | git <consumer>` without a shell (portable, no quoting issues)."""
    base = ["git", "-C", str(repo_dir)]
    try:
        first = subprocess.run([*base, *producer], capture_output=True, timeout=timeout, check=False)
        if first.returncode != 0:
            raise GitError(f"git {' '.join(producer)} failed: {first.stderr.decode(errors='replace')}")
        second = subprocess.run([*base, *consumer], input=first.stdout, capture_output=True,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git pipeline timed out after {timeout}s") from exc
    if second.returncode != 0:
        raise GitError(f"git {' '.join(consumer)} failed: {second.stderr.decode(errors='replace')}")
    return second.stdout.decode("utf-8", errors="replace")
