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
