#!/usr/bin/env python3
"""Claude Code status line: conversation size against the window, the handoff floor, and the floor's basis.

Prints one line such as `ctx 312K/1.0M · handoff at next break`. On any error: no stdout, exit 0, one log line.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))


def render(payload: dict) -> str:
    from breaks import load_state, save_state
    from handoff_lib import basis_status, context_size, fmt_tokens, load_config, usage_size

    cfg = load_config()
    cw = payload.get("context_window") or {}
    model_id = (payload.get("model") or {}).get("id")
    sid = payload.get("session_id")

    usage = cw.get("current_usage")
    if isinstance(usage, dict):
        size = usage_size(usage)
    else:
        path = payload.get("transcript_path")
        size = context_size(path) if isinstance(path, str) and path else None

    window = cw.get("context_window_size")
    if sid:
        # Write only on change: an unconditional load-modify-save on every render races the hooks' writes.
        state = load_state(sid)
        changed = False
        if window and state.get("context_window") != window:
            state["context_window"] = window
            changed = True
        if model_id and state.get("model_id") != model_id:
            state["model_id"] = model_id
            changed = True
        if changed:
            save_state(sid, state)
        window = window or state.get("context_window")
    window = window or cfg["default_context_window"]

    line = f"ctx {fmt_tokens(size) if size is not None else '?'}/{fmt_tokens(window)}"
    if size is not None and size >= cfg["floor_tokens"]:
        line += " · handoff at next break"
    if basis_status(cfg, model_id, payload.get("version")) != "verified":
        line += " · floor unverified"
    return line


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        line = render(payload if isinstance(payload, dict) else {})
        sys.stdout.write(line + "\n")
    except Exception as exc:
        try:
            from handoff_lib import log_error
            log_error("statusline", exc)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
