import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from helpers import REPO

sys.path.insert(0, str(REPO / "bin"))
import handoff_path as hp  # noqa: E402

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "init.defaultBranch=main"]


def git(cwd, *args):
    return subprocess.run(GIT + list(args), cwd=cwd, check=True, capture_output=True, text=True).stdout


class NotePaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.main = self.root / "main"
        self.main.mkdir()
        git(self.main, "init", "-q")
        git(self.main, "commit", "-q", "--allow-empty", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def test_note_dir_from_worktree(self):
        wt = self.root / "wt"
        git(self.main, "worktree", "add", "-q", "-b", "feat/x", str(wt))
        self.assertEqual(hp.note_dir(str(wt)), self.main / ".claude" / "handoffs")
        self.assertEqual(hp.branch_slug(str(wt)), "feat-x")

    def test_branch_slug_detached(self):
        git(self.main, "checkout", "-q", "--detach")
        self.assertRegex(hp.branch_slug(str(self.main)), r"^detached-[0-9a-f]{7}$")

    def test_ensure_excluded_idempotent(self):
        hp.ensure_excluded(str(self.main))
        hp.ensure_excluded(str(self.main))
        lines = (self.main / ".git" / "info" / "exclude").read_text().splitlines()
        self.assertEqual(lines.count(".claude/handoffs/"), 1)
        note = hp.new_note_path(str(self.main), "Some Topic!", datetime(2026, 11, 5, 1, 51))
        self.assertEqual(note.name, "2026-11-05-0151-main-some-topic.md")
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("x")
        self.assertEqual(git(self.main, "status", "--short"), "")

    def test_latest_note_branch_scoped(self):
        d = self.main / ".claude" / "handoffs"
        d.mkdir(parents=True)
        (d / "2026-11-05-0900-feat-b-older.md").write_text("b")
        (d / "2026-11-05-1000-feat-a-newer.md").write_text("a")
        git(self.main, "checkout", "-q", "-b", "feat/b")
        self.assertEqual(hp.latest_note(str(self.main)), d / "2026-11-05-0900-feat-b-older.md")
        git(self.main, "checkout", "-q", "-b", "feat/c")
        self.assertIsNone(hp.latest_note(str(self.main)))

    def test_outside_git(self):
        plain = self.root / "plain"
        plain.mkdir()
        self.assertIsNone(hp.main_checkout(str(plain)))
        self.assertEqual(hp.note_dir(str(plain)), plain / ".claude" / "handoffs")


if __name__ == "__main__":
    unittest.main()
