"""registry extractor: dense tables of named constants. See GLOSSARY "Registry" and plan-v1.md U2.

Shapes claimed, in order:
  R1 constant tables   `{UPPER_SNAKE:"kebab-or-snake", …}` with >= 20 pairs (Loom's 372 flag names, Supabase's
                       `UI_PREVIEW_*` local-storage keys in backticks, Stripe's SETTINGS_* route names and its
                       1,949-entry route→owner map). When the values are 1:1 identifiers the value is the key
                       (it is the name the flag service knows); when many names share a value (an owner map) or
                       the values are paths, the constant NAME is the key and the value is kept as `value`.
  R2 keyed entries     `name_key:{name:"Human",jira:"TEAM"}` runs of >= 20 (Stripe's project registry); the
                       preceding property name is the key, found by look-back so a cut excerpt still works.
  R3 assignment runs   `e.ErrorTracking=`error-tracking`,e.IssuesV0=`issues-v0`,…` of >= 20 identifier values
                       (Amplitude's 695-flag enum). Regex over strings; values are the keys.
  R4 string arrays     balanced arrays of >= 20 identifier strings (Stripe's permission and property lists), and
                       any identifier array or map under a registry noun (`plans:[…]`, `flags:[…]`, `gates:{…}`).
  R5 accessor families a minified accessor reading >= 3 flag-scheme strings (`(0,_._)("project_vulpix_ui")`,
                       `site.get("hud_enabled")`): Netlify's Pokémon flags. Pattern-only, so confidence "low".
  R6 route groups      `$("revenueStarter","/accounting",{…})` families of >= 20: the group name is the key.
Inlined JSON (`JSON.parse('…')`, how webpack ships JSON modules) is decoded and scanned too (R1/R2/R4), with
receipts pointing at the key inside the string in the body.
"""
from __future__ import annotations
import hashlib
import re
from dataclasses import replace

from schema import Observation, Source
import scanner

VERSION = "0.1.0"
NAME = "registry"
_CTX = 200
_MIN_TABLE = 20
_MIN_FAMILY = 1          # the flag scheme does the filtering; one accessor read of a flag-scheme key is a read
_UPPER = re.compile(r"^[A-Z][A-Z0-9_]*$")
_IDENT = re.compile(r"^[A-Za-z0-9/][\w.:/-]{0,119}$")                      # no spaces: a token or a path, not prose
_IDENT_SEP = re.compile(r"^[a-z][a-z0-9]*(?:[-_.:/][a-z0-9]+)+$")          # kebab / snake / dotted
_PATH = re.compile(r"^/")
_FLAG_SCHEME = re.compile(r"^(?:project|ops|ff|flag|flags|feature|features|exp|experiment|rollout|gate|enable|release)[_-][a-z0-9_-]+$"
                          r"|^[a-z][a-z0-9_-]*[_-](?:ui|enabled|flag|gate|experiment|rollout|beta|preview)$")
_NOUNS = frozenset({"plans", "flags", "features", "experiments", "gates", "permissions", "skus", "tiers", "addons",
                    "capabilities", "scopes", "entitlements", "feature_flags", "featureFlags", "flag_keys", "gate_names"})
_ENTRY_KEYS = frozenset({"name", "jira", "owner", "team", "ticket", "description", "label", "title", "slack", "channel"})
_ENTRY_TAGS = ("jira", "owner", "team", "ticket")
_KEY_BEFORE = re.compile(r'(?:"((?:\\.|[^"\\])*)"|\'((?:\\.|[^\'\\])*)\'|([A-Za-z_$][\w$]*))\s*:\s*$')
_VAR_BEFORE = re.compile(r'(?:\b(?:var|let|const)\s+)?([A-Za-z_$][\w$]*)\s*=\s*$')
_ASSIGN = re.compile(r'\b([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)\s*=\s*(?:"((?:\\.|[^"\\\n])*)"|\'((?:\\.|[^\'\\\n])*)\'|`((?:\\.|[^`\\$])*)`)')
_ACCESSOR = re.compile(r'(?:\(0,\s*[A-Za-z_$][\w$]*\.([A-Za-z_$][\w$]*)\)|\.(get|has|getIn|is|isEnabled|flag|variation))\(\s*"([a-z][a-z0-9_-]{2,80})"')
_ROUTE_GROUP = re.compile(r'(?<![\w$.])([A-Za-z_$][\w$]*)\(\s*"([A-Za-z][\w]{1,60})"\s*,\s*"(/[^"\n]{0,160})"\s*,\s*\{')
_JSON_PARSE = re.compile(r'JSON\.parse\(\s*(?:\'((?:\\.|[^\'\\])*)\'|"((?:\\.|[^"\\])*)")\s*\)')
_HUMAN = re.compile(r'"([A-Z][^"\\]{3,80}?[a-z][^"\\]*?)"')


def _oid(kind: str, key: str, src: Source) -> str:
    return hashlib.sha1(f"{kind}|{key}|{src.sha256}|{src.offset}".encode("utf-8")).hexdigest()[:16]


