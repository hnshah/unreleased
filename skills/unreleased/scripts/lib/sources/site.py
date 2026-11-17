"""site source: robots.txt, sitemap.xml and the landing pages they list — the marketing-side twin of the code
read (the "campaign" signals: hidden ad paths, who a compare page targets next, the headline that is winning).

Contract: `fetch(plan, fetcher) -> (records, outcomes)`; records are `Observation`s of three kinds:

- `robots`   key = a `Disallow` prefix (`/lp/`), context = the user-agent block it sits in. A company that
             hides `/lp/`, `/go/`, `/demo-` from search engines has listed its paid landing pages. Finding
             when the prefix looks like a campaign path, key-list otherwise.
- `sitemap`  key = a page path, value = `lastmod` (YYYY-MM-DD or None), context names the sitemap file.
             Kept when the path is a compare page (`/compare/`, `-vs-`, `/alternatives/`), a landing page
             (`/lp/`, `/go/`, `/demo`, `/try`, `/webinar`, `/ebook`, `/offer`, `/promo`) or recent (lastmod
             inside RECENT_DAYS); everything else is counted, not kept. Finding = compare or landing page.
- `headline` key = an `<h1>`/`<title>` text shared by two or more of the landing pages read, value = count,
             context = the pages. Nobody keeps a losing headline on three pages.

Policy, which is the point: robots.txt `Disallow` is a request not to crawl, and this engine never goes
around a request. The disallowed prefixes are reported as what they are (a published list); the pages
under them are never fetched. Landing pages are opened only when the sitemap lists them AND robots.txt
allows them, at most LANDING_PAGES of them, one polite request each. Hostile hosts (403, challenge) end
the source, never a retry.

Receipts: every record points at the robots.txt / sitemap / page body by sha256 and byte offset, like a
code observation; the bodies are returned through `fetch_bodies` so the pipeline stores them as blobs.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import re
from urllib.parse import urlsplit, urljoin

from schema import Observation, Source, SourceOutcome

SOURCE = "site"
ROBOTS_LIMIT = 256_000
SITEMAP_LIMIT = 4_000_000
PAGE_LIMIT = 1_500_000
MAX_SITEMAPS = 12             # child sitemaps read from an index (marketing-shaped ones first)
MAX_URLS = 50_000             # entries parsed across all sitemaps
RECENT_DAYS = 45
KEEP_RECENT = 150             # recent ordinary pages kept as key-list (so the next run can say "pages added")
KEEP_SEO = 100                # compare posts under the blog kept as key-list (newest first in the sitemap order)
LANDING_PAGES = 3

# paid-traffic shapes only, as whole path segments (`/lp/`, `/go/x`, `/webinars/x`) or the thread's `/demo-…` prefix
# form; a blog slug that merely contains "campaign" or "deal" is content, not a campaign (monday.com, ClickUp)
_CAMPAIGN = re.compile(r"(?:^|/)(?:lp|go|try|demo[s]?|offer[s]?|promo[s]?|campaign[s]?|landing|ppc|ads|webinar[s]?|ebook[s]?|e-book[s]?|whitepaper[s]?|signup|sign-up|free-trial|deal[s]?)(?:/|$)|^/(?:lp|go|demo|offer|promo|try)-[a-z0-9]", re.I)
# robots.txt prefixes are judged more loosely: a company that hides `/beta/*`, `/roi/*`, `/legacy-drlp/*` or
# `/p13n-copies/*` from search (Intercom) has named its landing-page and personalisation folders itself
_ROBOTS_CAMPAIGN = re.compile(r"(?:^|[/-])(?:lp|drlp|landing|beta|roi|promo[s]?|offer[s]?|demo[s]?|go|try|webinar[s]?|ebook[s]?|campaign[s]?|ads|ppc|abm|personali[sz]ation|p13n|copies|partner[s]?|deal[s]?|trial|signup|calculator|early-access|preview|labs?)(?:[/*-]|$)", re.I)
# `-vs-` needs a competitor on both sides: /integrations/vs-code is an editor, not a comparison
_COMPARE = re.compile(r"(?:^|/)(?:compare|comparison[s]?|versus|vs|alternative[s]?|alternatives-to|switch(?:-from)?|migrate(?:-from)?)(?:[-/]|$)|[a-z0-9]-vs-(?!code\b)[a-z0-9]|-versus-|-alternative[s]?(?:/|$)|-comparison(?:/|$)", re.I)
# a compare post under the blog is SEO content; a compare page at the top level is a product page built for a campaign
_CONTENT_DIR = re.compile(r"^/(?:blog|learning-center|learn|resources|resource|articles|guides?|hub|library|help|docs|support|academy|glossary|templates?|community|podcasts?|news|press|events?|legal|careers|customers|case-stud)", re.I)
_LOCALE = re.compile(r"^/(?:en|de|fr|es|it|pt|ja|ko|zh|nl|sv|ru|pl|tr|ar|he|id|th|vi|cs|da|fi|nb|no|hu|el|ro|uk|ms|hi|bn|ca|sk|sl|hr|bg|lt|lv|et|fa|ur|tl)(?:[-_][a-z]{2,4})?(?:/|$)", re.I)   # `/lp/` and `/go/` are not locales
_MARKETING_SITEMAP = re.compile(r"page|core|main|static|marketing|site|landing|compare|misc|general|root", re.I)
_SKIP_SITEMAP = re.compile(r"jobs?|compan|people|profile|product[s]?-\d|user|blog|post|news|article|tag|categor|author|image|video|docs?-|help|changelog|release", re.I)
_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)
_ENTRY = re.compile(r"<(url|sitemap)>(.*?)</\1>", re.I | re.S)
_LASTMOD = re.compile(r"<lastmod>\s*(\d{4}-\d{2}-\d{2})", re.I)
_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def _src(url: str, body: str, offset: int) -> Source:
    return Source(url=url, sha256=_sha(body), offset=offset, first_party=True, attribution="domain")


def parse_robots(body: str) -> list[tuple[str, str, int]]:
    """(prefix, user-agent block, offset) for every Disallow with a path; `Disallow:` alone (allow all) is skipped."""
    out, agent = [], "*"
    pos = 0
    for line in body.splitlines(keepends=True):
        s = line.strip()
        low = s.lower()
        if low.startswith("user-agent:"):
            agent = s.split(":", 1)[1].strip() or "*"
        elif low.startswith("disallow:"):
            path = s.split(":", 1)[1].split("#", 1)[0].strip()
            if path and path != "/":
                out.append((path, agent, pos + line.lower().find("disallow")))
        pos += len(line)
    return out


def disallowed(path: str, prefixes: list[str]) -> bool:
    """robots matching for our own fetches: a prefix match, `*` as a wildcard, `$` as end-anchor."""
    for p in prefixes:
        rx = "^" + re.escape(p).replace(r"\*", ".*").replace(r"\$", "$")
        if re.match(rx, path):
            return True
    return False


def parse_sitemap(body: str) -> tuple[list[tuple[str, str | None, int]], list[str]]:
    """(urls with lastmod and offset, child sitemap urls)."""
    urls, children = [], []
    for m in _ENTRY.finditer(body):
        kind, inner = m.group(1).lower(), m.group(2)
        loc = _LOC.search(inner)
        if not loc:
            continue
        u = html.unescape(loc.group(1).strip())
        lm = _LASTMOD.search(inner)
        if kind == "sitemap":
            children.append(u)
        else:
            urls.append((u, lm.group(1) if lm else None, m.start() + inner.find(loc.group(1))))
    if not urls and not children:          # a plain-text sitemap: one url per line
        for m in re.finditer(r"^(https?://\S+)$", body, re.M):
            urls.append((m.group(1), None, m.start()))
    return urls, children


def _headline(body: str) -> str:
    m = _H1.search(body) or _TITLE.search(body)
    if not m:
        return ""
    t = html.unescape(_TAG.sub(" ", m.group(1)))
    t = re.sub(r"\s+", " ", t).strip()
    return t[:160]


def _path(u: str) -> str:
    sp = urlsplit(u)
    return (sp.path or "/") + (("?" + sp.query) if sp.query else "")


def fetch(plan, fetcher):
    """Returns (observations, outcomes, bodies) — bodies is {sha256: (url, text)} for the blobs."""
    base = f"https://{plan.domain}"
    obs: list[Observation] = []; outcomes: list[SourceOutcome] = []; bodies: dict[str, tuple[str, str]] = {}
    n = 0

    def oid() -> str:
        nonlocal n; n += 1; return f"s{n:05d}"

    # robots.txt
    prefixes: list[str] = []
    rb = fetcher.get(base + "/robots.txt", ROBOTS_LIMIT, "page")
    if rb.state in ("blocked-403", "challenge"):
        outcomes.append(SourceOutcome("robots", rb.state, 0, True, "robots.txt refused; nothing under this source was fetched")); return obs, outcomes, bodies
    if rb.state == "ok" and rb.body and "<html" not in rb.body[:400].lower():
        bodies[rb.sha256] = (rb.final_url, rb.body)
        rows, seen_prefix = [], set()
        for path, agent, off in parse_robots(rb.body):
            if path in seen_prefix:
                continue                   # the same prefix under several user-agent blocks is one line
            seen_prefix.add(path); rows.append((path, agent, off))
        for path, agent, off in rows:
            prefixes.append(path)
            campaign = bool(_ROBOTS_CAMPAIGN.search(path)) or bool(_CAMPAIGN.search(path)) or bool(_COMPARE.search(path))
            obs.append(Observation(id=oid(), kind="robots", key=path, source=Source(rb.final_url, rb.sha256, off, True, "domain"),
                                   context=f"Disallow in robots.txt (User-agent: {agent})", extractor="site", group="robots",
                                   tier="finding" if campaign else "key-list", confidence="high"))
        sitemaps = [html.unescape(m.group(1).strip()) for m in re.finditer(r"(?im)^sitemap:\s*(\S+)", rb.body)]
        outcomes.append(SourceOutcome("robots", "ok", len(rows), True, f"{len(rows)} Disallow lines, {len(sitemaps)} sitemap pointers"))
    else:
        sitemaps = []
        outcomes.append(SourceOutcome("robots", "no-results" if rb.state in ("ok", "no-results", "error") else rb.state, 0, True, f"robots.txt {rb.status}"))

    # sitemaps: the ones robots names, else /sitemap.xml; an index is followed, marketing-shaped children first
    queue = list(dict.fromkeys(sitemaps or [base + "/sitemap.xml"]))
    read, entries, children_seen, capped, redirected = 0, [], 0, False, 0
    while queue and read < MAX_SITEMAPS and len(entries) < MAX_URLS:
        u = queue.pop(0)
        f = fetcher.get(u, SITEMAP_LIMIT, "page")
        if f.state in ("blocked-403", "challenge"):
            outcomes.append(SourceOutcome("sitemap", f.state, read, True, f"{u} refused")); break
        read += 1
        if f.state != "ok" or not f.body:
            continue
        urls, children = parse_sitemap(f.body)
        if not urls and not children:
            if f.final_url and urlsplit(f.final_url).path != urlsplit(u).path:
                redirected += 1            # a sitemap served only to search engines: a sign-in page answered instead
            continue
        bodies[f.sha256] = (f.final_url, f.body)
        if f.truncated:
            capped = True
        entries += [(url, lm, off, f.final_url, f.sha256) for url, lm, off in urls]
        children_seen += len(children)
        ranked = sorted(children, key=lambda c: (3 if re.search(r"[/_-](?:[a-z]{2}(?:-[a-z]{2})?)[._-]", c.rsplit("/", 1)[-1].lower()) and not _MARKETING_SITEMAP.search(c.rsplit("/", 1)[-1]) else 0 if _MARKETING_SITEMAP.search(c.rsplit("/", 1)[-1]) else 2 if _SKIP_SITEMAP.search(c.rsplit("/", 1)[-1]) else 1, c))
        queue = [c for c in ranked if c not in queue] + queue
    if not entries:
        why = (f"{redirected} of {read} sitemap files redirected elsewhere (served to search engines only?)" if redirected
               else "no sitemap found (robots pointer or /sitemap.xml)" if read == 0 else f"{read} sitemap file(s) read, no page entries")
        outcomes.append(SourceOutcome("sitemap", "no-results", 0, True, why + (f"; {children_seen} children listed" if children_seen else "")))
        return obs, outcomes, bodies
    if queue or len(entries) >= MAX_URLS:
        capped = True
    cutoff = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=RECENT_DAYS)).isoformat()
    kept_recent = 0; seen_paths = set(); localized = 0; seo = 0
    for url, lm, off, smurl, smsha in entries:
        if urlsplit(url).netloc.split(":")[0].lower().removeprefix("www.") != plan.domain.lower().removeprefix("www."):
            continue
        path = _path(url)
        if path in seen_paths:
            continue
        seen_paths.add(path)
        if _LOCALE.match(path):
            localized += 1; continue          # /de/…, /pt-br/…: the same pages again
        content = bool(_CONTENT_DIR.match(path))
        compare, landing = bool(_COMPARE.search(path)), bool(_CAMPAIGN.search(path)) and not content
        recent = bool(lm and lm >= cutoff)
        if not (compare or landing or recent):
            continue
        if compare and content:
            seo += 1
            if seo > KEEP_SEO:
                continue
        if not (compare or landing):
            if kept_recent >= KEEP_RECENT:
                continue
            kept_recent += 1
        what = ("compare post (content)" if content else "compare page") if compare else "landing page" if landing else "page"
        is_finding = (compare and not content) or landing
        obs.append(Observation(id=oid(), kind="sitemap", key=path, value=lm, source=Source(smurl, smsha, off, True, "domain"),
                               context=f"{what} in {smurl.rsplit('/', 1)[-1]}" + (f", lastmod {lm}" if lm else "") + ("; disallowed in robots.txt" if disallowed(path, prefixes) else ""),
                               extractor="site", group="sitemap", tier="finding" if is_finding else "key-list", confidence="high"))
    outcomes.append(SourceOutcome("sitemap", "capped" if capped else "ok", len(seen_paths), True,
                                  f"{len(entries):,} urls in {read} sitemap file(s)" + (f", {children_seen} children listed" if children_seen else "") + (f"; {redirected} redirected" if redirected else "") + (f"; {localized:,} localized copies skipped" if localized else "") + (f"; {seo} compare posts under content dirs" if seo else "") + (f"; stopped at {MAX_SITEMAPS} files" if queue else "")))

    # landing pages: sitemap-listed, robots-allowed, the most recently modified first; the shared headline is the winner
    cands = [o for o in obs if o.kind == "sitemap" and "landing page" in o.context and "disallowed" not in o.context]
    cands.sort(key=lambda o: (o.value or ""), reverse=True)
    heads: dict[str, list[str]] = {}
    for o in cands[:LANDING_PAGES]:
        u = urljoin(base, o.key)
        f = fetcher.get(u, PAGE_LIMIT, "page")
        if f.state in ("blocked-403", "challenge"):
            outcomes.append(SourceOutcome("landing", f.state, 0, True, f"{u} refused")); break
        if f.state != "ok" or not f.body:
            continue
        bodies[f.sha256] = (f.final_url, f.body)
        h = _headline(f.body)
        if h:
            heads.setdefault(h, []).append(f"{f.final_url} sha256:{f.sha256[:12]}")
            if len(heads[h]) == 1:
                obs.append(Observation(id=oid(), kind="headline", key=h, value=1, source=Source(f.final_url, f.sha256, max(f.body.find(h[:40]), 0), True, "domain"),
                                       context=f"headline of {f.final_url}", extractor="site", group="headline", tier="key-list", confidence="high"))
    for o in obs:
        if o.kind == "headline" and len(heads.get(o.key, [])) >= 2:
            o.value = len(heads[o.key]); o.tier = "finding"
            o.context = f"headline on {o.value} of {min(len(cands), LANDING_PAGES)} landing pages read: " + "; ".join(heads[o.key])
    if cands:
        outcomes.append(SourceOutcome("landing", "ok", min(len(cands), LANDING_PAGES), True, f"{min(len(cands), LANDING_PAGES)} of {len(cands)} landing pages read; {len(heads)} distinct headlines"))
    return obs, outcomes, bodies


def health(fetcher) -> SourceOutcome:
    f = fetcher.get("https://example.com/robots.txt", ROBOTS_LIMIT, "page")
    return SourceOutcome(SOURCE, "ok" if f.status in (200, 404) else f.state, 0, True, None)
