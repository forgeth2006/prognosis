"""Minimal GitHub REST client for PRognosis scraping.

Handles authentication, pagination, rate limits (primary and secondary), retries
with backoff, and an optional on-disk cache so an interrupted scrape can resume
without re-spending API quota.

Auth: set GITHUB_TOKEN (a classic or fine-grained personal access token with
public-repo read access). Without a token GitHub allows only 60 requests/hour.
Never commit a token; .env is already in .gitignore.
"""
import hashlib
import json
import os
import time
from pathlib import Path

import requests

API = "https://api.github.com"
UA = "PRognosis-student-project (academic use)"


class GitHubError(RuntimeError):
    def __init__(self, status, url, message=""):
        super().__init__(f"HTTP {status} for {url}: {message[:200]}")
        self.status = status
        self.url = url


class GitHubClient:
    def __init__(self, token=None, cache_dir=None, min_interval=0.05, max_retries=5,
                 session=None, sleep=time.sleep, now=time.time, log=print):
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self._sleep, self._now, self.log = sleep, now, log
        self._last_request = 0.0
        self.requests_made = 0
        if not self.token:
            self.log("WARNING: no GITHUB_TOKEN set; limited to 60 requests/hour.")

    # ---- low level -------------------------------------------------------
    def _headers(self):
        h = {"User-Agent": UA, "Accept": "application/vnd.github+json",
             "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    @staticmethod
    def _url(path):
        return path if path.startswith("http") else f"{API}{path}"

    def _seconds_until_reset(self, resp):
        reset = resp.headers.get("X-RateLimit-Reset")
        if reset and reset.isdigit():
            return max(int(reset) - self._now(), 0) + 2
        return 60

    def _rate_limit_wait(self, resp):
        """Seconds to wait if this 403/429 is a rate limit, else None (a real error)."""
        if resp.headers.get("Retry-After", "").isdigit():
            return int(resp.headers["Retry-After"]) + 1
        if resp.headers.get("X-RateLimit-Remaining") == "0":
            return self._seconds_until_reset(resp)
        if "rate limit" in resp.text.lower():  # secondary / abuse limit
            return 60
        return None

    def _request(self, url, params=None):
        attempt = 0
        while True:
            gap = self.min_interval - (self._now() - self._last_request)
            if gap > 0:
                self._sleep(gap)
            try:
                resp = self.session.get(url, headers=self._headers(), params=params, timeout=30)
            except requests.RequestException as e:
                attempt += 1
                if attempt > self.max_retries:
                    raise GitHubError(0, url, f"network error: {type(e).__name__}")
                self._sleep(2 ** attempt)
                continue
            self._last_request = self._now()
            self.requests_made += 1
            if resp.status_code in (403, 429):
                wait = self._rate_limit_wait(resp)
                if wait is None:
                    raise GitHubError(resp.status_code, url, resp.text)
                self.log(f"rate limited; sleeping {int(wait)}s")
                self._sleep(wait)
                continue  # rate-limit waits do not count as failures
            if resp.status_code >= 500:
                attempt += 1
                if attempt > self.max_retries:
                    raise GitHubError(resp.status_code, url, resp.text)
                self._sleep(2 ** attempt)
                continue
            # Proactively pause when the hourly quota is almost gone.
            remaining = resp.headers.get("X-RateLimit-Remaining")
            if remaining is not None and remaining.isdigit() and int(remaining) <= 2:
                wait = self._seconds_until_reset(resp)
                self.log(f"quota nearly exhausted; sleeping {int(wait)}s until reset")
                self._sleep(wait)
            return resp

    # ---- cache -----------------------------------------------------------
    def _cache_file(self, url, params):
        key = url + "?" + json.dumps(params or {}, sort_keys=True)
        return self.cache_dir / (hashlib.sha1(key.encode()).hexdigest() + ".json")

    def _page(self, path, params, cache, allow_404):
        """One page -> (parsed_json, next_url). Returns (None, None) for an allowed 404."""
        url = self._url(path)
        cf = self._cache_file(url, params) if (cache and self.cache_dir) else None
        if cf and cf.exists():
            blob = json.loads(cf.read_text(encoding="utf-8"))
            return blob["data"], blob["next"]
        resp = self._request(url, params)
        if resp.status_code == 404 and allow_404:
            return None, None
        if resp.status_code != 200:
            raise GitHubError(resp.status_code, url, resp.text)
        data = resp.json()
        nxt = resp.links.get("next", {}).get("url")
        if cf:
            cf.write_text(json.dumps({"data": data, "next": nxt}), encoding="utf-8")
        return data, nxt

    # ---- public ----------------------------------------------------------
    def get(self, path, params=None, cache=False, allow_404=False):
        data, _ = self._page(path, params, cache, allow_404)
        return data

    def paginate(self, path, params=None, item_key=None, cache=False, max_items=None,
                 allow_404=False):
        """Yield items across pages. item_key names the list inside dict responses
        (e.g. 'workflow_runs'). Stops after max_items if given."""
        params = dict(params or {})
        params.setdefault("per_page", 100)
        url, count = path, 0
        while url:
            data, url = self._page(url, params if url == path else None, cache, allow_404)
            if data is None:
                return
            items = data[item_key] if item_key else data
            for item in items:
                yield item
                count += 1
                if max_items is not None and count >= max_items:
                    return
