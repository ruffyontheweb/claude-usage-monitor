#!/usr/bin/env python3
"""Remove exactly what install.py added: our hook handlers, our statusLine, our skill symlink."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install import (Refusal, backup, is_ours, link_is_ours, main, paths,  # noqa: E402
                     read_settings, write_settings)


def stripped(settings: dict) -> dict:
    s = json.loads(json.dumps(settings))
    if isinstance(s.get("statusLine"), dict) and is_ours(s["statusLine"]):
        del s["statusLine"]
    hooks = s.get("hooks")
    if isinstance(hooks, dict):
        for event in list(hooks):
            groups = hooks[event]
            if not isinstance(groups, list):
                continue
            kept = []
            for g in groups:
                if isinstance(g, dict) and isinstance(g.get("hooks"), list) and any(is_ours(h) for h in g["hooks"]):
                    g = dict(g, hooks=[h for h in g["hooks"] if not is_ours(h)])
                    if not g["hooks"]:
                        continue
                kept.append(g)
            if kept:
                hooks[event] = kept
            elif groups:
                del hooks[event]
        if not hooks and settings.get("hooks"):
            del s["hooks"]
    return s


def uninstall(home: Path) -> str:
    """Remove the session-handoff status line, hooks and skill link."""
    settings_path, link = paths(home)
    report = []
    settings, existed = read_settings(settings_path)
    new = stripped(settings)
    if existed and new != settings:
        report.append(f"backup: {backup(settings_path)}")
        write_settings(settings_path, new)
        report.append(f"updated: {settings_path}")
    else:
        report.append(f"unchanged: {settings_path}")
    if link_is_ours(link):
        link.unlink()
        report.append(f"removed: {link}")
        try:
            link.parent.rmdir()  # only succeeds when empty, i.e. nothing else lives in ~/.claude/skills
            report.append(f"removed empty: {link.parent}")
        except OSError:
            pass
    return "\n".join(report)


if __name__ == "__main__":
    sys.exit(main(action=uninstall))
