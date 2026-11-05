#!/usr/bin/env python3
"""Claude Code hook entry point for session handoff. Dispatches on hook_event_name.

Never raises, never blocks, never prints on error: any exception is logged to
~/.cache/claude-handoff/errors.log and the process exits 0 with no stdout.
"""
import json
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent
sys.path[:0] = [str(BIN.parent / "lib"), str(BIN)]

CONVENTION = ("Session handoff convention (claude-usage-monitor): when you finish a natural unit of work (a pull "
              "request opened or merged, a plan or design written and committed, or the user saying a piece of work "
              "is done) and a [handoff] line has said the conversation is above the floor, suggest /handoff in one "
              "line before starting anything new. Never stop mid-task for this.")
NOTE_MENTION = " A handoff note exists for this branch: {path}. Mention it to the user once."


def _size(event):
    from handoff_lib import context_size
    path = event.get("transcript_path")
    return context_size(path) if isinstance(path, str) and path else None


def session_start(event):
    text = CONVENTION
    if event.get("source") in ("startup", "clear") and event.get("cwd"):
        try:
            from handoff_path import latest_note
            note = latest_note(event["cwd"])
        except Exception:
            note = None
        if note:
            text += NOTE_MENTION.format(path=note)
    return text


def user_prompt_submit(event):
    from breaks import load_state, save_state, size_note
    from handoff_lib import load_config
    sid = event.get("session_id")
    if not sid:
        return None
    cfg = load_config()
    state = load_state(sid)
    window = state.get("context_window") or cfg["default_context_window"]
    text = size_note(cfg, _size(event), window, state)
    save_state(sid, state)
    return text


def post_tool_use(event):
    from breaks import break_nudge, detect_break, load_state, save_state
    from handoff_lib import load_config
    kind = detect_break(event)
    sid = event.get("session_id")
    if not kind or not sid:
        return None
    cfg = load_config()
    state = load_state(sid)
    text = break_nudge(cfg, _size(event), state, kind, str(event.get("tool_use_id") or ""))
    if text:
        save_state(sid, state)
    return text


HANDLERS = {"SessionStart": session_start, "UserPromptSubmit": user_prompt_submit, "PostToolUse": post_tool_use}


def dispatch(raw: str) -> str | None:
    event = json.loads(raw)
    if not isinstance(event, dict):
        return None
    name = event.get("hook_event_name")
    handler = HANDLERS.get(name)
    text = handler(event) if handler else None
    if not text:
        return None
    return json.dumps({"hookSpecificOutput": {"hookEventName": name, "additionalContext": text}})


def main() -> int:
    try:
        out = dispatch(sys.stdin.read())
        if out:
            sys.stdout.write(out + "\n")
    except Exception as exc:
        try:
            from handoff_lib import log_error
            log_error("handoff_hook", exc)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
