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
        self.assertIn("/compact", text)
        self.assertIn("/handoff", text)

    def test_break_nudge_once_per_tool_use(self):
        state = {}
        self.assertIsNotNone(breaks.break_nudge(self.cfg, 300_000, state, "pr-merge", "t1"))
        self.assertIsNone(breaks.break_nudge(self.cfg, 300_000, state, "pr-merge", "t1"))

    @staticmethod
    def _kind(text):
        return None if text is None else "near" if "compaction is near" in text else "size"

    def test_near_full_once_per_crossing(self):
        state = {}
        # 820K is in the step 810K already announced (as near): silent. 300K is a lower step after a drop: silent too.
        seq = [(790_000, "size"), (810_000, "near"), (820_000, None), (300_000, None), (850_000, "near")]
        for size, want in seq:
            text = breaks.size_note(self.cfg, size, 1_000_000, state)
            self.assertEqual(self._kind(text), want, f"size {size}: {text}")
            if want == "near":
                self.assertIn("/compact", text)
                self.assertIn("/handoff", text)
        self.assertIsNone(breaks.size_note(self.cfg, 150_000, 1_000_000, state))

    def test_size_line_once_per_step(self):
        # floor 200K, step 100K: one line on crossing the floor, one per further 100K, none in between
        state = {}
        seq = [(199_999, None), (200_000, "size"), (210_000, None), (299_999, None), (300_000, "size"),
               (305_000, None), (520_000, "size"), (530_000, None)]
        for size, want in seq:
            text = breaks.size_note(self.cfg, size, 1_000_000, state)
            self.assertEqual(self._kind(text), want, f"size {size}: {text}")
        self.assertIn("520K", breaks.size_note(self.cfg, 520_000, 1_000_000, {}))

    def test_size_line_again_after_a_compaction(self):
        # below the floor forgets the steps: the next crossing is announced again
        state = {}
        self.assertEqual(self._kind(breaks.size_note(self.cfg, 450_000, 1_000_000, state)), "size")
        self.assertIsNone(breaks.size_note(self.cfg, 460_000, 1_000_000, state))
        self.assertIsNone(breaks.size_note(self.cfg, 70_000, 1_000_000, state))
        self.assertEqual(self._kind(breaks.size_note(self.cfg, 205_000, 1_000_000, state)), "size")

    def test_size_step_is_configurable_and_defaults_to_100k(self):
        cfg = dict(self.cfg)
        cfg.pop("size_step_tokens", None)
        state = {}
        self.assertEqual(self._kind(breaks.size_note(cfg, 200_000, 1_000_000, state)), "size")
        self.assertIsNone(breaks.size_note(cfg, 299_999, 1_000_000, state))
        cfg["size_step_tokens"] = 50_000
        state = {}
        self.assertEqual(self._kind(breaks.size_note(cfg, 200_000, 1_000_000, state)), "size")
        self.assertEqual(self._kind(breaks.size_note(cfg, 250_000, 1_000_000, state)), "size")


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
