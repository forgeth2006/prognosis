import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from snapshots import read_py_sources, sha_before, snapshot_rows  # noqa: E402


def git(cwd, *args, date=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        d = Path(self.tmp.name)
        git(d, "init", "-q", "-b", "main")
        (d / "app").mkdir()
        (d / "app" / "__init__.py").write_text("")
        (d / "app" / "core.py").write_text("import requests\n")
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "v1", date="2026-01-10T12:00:00+00:00")
        (d / "app" / "util.py").write_text("import yaml\nimport requests\n")
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "v2", date="2026-03-10T12:00:00+00:00")
        git(d, "branch", "snapshot-head")
        self.gitdir = d / ".git"

    def tearDown(self):
        self.tmp.cleanup()

    def test_sha_is_last_commit_strictly_before_month_start(self):
        self.assertEqual(sha_before(self.gitdir, "2025-12"), "")                  # repo did not exist yet
        feb, mar, apr = (sha_before(self.gitdir, m) for m in ("2026-02", "2026-03", "2026-04"))
        self.assertEqual(feb, mar)                                                   # nothing between Jan 10 and Mar 10
        self.assertNotEqual(mar, apr)                                                # Mar 10 commit visible from April

    def test_snapshot_sees_only_older_code(self):
        _, march = snapshot_rows(self.gitdir, "o/r", "2026-03", {})
        _, april = snapshot_rows(self.gitdir, "o/r", "2026-04", {})
        self.assertEqual({r["package_norm"] for r in march}, {"requests"})
        self.assertEqual({r["package_norm"] for r in april}, {"requests", "pyyaml"})
        self.assertEqual({r["package_norm"]: r["blast_direct"] for r in april}["requests"], 2)

    def test_missing_snapshot_and_cache(self):
        idx, rows = snapshot_rows(self.gitdir, "o/r", "2025-12", {})
        self.assertFalse(idx["snapshot_exists"])
        self.assertEqual(rows, [])
        cache = {}
        snapshot_rows(self.gitdir, "o/r", "2026-02", cache)
        snapshot_rows(self.gitdir, "o/r", "2026-03", cache)
        self.assertEqual(len(cache), 1)  # same commit analysed once

    def test_read_sources(self):
        src = read_py_sources(self.gitdir, sha_before(self.gitdir, "2026-04"))
        self.assertEqual(set(src), {"app/__init__.py", "app/core.py", "app/util.py"})
        self.assertIn("import yaml", src["app/util.py"])


if __name__ == "__main__":
    unittest.main()
