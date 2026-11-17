"""hidden extractor: UI that exists but is hidden, scheduled or gated behind a waitlist. See plan-v1.md U2.

The readers asked for these as a class of their own ("UI that exists but is hidden"), separate from flags.
Shapes claimed, in order:
  H1 hidden entries   `"/path":{label:"…",visible:()=>!1}` (also `visible:!1`, `hidden:!0`): the path (or the
                      label when the entry has no path) with value "hidden" — Vercel's playgrounds.
  H2 internal routes  any quoted `/internal/…` path, with the entry's label when it keys an entry object.
  H3 noindex          `{name:"robots",content:"noindex"}` meta objects, keyed by the route call that encloses
                      them (``s("/lovtok")({…head:()=>({meta:[…]})``) or the sibling `title`; and HTML
                      `<meta name="robots" content="noindex">`, keyed by the page's path.
  H4 badges           `{label:"…",badge:"private-alpha"}` entries (alpha, beta, early access, coming soon,
                      preview, internal) and the badge vocabulary maps a CMS ships (`"private-alpha":"Private Alpha"`).
  H5 releases         CMS content releases `{id,name,status:"scheduled"|"active"|"draft"}` — the title is the
                      key, the status the value (Retool's Sanity release map). Published/archived are not hidden.
  H6 waitlists        `NAME_WAITLIST="…"` identifiers, `/waitlist/*` and `*-waitlist` paths, `*_waitlist` slugs.
  H7 isForced         `{…,isForced:!0}` entries keyed by their label/name (rare; kept because the brief names it).
Values read from balanced literals are "high"; bare strings are "medium" (a `/internal/` path is unambiguous)
or "low" (a waitlist-looking slug).
"""
from __future__ import annotations
import hashlib
import re
from dataclasses import replace
from urllib.parse import urlsplit

from schema import Observation, Source
import scanner
from extractors.routes import is_path, _key_before, _key_offset, _raw_value, _array_items, _clip, _first_segment

VERSION = "0.1.0"
NAME = "hidden"

_PLACEHOLDERS = ("fn", "ref", "{}", "[]")
_HUMAN = ("label", "title", "name", "text", "description", "group", "screen")
_IDENTITY = ("path", "href", "route", "to", "url", "label", "title", "name", "key", "id", "slug")
_HIDDEN_FN = re.compile(r"\bvisible\s*:\s*\(\s*\)\s*=>\s*(?:!1|false)\b")
_BADGE = re.compile(r"^(?:private[-_ ]?alpha|closed[-_ ]?alpha|alpha|private[-_ ]?beta|closed[-_ ]?beta|open[-_ ]?beta|beta|early[-_ ]?access|coming[-_ ]?soon|preview|experimental|internal[-_ ]?only|internal|labs?)$", re.I)
_BADGE_KEYS = ("badge", "tag", "stage", "status", "pill", "chip", "variant", "ribbon")
_BADGE_VOCAB = ("private-alpha", "closed-alpha", "private-beta", "closed-beta", "early-access", "coming-soon", "internal-only")
_RELEASE_STATUS = frozenset(("scheduled", "active", "draft", "upcoming", "pending", "queued", "unpublished"))
_INTERNAL = re.compile(r'["\'`](/internal/[\w$./\[\]:-]{1,160})["\'`]')
_WAITLIST_IDENT = re.compile(r'(?<![\w$])((?:[A-Za-z_$][\w$]*\.)?)([A-Za-z_][\w]*(?i:waitlist)[\w]*)\s*=\s*(?:"((?:\\.|[^"\\\n]){0,200})")?')
_WAITLIST_STRING = re.compile(r'["\'`]((?:/[\w$./-]*)?[\w$./-]*waitlist[\w$./-]*)["\'`]', re.I)
_NOINDEX_HTML = re.compile(r'<meta\s+(?=[^>]*name=["\']robots["\'])(?=[^>]*content=["\'][^"\']*noindex)[^>]*>', re.I)
_TITLE_HTML = re.compile(r"<title[^>]*>([^<]{1,120})</title>", re.I)
_ROUTE_CALL_BEFORE = re.compile(r'[A-Za-z_$][\w$]*\(\s*[`"\'](/[^`"\'\n]{0,200})[`"\']\s*\)\s*\(')


def _oid(kind: str, key: str, src: Source) -> str:
    return hashlib.sha1(f"{kind}|{key}|{src.sha256}|{src.offset}".encode("utf-8")).hexdigest()[:16]


def _human(pairs: dict, skip: tuple = ()) -> str:
    parts = []
    for k in _HUMAN:
        v = pairs.get(k)
        if isinstance(v, str) and v not in _PLACEHOLDERS and k not in skip:
            parts.append(v if k in ("label", "title", "name", "text", "description") else f"{k}={v}")
    return " ".join(parts)


def _identity(pairs: dict) -> str | None:
    for k in _IDENTITY:
        v = pairs.get(k)
        if isinstance(v, str) and v not in _PLACEHOLDERS and v.strip():
            return v
    return None


class _Sink:
    def __init__(self, artifact: Source):
        self.artifact, self.out, self.seen = artifact, [], set()

    def add(self, key: str, offset: int, *, value=None, context: str = "", group: str = "", confidence: str = "high") -> bool:
        key = key.strip()
        if not key or (key, value) in self.seen:
            return False
        self.seen.add((key, value))
        src = replace(self.artifact, offset=offset)
        self.out.append(Observation(id=_oid("hidden", key, src), kind="hidden", key=key, source=src, value=value, group=group,
                                    context=_clip(context), extractor=NAME, confidence=confidence))
        return True


