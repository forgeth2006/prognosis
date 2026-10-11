import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from import_graph import analyze, dist_name  # noqa: E402

FILES = {
    "src/app/__init__.py": "from . import core\n",
    "src/app/core.py": "import requests\nfrom app import util\n",
    "src/app/util.py": "import yaml\nimport os\ntry:\n    import numpy\nexcept ImportError:\n    numpy = None\n",
    "src/app/cli.py": "from .core import run\nimport click\n",
    "src/app/broken.py": "def (:\n",
    "tests/test_core.py": "import pytest\nimport requests\nfrom app import core\n",
    "tests/conftest.py": "import pytest\n",
}


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        for rel, text in FILES.items():
            p = Path(self.tmp.name) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        self.rows = {r["package"]: r for r in analyze(self.tmp.name, "demo")}

    def tearDown(self):
        self.tmp.cleanup()

    def test_packages_found_stdlib_and_internal_excluded(self):
        self.assertEqual(set(self.rows), {"requests", "pyyaml", "numpy", "click", "pytest"})

    def test_direct_blast_radius_and_roles(self):
        r = self.rows["requests"]
        self.assertEqual((r["blast_direct"], r["blast_direct_src"], r["blast_direct_tests"]), (2, 1, 1))
        self.assertEqual(self.rows["pytest"]["blast_direct_src"], 0)

    def test_transitive_blast_radius(self):
        # core.py imports requests; util.py is imported BY core, so util does not reach requests,
        # while __init__, cli and test_core reach it through core.py
        r = self.rows["requests"]
        self.assertEqual(r["blast_transitive"], 4)  # core, __init__, cli, test_core
        # yaml is imported by util; core, __init__, cli and test_core all reach util
        self.assertEqual(self.rows["pyyaml"]["blast_transitive"], 5)

    def test_depth(self):
        self.assertEqual(self.rows["click"]["depth_min"], 0)   # cli.py is an entry point
        self.assertLessEqual(self.rows["numpy"]["depth_min"], 2)

    def test_parse_failure_counted_and_alias_mapping(self):
        self.assertEqual(self.rows["requests"]["repo_parse_failures"], 1)
        self.assertEqual(dist_name("yaml"), "pyyaml")
        self.assertEqual(dist_name("PIL"), "pillow")
        self.assertEqual(dist_name("pytest_asyncio"), "pytest-asyncio")


if __name__ == "__main__":
    unittest.main()
