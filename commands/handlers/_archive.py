"""llm-dev archive storage core — branch-independent session records.

Bare-repo "container" layout: a project folder that is not itself a working
tree, holding `.bare/` (git database), `.archive/` (a worktree of the orphan
`llm-dev-archive` branch), and `streams/<branch>/` worktrees. Records live on
`llm-dev-archive`, reachable from any stream worktree.

Stdlib only; Python 3.12+.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ARCHIVE_BRANCH = "llm-dev-archive"
ARCHIVE_DIRS = ("transcripts", "session-notes", "session-handoff",
                "artifacts", "sessions", "streams")


def _git(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        check=check, capture_output=True, text=True,
    )


def _git_out(*args: str, cwd: Path | None = None) -> str | None:
    try:
        return _git(*args, cwd=cwd).stdout.strip()
    except subprocess.CalledProcessError:
        return None


def _seed_archive_skeleton(archive_wt: Path) -> None:
    for d in ARCHIVE_DIRS:
        sub = archive_wt / d
        sub.mkdir(parents=True, exist_ok=True)
        (sub / ".gitkeep").touch()


def bootstrap_greenfield(container: Path, default_branch: str = "main") -> Path:
    """Create a brand-new container with no remote.

    Layout: <container>/{.bare, .git(pointer), streams/<default_branch>, .archive}.
    `main` starts as an orphan branch (unborn repo) with one empty commit;
    `llm-dev-archive` is an orphan branch seeded with the archive skeleton.
    """
    container = Path(container)
    container.mkdir(parents=True, exist_ok=True)
    _git("init", "--bare", str(container / ".bare"))
    (container / ".git").write_text("gitdir: ./.bare\n", encoding="utf-8")

    _git("worktree", "add", "-b", default_branch,
         f"streams/{default_branch}", cwd=container)
    main_wt = container / "streams" / default_branch
    _git("commit", "--allow-empty", "-m", "Initialize project", cwd=main_wt)

    archive_wt = container / ".archive"
    _git("worktree", "add", "--orphan", "-b", ARCHIVE_BRANCH, str(archive_wt), cwd=container)
    _seed_archive_skeleton(archive_wt)
    _git("add", "-A", cwd=archive_wt)
    _git("commit", "-m", "Initialize llm-dev archive", cwd=archive_wt)
    return container


def _branch_exists(bare: Path, branch: str) -> bool:
    return _git("--git-dir", str(bare), "show-ref", "--verify", "--quiet",
                f"refs/heads/{branch}", check=False).returncode == 0


def bootstrap_from_clone(container: Path, url: str, default_branch: str = "main") -> Path:
    """Create a container by cloning an existing remote (onboarding / existing project).

    A `--bare` clone leaves an empty fetch refspec, so we set the standard one
    and fetch before materializing worktrees. If the remote has no
    `llm-dev-archive` branch yet, seed it locally.
    """
    container = Path(container)
    container.mkdir(parents=True, exist_ok=True)
    bare = container / ".bare"
    _git("clone", "--bare", url, str(bare))
    (container / ".git").write_text("gitdir: ./.bare\n", encoding="utf-8")
    _git("--git-dir", str(bare), "config", "remote.origin.fetch",
         "+refs/heads/*:refs/remotes/origin/*")
    _git("--git-dir", str(bare), "fetch", "origin")

    _git("worktree", "add", f"streams/{default_branch}", default_branch, cwd=container)

    archive_wt = container / ".archive"
    if _branch_exists(bare, ARCHIVE_BRANCH):
        _git("worktree", "add", str(archive_wt), ARCHIVE_BRANCH, cwd=container)
        # Set upstream so pull --rebase and push work without specifying remote+branch.
        _git("branch", f"--set-upstream-to=origin/{ARCHIVE_BRANCH}", ARCHIVE_BRANCH,
             cwd=archive_wt)
    else:
        _git("worktree", "add", "--orphan", "-b", ARCHIVE_BRANCH, str(archive_wt), cwd=container)
        _seed_archive_skeleton(archive_wt)
        _git("add", "-A", cwd=archive_wt)
        _git("commit", "-m", "Initialize llm-dev archive", cwd=archive_wt)
    return container


def container_root(cwd: Path) -> Path | None:
    """Return the container directory (parent of `.bare`) for any worktree under it.

    Uses the shared git common dir, so it resolves the same from `streams/<b>/`,
    `.archive/`, or the container itself. Returns None for non-container repos.
    """
    common = _git_out("rev-parse", "--git-common-dir", cwd=cwd)
    if not common:
        return None
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = (Path(cwd) / common_path).resolve()
    if common_path.name == ".bare":
        return common_path.parent
    return None


def archive_worktree(cwd: Path) -> Path | None:
    """Return the `.archive/` worktree path (checked out on llm-dev-archive), or None."""
    root = container_root(cwd)
    if root is None:
        return None
    aw = root / ".archive"
    if aw.is_dir() and _git_out("symbolic-ref", "--short", "HEAD", cwd=aw) == ARCHIVE_BRANCH:
        return aw.resolve()
    return None


class FileLock:
    """Cross-platform advisory lock via O_CREAT|O_EXCL.

    Serializes archive-sync invocations within one worktree. Breaks a lock
    older than `stale` seconds (a crashed holder). Raises TimeoutError if it
    cannot acquire within `timeout`.

    This is an advisory lock: under concurrent stale-break (two processes
    breaking the same expired lock at once) it does not guarantee hard mutual
    exclusion. That is acceptable here because git's own index.lock serializes
    the underlying commit operations.
    """

    def __init__(self, path: Path, timeout: float = 10.0,
                 poll: float = 0.1, stale: float = 300.0) -> None:
        self.path = Path(path)
        self.timeout = timeout
        self.poll = poll
        self.stale = stale

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + self.timeout
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale:
                        self.path.unlink()
                        continue
                except OSError:
                    pass
                if time.time() >= deadline:
                    raise TimeoutError(f"could not acquire lock: {self.path}")
                time.sleep(self.poll)

    def __exit__(self, *exc) -> None:
        try:
            self.path.unlink()
        except OSError:
            pass


def _lock_path_for(archive_dir: Path) -> Path:
    """A lock path inside the worktree's private git dir (untracked)."""
    git_dir = _git_out("rev-parse", "--git-dir", cwd=archive_dir)
    if git_dir:
        gd = Path(git_dir)
        if not gd.is_absolute():
            gd = (Path(archive_dir) / gd).resolve()
        return gd / "llm-dev-archive-sync.lock"
    return Path(archive_dir) / ".llm-dev-archive-sync.lock"


