import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import REPO

INSTALL = REPO / "bin" / "install.py"
UNINSTALL = REPO / "bin" / "uninstall.py"
MARK = "claude-usage-monitor/bin/"

HERDR = {"matcher": "^(startup|resume|clear|compact|fork)$",
         "hooks": [{"type": "command", "command": "bash '/home/x/.claude/hooks/herdr-agent-state.sh' session",
                    "timeout": 10}]}
ORIGINAL = {"env": {"CLAUDE_CODE_ENABLE_TELEMETRY": "1", "OTEL_METRICS_EXPORTER": "otlp"},
            "hooks": {"SessionStart": [HERDR]}, "tui": {"x": 1}, "model": "opus"}


def ours(handlers):
    return [h for group in handlers for h in group.get("hooks", []) if MARK in h.get("command", "")]


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / ".claude").mkdir()
        self.settings = self.home / ".claude" / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        self.settings.write_text(data if isinstance(data, str) else json.dumps(data, indent=2))

    def run_script(self, script):
        return subprocess.run(["python3", "-I", str(script), "--home", str(self.home)],
                              capture_output=True, text=True, timeout=10)

    def load(self):
        return json.loads(self.settings.read_text())

    def backups(self):
        return list((self.home / ".claude").glob("settings.json.bak-*"))

    def test_install_keeps_existing(self):
        self.write(ORIGINAL)
        r = self.run_script(INSTALL)
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.load()
        for key in ("env", "tui", "model"):
            self.assertEqual(s[key], ORIGINAL[key])
        self.assertIn(HERDR, s["hooks"]["SessionStart"])
        for event in ("SessionStart", "UserPromptSubmit", "PostToolUse"):
            mine = ours(s["hooks"][event])
            self.assertEqual(len(mine), 1, event)
            self.assertEqual(mine[0]["timeout"], 5)
        self.assertIn(MARK + "statusline.py", s["statusLine"]["command"])
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(json.loads(self.backups()[0].read_text()), ORIGINAL)
        link = self.home / ".claude" / "skills" / "handoff"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (REPO / "skills" / "handoff").resolve())

    def test_install_idempotent(self):
        self.write(ORIGINAL)
        self.run_script(INSTALL)
        r = self.run_script(INSTALL)
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.load()
        for event in ("SessionStart", "UserPromptSubmit", "PostToolUse"):
            self.assertEqual(len(ours(s["hooks"][event])), 1, event)

    def test_uninstall_restores(self):
        self.write(ORIGINAL)
        self.run_script(INSTALL)
        r = self.run_script(UNINSTALL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.load(), ORIGINAL)
        self.assertFalse((self.home / ".claude" / "skills" / "handoff").exists())

    def test_refuse_bad_settings(self):
        self.write("{not json")
        before = self.settings.read_bytes()
        r = self.run_script(INSTALL)
        self.assertEqual(r.returncode, 2)
        self.assertIn("not valid JSON", r.stderr)
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertEqual(self.backups(), [])

        self.settings.unlink()
        r = self.run_script(INSTALL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(set(self.load()), {"statusLine", "hooks"})

        self.write("")
        r = self.run_script(INSTALL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(set(self.load()), {"statusLine", "hooks"})

    def test_refuse_foreign_statusline(self):
        self.write(dict(ORIGINAL, statusLine={"type": "command", "command": "foo.sh"}))
        before = self.settings.read_bytes()
        r = self.run_script(INSTALL)
        self.assertEqual(r.returncode, 2)
        self.assertIn("statusLine", r.stderr)
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertFalse((self.home / ".claude" / "skills" / "handoff").exists())


if __name__ == "__main__":
    unittest.main()
