"""Shared pieces of the session-handoff tool: config, conversation size, floor basis, formatting, error log."""
import json
import os
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO / "config" / "handoff.json"
STATE_DIR = Path.home() / ".cache" / "claude-handoff"

TAIL_BYTES = 1_048_576


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path) as f:
        return json.load(f)


def usage_size(usage: dict) -> int:
    """Context size of one request: input + cache creation + cache read."""
    return (int(usage.get("input_tokens") or 0)
            + int(usage.get("cache_creation_input_tokens") or 0)
            + int(usage.get("cache_read_input_tokens") or 0))


def context_size(transcript_path: str, tail_bytes: int = TAIL_BYTES) -> int | None:
    """Size of the latest main-session assistant request, read from the last `tail_bytes` of the transcript."""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            start = max(0, end - tail_bytes)
            f.seek(start)
            data = f.read()
    except OSError:
        return None
    lines = data.split(b"\n")
    if start > 0:
        lines = lines[1:]  # the first line is cut by the seek
    for raw in reversed(lines):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            continue  # a half-written last line, or garbage
        if not isinstance(obj, dict) or obj.get("type") != "assistant" or obj.get("isSidechain") is True:
            continue
        msg = obj.get("message")
        usage = msg.get("usage") if isinstance(msg, dict) else None
        if isinstance(usage, dict):
            return usage_size(usage)
    return None


def _minor(version: str | None) -> str | None:
    if not version:
        return None
    parts = str(version).split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else parts[0]


def basis_status(config: dict, model_id: str | None, version: str | None) -> str:
    measured = config.get("measured_on", {})
    if not model_id or model_id not in measured.get("models", []):
        return "unverified-model"
    if _minor(version) not in measured.get("claude_code_versions", []):
        return "unverified-version"
    return "verified"


def fmt_tokens(n: int) -> str:
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{round(n / 1000)}K"
    return f"{n / 1_000_000:.1f}M"


def log_error(where: str, exc: BaseException) -> None:
    """Append one line to the error log. Never raises."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tb = traceback.extract_tb(exc.__traceback__)
        loc = f"{Path(tb[-1].filename).name}:{tb[-1].lineno}" if tb else "?"
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {where} {type(exc).__name__} at {loc}: {exc}".replace("\n", " ")
        with open(STATE_DIR / "errors.log", "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
