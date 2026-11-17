"""Fetch: the only module that touches the network. Politeness, caps, blobs, and a recorded fetcher for tests.

Boundary discipline: everything past this module trusts `Fetched`.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Protocol
import gzip, hashlib, io, os, re, time, urllib.parse, urllib.request, urllib.error, zlib

from schema import RunOutcomeState

from version import VERSION
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36 "
      f"unreleased/{VERSION} (research; public pages only; https://github.com/hnshah/unreleased)")
Kind = Literal["page", "script", "api"]
CHALLENGE = re.compile(r"<title>\s*Just a moment|_cf_chl_opt|cf-chl-|challenge-platform/h/|<title>\s*Attention Required|<title>\s*Access Denied|px-captcha|/_Incapsula_Resource|awswaf-captcha", re.I)
# the small-page rule is for interstitials, which are short; a bare "captcha" token is a login form's reCAPTCHA
# tag or an API field, so it is not a marker (review S3)
SMALL_CHALLENGE = re.compile(r"verify you are human|enable javascript and cookies|checking your browser|please stand by", re.I)


@dataclass
class Fetched:
    url: str
    final_url: str
    status: int | str
    state: RunOutcomeState
    body: str = ""
    sha256: str = ""
    bytes: int = 0
    truncated: bool = False
    content_type: str = ""
    location: str = ""          # a 3xx answer's Location, resolved; LiveFetcher follows it hop by hop under robots.txt


class Fetcher(Protocol):
    def get(self, url: str, limit: int, kind: Kind = "page") -> Fetched: ...


class BlobStore:
    """Content-addressed store of every body read. Identical bodies are stored once."""
    def __init__(self, root: str):
        self.root = root; os.makedirs(root, exist_ok=True)

    def put(self, data: bytes) -> str:
        h = hashlib.sha256(data).hexdigest()
        p = os.path.join(self.root, h)
        if not os.path.exists(p):
            with open(p, "wb") as f: f.write(data)
        return h

    def get(self, sha256: str) -> bytes | None:
        p = os.path.join(self.root, sha256)
        return open(p, "rb").read() if os.path.exists(p) else None


def classify_page(status: int, text: str, kind: Kind = "page") -> RunOutcomeState:
    if status == 403: return "blocked-403"
    if status == 429: return "rate-limited"
    if status == 402: return "payment-required"
    if status in (401,): return "auth-failed"
    if status == 404: return "no-results"
    if status >= 500: return "unreachable"
    if kind == "page" and (CHALLENGE.search(text[:6000]) or (len(text) < 3000 and SMALL_CHALLENGE.search(text))): return "challenge"
    return "ok"


DEAD_AFTER = 3     # consecutive timeouts or connection failures before a host is treated as down for the rest of the run


ROBOTS_LIMIT = 256_000
ROBOTS_AGENTS = ("*", "unreleased")   # the user-agent groups that bind this engine


def _gunzip(data: bytes, limit: int) -> bytes:
    """Inflate every gzip member (a body may be several concatenated), at most `limit` bytes; a cut stream inflates
    to a valid prefix instead of raising."""
    out = b""
    while data and len(out) < limit:
        d = zlib.decompressobj(wbits=31)
        out += d.decompress(data, limit - len(out))
        if not d.eof:
            break                                   # cut at the cap, or the output limit reached
        data = d.unused_data
    return out


def robots_rules(body: str) -> list[str]:
    """Disallow prefixes that bind this engine: the `*` group and any group naming `unreleased`. `Disallow: /` is
    kept (it means the whole host); an empty `Disallow:` allows all. Allow lines are not modelled: we read less."""
    out: list[str] = []
    agents: list[str] = []; in_rules = False
    for line in body.lstrip("\ufeff").splitlines():
        s = line.split("#", 1)[0].strip()
        if ":" not in s:
            continue
        field, value = (x.strip() for x in s.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(value.lower())
        elif field in ("disallow", "allow"):
            in_rules = True
            if field == "disallow" and value and any(a == "*" or "unreleased" in a for a in agents):
                out.append(value)
    return out


def robots_disallows(path: str, prefixes: list[str]) -> bool:
    """robots matching: a prefix match, `*` as a wildcard, `$` as end-anchor."""
    for p in prefixes:
        rx = "^" + re.escape(p).replace(r"\*", ".*").replace(r"\$", "$")
        if re.match(rx, path or "/"):
            return True
    return False


MAX_HOPS = 5


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects come back as answers, so every hop passes robots.txt, the host state and the per-host spacing."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def host_key(sp: urllib.parse.SplitResult) -> str:
    """One host, one state: lower-case, default ports dropped (`A.com:443` and `a.com` are the same host)."""
    h = (sp.hostname or "").lower()
    try:
        port = sp.port
    except ValueError:
        port = None
    port = port if port and port != {"http": 80, "https": 443}.get(sp.scheme) else None
    return f"{h}:{port}" if port else h


def fetchable(url: str) -> bool:
    """A redirect target is followed only when it is a well-formed http(s) URL with a host (never `file:`, never a bad port)."""
    try:
        sp = urllib.parse.urlsplit(url)
        sp.port
    except ValueError:
        return False
    return sp.scheme in ("http", "https") and bool(sp.hostname)


class LiveFetcher:
    """Polite HTTP, as POLICY.md says it is:
    - robots.txt of a host is read before any other request to it, and a page or script under a `Disallow` that
      binds us is never requested (`Disallow: /` closes the host). APIs that exist to be queried (crt.sh, job
      board APIs; kind "api") are not crawled pages and are not gated on robots.
    - >= min_interval s between requests to one host; caps on bytes.
    - a 403 or a challenge page stops the host for the rest of the run: no retry, no second request; a 429 too.
    - redirects are followed here, hop by hop, so every hop passes robots.txt and the host state.
    - DEAD_AFTER consecutive timeouts or connection failures stop the host (SM-7)."""
    def __init__(self, blobs: BlobStore | None = None, min_interval: float = 1.0, sleep=time.sleep, now=time.time, robots: bool = True):
        self.blobs, self.min_interval, self.robots = blobs, min_interval, robots
        self._sleep, self._now, self._last = sleep, now, {}
        self.requests = 0
        self.rate_limited: set[str] = set()      # hosts that answered 429: no further request this run (POLICY: back off and stop)
        self.stopped: dict[str, RunOutcomeState] = {}   # hosts that answered 403 or a challenge: no further request this run
        self.failures: dict[str, int] = {}       # consecutive timeout/unreachable per host; at DEAD_AFTER the host is not asked again (SM-7)
        self._robots: dict[str, tuple[Fetched, list[str]]] = {}   # host -> (the robots.txt answer, the prefixes that bind us)

    def _polite(self, url: str):
        host = urllib.parse.urlparse(url).netloc
        wait = self.min_interval - (self._now() - self._last.get(host, 0.0))
        if wait > 0: self._sleep(wait)
        self._last[host] = self._now()

    def _once(self, url: str, limit: int, kind: Kind = "page") -> Fetched:
        self._polite(url); self.requests += 1
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip", "Accept": "*/*"})
        try:
            with _OPENER.open(req, timeout=30) as r:
                raw = r.read(limit + 1); cut = len(raw) > limit
                if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                    # inflate incrementally: a body cut at the cap is still a valid prefix. Inflating the cut stream
                    # whole raised, and the compressed bytes were then scanned as if they were code.
                    try:
                        raw = _gunzip(raw, limit + 1)
                    except zlib.error:
                        return Fetched(url, r.geturl(), r.status, "error")       # not gzip after all: nothing to read, nothing scanned
                truncated = cut or len(raw) > limit; raw = raw[:limit]
                text = raw.decode("utf-8", "replace")
                sha = self.blobs.put(raw) if self.blobs else hashlib.sha256(raw).hexdigest()
                return Fetched(url, r.geturl(), r.status, classify_page(r.status, text, kind), text, sha, len(raw), truncated, r.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as e:
            if 300 <= e.code < 400 and e.headers.get("Location"):
                return Fetched(url, url, e.code, "ok", location=urllib.parse.urljoin(url, e.headers["Location"]))
            return Fetched(url, url, e.code, classify_page(e.code, ""))
        except urllib.error.URLError as e:
            return Fetched(url, url, "error", "unreachable" if "resolve" in str(e).lower() or "refused" in str(e).lower() else "timeout" if "timed out" in str(e).lower() else "error")
        except Exception as e:
            return Fetched(url, url, "error", "error")

    def _request(self, host: str, url: str, limit: int, kind: Kind) -> Fetched:
        """One request with the host's state machine applied: refused hosts are not asked, answers update the state."""
        if host in self.rate_limited:
            return Fetched(url, url, 429, "rate-limited")          # no request: the host said stop
        if host in self.stopped:
            return Fetched(url, url, "stopped", self.stopped[host])  # no request: the host refused once this run
        if self.failures.get(host, 0) >= DEAD_AFTER:
            return Fetched(url, url, "error", "unreachable")      # no request: the host has not answered DEAD_AFTER times in a row
        f = self._once(url, limit, kind)
        self.failures[host] = self.failures.get(host, 0) + 1 if f.state in ("timeout", "unreachable") else 0
        if f.state == "rate-limited":
            self.rate_limited.add(host)
        elif f.state in ("blocked-403", "challenge"):
            self.stopped[host] = f.state                          # never retried, never routed around
        return f

    def _robots_for(self, scheme: str, netloc: str, host: str) -> tuple[Fetched, list[str]]:
        """RFC 9309: a robots.txt that answers 4xx allows everything; one that cannot be read (5xx, timeout, no
        connection) disallows everything. Read as text, so a challenge marker in a Disallow line is not a challenge;
        an HTML interstitial in its place is."""
        if host not in self._robots:
            u = f"{scheme}://{netloc}/robots.txt"
            f = self._request(host, u, ROBOTS_LIMIT, "script")
            for _ in range(MAX_HOPS):                    # a robots.txt that redirects (to https, to www) is read where it lands
                if not (f.state == "ok" and f.location and fetchable(f.location)):
                    break
                nxt = urllib.parse.urlsplit(f.location)
                f = self._request(host_key(nxt), f.location, ROBOTS_LIMIT, "script")
            html_body = "<html" in (f.body or "")[:400].lower()
            if f.state == "ok" and html_body and classify_page(200, f.body, "page") == "challenge":
                f.state = "challenge"; self.stopped[host] = "challenge"
            if f.state == "ok" and f.location:
                rules: list[str] = ["/"]                  # still redirecting after MAX_HOPS, or to a non-http target: unreadable
            elif f.state == "ok":
                rules = [] if html_body else robots_rules(f.body)
            elif isinstance(f.status, int) and 400 <= f.status < 500:
                rules = []
            else:
                rules = ["/"]
            self._robots[host] = (f, rules)
        return self._robots[host]

    def _one(self, url: str, limit: int, kind: Kind) -> Fetched:
        sp = urllib.parse.urlsplit(url)
        host = host_key(sp) or url
        if self.robots and kind != "api" and sp.scheme in ("http", "https"):
            rb, rules = self._robots_for(sp.scheme, sp.netloc, host)
            if (sp.path or "/") == "/robots.txt":
                return rb                                         # read once per host, before anything else
            if host in self.stopped:
                return Fetched(url, url, "stopped", self.stopped[host])
            if robots_disallows((sp.path or "/") + (("?" + sp.query) if sp.query else ""), rules):
                return Fetched(url, url, "robots.txt", "skipped-unconfigured")   # no request: robots.txt asks us not to
        return self._request(host, url, limit, kind)

    def get(self, url: str, limit: int, kind: Kind = "page") -> Fetched:
        """Follows redirects itself, at most MAX_HOPS, each hop a request of its own under robots.txt and host state."""
        cur = url
        for _ in range(MAX_HOPS + 1):
            if not fetchable(cur):
                return Fetched(url, cur, "bad-redirect", "error")      # never file:, never a malformed target
            f = self._one(cur, limit, kind)
            if not f.location:
                f.url = url
                if f.final_url == cur or not f.final_url:
                    f.final_url = cur
                return f
            cur = f.location
        return Fetched(url, cur, "redirects", "error")