def _prefix(key: str) -> str:
    return re.split(r"[-_./:]", key, maxsplit=1)[0] if key else ""


def _is_str(v) -> bool:
    return isinstance(v, str) and v not in ("fn", "ref", "{}", "[]") and "${" not in v


class _Sink:
    """Collects observations; resolves receipts for text that is a decoded `JSON.parse('…')` payload."""

    def __init__(self, body: str, artifact: Source):
        self.body, self.artifact, self.out, self.seen = body, artifact, [], set()

    def add(self, key: str, local_off: int, base: tuple[int, int] | None, *, value=None, context="", group="",
            confidence="high", params=None):
        if base is None:
            off = local_off
        else:   # inside an inlined JSON string: the receipt is the key's spelling inside that string
            off = self.body.find('"' + key + '"', base[0], base[1])
            off = off + 1 if off != -1 else base[0]
        if (key, off) in self.seen:
            return
        self.seen.add((key, off))
        src = replace(self.artifact, offset=off)
        self.out.append(Observation(id=_oid(NAME, key, src), kind="registry", key=key, source=src, value=value,
                                    params=params or [], group=group or _prefix(key), context=context[:_CTX],
                                    extractor=NAME, confidence=confidence))


def _find_quoted(text: str, s: str, lo: int, hi: int) -> int:
    """Offset of `s` inside its quotes (any of the three) within [lo, hi), or lo."""
    for q in ('"', "'", "`"):
        off = text.find(q + s + q, lo, hi)
        if off != -1:
            return off + 1
    return lo


def _find_prop(text: str, key: str, lo: int, hi: int) -> int:
    """Offset of `key:` as a property name inside [lo, hi), or lo."""
    pos = lo
    while True:
        pos = text.find(key, pos, hi)
        if pos == -1:
            return lo
        before = text[pos - 1] if pos > 0 else ""
        after = text[pos + len(key):pos + len(key) + 1]
        if (before in "{,\"'" or before.isspace()) and (after in ":\"'" or after.isspace()):
            return pos          # `find` landed on the key text itself, quoted or bare
        pos += len(key)


def _look_back_name(text: str, pos: int, limit: int = 80) -> str:
    """The property or variable name a literal at `pos` is assigned to, if any."""
    head = text[max(0, pos - limit):pos]
    m = _KEY_BEFORE.search(head) or _VAR_BEFORE.search(head)
    if not m:
        return ""
    return next((g for g in m.groups() if g is not None), "")


def _structural(text: str, base: tuple[int, int] | None, sink: _Sink) -> None:
    """R1, R2 and R4 over balanced literals in `text` (the body, or one decoded JSON payload)."""
    lits = list(scanner.iter_literals(text))
    parent_of = {span: p for p in lits for span in p._children}
    entry_clusters: dict[frozenset, list] = {}
    for l in lits:
        if l.kind == "object":
            ks, vs = l.keys, l.values
            if not ks:
                continue
            # R1 constant table
            upper = sum(1 for k in ks if _UPPER.match(k))
            pairs = [(k, v) for k, v in zip(ks, vs) if _UPPER.match(k) and _is_str(v) and (v == "" or _IDENT.match(v))]
            if len(pairs) >= _MIN_TABLE and upper >= 0.9 * len(ks):
                table = _look_back_name(text, l.start)
                vals = [v for _, v in pairs]
                one_to_one = len(set(vals)) >= 0.9 * len(vals) and not any(_PATH.match(v) for v in vals)
                for k, v in pairs:
                    if one_to_one:
                        if not v:
                            continue
                        sink.add(v, _find_quoted(text, v, l.start, l.end), base, value=v, context=f"{k} in {table}" if table else k,
                                 group=table or _prefix(v))
                    else:
                        sink.add(k, _find_prop(text, k, l.start, l.end), base, value=v, context=f"{v} ({table})" if table else v,
                                 group=v if (v and not _PATH.match(v)) else table)
                continue
            # R2 keyed entries: {name:"Human", jira:"TEAM"} clustered by signature, keyed by the preceding property
            kset = set(ks)
            if 2 <= len(ks) <= 6 and "name" in kset and kset <= _ENTRY_KEYS and any(t in kset for t in _ENTRY_TAGS):
                entry_clusters.setdefault(frozenset(ks), []).append(l)
            # R4 named map: `gates:{"x":{…},"y":{…}}` under a registry noun
            name = _look_back_name(text, l.start)
            if name in _NOUNS and len(ks) >= 2 and all(_IDENT_SEP.match(k) for k in ks):
                for k in ks:
                    sink.add(k, _find_prop(text, k, l.start, l.end), base, context=f"{name} key", group=name, confidence="medium")
        else:
            items = [i for i in l.items if _is_str(i)]
            if not items or len(items) < 0.9 * len(l.items):
                continue
            name = _look_back_name(text, l.start)
            dense = len(items) >= _MIN_TABLE and sum(1 for i in items if _IDENT_SEP.match(i)) >= 0.9 * len(items)
            named = name in _NOUNS and all(_IDENT.match(i) for i in items)
            if not (dense or named):
                continue
            p = parent_of.get((l.start, l.end))
            table = name or (_look_back_name(text, p.start) if p is not None else "")
            for i in items:
                if not _IDENT.match(i):
                    continue
                sink.add(i, _find_quoted(text, i, l.start, l.end), base, context=f"in {table}" if table else "list",
                         group=table or _prefix(i), confidence="medium")
    for sig, entries in entry_clusters.items():
        if len(entries) < _MIN_TABLE:
            continue
        for l in entries:
            head = text[max(0, l.start - 80):l.start]
            m = _KEY_BEFORE.search(head)
            if not m:
                continue
            key = next((g for g in m.groups() if g is not None), "")
            if not key or not _IDENT.match(key):
                continue
            pairs = dict(zip(l.keys, l.values))
            off = l.start - len(head) + m.start() + (1 if head[m.start()] in "\"'" else 0)
            tag = next((pairs[t] for t in _ENTRY_TAGS if _is_str(pairs.get(t))), "")
            human = pairs.get("name") if _is_str(pairs.get("name")) else ""
            sink.add(key, off, base, value=human, context=" · ".join(x for x in (human, tag) if x), group=tag or _prefix(key))


