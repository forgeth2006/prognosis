import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from github_client import GitHubClient, GitHubError  # noqa: E402


class Resp:
    def __init__(self, status=200, data=None, headers=None, links=None, text=""):
        self.status_code, self._data, self.headers = status, data, headers or {}
        self.links, self.text = links or {}, text

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append((url, params))
        return self.responses.pop(0)


def client(responses, **kw):
    sleeps = []
    c = GitHubClient(token="t", session=FakeSession(responses), sleep=sleeps.append, now=lambda: 1000.0,
                     log=lambda *_: None, min_interval=0, **kw)
    return c, sleeps


class ClientTests(unittest.TestCase):
    def test_pagination_follows_next_and_respects_max(self):
        c, _ = client([Resp(data=[1, 2], links={"next": {"url": "https://api.github.com/p2"}}),
                       Resp(data=[3, 4])])
        self.assertEqual(list(c.paginate("/x")), [1, 2, 3, 4])
        c2, _ = client([Resp(data=[1, 2], links={"next": {"url": "https://api.github.com/p2"}})])
        self.assertEqual(list(c2.paginate("/x", max_items=2)), [1, 2])

    def test_item_key(self):
        c, _ = client([Resp(data={"total_count": 1, "workflow_runs": [{"id": 1}]})])
        self.assertEqual(list(c.paginate("/runs", item_key="workflow_runs")), [{"id": 1}])

    def test_primary_rate_limit_sleeps_until_reset_then_retries(self):
        limited = Resp(403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1100"}, text="rate limit")
        c, sleeps = client([limited, Resp(data={"ok": 1})])
        self.assertEqual(c.get("/x"), {"ok": 1})
        self.assertEqual(sleeps, [102])  # reset(1100) - now(1000) + 2

    def test_secondary_limit_and_retry_after(self):
        c, sleeps = client([Resp(403, text="You have exceeded a secondary rate limit"), Resp(data=1)])
        self.assertEqual(c.get("/x"), 1)
        self.assertEqual(sleeps, [60])
        c, sleeps = client([Resp(429, headers={"Retry-After": "5"}), Resp(data=2)])
        self.assertEqual(c.get("/x"), 2)
        self.assertEqual(sleeps, [6])

    def test_real_403_raises(self):
        c, _ = client([Resp(403, text="Resource not accessible")])
        with self.assertRaises(GitHubError):
            c.get("/x")

    def test_server_error_retried_then_raises(self):
        c, sleeps = client([Resp(502), Resp(data=1)])
        self.assertEqual(c.get("/x"), 1)
        c, _ = client([Resp(500)] * 3, max_retries=2)
        with self.assertRaises(GitHubError):
            c.get("/x")

    def test_allow_404(self):
        c, _ = client([Resp(404)])
        self.assertIsNone(c.get("/x", allow_404=True))

    def test_low_quota_pauses_proactively(self):
        c, sleeps = client([Resp(data=1, headers={"X-RateLimit-Remaining": "1", "X-RateLimit-Reset": "1050"})])
        c.get("/x")
        self.assertEqual(sleeps, [52])

    def test_cache_avoids_second_request(self):
        with TemporaryDirectory() as d:
            c, _ = client([Resp(data=[1])], cache_dir=d)
            self.assertEqual(list(c.paginate("/x", cache=True)), [1])
            self.assertEqual(list(c.paginate("/x", cache=True)), [1])
            self.assertEqual(c.requests_made, 1)


if __name__ == "__main__":
    unittest.main()
