# Repository selection and changelog features

*Author: Esther (Person A). Covers how the repositories were chosen and how the changelog features were built. Labels, graph features and the dataset checks are described in the data methodology section.*

## 1. Choosing the repositories

No ready-made dataset of dependency-update pull requests and their CI outcomes exists, so we built one from public GitHub repositories. We wrote a script that checked 86 candidate Python repositories automatically against four rules:

1. Dependabot opens pip (Python package) update pull requests.
2. About 100 or more single-package update pull requests, enough to learn from. This count is estimated from a sample, so some repositories turned out to be borderline once the full data was pulled.
3. Tests run on pull requests through GitHub Actions, so each update has a pass/fail result.
4. At least one Dependabot pull request in the last 180 days, so the project is still active.

17 repositories passed all four rules. We chose automatic checks over hand-picking so the selection is repeatable and not based on our own guesses about which projects would be interesting.

**Limits.** Seventeen repositories is a small sample of the Python ecosystem, and breakage rates differ a lot between them (from 0% to about 33%). Results should therefore be read as indicative for projects like these, not for all software projects.

## 2. Changelog features

The idea is simple: an update with long release notes, or notes that mention breaking changes, may be riskier than one with short or no notes. For each unique update (package, old version, new version) we tried to find the release notes and turn them into a few numbers.

**Where we look, in order:**
1. The package's PyPI page, which often links to a changelog or the project repository.
2. A changelog file in the project repository (for example `CHANGELOG`, `CHANGES`, `HISTORY`, `NEWS`, or a `docs/changelog` file).
3. As a last resort, the project's documentation page. Text from a documentation page is accepted only if it looks like real release notes (several lines and enough text), because menus and version lists on those pages can look like changelogs.

**How we cut out the right part.** We find the heading for the new version and the heading for the old version, and keep the text between them. When a page lists versions in a menu as well as in the notes, we pick the heading pair that has the notes between them. The scraper waits one second between requests and caches every download, so reruns are fast and polite to the servers.

**Features produced** (one row per update): where the notes came from (`source_type`), the release date of the new version, whether a changelog was found (`changelog_found`), its length in characters and lines (`changelog_chars`, `changelog_lines`), and whether it contains a breaking-change keyword (`has_breaking_keyword`).

**Coverage.** Across 1,096 unique updates, changelog text was found for 61%. A first version found only 25% on a test sample, mostly because it rejected valid sections and missed some filenames; fixing the heading matching and adding filenames raised it to 61%. Of the misses, about half (220 updates) are packages that publish no downloadable changelog at all, which no scraper can fix. After joining to the labeled table, 64% of the 1,314 labeled pull requests have changelog features.

**How "missing" is treated.** A missing changelog is kept as its own signal (`changelog_found = 0`) and is not filled in with a guess. In the frozen dataset, pull requests without changelog information had a slightly higher observed breakage rate (11.8%) than those with it (8.7%). This is only a descriptive pattern and may reflect which packages publish notes rather than anything about risk.

**Limits.**
- Changelog length is a rough proxy. Short notes can describe a big change and long notes a trivial one.
- The breaking-change keyword check is a simple text search and can be wrong in both directions.
- The changelog scraper is not part of the live scoring pipeline. For new pull requests the changelog features are marked "not scraped", which is acceptable because 36% of the training rows had none either.