def _assignment_runs(body: str, sink: _Sink) -> None:
    """R3: `obj.Prop="value"` runs; a run is consecutive assignments on the same object with <= 3 bytes between."""
    run, last_end, last_obj = [], -1, None

    def flush():
        if len(run) >= _MIN_TABLE:
            vals = [v for _, _, v, _, _ in run]
            if sum(1 for v in vals if _IDENT.match(v)) >= 0.9 * len(vals):
                unique = len(set(vals)) >= 0.9 * len(vals)
                for obj, prop, v, prop_off, val_off in run:
                    if not _IDENT.match(v):
                        continue
                    if unique:
                        sink.add(v, val_off, None, value=v, context=f"{obj}.{prop}", group=_prefix(v), confidence="medium")
                    else:
                        sink.add(prop, prop_off, None, value=v, context=f"{obj}.{prop} = {v}", group=obj, confidence="medium")
        run.clear()

    for m in _ASSIGN.finditer(body):
        obj, prop = m.group(1), m.group(2)
        v = next(g for g in m.groups()[2:] if g is not None)
        if m.start() - last_end > 3 or obj != last_obj:
            flush()
        run.append((obj, prop, v, m.start(2), m.end() - 1 - len(v)))
        last_end, last_obj = m.end(), obj
    flush()


def _accessor_families(body: str, sink: _Sink) -> None:
    """R5: one accessor reading >= 3 flag-scheme strings."""
    fam: dict[str, list] = {}
    for m in _ACCESSOR.finditer(body):
        member, key = m.group(1) or m.group(2), m.group(3)
        if _FLAG_SCHEME.match(key):
            fam.setdefault(member, []).append((key, m.start(3)))
    for member, hits in fam.items():
        if len(hits) < _MIN_FAMILY:
            continue
        for key, off in hits:
            window = body[max(0, off - 200):off + 200]
            human = [h for h in _HUMAN.findall(window) if " " in h]
            ctx = f"{member}() read" + (" · " + " / ".join(human[:3]) if human else "")
            sink.add(key, off, None, context=ctx, group=_prefix(key), confidence="low")


def _route_groups(body: str, sink: _Sink) -> None:
    """R6: `callee("groupName","/path",{…})` families of >= 20 named route groups."""
    fam: dict[str, list] = {}
    for m in _ROUTE_GROUP.finditer(body):
        fam.setdefault(m.group(1), []).append((m.group(2), m.group(3), m.start(2)))
    for callee, hits in fam.items():
        if len(hits) < _MIN_TABLE or len({n for n, _, _ in hits}) < 0.9 * len(hits):
            continue
        for name, path, off in hits:
            sink.add(name, off, None, value=path, context=f"{path} route group ({callee})", group=_prefix(path.strip("/")) or callee,
                     confidence="medium")


def _unescape_js(s: str) -> str:
    out = _unescape_js_raw(s)
    try:
        return out.encode("utf-16", "surrogatepass").decode("utf-16", "replace")   # rejoin \\ud83d\\ude80 (review S6)
    except UnicodeError:
        return out


def _unescape_js_raw(s: str) -> str:
    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", lambda m: {"n": "\n", "t": "\t", "r": "\r", "'": "'", '"': '"', "\\": "\\", "/": "/"}.get(m.group(1), "\\" + m.group(1)) if len(m.group(1)) == 1 else chr(int(m.group(1)[1:], 16)), s)


def extract(body: str, artifact: Source) -> list[Observation]:
    sink = _Sink(body, artifact)
    _structural(body, None, sink)
    for m in _JSON_PARSE.finditer(body):
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        if len(raw) < 20:
            continue
        _structural(_unescape_js(raw), (m.start(), m.end()), sink)
    _assignment_runs(body, sink)
    _accessor_families(body, sink)
    _route_groups(body, sink)
    sink.out.sort(key=lambda o: o.source.offset)
    return sink.out
