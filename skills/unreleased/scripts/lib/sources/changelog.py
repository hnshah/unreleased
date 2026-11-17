"""changelog source: the product's own dated announcements, from a feed, an index page or embedded JSON.

Contract (shared across `sources/`): `fetch(plan, fetcher) -> (entries, outcomes)` where each entry is
`{"date": "YYYY-MM-DD", "title": str, "url": str, "text": str}`, newest first, at most 200; one
`SourceOutcome`. `health(fetcher) -> SourceOutcome`. The entries feed the cross-check (U7): a flag or a
string that matches a dated entry is `announced`, which changed the verdict on a third of candidate lines.

Three pure parsers, each with a fixture test:
- `parse_feed(xml)`: Atom (`entry`: title, link[rel=alternate], published|updated, summary|content) and
  RSS 2.0 (`item`: title, link, pubDate, description) via `xml.etree`, namespaces ignored;
- `parse_html_index(html, base_url)`: an index page. A date is a `<time datetime>` or a text node that is
  (almost) only a date (`2026-10-22`, `October 22, 2026`, `8 October 2026`); it pairs with the nearest
  heading (h1-h4) within a few nodes before or after, the heading's link is the URL, the first paragraph
  after the heading is the text. Dates inside sentences ("Last updated September 1, 2026") do not count,
  so a footer never steals an undated heading;
- `parse_embedded_json(html, base_url)`: a `changelog*` / `releases` / `releaseNotes` array in page JSON,
  plain (`<script type="application/json">`) or escaped inside a React Server Components payload (cursor.com
  embeds `\\"changelogData\\":[{\\"id\\",\\"title\\",\\"slug\\",\\"date\\",\\"excerpt\\"}]` in the homepage).
"""
from __future__ import annotations

import datetime as dt
import email.utils
import html as htmlmod
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from schema import SourceOutcome

SOURCE = "changelog"
LIMIT = 4_000_000
CAP = 200
HEALTH_URL = "https://example.com/"

_MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"])}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})
_MONTHS["sept"] = 9
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE_RE = re.compile(r"(?<![\d-])(?P<iso>20\d\d-\d\d-\d\d)(?![\d-])|\b(?P<mon>" + _MON + r")\s+(?P<d1>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<y1>20\d\d)\b|\b(?P<d2>\d{1,2})(?:st|nd|rd|th)?\s+(?P<mon2>" + _MON + r")\s+(?P<y2>20\d\d)\b", re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_HEADINGS = {"h1", "h2", "h3", "h4"}
_SKIP = {"script", "style", "svg", "noscript", "template"}
_BLOCKS = {"p", "div", "section", "article", "li", "ul", "ol", "header", "footer", "nav", "main", "aside", "figure", "figcaption", "table", "tr", "td", "th", "dd", "dt", "dl", "blockquote", "pre", "br", "hr", "time", "span"}
_EMBED_KEY = re.compile(r'(?P<esc>\\?)"(?P<key>changelog[A-Za-z_]*|releases|release_?notes|releaseNotes|release_?log)\\?"\s*:\s*\[', re.I)
_JS_ESCAPE = re.compile(r'\\(u[0-9a-fA-F]{4}|.)', re.S)
_DATE_KEYS = ("date", "publishedAt", "published_at", "published", "datetime", "dateTime", "releaseDate", "release_date", "createdAt", "created_at", "updatedAt", "updated_at")
_TITLE_KEYS = ("title", "name", "headline", "heading")
_URL_KEYS = ("url", "href", "link", "permalink", "path")
_TEXT_KEYS = ("excerpt", "description", "summary", "subtitle", "body", "content", "text")


# --- helpers ----------------------------------------------------------------------------------------

def _clean(text: str, cap: int = 500) -> str:
    text = htmlmod.unescape(_TAG.sub(" ", text or ""))
    text = _WS.sub(" ", text).strip()
    return text[:cap]


def norm_date(value) -> str:
    """A YYYY-MM-DD from an ISO string, an RFC 2822 string, a prose date or an epoch; '' when none."""
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = float(value)
        if v > 1e11:
            v /= 1000.0
        try:
            return dt.datetime.fromtimestamp(v, dt.timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ""
    s = str(value).strip()
    m = DATE_RE.search(s)
    if m:
        return _from_match(m)
    try:
        d = email.utils.parsedate_to_datetime(s)
        return d.date().isoformat() if d else ""
    except (TypeError, ValueError, IndexError):
        return ""


def _from_match(m: re.Match) -> str:
    if m.group("iso"):
        y, mo, d = m.group("iso").split("-")
    elif m.group("mon"):
        y, mo, d = m.group("y1"), _MONTHS.get(m.group("mon").rstrip(".").lower()[:4].rstrip("."), _MONTHS.get(m.group("mon").lower()[:3])), m.group("d1")
    else:
        y, mo, d = m.group("y2"), _MONTHS.get(m.group("mon2").rstrip(".").lower()[:4], _MONTHS.get(m.group("mon2").lower()[:3])), m.group("d2")
    try:
        return dt.date(int(y), int(mo), int(d)).isoformat()
    except (TypeError, ValueError):
        return ""


def _finish(entries: list[dict]) -> list[dict]:
    seen, out = set(), []
    horizon = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    for e in entries:
        key = (e["date"], e["title"].lower())
        if e["date"] > horizon:
            continue                         # a changelog cannot announce from the future; a date past today is a parse error
        if e["title"] and (e["date"] or e["url"]) and key not in seen:
            seen.add(key); out.append(e)     # an undated entry with a URL still answers "was this mentioned?"
    out.sort(key=lambda e: e["date"], reverse=True)
    return out[:CAP]


# --- feeds ------------------------------------------------------------------------------------------

def _local(tag) -> str:
    return tag.split("}")[-1] if isinstance(tag, str) else ""


def _child(el, name):
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _text_of(el) -> str:
    if el is None:
        return ""
    if len(el):                                     # xhtml content: child elements
        return _clean("".join(el.itertext()))
    return _clean(el.text or "")


def _reparse_truncated(xml) -> "ET.Element | None":
    """A feed cut by the byte cap (vercel.com/atom is 4 MB of xhtml) still holds whole entries: keep up to
    the last complete one and close the root. None when there is no complete entry."""
    if not isinstance(xml, str):
        return None
    for end_tag, closer in (("</entry>", "</feed>"), ("</item>", "</channel></rss>")):
        i = xml.rfind(end_tag)
        if i > 0:
            try:
                return ET.fromstring((xml[:i + len(end_tag)] + closer).encode("utf-8"))
            except (ET.ParseError, ValueError):
                continue
    return None


def parse_feed(xml: str) -> list[dict]:
    """Entries of an Atom or RSS 2.0 feed; [] when the body is not a feed."""
    try:
        root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except (ET.ParseError, ValueError, TypeError):
        root = _reparse_truncated(xml)
        if root is None:
            return []
    kind = _local(root.tag)
    entries = []
    if kind == "feed":
        for e in root.iter():
            if _local(e.tag) != "entry":
                continue
            url = ""
            for l in e:
                if _local(l.tag) == "link" and l.get("rel", "alternate") == "alternate":
                    url = l.get("href", ""); break
            date = norm_date(_text_of(_child(e, "published")) or _text_of(_child(e, "updated")))
            text = _text_of(_child(e, "summary")) or _text_of(_child(e, "content"))
            entries.append({"date": date, "title": _text_of(_child(e, "title")), "url": url, "text": text})
    elif kind in ("rss", "RDF"):
        for item in root.iter():
            if _local(item.tag) != "item":
                continue
            link = _child(item, "link")
            url = _clean(link.text or "") if link is not None else ""
            if not url:
                guid = _child(item, "guid")
                url = _clean(guid.text or "") if guid is not None and (guid.text or "").startswith("http") else ""
            date = norm_date(_text_of(_child(item, "pubDate")) or _text_of(_child(item, "date")))
            entries.append({"date": date, "title": _text_of(_child(item, "title")), "url": url, "text": _text_of(_child(item, "description"))})
    else:
        return []
    return _finish(entries)


# --- html index --------------------------------------------------------------------------------------

class _Linear(HTMLParser):
    """Linearises a page into nodes: heading (with its link), date, link, text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes, self._skip, self._heading, self._href, self._a_text = [], [], None, [], None
        self._buf = []

    def _flush(self):
        text = _WS.sub(" ", "".join(self._buf)).strip()
        self._buf = []
        if text:
            self.nodes.append({"kind": "text", "text": text})

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in _SKIP:
            self._skip.append(tag); return
        if self._skip:
            return
        if tag in _HEADINGS:
            self._flush(); self._heading = {"kind": "heading", "level": int(tag[1]), "text": "", "href": self._href[-1] if self._href else ""}; self._buf = []
            return
        if tag == "a":
            href = a.get("href") or ""
            self._href.append(href)
            if self._heading is not None and not self._heading["href"]:
                self._heading["href"] = href
            elif self._heading is None:
                self._flush(); self._a_text = []
            return
        if tag == "time" and a.get("datetime"):
            self._flush(); self.nodes.append({"kind": "date", "date": norm_date(a.get("datetime"))})
            return
        if tag in _BLOCKS and self._heading is None:
            self._flush()

    def handle_endtag(self, tag):
        if tag in _SKIP:
            if self._skip and self._skip[-1] == tag:
                self._skip.pop()
            return
        if self._skip:
            return
        if tag in _HEADINGS and self._heading is not None:
            h = self._heading; h["text"] = _WS.sub(" ", "".join(self._buf)).strip(); self._buf = []; self._heading = None
            if h["text"]:
                self.nodes.append(h)
            return
        if tag == "a":
            href = self._href.pop() if self._href else ""
            if self._a_text is not None and self._heading is None:
                text = _WS.sub(" ", "".join(self._a_text)).strip(); self._a_text = None
                if text:
                    self.nodes.append({"kind": "link", "text": text, "href": href})
            return
        if tag in _BLOCKS and self._heading is None:
            self._flush()

    def handle_data(self, data):
        if self._skip:
            return
        if self._a_text is not None and self._heading is None:
            self._a_text.append(data)
        else:
            self._buf.append(data)

    def close(self):
        super().close(); self._flush()


def _standalone_date(text: str) -> str:
    """The date when a text node is (almost) only a date: 'October 22, 2026', 'Posted on 2026-10-22'."""
    m = DATE_RE.search(text)
    if not m:
        return ""
    rest = (text[: m.start()] + text[m.end():]).strip(" \t·•|-–—,.:")
    return _from_match(m) if len(rest) <= 20 else ""


def linearise(html: str) -> list[dict]:
    """The page as a list of nodes: heading (text, href), date, link (text, href), text. Shared with ats."""
    p = _Linear()
    try:
        p.feed(html); p.close()
    except Exception:
        return []
    return p.nodes


def parse_html_index(html: str, base_url: str) -> list[dict]:
    """Dated entries of an HTML changelog index: each standalone date paired with its nearest heading."""
    nodes = linearise(html)
    for n in nodes:
        if n["kind"] == "text":
            d = _standalone_date(n["text"])
            if d:
                n["kind"], n["date"] = "date", d
        elif n["kind"] == "link":
            d = _standalone_date(n["text"])
            if d:
                n["kind"], n["date"] = "date", d
    dates = [i for i, n in enumerate(nodes) if n["kind"] == "date" and n["date"]]
    titles = [i for i, n in enumerate(nodes) if n["kind"] == "heading" or (n["kind"] == "link" and len(n["text"].split()) >= 2)]
    pairs = []
    for i in dates:
        best = None
        for j in titles:
            dist = abs(j - i)
            if dist > 6:
                continue
            rank = (0 if nodes[j]["kind"] == "heading" else 1, dist, 0 if j > i else 1)
            if best is None or rank < best[0]:
                best = (rank, j)
        if best:
            pairs.append((best[0], i, best[1]))
    pairs.sort()
    used_titles, used_dates, entries = set(), set(), []
    for _, i, j in pairs:
        if j in used_titles or i in used_dates:
            continue
        used_titles.add(j); used_dates.add(i)
        node = nodes[j]
        href = node.get("href", "")
        if not href:
            for k in range(j + 1, min(j + 3, len(nodes))):
                if nodes[k]["kind"] == "link":
                    href = nodes[k]["href"]; break
        text = ""                                       # the longest paragraph before the next heading
        for k in range(j + 1, min(j + 40, len(nodes))):
            if nodes[k]["kind"] == "heading":
                break
            if nodes[k]["kind"] == "text" and len(nodes[k]["text"].split()) >= 2 and len(nodes[k]["text"]) > len(text):
                text = nodes[k]["text"][:300]
        entries.append({"date": nodes[i]["date"], "title": node["text"][:200], "url": urllib.parse.urljoin(base_url, href) if href else "", "text": text})
    return _finish(entries)


# --- embedded json -----------------------------------------------------------------------------------

def _unescape_js(s: str) -> str:
    def rep(m):
        e = m.group(1)
        if e.startswith("u"):
            try:
                return chr(int(e[1:], 16))
            except ValueError:
                return m.group(0)
        return {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "/": "/", '"': '"', "\\": "\\", "'": "'"}.get(e, e)
    return _JS_ESCAPE.sub(rep, s)


def _js_string_end(s: str, start: int) -> int:
    """Index of the unescaped quote that ends the JS string literal we are inside at `start`."""
    i = start
    while i < len(s):
        if s[i] == "\\":
            i += 2; continue
        if s[i] == '"':
            return i
        i += 1
    return len(s)


def _entry_from(item: dict, key: str, base_url: str) -> dict | None:
    if not isinstance(item, dict):
        return None
    date = next((norm_date(item[k]) for k in _DATE_KEYS if k in item and norm_date(item[k])), "")
    title = next((str(item[k]).strip() for k in _TITLE_KEYS if isinstance(item.get(k), str) and item[k].strip()), "")
    if not (date and title):
        return None
    url = next((str(item[k]) for k in _URL_KEYS if isinstance(item.get(k), str) and item[k]), "")
    if not url and isinstance(item.get("slug"), str) and base_url:
        section = "releases" if key.lower().startswith("release") else "changelog"
        url = f"/{section}/{item['slug']}"
    text = next((_clean(str(item[k])) for k in _TEXT_KEYS if isinstance(item.get(k), str) and item[k].strip()), "")
    return {"date": date, "title": _clean(title, 200), "url": urllib.parse.urljoin(base_url, url) if url else "", "text": text}


def parse_embedded_json(html: str, base_url: str = "") -> list[dict]:
    """Dated entries from a changelog/releases array embedded in page JSON (plain or RSC-escaped)."""
    entries, dec = [], json.JSONDecoder()
    for m in _EMBED_KEY.finditer(html):
        start = m.end() - 1                                       # the '['
        try:
            if m.group("esc"):
                segment = _unescape_js(html[start:_js_string_end(html, start)])
                arr, _ = dec.raw_decode(segment)
            else:
                arr, _ = dec.raw_decode(html, start)
        except (ValueError, RecursionError):
            continue
        if not isinstance(arr, list):
            continue
        for item in arr:
            e = _entry_from(item, m.group("key"), base_url)
            if e:
                entries.append(e)
    return _finish(entries)


# --- the seam ----------------------------------------------------------------------------------------

def _looks_like_feed(fetched) -> bool:
    head = fetched.body.lstrip()[:200].lower()
    ct = (getattr(fetched, "content_type", "") or "").lower()
    return head.startswith("<?xml") or head.startswith("<feed") or head.startswith("<rss") or "xml" in ct or "atom" in ct or "rss" in ct


def parse_body(fetched, base_url: str) -> tuple[list[dict], str]:
    """(entries, how) for a fetched changelog body: feed, embedded JSON and/or HTML index."""
    if _looks_like_feed(fetched):
        entries = parse_feed(fetched.body)
        if entries:
            return entries, "feed"
        return [], "feed: no entries"      # a feed is never read as an HTML index: its xhtml content is posts, not a changelog
    embedded = parse_embedded_json(fetched.body, base_url)
    index = parse_html_index(fetched.body, base_url)
    how = " + ".join(h for h, n in (("embedded JSON", embedded), ("index", index)) if n)
    return _finish(embedded + index), how or "none"


def fetch(plan, fetcher) -> tuple[list[dict], list[SourceOutcome]]:
    if not plan.changelog:
        return [], [SourceOutcome(SOURCE, "skipped-unconfigured", 0, False, "no changelog URL in the plan")]
    url = plan.changelog
    f = fetcher.get(url, LIMIT, kind="page")
    if f.state == "blocked-403":
        return [], [SourceOutcome(SOURCE, "blocked-403", 0, True, f"{url}: HTTP 403, not retried")]
    if f.state == "challenge":
        return [], [SourceOutcome(SOURCE, "challenge", 0, True, f"{url}: interstitial challenge")]
    if f.status == 404:
        return [], [SourceOutcome(SOURCE, "no-results", 0, True, f"{url}: HTTP 404")]
    if f.state != "ok" or f.status != 200:
        return [], [SourceOutcome(SOURCE, f.state, 0, True, f"{url}: HTTP {f.status}")]
    entries, how = parse_body(f, f.final_url or url)
    if not entries:
        return [], [SourceOutcome(SOURCE, "no-results", 0, True, f"{url}: no dated entries found in {f.bytes} bytes")]
    return entries, [SourceOutcome(SOURCE, "ok", len(entries), True, f"{url}: {how}: {len(entries)} entries, newest {entries[0]['date']}")]


def health(fetcher) -> SourceOutcome:
    """One small public page: says whether page fetching works right now (the parsers are pure)."""
    f = fetcher.get(HEALTH_URL, 200_000, kind="page")
    if f.state != "ok" or not f.body:
        return SourceOutcome(SOURCE, f.state if f.state != "ok" else "error", 0, True, f"{HEALTH_URL}: HTTP {f.status}")
    return SourceOutcome(SOURCE, "ok", 0, True, f"{HEALTH_URL}: {f.bytes} bytes")
