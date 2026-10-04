"""The runtime copy of the workspace (the app never writes to the pristine seed) and its git."""

import os
import shutil
import subprocess
from pathlib import Path

from app.config import settings

USERS = {
    "Anna Chan": "anna.chan@harbourlane.com.hk",
    "Ken Lau": "ken.lau@harbourlane.com.hk",
    "David Wong": "david.wong@harbourlane.com.hk",
}


def root() -> Path:
    return Path(settings.trace_workspace).resolve()


def seed() -> Path:
    return Path(settings.trace_seed_workspace).resolve()


def path(rel: str) -> Path:
    return root() / rel


def trace_dir() -> Path:
    return root() / ".trace"


def git(*args: str, check: bool = True, env: dict | None = None) -> str:
    ws = root()
    out = subprocess.run(
        ["git", f"--git-dir={ws / '.trace' / 'git'}", f"--work-tree={ws}", *args],
        capture_output=True,
        text=True,
        check=check,
        env={**os.environ, **(env or {})},
    )
    return out.stdout


def reset() -> None:
    """Delete the runtime copy and copy the seed again (incl. its git history)."""
    ws, src = root(), seed()
    if ws.exists():
        shutil.rmtree(ws)
    ws.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, ws, ignore=shutil.ignore_patterns("ground_truth"))
    git("config", "core.worktree", str(ws))
    # caches Trace rebuilds itself: never "new files", never committed
    (ws / ".trace" / "git" / "info").mkdir(exist_ok=True)
    (ws / ".trace" / "git" / "info" / "exclude").write_text(
        ".trace/extracted/\n.trace/index.json\n"
    )
    from app.core import expectations, indexer  # late import: they depend on this module

    expectations.seed()
    indexer.build()


def ensure() -> None:
    if not (root() / ".trace" / "git").exists():
        reset()


def commit(paths: list[str], subject: str, body: str, author: str) -> str:
    email = USERS.get(author, "trace@harbourlane.com.hk")
    env = {
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": author,
        "GIT_COMMITTER_EMAIL": email,
    }
    git("add", "--", *paths)
    git("commit", "-q", "-m", subject, "-m", body, env=env)
    return git("rev-parse", "HEAD").strip()


def untracked() -> set[str]:
    out = git("ls-files", "--others", "--exclude-standard")
    return set(out.splitlines())


def last_commits() -> dict[str, str]:
    """path -> last commit hash touching it."""
    out = git("log", "--name-only", "--format=@%H")
    seen: dict[str, str] = {}
    current = ""
    for line in out.splitlines():
        if line.startswith("@"):
            current = line[1:]
        elif line and line not in seen:
            seen[line] = current
    return seen


def log() -> list[dict]:
    sep = "\x1f"
    out = git(
        "log", f"--format=%H{sep}%an{sep}%ad{sep}%s{sep}%b\x1e", "--date=format:%Y-%m-%d %H:%M"
    )
    commits = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        h, an, ad, s, b = rec.split(sep)
        files = git("show", "--name-only", "--format=", h).split()
        commits.append(dict(hash=h, author=an, date=ad, subject=s, body=b.strip(), files=files))
    return commits
