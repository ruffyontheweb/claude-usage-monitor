import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import REPO, entry

sys.path.insert(0, str(REPO / "bin"))
import remeasure  # noqa: E402

# Pooled shares of tokens from requests >= 100K, 150K, 200K, 300K: 0.95, 0.90, 0.85, 0.60 (total 6.0M).
MODEL_A = [50_000] * 6 + [100_000] * 3 + [150_000] * 2
MODEL_B = [250_000] * 6 + [400_000] * 9


class Remeasure(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.projects = Path(self.tmp.name) / "projects"
        proj = self.projects / "-home-x-proj"
        proj.mkdir(parents=True)
        lines = [entry(s, f"a{i}", model="claude-fable-5-1") for i, s in enumerate(MODEL_A)]
        lines.append(entry(150_000, "a0", model="claude-fable-5-1"))          # duplicate id: counted once
        lines.append(entry(900_000, "side", sidechain=True))                   # sidechain: ignored
        lines.append(json.dumps({"type": "system", "subtype": "compact_boundary"}))
        (proj / "s1.jsonl").write_text("\n".join(lines) + "\n")
        (proj / "s2.jsonl").write_text("\n".join(
            entry(s, f"b{i}", model="claude-opus-5-5", version="2.2.1") for i, s in enumerate(MODEL_B)) + "\n")
        old = proj / "old.jsonl"
        old.write_text(entry(5_000_000, "old") + "\n")                       # outside --days: ignored
        t = time.time() - 30 * 86400
        os.utime(old, (t, t))

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = remeasure.main(["--days", "14", "--projects-dir", str(self.projects)])
        return rc, buf.getvalue()

    def test_suggested_floor(self):
        report = remeasure.analyse(self.projects, days=14)
        self.assertEqual(report["models"]["claude-fable-5-1"]["requests"], 11)
        self.assertEqual(report["models"]["claude-fable-5-1"]["compactions"], 1)
        self.assertEqual(report["models"]["claude-opus-5-5"]["versions"], ["2.2.1"])
        shares = report["pooled_share_above"]
        self.assertEqual([round(shares[t], 2) for t in remeasure.CANDIDATES], [0.95, 0.90, 0.85, 0.60])
        self.assertEqual(report["suggested_floor"], 200_000)
        rc, out = self.run_main()
        self.assertEqual(rc, 0)
        self.assertIn("suggested floor: 200K", out)
        self.assertEqual(out.strip().splitlines()[-1], "config not changed; edit config/handoff.json to apply")

    def test_read_only(self):
        before = os.stat(remeasure.CONFIG_PATH).st_mtime_ns
        self.run_main()
        self.assertEqual(os.stat(remeasure.CONFIG_PATH).st_mtime_ns, before)


if __name__ == "__main__":
    unittest.main()