class RecordingFetcher:
    """Wraps a live fetcher and keeps what it read in the corpus layout RecordedFetcher replays: raw/<sha1(url)[:10]>.html|.js,
    summary.json (pages, certificate-log names, job titles, pricing) and pricing.txt. `run --record DIR` uses it, so anyone
    can build a corpus of their own and score it with tools/run_corpus.py; the bodies stay on their disk."""
    def __init__(self, inner, run_dir: str):
        self.inner, self.run_dir, self.pages = inner, run_dir, []
        os.makedirs(os.path.join(run_dir, "raw"), exist_ok=True)

    @property
    def requests(self) -> int:
        return getattr(self.inner, "requests", 0)

    def get(self, url: str, limit: int, kind: Kind = "page") -> Fetched:
        f = self.inner.get(url, limit, kind)
        if kind != "api":
            self.pages.append({"url": url, "status": f.status, "state": f.state, "final_url": f.final_url, "kind": kind})
            if f.state == "ok" and f.body:
                ext = ".js" if kind == "script" else ".html"
                with open(os.path.join(self.run_dir, "raw", hashlib.sha1(url.encode()).hexdigest()[:10] + ext), "w", encoding="utf-8") as fh:
                    fh.write(f.body)
        return f

    def finish(self, result, plan_dict: dict) -> str:
        import json
        pr = result.pricing
        states = {s.source: s.state for s in result.coverage.sources if s.source in ("crt", "ats", "pricing")}
        summary = {"pages": self.pages, "source_states": states,
                   "crt": {"recent": [{"name": s.name, "first_seen": s.first_seen} for s in result.subdomains]},
                   "jobs": [{"board": j.ats} for j in result.jobs[:1]],
                   "job_titles": [j.title for j in result.jobs],
                   "pricing": {"url": pr.url, "final_url": pr.final_url, "sha256_text": pr.sha256_text, "chars": pr.chars} if pr and pr.status == "ok" else None}
        if summary["pricing"]:
            with open(os.path.join(self.run_dir, "pricing.txt"), "w", encoding="utf-8") as fh:
                fh.write(pr.text or "\n".join(pr.lines))
        with open(os.path.join(self.run_dir, "summary.json"), "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=1)
        with open(os.path.join(self.run_dir, "plan.json"), "w", encoding="utf-8") as fh:
            json.dump(plan_dict, fh, indent=1)
        return self.run_dir


class RecordedFetcher:
    """Replays a probe run folder from the corpus: url -> raw/<sha1(url)[:10]>.<ext>. No network."""
    def __init__(self, run_dir: str):
        import json
        self.run_dir = run_dir
        with open(os.path.join(run_dir, "summary.json"), encoding="utf-8") as f:
            self.summary = json.load(f)
        self.status_by_url = {p["url"]: p for p in self.summary.get("pages", [])}
        # the probe resolved relative script URLs against the page URL it asked for, not the redirect target
        # (www.notion.so/login -> app.notion.com/login); the pipeline uses the final URL. Map hosts back.
        self.host_alias: dict[str, str] = {}
        for pg in self.summary.get("pages", []):
            fin, orig = pg.get("final_url") or "", pg.get("url") or ""
            if fin and orig and "//" in fin and "//" in orig:
                fh, oh = fin.split("/")[2], orig.split("/")[2]
                if fh != oh:
                    self.host_alias[fh] = oh
        self.requests = 0

    def _candidates(self, url: str) -> list[str]:
        out = [url]
        if "//" in url:
            scheme, rest = url.split("//", 1)
            host, _, path = rest.partition("/")
            if host in self.host_alias:
                out.append(f"{scheme}//{self.host_alias[host]}/{path}")
        return out

    def get(self, url: str, limit: int, kind: Kind = "page") -> Fetched:
        self.requests += 1
        for cand in self._candidates(url):
            stem = hashlib.sha1(cand.encode()).hexdigest()[:10]
            for ext in (".html", ".js"):
                p = os.path.join(self.run_dir, "raw", stem + ext)
                if not os.path.exists(p):
                    continue
                with open(p, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()[:limit]
                data = text.encode("utf-8", "replace")
                meta = self.status_by_url.get(cand, {})
                return Fetched(url, meta.get("final_url", url), 200, classify_page(200, text), text, hashlib.sha256(data).hexdigest(), len(data), False)
        meta = self.status_by_url.get(url)
        if meta and meta.get("status") not in (200, None):
            st = meta["status"]
            if isinstance(st, int) or str(st).isdigit():
                return Fetched(url, url, int(st), classify_page(int(st), ""))
            return Fetched(url, url, st, meta.get("state") or ("skipped-unconfigured" if st == "robots.txt" else "error"))
        return Fetched(url, url, "not-recorded", "skipped-unconfigured")
