#!/usr/bin/env python3
"""Where handoff notes live: <main checkout>/.claude/handoffs/<YYYY-MM-DD-HHMM>-<branch>-<topic>.md.

CLI:
  handoff_path.py new <topic>   print the path for a new note; create the folder; add it to .git/info/exclude
  handoff_path.py latest        print the newest note for this branch, or list all notes and exit 1
"""
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

EXCLUDE_LINE = ".claude/handoffs/"


def _git(cwd: str, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _common_dir(cwd: str) -> Path | None:
    out = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(out) if out else None


def main_checkout(cwd: str) -> Path | None:
    common = _common_dir(cwd)
    return common.parent if common else None


def branch_slug(cwd: str) -> str:
    branch = _git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch:
        return branch.replace("/", "-")
    sha = _git(cwd, "rev-parse", "--short=7", "HEAD")
    return f"detached-{sha}" if sha else "no-git"


def note_dir(cwd: str) -> Path:
    top = main_checkout(cwd)
    return (top if top else Path(cwd)) / ".claude" / "handoffs"


def ensure_excluded(cwd: str) -> None:
    common = _common_dir(cwd)
    if not common:
        return
    exclude = common / "info" / "exclude"
    text = exclude.read_text() if exclude.exists() else ""
    if EXCLUDE_LINE in text.splitlines():
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with open(exclude, "a") as f:
        if text and not text.endswith("\n"):
            f.write("\n")
        f.write(EXCLUDE_LINE + "\n")


def _topic_slug(topic: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:40].strip("-")
    return slug or "note"


def new_note_path(cwd: str, topic: str, now: datetime) -> Path:
    return note_dir(cwd) / f"{now:%Y-%m-%d-%H%M}-{branch_slug(cwd)}-{_topic_slug(topic)}.md"


def latest_note(cwd: str) -> Path | None:
    d = note_dir(cwd)
    if not d.is_dir():
        return None
    ours = branch_slug(cwd)
    # A note name can't say where the branch ends and the topic starts ("feat-login-x" fits branch "feat" and
    # "feat-login"), so a note belongs to the longest local branch whose slug it matches.
    refs = _git(cwd, "for-each-ref", "--format=%(refname:short)", "refs/heads") or ""
    slugs = {r.replace("/", "-") for r in refs.splitlines() if r} | {ours}

    def owner(name: str) -> str | None:
        hits = [s for s in slugs if re.match(r"^\d{4}-\d{2}-\d{2}-\d{4}-" + re.escape(s) + r"-.*\.md$", name)]
        return max(hits, key=len) if hits else None

    notes = sorted(p for p in d.iterdir() if p.is_file() and owner(p.name) == ours)
    return notes[-1] if notes else None


def main(argv: list[str]) -> int:
    cwd = str(Path.cwd())
    if len(argv) >= 2 and argv[0] == "new":
        path = new_note_path(cwd, " ".join(argv[1:]), datetime.now())
        path.parent.mkdir(parents=True, exist_ok=True)
        ensure_excluded(cwd)
        print(path)
        return 0
    if argv == ["latest"]:
        note = latest_note(cwd)
        if note:
            print(note)
            return 0
        d = note_dir(cwd)
        notes = sorted(d.glob("*.md")) if d.is_dir() else []
        print(f"No handoff note for branch {branch_slug(cwd)}. Notes in {d}:")
        for p in notes:
            print(f"  {p.name}")
        if not notes:
            print("  (none)")
        return 1
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
