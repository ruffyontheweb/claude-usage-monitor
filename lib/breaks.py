"""Natural-break detection, handoff nudges, and per-session state."""
import json
import os
import re
import tempfile
from pathlib import Path

from handoff_lib import STATE_DIR, fmt_tokens

BASH_BREAK = re.compile(r"\bgh\s+pr\s+(create|merge)\b")
MCP_BREAK = re.compile(r"^mcp__.*github.*__(create_pull_request|merge_pull_request)$")

BREAK_TEXT = ("[handoff] Natural break ({kind}) and the conversation is {size} tokens, above the {floor} floor. "
              "Finish this reply, then in one line suggest /compact if the next work continues this thread, or /handoff "
              "if it is a new task; start nothing new until the user answers.")
SIZE_TEXT = "[handoff] Conversation is {size} tokens, above the {floor} floor."
NEAR_FULL_TEXT = ("[handoff] Conversation is {size} of a {window} window; compaction is near. "
                  "At your next stopping point, suggest in one line /compact (with what to keep) to continue, or /handoff "
                  "if the next work is a new task. Do not stop mid-task.")


DEFAULT_SIZE_STEP = 100_000   # tokens between two size lines above the floor, when the config names none


def detect_break(event: dict) -> str | None:
    tool = event.get("tool_name") or ""
    if tool == "Bash":
        cmd = (event.get("tool_input") or {}).get("command") or ""
        m = BASH_BREAK.search(cmd)
        return f"pr-{m.group(1)}" if m else None
    m = MCP_BREAK.match(tool)
    if m:
        return "pr-create" if m.group(1) == "create_pull_request" else "pr-merge"
    return None


def _state_path(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id) or "unknown"
    return STATE_DIR / f"{safe}.json"


def load_state(session_id: str) -> dict:
    try:
        with open(_state_path(session_id)) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(session_id: str, state: dict) -> None:
    """Write atomically: temp file in the same directory, then os.replace."""
    path = _state_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def break_nudge(config: dict, size: int | None, state: dict, kind: str, tool_use_id: str) -> str | None:
    floor = config["floor_tokens"]
    if size is None or size < floor:
        return None
    seen = state.setdefault("nudged_tool_uses", [])
    if tool_use_id in seen:
        return None
    seen.append(tool_use_id)
    del seen[:-50]
    return BREAK_TEXT.format(kind=kind, size=fmt_tokens(size), floor=fmt_tokens(floor))


def size_note(config: dict, size: int | None, window: int, state: dict) -> str | None:
    """The line a prompt gets about the conversation's size, or None.

    Above the floor the size is said once per step: on crossing the floor, then each time it has grown by another
    `size_step_tokens` (default 100K). Every prompt used to carry the line; in a long session that was the same fact
    a hundred times. Below the floor the steps are forgotten, so the crossing after a compaction is said again. The
    near-full line keeps its own once-per-crossing rule and counts as the line of its step.
    """
    if size is None:
        return None
    floor = config["floor_tokens"]
    step = max(1, int(config.get("size_step_tokens") or DEFAULT_SIZE_STEP))
    if size < floor:
        state["size_level"] = -1
        level = -1
    else:
        level = (size - floor) // step
    new_step = level > state.get("size_level", -1)
    if new_step:
        state["size_level"] = level
    if size >= window * config["near_full_fraction"]:
        if not state.get("near_full_fired"):
            state["near_full_fired"] = True
            return NEAR_FULL_TEXT.format(size=fmt_tokens(size), window=fmt_tokens(window))
    else:
        state["near_full_fired"] = False
    if new_step:
        return SIZE_TEXT.format(size=fmt_tokens(size), floor=fmt_tokens(floor))
    return None
