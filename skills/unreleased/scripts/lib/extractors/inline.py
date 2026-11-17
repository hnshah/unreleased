"""inline extractor: values read from page-level objects (kind "inline").

Where the values come from (see plan-v1.md U2 and the Vercel/Zoom/Slack/Asana/Spotify/Hugging Face readers):

- `<script type="application/json" ...>` blocks: a block whose tag carries a flag attribute (`data-flag-values`) yields
  every top-level key with its value (Vercel). Any other JSON block (Next `__NEXT_DATA__`, Figma `data-initial`,
  PostHog `posthog-app-context`) yields its flag-named objects in full (`featureFlags`, `experiments`, ...) and,
  elsewhere, its server-prop booleans: `can*`, `is*`, `has*`, `show*`, `enable*`, `should*`, `allow*`, `use*` keys
  with boolean values. Objects that are gate maps (>= 8 keys, >= 90% boolean) are left to the gatemap extractor.
- `window.X = {...}` / `window.X.Y = {...}` assignments and flag-named assignments such as
  `TD.boot_data.experiments = [...]`, `window.experimentVariants = {...}`: every scalar key with its value, or every
  string item of the array (`name.arm` items split into key = name, value = arm).
- `data-*="{...}"` HTML attributes holding entity-encoded JSON (`data-props`, `data-flag-values`): decoded, then
  read like a JSON block.

Context and group are the object's or attribute's name. Values come from balanced literals, so confidence is high.
Pure function; no network, no file writes.
"""
from __future__ import annotations
import html
import re
from schema import Observation, Source
import scanner

VERSION = "0.1.0"

CONTEXT_MAX = 200
GATE_MAP_MIN = 8
GATE_MAP_SHARE = 0.9

_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S | re.I)
_JSON_TYPE = re.compile(r"""type\s*=\s*["']?application/(?:json|ld\+json)""", re.I)
_FLAG_ATTR = re.compile(r"""(data-[\w-]*(?:flag|gate|experiment|feature)[\w-]*)""", re.I)
_DATA_ATTR = re.compile(r"""\s(data-[\w-]+)\s*=\s*"(\{(?:&quot;|&#34;|[^"])*\})\"""")
_ASSIGN = re.compile(r"""(?<![\w$.])((?:window|self|globalThis)\.[\w$]+(?:\.[\w$]+)*|[\w$]+(?:\.[\w$]+)*)\s*=\s*(?=[{\[])""")
_FLAGGY = re.compile(r"(?:^|[_\-])(?:experiment|flag|gate|feature|variant)s?$|(?:Experiment|Flag|Gate|Feature|Variant)s?$"
                     r"|^(?:EXPERIMENT|FLAG|GATE|FEATURE|VARIANT)S?$|^__(?:EXPERIMENTS|FLAGS)__$")
_GLOBAL = re.compile(r"^(?:window|self|globalThis)\.")
_SERVER_PROP = re.compile(r"^(?:can|is|has|show|enable|should|allow|use)(?:[A-Z_]|$)")
_ARM = re.compile(r"^([A-Za-z][\w-]*(?:[._-][\w-]+)*?)\.([A-Za-z][\w-]*)$")


# --- literal helpers (offsets and child spans; the scanner's shallow parse keeps neither) -------------------

def _pairs(lit: scanner.Literal):
    """(key, value, key_offset, child_span) for one object literal, in source order. Mirrors Literal._parsed."""
    src = lit._text
    children = list(lit._children)
    out = []
    for (gs, ge), nxt in zip(lit._gaps(), children + [None]):
        gap = src[gs:ge]
        for m in scanner._PAIR.finditer(gap):
            k = m.group(1) if m.group(1) is not None else m.group(2) if m.group(2) is not None else m.group(3)
            if k is None:
                continue
            if "\\" in k:
                k = scanner.unescape(k)
            v = m.group(4)
            off = gs + m.start()
            if v is not None:
                out.append((k, scanner._scalar(v), off, None))
            else:
                tail = gap[m.end():m.end() + 40]
                if scanner._FN_HINT.match(tail):
                    out.append((k, "fn", off, None))
                elif m.end() >= len(gap.rstrip()) and nxt is not None:
                    out.append((k, "{}" if src[nxt[0]] == "{" else "[]", off, nxt))
                elif re.match(r"\s*[A-Za-z_$][\w$.]*", tail):
                    out.append((k, "ref", off, None))
                else:
                    out.append((k, None, off, None))
    return out


def _items(lit: scanner.Literal):
    """(string_item, offset) for the scalar string items of one array literal."""
    src = lit._text
    out = []
    for gs, ge in lit._gaps():
        for m in scanner._ITEM.finditer(src[gs:ge]):
            tok = m.group(1)
            if tok and tok[0] in "\"'`":
                out.append((tok[1:-1], gs + m.start()))
    return out


def _is_scalar(v) -> bool:
    return v is None or isinstance(v, (bool, int, float, str)) and v not in ("fn", "ref", "{}", "[]")


def _is_gate_map(pairs) -> bool:
    n = len(pairs)
    return n >= GATE_MAP_MIN and sum(1 for _, v, _, _ in pairs if isinstance(v, bool) or v in (0, 1)) >= GATE_MAP_SHARE * n


