"""routes extractor: route tables and trees as evidence rows. See plan-v1.md U2, GLOSSARY "Route table".

Shapes claimed, in the order they run (the first rule to claim a key wins):
  R1 route entry    `"/path":{label,group,flag,aliases,parent,visible,…}` — a Next.js-style dashboard table
                    (Vercel). The entry's `flag:` also becomes its own observation (group "route-flag"), and
                    `source:"pages/x.page.tsx"` entries (Replit's typed table) emit the page source as a key.
  R2 path map       `{"/path":[…]|"…"}` — an object keyed by paths whose values are arrays or strings
                    (PostHog scene routes, prerender manifests).
  R3 name→path map  `{NAME:"/path", camel:"/path"}` — constant maps (Netlify, Discord `Routes`, Lovable,
                    Notion). The path is the key; for UPPER_SNAKE maps the constant is emitted too, and route
                    builders (`NAME:e=>`/path/${e}``) emit the constant with the template path as context.
  R4 constant map   `{UPPER:"id"|"slug", …}` and enum chains `(c={}).UPPER="…",c.UPPER="…"` whose values
                    are slugs, sub-paths or ids (Discord SKUs and settings tabs; Spotify's page-id enum emits
                    the page ids). Confidence "medium": the table is balanced but its meaning is a guess.
  R5 path-carrying  objects with `path`/`href`/`source`/`destination`/… whose value is a path, with the
                    sibling label/title/name as context (HF nav items, Retool sitemap entries, Next rewrites).
  R6 route calls    TanStack `C(`/path`)({…})` trees (Supabase, Lovable) and Stripe's
                    `$("name","/base",{SUB:"/x"})` groups (the sub-paths are composed onto the base).
  R7 href           `href="/path"` in HTML or template strings, with the link text as context.
  R8 fallback       any other quoted route-like literal, confidence "low", capped at 400 per body, skipping
                    asset paths and Emscripten/SDK sample paths.

Every observation carries the byte offset of its key (or of the literal it was read from) as the receipt.
"""
from __future__ import annotations
import hashlib
import re
from dataclasses import replace

from schema import Observation, Source
import scanner

VERSION = "0.1.0"
NAME = "routes"

_CTX = 200
_FALLBACK_CAP = 400
_PLACEHOLDERS = ("fn", "ref", "{}", "[]")

# A path as a structured value: starts with "/", no whitespace or markup, allows Next/TanStack/Express params.
_PATH = re.compile(r"^/(?:[\w$:.\[\]~@*?()|+-]+(?:/[\w$:.\[\]~@*?()|+-]*)*)?$")
_ASSET = re.compile(r"\.(?:m?js|cjs|css|map|png|jpe?g|gif|svg|webp|avif|ico|woff2?|ttf|otf|eot|mp[34]|webm|json|xml|txt|pdf|wasm|zip)$", re.I)
_SKIP_PREFIX = ("/dev/", "/proc/", "/foo", "/aws/", "/tmp/", "/usr/", "/etc/", "/bin/", "/var/", "/home/", "/root/",
                "/node_modules/", "/_next/", "/static/", "/assets/", "/images/", "/img/", "/fonts/", "/cdn-cgi/",
                "/sys/", "/lib/", "/opt/", "/mnt/", "/__", "/./", "/../")
_SKIP_EXACT = {"/", "/dev", "/proc", "/foo", "/tmp", "/usr", "/etc", "/bin", "/var", "/home", "/root", "/sys", "/lib", "/opt"}

_UPPER = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")
_IDENT = re.compile(r"^[A-Za-z_$][\w$]*$")
_SLUG_VALUE = re.compile(r"^(?:[a-z0-9][a-z0-9_./:-]{1,120}|\d{6,})$")

# What precedes a child literal when it is the value of a key: "k":{ | 'k':{ | k:{ | `k`:{
_KEY_BEFORE = re.compile(r'(?:"((?:\\.|[^"\\])*)"|\'((?:\\.|[^\'\\])*)\'|`([^`]*)`|([A-Za-z_$][\w$]*))\s*:\s*$')
# `name:(0,a.wrapper)(` or `name:wrapper(` or `name:(` just before a route-entry object (Replit's typed table)
_CALL_BEFORE = re.compile(r'([A-Za-z_$][\w$]*)\s*:\s*(?:\(0,\s*[\w$]+\.([A-Za-z_$][\w$]*)\)|([A-Za-z_$][\w$]*))?\s*\(\s*$')

