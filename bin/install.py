#!/usr/bin/env python3
"""Wire the session-handoff tool into Claude Code: status line, three hooks, and the /handoff skill.

Touches only <home>/.claude/settings.json (timestamped backup first, merged, every existing key kept) and the symlink
<home>/.claude/skills/handoff. Idempotent. Refuses (exit 2, nothing written) on unparseable settings, a foreign
statusLine, or a non-symlink where the skill link goes.
"""
import argparse
import json
import os
import shlex
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MARK = "claude-usage-monitor/bin/"
STATUS_CMD = f"python3 -I {shlex.quote(str(REPO / 'bin' / 'statusline.py'))}"
HOOK_CMD = f"python3 -I {shlex.quote(str(REPO / 'bin' / 'handoff_hook.py'))}"
SKILL_SRC = REPO / "skills" / "handoff"
POST_TOOL_MATCHER = r"^Bash$|^mcp__.*github.*__(create|merge)_pull_request$"
EVENTS = {"SessionStart": None, "UserPromptSubmit": None, "PostToolUse": POST_TOOL_MATCHER}


class Refusal(Exception):
    pass


def is_ours(handler) -> bool:
    return isinstance(handler, dict) and MARK in str(handler.get("command", ""))


def paths(home: Path):
    claude = home / ".claude"
    return claude / "settings.json", claude / "skills" / "handoff"


def read_settings(path: Path) -> tuple[dict, bool]:
    """(settings, existed). Missing or empty file -> {}. Unparseable or not an object -> Refusal."""
    if not path.exists():
        return {}, False
    text = path.read_text()
    if not text.strip():
        return {}, True
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise Refusal(f"{path} is not valid JSON ({exc}); fix it first. Nothing was written.")
    if not isinstance(data, dict):
        raise Refusal(f"{path} is not a JSON object; nothing was written.")
    return data, True


def backup(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = path.with_name(f"{path.name}.bak-{stamp}")
    n = 1
    while dest.exists():
        dest = path.with_name(f"{path.name}.bak-{stamp}-{n}")
        n += 1
    dest.write_bytes(path.read_bytes())
    return dest


def write_settings(path: Path, data: dict) -> None:
    """Atomic write that keeps the file's permissions and, if settings.json is a symlink, writes its target."""
    path = Path(os.path.realpath(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        mode = path.stat().st_mode & 0o777
    else:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings.", suffix=".tmp")
    os.fchmod(fd, mode)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def link_is_ours(link: Path) -> bool:
    return link.is_symlink() and Path(os.readlink(link)) == SKILL_SRC


def merged(settings: dict) -> dict:
    s = json.loads(json.dumps(settings))
    s["statusLine"] = {"type": "command", "command": STATUS_CMD}
    hooks = s.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise Refusal("settings.json `hooks` is not an object; nothing was written.")
    for event, matcher in EVENTS.items():
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise Refusal(f"settings.json `hooks.{event}` is not a list; nothing was written.")
        if any(is_ours(h) for g in groups if isinstance(g, dict) for h in g.get("hooks", [])):
            continue
        group = {"hooks": [{"type": "command", "command": HOOK_CMD, "timeout": 5}]}
        if matcher:
            group = {"matcher": matcher, **group}
        groups.append(group)
    return s


def install(home: Path) -> str:
    settings_path, link = paths(home)
    settings, existed = read_settings(settings_path)
    current = settings.get("statusLine")
    if current and not (isinstance(current, dict) and is_ours(current)):
        raise Refusal(f"a statusLine is already set ({json.dumps(current)}); remove it or merge by hand. "
                      "Nothing was written.")
    if (link.exists() or link.is_symlink()) and not link_is_ours(link):
        raise Refusal(f"{link} exists and is not our symlink; move it away first. Nothing was written.")
    new = merged(settings)
    report = []
    if new != settings or not existed:
        if existed:
            report.append(f"backup: {backup(settings_path)}")
        write_settings(settings_path, new)
        report.append(f"updated: {settings_path}")
    else:
        report.append(f"unchanged: {settings_path}")
    if not link_is_ours(link):
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(SKILL_SRC)
        report.append(f"linked: {link} -> {SKILL_SRC}")
    report.append("Restart open Claude Code sessions to pick up the hooks and status line.")
    return "\n".join(report)


def main(argv=None, action=install) -> int:
    ap = argparse.ArgumentParser(description=(action.__doc__ or __doc__).strip().splitlines()[0])
    ap.add_argument("--home", type=Path, default=Path.home())
    args = ap.parse_args(argv)
    try:
        print(action(args.home))
    except Refusal as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
