"""Shared builders for synthetic transcript fixtures."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"
sys.path.insert(0, str(REPO / "lib"))


def entry(size, mid, sidechain=False, kind="assistant", model="claude-fable-5-1", version="2.1.318"):
    """One transcript line whose context size (input + cache creation + cache read) is `size`."""
    return json.dumps({
        "type": kind, "isSidechain": sidechain, "version": version, "sessionId": "s-test",
        "message": {"id": mid, "model": model, "role": kind,
                    "usage": {"input_tokens": 1, "cache_creation_input_tokens": 9,
                              "cache_read_input_tokens": size - 10, "output_tokens": 50}},
    })