_ENTRY_KEYS = frozenset(("label", "group", "flag", "flags", "aliases", "parent", "visible", "hash", "description",
                         "title", "name", "screen", "source", "page", "component", "icon", "breadcrumbRoot", "redirect"))
_HUMAN_KEYS = ("label", "title", "name", "screen", "group", "description", "page", "component")
_PATH_KEYS = ("path", "pathname", "href", "route", "url", "to", "source", "destination", "from", "target")
_SOURCE_FILE = re.compile(r"^(?:pages|src|app|routes)/[\w./\[\]$-]+\.(?:tsx?|jsx?|vue|svelte|mdx?)$")

# R2/R3 as text runs (for tables whose enclosing object is not balanced in the body read):
# `"/path":["Scene","key"]` and `NAME:"/path"` pairs, at least three in a row.
_PATH_ARRAY = re.compile(r'"(/[^"\n]{1,200})"\s*:\s*\[((?:\s*"[^"\n]*"\s*,?)*)\]')
_PAIR_PATH = re.compile(r'(?<![\w$.])(?:"([A-Za-z_$][\w$]*)"|([A-Za-z_$][\w$]*))\s*:\s*"(/[^"\n]{1,200})"')
# R4 enum chains: `(c={}).NAME="v"` opens a chain, `c.NAME="v"` continues it.
# A chain opens with `(c={})` or TypeScript's `(o=r||(r={}))`.
_CHAIN = re.compile(r'(?:\(([A-Za-z_$][\w$]*)=(?:\{\}|[\w$]+\|\|\([\w$]+=\{\}\))\)|(?<![\w$.])([A-Za-z_$][\w$]*))\.([A-Z][A-Z0-9_]{1,})\s*=\s*"((?:\\.|[^"\\\n]){0,200})"')
# R6 route calls
_TANSTACK = re.compile(r'(?<![\w$.])[A-Za-z_$][\w$]*\(\s*[`"\'](/[^`"\'\n]{0,200})[`"\']\s*\)\s*\(\s*\{')
_STRIPE_GROUP = re.compile(r'\$\(\s*"([A-Za-z_$][\w$]*)"\s*,\s*"(/[^"\n]{0,200})"\s*,\s*\{')
_LAZY_IMPORT = re.compile(r'import\(\s*[`"\']\.?/?(?:[\w./-]*/)?([\w.-]+?)(?:[-.][A-Za-z0-9_-]{6,24})?\.(?:m?js|tsx?)[`"\']\s*\)')
_TITLE_NEAR = re.compile(r'(?:title|settingsLayoutTitle|label|heading)\s*:\s*[`"\']([^`"\'\n]{1,80})[`"\']')
# R7 href
_HREF = re.compile(r'href=\\?["\'](/[^"\'\\\s<>]{1,200})\\?["\']', re.I)
_TAG = re.compile(r"<[^>]*>")
_ARIA = re.compile(r'aria-label=\\?["\']([^"\'\\]{1,80})')
# R8 fallback
_LITERAL = re.compile(r'["\'](/[a-z0-9][a-z0-9-]*(?:/[a-z0-9_$:.\[\]-]+)*)["\']')
_HAS_LETTER = re.compile(r"[a-z]")


def _oid(kind: str, key: str, src: Source) -> str:
    return hashlib.sha1(f"{kind}|{key}|{src.sha256}|{src.offset}".encode("utf-8")).hexdigest()[:16]


def _clip(s: str, n: int = _CTX) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def is_path(v: object) -> bool:
    """A structured route path: `/x`, `/x/[id]`, `/x/$id`, `/x/:id`, not an asset, not an SDK sample path."""
    if not isinstance(v, str) or v in _PLACEHOLDERS or len(v) < 2 or len(v) > 200:
        return False
    if not _PATH.match(v) or v.startswith("//") or v in _SKIP_EXACT or v.startswith(_SKIP_PREFIX):
        return False
    return not _ASSET.search(v)


def _first_segment(path: str) -> str:
    seg = [s for s in path.split("/") if s and not s.startswith(("[", "$", ":", "~", "@"))]
    return seg[0] if seg else ""