class _Emitter:
    def __init__(self, body: str, artifact: Source):
        self.body, self.artifact, self.out, self.seen = body, artifact, [], set()

    def emit(self, key: str, offset: int, value, context: str, confidence: str = "high"):
        if not key or (key, offset) in self.seen:
            return
        self.seen.add((key, offset))
        src = Source(url=self.artifact.url, sha256=self.artifact.sha256, offset=offset,
                     first_party=self.artifact.first_party, attribution=self.artifact.attribution)
        self.out.append(Observation(id="", kind="inline", key=key, source=src, value=value, context=context[:CONTEXT_MAX],
                                    group=context[:CONTEXT_MAX], extractor="inline", confidence=confidence))

    def object_all(self, lit: scanner.Literal, base: int, name: str, offset_of=None):
        """Every scalar pair of a named page-level object."""
        for k, v, off, _ in _pairs(lit):
            if _is_scalar(v):
                self.emit(k, offset_of(k) if offset_of else base + off, v, name)

    def array_all(self, lit: scanner.Literal, base: int, name: str, offset_of=None):
        """Every string item of a named experiment/flag array; `name.arm` items split into key and value."""
        for s, off in _items(lit):
            m = _ARM.match(s)
            key, val = (m.group(1), m.group(2)) if m and "_" in m.group(1) else (s, None)
            self.emit(key, offset_of(s) if offset_of else base + off, val, name)

    def sweep(self, text: str, base: int, name: str, offset_of=None):
        """A JSON block or decoded attribute: flag-named objects in full, server-prop booleans elsewhere."""
        lits = list(scanner.iter_literals(text))
        by_span = {(l.start, l.end): l for l in lits}
        claimed: set[tuple[int, int]] = set()
        for lit in lits:
            if lit.kind != "object":
                continue
            for k, v, off, span in _pairs(lit):
                if span is None or not _FLAGGY.search(k):
                    continue
                child = by_span.get(span)
                if child is None:
                    continue
                claimed.add(span)
                label = f"{name}.{k}" if name else k
                if child.kind == "object":
                    self.object_all(child, base, label, offset_of)
                else:
                    self.array_all(child, base, label, offset_of)
        for lit in lits:
            if lit.kind != "object" or (lit.start, lit.end) in claimed:
                continue
            pairs = _pairs(lit)
            if _is_gate_map(pairs):
                continue
            for k, v, off, _ in pairs:
                if isinstance(v, bool) and _SERVER_PROP.match(k):
                    self.emit(k, offset_of(k) if offset_of else base + off, v, name)


def _segments(body: str) -> list[tuple[int, str]]:
    """(offset, text) of each <script> body, then the whole body (which also covers a script cut off mid-way;
    HTML prose with stray quotes can hide a literal from the whole-body scan, so the per-script scan goes first)."""
    return [(m.start(2), m.group(2)) for m in _SCRIPT.finditer(body)] + [(0, body)]


def extract(body: str, artifact: Source) -> list[Observation]:
    em = _Emitter(body, artifact)

    # 1. <script type="application/json"> blocks
    for m in _SCRIPT.finditer(body):
        attrs, text = m.group(1), m.group(2)
        if not _JSON_TYPE.search(attrs) or not text.strip():
            continue
        base = m.start(2)
        fa = _FLAG_ATTR.search(attrs)
        if fa:
            name = fa.group(1)
            for lit in scanner.iter_literals(text):
                if lit.depth == 0:
                    (em.object_all if lit.kind == "object" else em.array_all)(lit, base, name)
            continue
        idm = re.search(r"""\bid\s*=\s*["']([^"']+)["']""", attrs)
        em.sweep(text, base, idm.group(1) if idm else "application/json")

    # 2. window.X = {...} and flag-named assignments inside scripts (or the whole body when it is a script)
    for base, text in _segments(body):
        by_start = {l.start: l for l in scanner.iter_literals(text)}
        for m in _ASSIGN.finditer(text):
            name = m.group(1)
            last = name.rsplit(".", 1)[-1]
            if not (_GLOBAL.match(name) or _FLAGGY.search(last)):
                continue
            lit = by_start.get(m.end())
            if lit is None:
                continue
            if lit.kind == "object":
                em.object_all(lit, base, name)
            elif _FLAGGY.search(last):
                em.array_all(lit, base, name)

    # 3. data-*="{...}" attributes holding entity-encoded JSON
    for m in _DATA_ATTR.finditer(body):
        attr, raw = m.group(1), m.group(2)
        text = html.unescape(raw)
        a0, a1 = m.start(2), m.end(2)

        def offset_of(key, a0=a0, a1=a1):
            i = body.find(key, a0, a1)
            return i if i != -1 else a0

        if _FLAG_ATTR.search(attr):
            for lit in scanner.iter_literals(text):
                if lit.depth == 0:
                    (em.object_all if lit.kind == "object" else em.array_all)(lit, 0, attr, offset_of)
        else:
            em.sweep(text, 0, attr, offset_of)
    return em.out