def extract(body: str, artifact: Source) -> list[Observation]:
    sink = _Sink(artifact)
    lits = list(scanner.iter_literals(body))
    objs = [l for l in lits if l.kind == "object" and 0 < len(l.keys) <= 40]

    for o in objs:
        pairs = dict(zip(o.keys, o.values))
        text = o.text
        path_key, path_off = _key_before(body, o.start)
        if path_key is not None and not is_path(path_key):
            path_key, path_off = None, -1

        # --- H1 hidden entries
        hidden_entry = (pairs.get("visible") == "fn" and _HIDDEN_FN.search(text)) or pairs.get("visible") is False or pairs.get("hidden") is True
        if hidden_entry:
            key = path_key or _identity(pairs)
            if key:
                off = path_off if path_key else _key_offset(body, o, key)
                ctx = _human(pairs, skip=("label",) if key == pairs.get("label") else ())
                sink.add(key, off, value="hidden", context=ctx or "visible=false", group="hidden-route", confidence="high")

        # --- H5 releases
        status = pairs.get("status")
        title = pairs.get("name") if isinstance(pairs.get("name"), str) else pairs.get("title")
        if isinstance(status, str) and status.lower() in _RELEASE_STATUS and isinstance(title, str) and title not in _PLACEHOLDERS \
                and title.strip() and ("id" in pairs or "_id" in pairs or "name" in pairs):
            extra = " ".join(f"{k}={v}" for k, v in pairs.items() if k not in ("name", "title", "status") and isinstance(v, (str, int))
                             and v not in _PLACEHOLDERS)
            sink.add(title, _key_offset(body, o, title), value=status.lower(), context=f"status={status} {extra}", group="release",
                     confidence="high")

        # --- H4 badges on entries
        for bk in _BADGE_KEYS:
            bv = pairs.get(bk)
            if isinstance(bv, str) and bv not in _PLACEHOLDERS and _BADGE.match(bv.strip()):
                key = path_key or _identity({k: v for k, v in pairs.items() if k != bk})
                if key and key != bv:
                    off = path_off if path_key else _key_offset(body, o, key)
                    sink.add(key, off, value=bv.strip().lower(), context=_human(pairs), group="badge", confidence="high")
                break
        # --- H4 badge vocabulary maps
        vocab = [k for k in o.keys if k in _BADGE_VOCAB]
        if vocab and all(isinstance(pairs[k], str) and pairs[k] not in _PLACEHOLDERS and re.search(r"[A-Z ]", pairs[k]) for k in vocab):
            # label maps (`"private-alpha":"Private Alpha"`), not the theme/colour maps keyed the same way
            for k in vocab:
                sink.add(k, _key_offset(body, o, k), value=pairs[k], context="badge vocabulary " + " ".join(o.keys[:12]),
                         group="badge", confidence="low")

        # --- H7 isForced
        if "isForced" in pairs and pairs["isForced"] in (True, False):
            key = path_key or _identity({k: v for k, v in pairs.items() if k != "isForced"})
            if key:
                sink.add(key, path_off if path_key else _key_offset(body, o, key), value=pairs["isForced"],
                         context="isForced " + _human(pairs), group="forced", confidence="high")

        # --- H3 noindex meta objects
        if pairs.get("name") == "robots" and isinstance(pairs.get("content"), str) and "noindex" in pairs["content"]:
            back = body[max(0, o.start - 1200): o.start]
            calls = list(_ROUTE_CALL_BEFORE.finditer(back))
            key, off = None, o.start
            if calls:
                m = calls[-1]
                key, off = m.group(1), max(0, o.start - 1200) + m.start(1)
            else:
                t = re.search(r'title\s*:\s*["\'`]([^"\'`\n]{1,120})["\'`]', back[-400:] + body[o.end:o.end + 400])
                if t:
                    key = t.group(1)
                    off = body.find(key, max(0, o.start - 400), o.end + 400)
            if key:
                sink.add(key, off, value="noindex", context=f"robots={pairs['content']}", group="noindex", confidence="high")

    # --- H2 /internal/ paths (those H1 already keyed keep their first value; this adds the bare ones)
    for m in _INTERNAL.finditer(body):
        path = m.group(1)
        if any(k == path for k, _ in sink.seen):
            continue
        tail = body[m.end(): m.end() + 200]
        label = re.match(r'\s*:\s*\{\s*(?:"?label"?|"?title"?|"?name"?)\s*:\s*["\'`]([^"\'`\n]{1,120})', tail)
        sink.add(path, m.start(1), value=None, context=label.group(1) if label else "", group="internal", confidence="medium")

    # --- H3 noindex in HTML
    for m in _NOINDEX_HTML.finditer(body):
        page = urlsplit(artifact.url).path or "/"
        t = _TITLE_HTML.search(body)
        sink.add(page, m.start(), value="noindex", context=(t.group(1).strip() if t else m.group(0)[:120]), group="noindex",
                 confidence="medium")

    # --- H6 waitlists
    for m in _WAITLIST_IDENT.finditer(body):
        ident = m.group(2)
        if ident.lower() == "waitlist" or len(ident) < 8:
            continue
        sink.add(ident, m.start(2), value=m.group(3), context=body[max(0, m.start() - 80): m.end() + 40], group="waitlist", confidence="medium")
    for m in _WAITLIST_STRING.finditer(body):
        s = m.group(1)
        if len(s) < 9 or s.lower() in ("waitlist", "/waitlist") or any(k == s for k, _ in sink.seen):
            continue
        conf = "medium" if s.startswith("/") else "low"
        sink.add(s, m.start(1), value=None, context=body[max(0, m.start() - 80): m.end() + 80],
                 group="waitlist", confidence=conf)
    return sink.out
