import os
import tempfile
import time
import unittest
from pathlib import Path

from helpers import FIXTURES, entry

import handoff_lib as hl


class ContextSize(unittest.TestCase):
    def test_context_size_last_main_entry(self):
        self.assertEqual(hl.context_size(str(FIXTURES / "main_entries.jsonl")), 5000)

    def test_context_size_dedupes_by_message_id(self):
        self.assertEqual(hl.context_size(str(FIXTURES / "dup_ids.jsonl")), 3000)

    def test_context_size_truncated_last_line(self):
        self.assertEqual(hl.context_size(str(FIXTURES / "truncated.jsonl")), 4000)

    def test_context_size_missing_file(self):
        self.assertIsNone(hl.context_size(str(FIXTURES / "no-such-file.jsonl")))


class TailOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "big.jsonl"
        line = entry(1234, "old") + "\n"
        with open(self.path, "w") as f:
            f.write(line * (50_000_000 // len(line) + 1))
            f.write(entry(77_000, "last") + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_context_size_tail_only(self):
        self.assertGreater(os.path.getsize(self.path), 50_000_000)
        t0 = time.perf_counter()
        size = hl.context_size(str(self.path))
        elapsed = time.perf_counter() - t0
        self.assertEqual(size, 77_000)
        self.assertLess(elapsed, 0.2)


class Basis(unittest.TestCase):
    def test_basis_status(self):
        cfg = hl.load_config()
        self.assertEqual(hl.basis_status(cfg, "claude-fable-5-1", "2.1.318"), "verified")
        self.assertEqual(hl.basis_status(cfg, "claude-opus-5-5", "2.1.318"), "unverified-model")
        self.assertEqual(hl.basis_status(cfg, "claude-fable-5-1", "2.2.0"), "unverified-version")
        self.assertEqual(hl.basis_status(cfg, None, None), "unverified-model")


class Fmt(unittest.TestCase):
    def test_fmt_tokens(self):
        self.assertEqual(hl.fmt_tokens(999), "999")
        self.assertEqual(hl.fmt_tokens(5000), "5K")
        self.assertEqual(hl.fmt_tokens(312_400), "312K")
        self.assertEqual(hl.fmt_tokens(1_000_000), "1.0M")


if __name__ == "__main__":
    unittest.main()
