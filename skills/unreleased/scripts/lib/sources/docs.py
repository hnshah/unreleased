"""docs source: the product's own documentation index, as a third cross-check source.

The changelog says what was launched and when; the pricing page says what is sold; the docs say what exists
today, including features that never got a changelog entry (Raycast's organization settings pages are on
manual.raycast.com, which the engine could not see, so six announced pages read as "no public mention").

`plan.docs` is one URL and may be any of:
- an `llms.txt` (Markdown: `- [Title](url): summary` lines, or bare URLs one per line),
- a sitemap or sitemap index (`<loc>` entries; titles from the slug),
- an HTML index or manual home (every same-host link with its anchor text).

Output: `[{"title", "url", "text"}]`, capped at MAX_PAGES; `text` is the slug's words so a title-less link
still matches. The cross-check treats a strong match as `announced` with the page url and no date, and the
brief writes it *announced (docs) <url>*. Never fetched: anything off the docs host, anything robots
disallows (the site source's prefixes are not available here; the docs index itself is public by design).
"""
from __future__ import annotations

import html
import re
from urllib.parse import urljoin, urlsplit

from schema import SourceOutcome

SOURCE = "docs"
LIMIT = 3_000_000
MAX_PAGES = 2_000
MAX_CHILD_SITEMAPS = 8
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)(?::\s*([^\n]*))?")
_A = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)
_SITEMAP_ENTRY = re.compile(r"<sitemap>(.*?)</sitemap>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_BARE_URL = re.compile(r"^\s*(?:[-*]\s+)?(https?://[^\s<>()\[\]]+)\s*$", re.M)
_SKIP = re.compile(r"^(?:#|mailto:|javascript:|tel:)", re.I)


def _slug_words(url: str) -> str:
    path = urlsplit(url).path
    return " ".join(w for w in re.split(r"[/_\-.]+", path) if len(w) >= 3 and not w.isdigit())


def _entry(title: str, url: str, extra: str = "") -> dict:
    title = re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", title))).strip()[:160]
    return {"title": title, "url": url, "text": (_slug_words(url) + " " + extra).strip()[:300], "date": None}


def parse(body: str, base: str) -> tuple[list[dict], list[str], str]:
    """(entries, child sitemaps, how)."""
    b = body.lstrip()
    if b.startswith("<?xml") or "<urlset" in b[:2000] or "<sitemapindex" in b[:2000]:
        children = [html.unescape(_LOC.search(m.group(1)).group(1).strip()) for m in _SITEMAP_ENTRY.finditer(b) if _LOC.search(m.group(1))]
        urls = [html.unescape(u.strip()) for u in _LOC.findall(b)]
        urls = [u for u in urls if u not in children]
        return [_entry("", u) for u in urls], children, "sitemap"
    if "<html" in b[:4000].lower() or "<a " in b[:4000].lower():
        host = urlsplit(base).netloc
        out, seen = [], set()
        for m in _A.finditer(b):
            href = m.group(1).strip()
            if _SKIP.match(href):
                continue
            u = urljoin(base, href).split("#", 1)[0]
            if urlsplit(u).netloc != host or u in seen:
                continue
            seen.add(u); out.append(_entry(m.group(2), u))
        return out, [], "html-index"
    out = []
    for m in _MD_LINK.finditer(b):
        out.append(_entry(m.group(1), m.group(2), m.group(3) or ""))
    # bare URLs, one per line (Cursor's: 535 lines, no Markdown), alone or mixed with links: each line is a page
    linked = {e["url"] for e in out}
    bare = [_entry("", u) for u in _BARE_URL.findall(b) if u not in linked]
    how = "llms.txt" if out and not bare else "llms.txt (bare urls)" if bare and not out else "llms.txt (links and bare urls)"
    out += bare
    return out, [], how if out else "text: no links"


def fetch(plan, fetcher) -> tuple[list[dict], list[SourceOutcome]]:
    url = getattr(plan, "docs", None)
    if not url:
        return [], [SourceOutcome(SOURCE, "skipped-unconfigured", 0, False, "no docs url in the plan")]
    f = fetcher.get(url, LIMIT, "page")
    if f.state != "ok" or not f.body:
        return [], [SourceOutcome(SOURCE, f.state if f.state != "ok" else "no-results", 0, True, f"{url}: HTTP {f.status}")]
    entries, children, how = parse(f.body, f.final_url or url)
    read = 1
    for c in children[:MAX_CHILD_SITEMAPS]:
        g = fetcher.get(c, LIMIT, "page")
        read += 1
        if g.state == "ok" and g.body:
            e2, _, _ = parse(g.body, g.final_url or c)
            entries += e2
        if len(entries) >= MAX_PAGES:
            break
    seen, out = set(), []
    for e in entries:
        if e["url"] in seen:
            continue
        seen.add(e["url"]); out.append(e)
        if len(out) >= MAX_PAGES:
            break
    if not out:
        return [], [SourceOutcome(SOURCE, "no-results", 0, True, f"{url}: {how}: no pages found")]
    capped = len(entries) > MAX_PAGES or len(children) > MAX_CHILD_SITEMAPS
    return out, [SourceOutcome(SOURCE, "capped" if capped else "ok", len(out), True, f"{url}: {how}: {len(out)} pages in {read} file(s)")]


def health(fetcher) -> SourceOutcome:
    return SourceOutcome(SOURCE, "ok", 0, True, "needs a plan url; nothing to probe")
