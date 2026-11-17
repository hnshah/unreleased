"""Test helpers: fixture loading, golden loading, a recorded fetcher over the corpus."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILL = os.path.join(ROOT, "skills", "unreleased")           # the plugin layout: skills/<name>/{SKILL.md,references,scripts}
sys.path.insert(0, os.path.join(SKILL, "scripts", "lib"))
FIXTURES = os.path.join(HERE, "fixtures")
GOLDENS = os.path.join(HERE, "goldens")


def fixture(shape: str, name: str) -> str:
    with open(os.path.join(FIXTURES, shape, name), encoding="utf-8") as f:
        return f.read()


def fixture_meta(shape: str, name: str) -> dict:
    with open(os.path.join(FIXTURES, shape, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def golden(product: str) -> dict:
    with open(os.path.join(GOLDENS, product + ".json"), encoding="utf-8") as f:
        return json.load(f)


def noise_oracle() -> dict:
    with open(os.path.join(GOLDENS, "_noise.json"), encoding="utf-8") as f:
        return json.load(f)


class FakeFetcher:
    """Serves canned bodies by URL: `{url: (status, body) | Fetched}`. Anything else is a 404 (`no-results`).
    Records every call as (url, limit, kind) so a test can assert politeness and order."""

    def __init__(self, routes):
        import fetch as fetchmod
        self._f = fetchmod
        self.routes, self.calls = dict(routes), []

    def get(self, url, limit, kind="page"):
        import hashlib
        f = self._f
        self.calls.append((url, limit, kind))
        r = self.routes.get(url)
        if r is None:
            return f.Fetched(url, url, 404, "no-results")
        if isinstance(r, f.Fetched):
            return r
        status, body = r
        if status != 200:
            return f.Fetched(url, url, status, f.classify_page(status, ""))
        data = body.encode("utf-8")
        return f.Fetched(url, url, 200, f.classify_page(200, body), body, hashlib.sha256(data).hexdigest(), len(data), False)