def _common_prefix(keys: list[str]) -> str:
    parts = [k.split("_") for k in keys]
    if not parts:
        return ""
    pre = parts[0]
    for p in parts[1:]:
        n = 0
        while n < len(pre) and n < len(p) and pre[n] == p[n]:
            n += 1
        pre = pre[:n]
        if not pre:
            break
    return "_".join(pre)


def _key_before(body: str, pos: int):
    """(key, key_offset) when the text before `pos` ends in `key:` — i.e. the literal at `pos` is a value."""
    m = _KEY_BEFORE.search(body[max(0, pos - 240):pos])
    if not m:
        return None, -1
    k = next(g for g in m.groups() if g is not None)
    off = max(0, pos - 240) + m.start()
    if body[off] in "\"'`":
        off += 1
    return k, off


def _key_offset(body: str, lit: scanner.Literal, key: str) -> int:
    """Offset of `key` as it appears inside one literal's text (quoted or bare)."""
    for pat in (f'"{key}"', f"'{key}'", f"`{key}`"):
        i = body.find(pat, lit.start, lit.end)
        if i != -1:
            return i + 1
    m = re.search(r"(?<![\w$])" + re.escape(key) + r"\s*:", body[lit.start:lit.end])
    return lit.start + m.start() if m else lit.start


