import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts lib/ on sys.path)
import breaks
import handoff_lib as hl


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


class DetectBreak(unittest.TestCase):
    def test_detect_break(self):
        self.assertEqual(breaks.detect_break(bash("gh pr create --fill")), "pr-create")
        self.assertEqual(breaks.detect_break(bash("cd x && gh pr merge 9 --squash")), "pr-merge")
        self.assertEqual(breaks.detect_break(bash("echo gh pr create")), "pr-create")
        self.assertIsNone(breaks.detect_break(bash("gh pr view 3")))
        self.assertEqual(breaks.detect_break(
            {"tool_name": "mcp__plugin_github_github__merge_pull_request", "tool_input": {}}), "pr-merge")
        self.assertIsNone(breaks.detect_break({"tool_name": "Read", "tool_input": {"file_path": "x"}}))


class Nudges(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(hl.load_config(), floor_tokens=200_000)  # pinned: tests the logic, not the live setting

    def test_break_nudge_floor(self):
        self.assertIsNone(breaks.break_nudge(self.cfg, 199_999, {}, "pr-create", "t1"))
        text = breaks.break_nudge(self.cfg, 200_000, {}, "pr-create", "t2")
        self.assertIsNotNone(text, "200_000 is at the floor and must nudge")
        self.assertIn("200K", text)
        self.assertIn("pr-create", text)

    def test_break_nudge_once_per_tool_use(self):
        state = {}
        self.assertIsNotNone(breaks.break_nudge(self.cfg, 300_000, state, "pr-merge", "t1"))
        self.assertIsNone(breaks.break_nudge(self.cfg, 300_000, state, "pr-merge", "t1"))

    def test_near_full_once_per_crossing(self):
        state = {}
        seq = [(790_000, "size"), (810_000, "near"), (820_000, "size"), (300_000, "size"), (850_000, "near")]
        for size, want in seq:
            text = breaks.size_note(self.cfg, size, 1_000_000, state)
            kind = "near" if "compaction is near" in text else "size"
            self.assertEqual(kind, want, f"size {size}: {text}")
        self.assertIsNone(breaks.size_note(self.cfg, 150_000, 1_000_000, state))


class State(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = breaks.STATE_DIR
        breaks.STATE_DIR = Path(self.tmp.name) / "state"

    def tearDown(self):
        breaks.STATE_DIR = self.orig
        self.tmp.cleanup()

    def test_state_atomic(self):
        breaks.save_state("sess-a", {"who": "a"})
        breaks.save_state("sess-b", {"who": "b"})
        self.assertEqual(breaks.load_state("sess-a"), {"who": "a"})
        self.assertEqual(breaks.load_state("sess-b"), {"who": "b"})
        self.assertEqual(list(breaks.STATE_DIR.glob("*.tmp")), [])
        self.assertEqual(breaks.load_state("sess-none"), {})


if __name__ == "__main__":
    unittest.main()
