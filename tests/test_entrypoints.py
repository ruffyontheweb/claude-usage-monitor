import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import REPO, entry

sys.path.insert(0, str(REPO / "lib"))
import handoff_lib  # noqa: E402

FLOOR = handoff_lib.load_config()["floor_tokens"]  # the scripts read the live config

HOOK = REPO / "bin" / "handoff_hook.py"
STATUS = REPO / "bin" / "statusline.py"


class EntryPoints(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = dict(os.environ, HOME=str(self.home))

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, script, stdin):
        return subprocess.run(["python3", "-I", str(script)], input=stdin, capture_output=True,
                              text=True, env=self.env, timeout=10)

    def transcript(self, size):
        p = self.home / "t.jsonl"
        p.write_text(entry(size, "m1") + "\n")
        return str(p)

    def test_hook_session_start_text(self):
        ev = {"hook_event_name": "SessionStart", "source": "startup", "session_id": "s1",
              "transcript_path": str(self.home / "none.jsonl"), "cwd": str(self.home)}
        r = self.run_script(HOOK, json.dumps(ev))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        self.assertTrue(out["additionalContext"].startswith("Session handoff convention"))
        self.assertIn("/compact", out["additionalContext"])
        self.assertIn("/handoff", out["additionalContext"])

    def test_hook_post_tool_use_nudge(self):
        ev = {"hook_event_name": "PostToolUse", "session_id": "s1", "transcript_path": self.transcript(FLOOR + 50_000),
              "cwd": str(self.home), "tool_name": "Bash", "tool_input": {"command": "gh pr merge 3 --squash"},
              "tool_use_id": "toolu_1"}
        r = self.run_script(HOOK, json.dumps(ev))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PostToolUse")
        self.assertIn("pr-merge", out["additionalContext"])

    def test_hook_bad_input(self):
        missing = {"hook_event_name": "PostToolUse", "session_id": "s1", "cwd": "/",
                   "transcript_path": str(self.home / "deleted.jsonl"), "tool_name": "Bash",
                   "tool_input": {"command": "gh pr merge 3"}, "tool_use_id": "toolu_2"}
        for stdin in ["{}", "not json", json.dumps(missing)]:
            with self.subTest(stdin=stdin[:20]):
                r = self.run_script(HOOK, stdin)
                self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_statusline_line(self):
        payload = {"session_id": "s1", "transcript_path": str(self.home / "none.jsonl"), "version": "2.1.318",
                   "model": {"id": "claude-unmeasured-0", "display_name": "Unmeasured"},
                   "context_window": {"context_window_size": 1_000_000,
                                      "current_usage": {"input_tokens": 400, "cache_creation_input_tokens": 2000,
                                                        "cache_read_input_tokens": 310_000, "output_tokens": 99}}}
        r = self.run_script(STATUS, json.dumps(payload))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "ctx 312K/1.0M · handoff at next break · floor unverified")
        state = json.loads((self.home / ".cache/claude-handoff/s1.json").read_text())
        self.assertEqual((state["context_window"], state["model_id"]), (1_000_000, "claude-unmeasured-0"))

    def test_statusline_leaves_unchanged_state_alone(self):
        state_file = self.home / ".cache/claude-handoff/s1.json"
        state_file.parent.mkdir(parents=True)
        state_file.write_text(json.dumps({"context_window": 1_000_000, "model_id": "claude-fable-5-1",
                                          "near_full_fired": True}))
        before = state_file.stat()
        payload = {"session_id": "s1", "version": "2.1.318", "model": {"id": "claude-fable-5-1"},
                   "context_window": {"context_window_size": 1_000_000,
                                      "current_usage": {"input_tokens": 1, "cache_creation_input_tokens": 0,
                                                        "cache_read_input_tokens": 850_000}}}
        r = self.run_script(STATUS, json.dumps(payload))
        self.assertTrue(r.stdout.startswith("ctx 850K/1.0M"), r.stdout)
        after = state_file.stat()
        self.assertEqual((after.st_ino, after.st_mtime_ns), (before.st_ino, before.st_mtime_ns),
                         "status line rewrote a state file it had nothing to change in")

    def test_statusline_null_usage_falls_back(self):
        payload = {"session_id": "s1", "transcript_path": self.transcript(5000), "version": "2.1.318",
                   "model": {"id": "claude-fable-5-1"},
                   "context_window": {"context_window_size": 200_000, "current_usage": None}}
        r = self.run_script(STATUS, json.dumps(payload))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("ctx 5K"), r.stdout)


if __name__ == "__main__":
    unittest.main()