def _raw_value(text: str, key: str) -> str | None:
    """The raw right-hand side of `key:` inside one object's text, up to the next top-level comma."""
    m = re.search(r'(?:^|[,{])\s*["\'`]?' + re.escape(key) + r'["\'`]?\s*:\s*', text)
    if not m:
        return None
    depth, i, start = 0, m.end(), m.end()
    while i < len(text):
        c = text[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif c == "," and depth == 0:
            break
        elif c in "\"'`":
            j = i + 1
            while j < len(text) and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j
        i += 1
    return text[start:i]


def _array_items(raw: str) -> list[str]:
    return [m.group(1) or m.group(2) for m in re.finditer(r'"((?:\\.|[^"\\])*)"|\'((?:\\.|[^\'\\])*)\'', raw)]


class _Sink:
    """Collects observations, first claim of a key wins, receipts copied from the artifact."""

    def __init__(self, body: str, artifact: Source):
        self.body, self.artifact, self.out, self.seen = body, artifact, [], set()

    def add(self, key: str, offset: int, *, value=None, context: str = "", group: str = "",
            confidence: str = "high", params: list[str] | None = None) -> bool:
        if not key or key in self.seen:
            return False
        self.seen.add(key)
        src = replace(self.artifact, offset=offset)
        self.out.append(Observation(id=_oid("route", key, src), kind="route", key=key, source=src, value=value,
                                    params=params or [], group=group, context=_clip(context), extractor=NAME,
                                    confidence=confidence))
        return True


def _entry_context(pairs: dict, text: str, skip: tuple = ()) -> tuple[str, str]:
    """(context, group) for one route entry from its human fields."""
    parts = []
    for k in ("label", "title", "name", "screen", "page"):
        v = pairs.get(k)
        if isinstance(v, str) and v not in _PLACEHOLDERS and k not in skip:
            parts.append(v)
    grp = pairs.get("group") if isinstance(pairs.get("group"), str) and pairs.get("group") not in _PLACEHOLDERS else ""
    if grp:
        parts.append(f"group={grp}")
    for k in ("flag", "source", "component", "parent"):
        v = pairs.get(k)
        if isinstance(v, str) and v not in _PLACEHOLDERS and k not in skip:
            parts.append(f"{k}={v}")
    if "flags" in pairs:
        raw = _raw_value(text, "flags")
        if raw:
            parts.append("flags=" + ",".join(_array_items(raw)))
    if "aliases" in pairs:
        raw = _raw_value(text, "aliases")
        if raw:
            parts.append("aliases=" + ",".join(_array_items(raw)))
    for k in ("description",):
        v = pairs.get(k)
        if isinstance(v, str) and v not in _PLACEHOLDERS:
            parts.append(v)
    if pairs.get("visible") == "fn" and re.search(r"visible\s*:\s*\(\s*\)\s*=>\s*(?:!1|false)", text):
        parts.append("visible=false")
    return " ".join(parts), grp


def _route_entry(sink: _Sink, body: str, lit: scanner.Literal, by_span: dict, path: str, path_off: int):
    """R1: one `"/path":{…}` entry (or a typed entry whose `path` is a child object)."""
    pairs = dict(zip(lit.keys, lit.values))
    text = lit.text
    ctx, grp = _entry_context(pairs, text)
    grp = grp or _first_segment(path)
    flag = pairs.get("flag") if isinstance(pairs.get("flag"), str) and pairs.get("flag") not in _PLACEHOLDERS else None
    sink.add(path, path_off, context=ctx, group=grp, confidence="high")
    # the entry's flag names a gate; it is its own evidence row (Vercel: 47 names this way)
    flags = [flag] if flag else []
    if "flags" in pairs:
        raw = _raw_value(text, "flags")
        flags += _array_items(raw) if raw else []
    for f in flags:
        if _IDENT.match(f) or re.match(r"^[\w.-]+$", f):
            fctx, _ = _entry_context(pairs, text, skip=("flag",))
            sink.add(f, _key_offset(body, lit, f), context=f"{fctx} route={path}", group="route-flag", confidence="high")
    # a typed table's page source is a receipt in its own right (Replit: pages/metric-observatory.page.tsx)
    src = pairs.get("source")
    if isinstance(src, str) and _SOURCE_FILE.match(src):
        sctx, _ = _entry_context(pairs, text, skip=("source",))
        sink.add(src, _key_offset(body, lit, src), context=f"{sctx} route={path}", group=grp, confidence="high")


def _typed_path(lit: scanner.Literal, by_span: dict, body: str) -> tuple[str, int] | None:
    """Replit-style `{path:{tanstack:"/x",express:"/x"},screen:"…",source:"pages/x.page.tsx"}`: the path child."""
    pairs = dict(zip(lit.keys, lit.values))
    if pairs.get("path") == "{}":
        for span in lit._children:
            k, _ = _key_before(body, span[0])
            if k != "path":
                continue
            child = by_span.get(span)
            if child is None or child.kind != "object":
                return None
            cp = dict(zip(child.keys, child.values))
            for pk in ("tanstack", "path", "express", "pattern", "default"):
                if is_path(cp.get(pk)):
                    return cp[pk], _key_offset(body, child, cp[pk])
            for v in child.values:
                if is_path(v):
                    return v, _key_offset(body, child, v)
            return None
    if is_path(pairs.get("path")) and ("screen" in pairs or "source" in pairs or "component" in pairs):
        return pairs["path"], _key_offset(body, lit, pairs["path"])
    return None


def _builder_path(entry_text: str) -> str:
    m = re.search(r'[`"\'](/[^`"\'\n]{1,160})', entry_text)
    return m.group(1) if m else ""


def _entry_text(obj_text: str, key: str) -> str:
    m = re.search(r'(?:^|[,{])\s*["\'`]?' + re.escape(key) + r'["\'`]?\s*:', obj_text)
    return obj_text[m.end(): m.end() + 300] if m else ""


def extract(body: str, artifact: Source) -> list[Observation]:
    sink = _Sink(body, artifact)
    lits = list(scanner.iter_literals(body))
    by_span = {(l.start, l.end): l for l in lits}
    objs = [l for l in lits if l.kind == "object"]

    # --- R1 route entries: an object whose preceding key is a path, or a typed entry with a `path` child
    for o in objs:
        ks = o.keys
        if not ks or len(ks) > 40:
            continue
        kset = set(ks)
        k, koff = _key_before(body, o.start)
        if k is not None and is_path(k) and (kset & _ENTRY_KEYS or len(ks) <= 6):
            _route_entry(sink, body, o, by_span, k, koff)
            continue
        if ("screen" in kset or "source" in kset or "component" in kset) and "path" in kset:
            tp = _typed_path(o, by_span, body)
            if tp:
                path, poff = tp
                name, wrapper = None, None
                m = _CALL_BEFORE.search(body[max(0, o.start - 80):o.start])
                if m:
                    name, wrapper = m.group(1), (m.group(2) or m.group(3))
                pairs = dict(zip(ks, o.values))
                ctx, grp = _entry_context(pairs, o.text)
                extra = " ".join(x for x in (name, wrapper) if x)
                sink.add(path, poff, context=f"{extra} {ctx}".strip(), group=grp or _first_segment(path), confidence="high")
                src = pairs.get("source")
                if isinstance(src, str) and _SOURCE_FILE.match(src):
                    sink.add(src, _key_offset(body, o, src), context=f"{extra} {ctx} route={path}".strip(),
                             group=grp or _first_segment(path), confidence="high")

    # --- R2 / R3 / R4: maps
    for o in objs:
        ks, vs = o.keys, o.values
        n = len(ks)
        if n < 2:
            continue
        path_keys = [(k, v) for k, v in zip(ks, vs) if is_path(k)]
        if len(path_keys) >= 2 and len(path_keys) * 2 >= n:
            # R2: keyed by paths with array/scalar values (objects were claimed by R1)
            for k, v in path_keys:
                if v in ("{}",):
                    continue
                ctx = ""
                if v == "[]":
                    raw = _raw_value(o.text, k)
                    ctx = " ".join(_array_items(raw)) if raw else ""
                elif isinstance(v, str) and v not in _PLACEHOLDERS:
                    ctx = v
                sink.add(k, _key_offset(body, o, k), context=ctx, group=_first_segment(k), confidence="high")
            continue
        if n < 3:
            continue
        str_vals = [(k, v) for k, v in zip(ks, vs) if isinstance(v, str) and v not in _PLACEHOLDERS]
        path_vals = [(k, v) for k, v in str_vals if is_path(v)]
        upper = all(_UPPER.match(k) for k in ks)
        if len(path_vals) >= 3 and len(path_vals) * 2 >= len(str_vals) and all(_IDENT.match(k) or _UPPER.match(k) for k in ks):
            # R3: name -> path
            grp = _common_prefix(ks) if upper else ""
            for k, v in path_vals:
                sink.add(v, _key_offset(body, o, v), context=k, group=grp or _first_segment(v), confidence="high")
            if upper:
                for k, v in zip(ks, vs):
                    if isinstance(v, str) and v in ("fn", "ref"):
                        sink.add(k, _key_offset(body, o, k), context=_builder_path(_entry_text(o.text, k)) or "builder",
                                 group=grp or "constants", confidence="medium")
                    elif isinstance(v, str) and v not in _PLACEHOLDERS:
                        sink.add(k, _key_offset(body, o, k), value=v, context=v, group=grp or _first_segment(v),
                                 confidence="medium")
            continue
        if upper and str_vals and all(isinstance(v, str) and v in ("ref",) or (isinstance(v, str) and v not in ("fn", "{}", "[]")) for v in vs) \
                and all(_SLUG_VALUE.match(v) for _, v in str_vals):
            # R4: constant map of slugs / ids
            grp = _common_prefix(ks) or "constants"
            for k, v in str_vals:
                sink.add(k, _key_offset(body, o, k), value=v, context=v, group=grp, confidence="medium")

    # --- R2b / R3b text runs
    def runs(pattern):
        run: list = []
        last_end = -1
        for m in pattern.finditer(body):
            if run and m.start() - last_end > 3:
                if len(run) >= 3:
                    yield run
                run = []
            run.append(m)
            last_end = m.end()
        if len(run) >= 3:
            yield run

    for run in runs(_PATH_ARRAY):
        for m in run:
            path = m.group(1)
            if is_path(path):
                sink.add(path, m.start(1), context=" ".join(_array_items(m.group(2))), group=_first_segment(path), confidence="high")
    for run in runs(_PAIR_PATH):
        names = [m.group(1) or m.group(2) for m in run]
        upper = all(_UPPER.match(n) for n in names)
        grp = _common_prefix(names) if upper else ""
        same = len(set(names)) == 1          # `{"path":"/a"},{"path":"/b"}`: the name says nothing
        for m, name in zip(run, names):
            path = m.group(3)
            if not is_path(path):
                continue
            sink.add(path, m.start(3), context="" if same else name, group=grp or _first_segment(path), confidence="high")
            if upper:
                sink.add(name, m.start(1) if m.group(1) else m.start(2), value=path, context=path,
                         group=grp or _first_segment(path), confidence="medium")

    # --- R4 enum chains: (c={}).A="x",c.B="y",…
    chain: list = []
    last_var, last_end = None, -1

    def flush(ch):
        if len(ch) < 3:
            return
        vals = [v for _, _, v, _ in ch]
        routeish = sum(1 for v in vals if v.startswith("/") or ("/" in v and " " not in v)) * 10 >= 3 * len(vals)
        if routeish:
            for name, name_off, v, v_off in ch:
                if is_path(v) or re.match(r"^[a-z0-9][\w-]*(?:/[\w.-]+)*$", v):
                    sink.add(v, v_off, context=name, group=v.lstrip("/").split("/")[0], confidence="medium")
        elif sum(1 for v in vals if _SLUG_VALUE.match(v)) * 5 >= 4 * len(vals):
            grp = _common_prefix([c[0] for c in ch]) or "constants"
            for name, name_off, v, v_off in ch:
                if _SLUG_VALUE.match(v):
                    sink.add(name, name_off, value=v, context=v, group=grp, confidence="medium")

    for m in _CHAIN.finditer(body):
        var = m.group(1) or m.group(2)
        opens = m.group(1) is not None
        if chain and (opens or var != last_var or m.start() - last_end > 3):
            flush(chain); chain = []
        chain.append((m.group(3), m.start(3), m.group(4), m.start(4)))
        last_var, last_end = var, m.end()
    flush(chain)

    # --- R5 path-carrying objects
    for o in objs:
        ks = o.keys
        if not ks or len(ks) > 30:
            continue
        pairs = dict(zip(ks, o.values))
        hits = [(k, pairs[k]) for k in _PATH_KEYS if is_path(pairs.get(k))]
        if not hits:
            continue
        ctx, grp = _entry_context(pairs, o.text, skip=("source",))
        for k, v in hits:
            others = " ".join(f"{k2}={v2}" for k2, v2 in hits if k2 != k)
            sink.add(v, _key_offset(body, o, v), context=" ".join(x for x in (ctx, others) if x), group=grp or _first_segment(v),
                     confidence="high")

    # --- R6 route calls
    for m in _TANSTACK.finditer(body):
        path = m.group(1)
        if not is_path(path):
            continue
        window = body[m.end(): m.end() + 3000]
        nxt = _TANSTACK.search(window)
        if nxt:
            window = window[: nxt.start()]
        parts = []
        t = _TITLE_NEAR.search(window)
        if t:
            parts.append(t.group(1))
        li = _LAZY_IMPORT.search(window)
        if li:
            parts.append(f"chunk={li.group(1)}")
        sink.add(path, m.start(1), context=" ".join(parts), group=_first_segment(path), confidence="high")
    for m in _STRIPE_GROUP.finditer(body):
        name, base = m.group(1), m.group(2)
        if not is_path(base):
            continue
        sink.add(base, m.start(2), context=name, group=name, confidence="high")
        lit = next((l for l in objs if l.start == m.end() - 1), None)
        if lit is None:
            continue
        for k, v in zip(lit.keys, lit.values):
            if isinstance(v, str) and v not in _PLACEHOLDERS and _UPPER.match(k) and v.startswith("/") and is_path(base.rstrip("/") + v):
                sink.add(base.rstrip("/") + v, _key_offset(body, lit, v), context=f"{k} ({name})", group=name, confidence="high")

    # --- R7 href="/path"
    for m in _HREF.finditer(body):
        path = m.group(1)
        if not is_path(path) or path in sink.seen:
            continue
        tail = body[m.end(): m.end() + 2000]
        tail = tail.split(">", 1)[1] if ">" in tail else ""          # the rest of the opening tag is not text
        tail = tail.split("</a>", 1)[0].split("`", 1)[0]
        tail = re.sub(r"<(svg|style|script)\b.*?</\1>|<[^>]*$", " ", tail, flags=re.S)
        text = _clip(_TAG.sub(" ", tail), 120)
        aria = _ARIA.search(body[max(0, m.start() - 200): m.end() + 200])
        ctx = " ".join(x for x in (aria.group(1) if aria else "", text) if x)
        sink.add(path, m.start(1), context=ctx, group=_first_segment(path), confidence="medium")

    # --- R8 fallback literals
    n = 0
    for m in _LITERAL.finditer(body):
        if n >= _FALLBACK_CAP:
            break
        path = m.group(1)
        if path in sink.seen or not _HAS_LETTER.search(path) or not is_path(path):
            continue
        s, e = max(0, m.start() - 60), min(len(body), m.end() + 60)
        if sink.add(path, m.start(1), context=body[s:e], group=_first_segment(path), confidence="low"):
            n += 1
    return sink.out
