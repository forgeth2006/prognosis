import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parse_bump import classify_files, extract_links, normalize_name, parse_title, version_delta  # noqa: E402


class TitleTests(unittest.TestCase):
    def test_simple(self):
        t = parse_title("Bump requests from 2.31.0 to 2.32.0")
        self.assertEqual((t["package"], t["old_version"], t["new_version"]), ("requests", "2.31.0", "2.32.0"))
        self.assertTrue(t["title_parsed"])
        self.assertFalse(t["is_grouped"])

    def test_prefix_and_directory_suffix(self):
        t = parse_title("build(deps): bump Pillow from 9.0.0 to 10.0.0 in /requirements")
        self.assertEqual((t["package"], t["package_norm"], t["new_version"]), ("Pillow", "pillow", "10.0.0"))

    def test_grouped_variants(self):
        for title in ["Bump the pip group with 3 updates",
                      "Bump the pip group across 1 directory with 2 updates",
                      "Bump black and flake8",
                      "Bump a, b and c"]:
            self.assertTrue(parse_title(title)["is_grouped"], title)
            self.assertFalse(parse_title(title)["title_parsed"], title)

    def test_range_update(self):
        t = parse_title("Update pytest requirement from <8,>=7 to >=7,<9")
        self.assertTrue(t["is_range_update"])
        self.assertEqual((t["package"], t["old_version"], t["new_version"]), ("pytest", "<8,>=7", ">=7,<9"))

    def test_unparseable(self):
        self.assertFalse(parse_title("Fix typo in README")["title_parsed"])

    def test_normalize(self):
        self.assertEqual(normalize_name("Typing_Extensions"), "typing-extensions")
        self.assertEqual(normalize_name("zope.interface"), "zope-interface")


class VersionTests(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(version_delta("2.31.0", "2.32.0")["bump_type"], "minor")
        self.assertEqual(version_delta("2.31.0", "3.0.0")["bump_type"], "major")
        self.assertEqual(version_delta("1.26.0", "1.26.4")["bump_type"], "patch")
        self.assertEqual(version_delta("3.1", "3.1.1")["bump_type"], "patch")
        self.assertEqual(version_delta("2.0.0", "1.9.0")["bump_type"], "downgrade")
        self.assertEqual(version_delta("abc", "1.0")["bump_type"], "unknown")

    def test_flags(self):
        self.assertTrue(version_delta("0.9.0", "0.10.0")["is_zero_major"])
        self.assertTrue(version_delta("1.0.0", "2.0.0rc1")["is_prerelease"])
        self.assertFalse(version_delta("1.0.0", "1.0.1")["is_prerelease"])
        self.assertEqual(version_delta("v1.2.3", "v1.2.4")["bump_type"], "patch")
        self.assertEqual(version_delta("1.2.3", "2.4.3")["major_delta"], 1)


class FileTests(unittest.TestCase):
    def test_pip_only(self):
        for files in (["requirements.txt"], ["requirements/test.txt", "requirements/dev.in"],
                      ["pyproject.toml", "uv.lock"], ["docs/requirements.txt"]):
            self.assertEqual(classify_files(files)["ecosystem"], "pip", files)

    def test_other_ecosystems_and_mixed(self):
        self.assertEqual(classify_files([".github/workflows/ci.yml"])["ecosystem"], "github-actions")
        self.assertEqual(classify_files(["package.json", "package-lock.json"])["ecosystem"], "npm")
        mixed = classify_files(["requirements.txt", ".github/workflows/ci.yml"])
        self.assertEqual(mixed["ecosystem"], "other")
        self.assertTrue(mixed["touches_ci_config"])
        self.assertEqual(mixed["n_non_dependency_files"], 1)


class LinkTests(unittest.TestCase):
    BODY = ('Bumps [requests](https://github.com/psf/requests) from 2.31.0 to 2.32.0.\n'
            '<details><summary>Release notes</summary><p><em>Sourced from <a href="https://github.com/psf/requests/releases">requests\'s releases</a>.</em></p></details>\n'
            '<details><summary>Changelog</summary><p><em>Sourced from <a href="https://github.com/psf/requests/blob/main/HISTORY.md">requests\'s changelog</a>.</em></p></details>\n'
            '<li><a href="https://github.com/psf/requests/compare/v2.31.0...v2.32.0">Compare view</a></li>')

    def test_links(self):
        l = extract_links(self.BODY)
        self.assertTrue(l["changelog_url"].endswith("HISTORY.md"))
        self.assertTrue(l["release_notes_url"].endswith("/releases"))
        self.assertIn("/compare/", l["compare_url"])
        self.assertEqual(l["source_repo_url"], "https://github.com/psf/requests")

    def test_empty(self):
        self.assertEqual(extract_links(None)["changelog_url"], "")


if __name__ == "__main__":
    unittest.main()
