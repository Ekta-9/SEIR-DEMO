"""Build small real git repositories for tests, with fully controlled dates/authors."""

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def java(package: str, name: str, body: str = "") -> str:
    return f"package {package};\n\npublic class {name} {{\n{body}}}\n"


class GitRepoBuilder:
    def __init__(self, path: Path):
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "default@test")
        self.git("config", "user.name", "default")

    def git(self, *args: str, env: dict | None = None) -> str:
        return subprocess.run(
            ["git", "-C", str(self.path), *args],
            check=True, capture_output=True, text=True, env={**os.environ, **(env or {})},
        ).stdout.strip()

    def write(self, rel_path: str, content: str) -> None:
        target = self.path / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def move(self, old: str, new: str) -> None:
        (self.path / new).parent.mkdir(parents=True, exist_ok=True)
        self.git("mv", old, new)

    def commit(self, message: str, when: datetime, author: str = "alice@test") -> str:
        stamp = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")
        env = {
            "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp,
            "GIT_AUTHOR_EMAIL": author, "GIT_AUTHOR_NAME": author.split("@")[0],
        }
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message, env=env)
        return self.git("rev-parse", "HEAD")
