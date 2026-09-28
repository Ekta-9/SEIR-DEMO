"""Clone or update a GitHub repository into the workspace and pin a snapshot."""

import re
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.git_cli import run_git

GITHUB_URL_PATTERN = re.compile(r"^https://github\.com/(?P<owner>[\w.-]+)/(?P<name>[\w.-]+?)(?:\.git)?/?$")


@dataclass(frozen=True)
class RepoCheckout:
    repo_id: str  # "owner/name"
    path: Path  # local working copy
    snapshot: str  # full SHA that was analyzed


def parse_github_url(url: str) -> str:
    """'https://github.com/owner/name(.git)' -> 'owner/name'."""
    match = GITHUB_URL_PATTERN.match(url.strip())
    if not match:
        raise ValueError(f"not a GitHub repository URL: {url!r}")
    return f"{match['owner']}/{match['name']}"


def local_path_for(repo_id: str, settings: Settings) -> Path:
    return settings.repos_dir / repo_id.replace("/", "__")


def fetch_repository(url: str, settings: Settings, ref: str | None = None) -> RepoCheckout:
    """Full clone (history is the point, so never shallow), then check out `ref`.

    `ref` may be a branch, tag or SHA; default is the remote's default branch.
    """
    repo_id = parse_github_url(url)
    path = local_path_for(repo_id, settings)
    timeout = settings.git_timeout_seconds

    if (path / ".git").exists():
        run_git(path, "fetch", "--quiet", "--tags", "origin", timeout=timeout)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        run_git(None, "clone", "--quiet", url, str(path), timeout=timeout)

    target = ref or run_git(path, "rev-parse", "--abbrev-ref", "origin/HEAD").strip()
    run_git(path, "checkout", "--quiet", "--force", "--detach", target, timeout=timeout)
    snapshot = run_git(path, "rev-parse", "HEAD").strip()
    return RepoCheckout(repo_id=repo_id, path=path, snapshot=snapshot)