@contextmanager
def archive_session(cwd: Path) -> Iterator[Path]:
    """Yield a usable llm-dev-archive worktree path.

    Prefers the persistent container `.archive/`. Otherwise (bare CI clone,
    non-container repo) creates a temporary worktree of llm-dev-archive,
    yields it, and removes it on exit. Requires the llm-dev-archive ref to be
    reachable from `cwd`'s repository.
    """
    aw = archive_worktree(cwd)
    if aw is not None:
        yield aw
        return
    tmp = Path(tempfile.mkdtemp(prefix="llm-dev-archive-"))
    wt = (tmp / "wt").resolve()
    try:
        _git("worktree", "add", str(wt), ARCHIVE_BRANCH, cwd=cwd)
        yield wt
    finally:
        _git("worktree", "remove", "--force", str(wt), cwd=cwd, check=False)
        shutil.rmtree(tmp, ignore_errors=True)


def archive_sync(archive_dir: Path, paths: list[str], message: str,
                 push: bool = True) -> dict:
    """Stage the given paths (or everything), commit, and best-effort push.

    Lock-guarded so concurrent triggers can't collide on the index. Returns
    {"committed": bool, "pushed": bool, "warnings": [str]}. Push failures
    (no remote / offline / non-fast-forward after rebase) are non-fatal: the
    local commit is durable and will push next time.
    """
    archive_dir = Path(archive_dir)
    result: dict = {"committed": False, "pushed": False, "warnings": []}
    with FileLock(_lock_path_for(archive_dir)):
        if paths:
            _git("add", "--", *paths, cwd=archive_dir)
        else:
            _git("add", "-A", cwd=archive_dir)
        if _git("diff", "--cached", "--quiet", cwd=archive_dir, check=False).returncode == 0:
            return result  # nothing staged
        _git("commit", "-m", message, cwd=archive_dir)
        result["committed"] = True
        if push:
            try:
                _git("pull", "--rebase", cwd=archive_dir)
            except subprocess.CalledProcessError as e:
                _git("rebase", "--abort", cwd=archive_dir, check=False)  # no-op if no rebase in progress
                result["warnings"].append(f"pull --rebase: {(e.stderr or '').strip()}")
                return result  # local commit is durable; retry push next sync
            try:
                _git("push", cwd=archive_dir)
                result["pushed"] = True
            except subprocess.CalledProcessError as e:
                result["warnings"].append(f"push: {(e.stderr or '').strip()}")
    return result


def resolve_archive_dir(cwd: Path) -> Path | None:
    """Return the usable `.archive/` directory for either layout, or None.

    - Container layout: the `.archive/` worktree on llm-dev-archive
      (`archive_worktree`).
    - In-place layout: ascend from `cwd` for the directory whose
      `.archive/transcripts/` exists, stopping at a `CLAUDE.md` boundary so a
      parent workspace's archive is never selected for a child project (unifies
      `init-session.find_transcripts_index` + `end-session._find_archive_dir`).

    The commit mechanism remains layout-specific (chosen by callers in 2b);
    this only locates where manifests/streams/index live.
    """
    cwd = Path(cwd).resolve()

    aw = archive_worktree(cwd)
    if aw is not None:
        return aw

    current = cwd
    while True:
        if (current / ".archive" / "transcripts").is_dir():
            return (current / ".archive").resolve()
        if (current / "CLAUDE.md").exists():
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None
