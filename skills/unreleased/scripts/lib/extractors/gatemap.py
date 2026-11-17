"""gatemap extractor: gate maps, gate lists, gate definitions and named configs read from balanced literals.

Classifiers (all over `scanner.iter_literals`; see plan-v1.md U2 and the Figma/Clarity/PostHog readers):

- gate map: an object with >= 8 keys whose values are >= 90% booleans or 0/1 (Figma `labmate_data.statsig`,
  Asana `experimentVariants`). Every key is reported with its value: the off gates are the product.
- enabled map: an object with >= 8 keys whose values are objects of the form `{enabled: bool}` (Clarity `features`).
- gate list: an array of >= 30 uniform kebab/snake strings (PostHog `persisted_feature_flags`), or any array of
  identifier-like strings under a key named `*flags`/`*gates` (Stripe `betaFlags`). Value is None.
- identity enum of gate names: `{x_beta_1:"x_beta_1", ...}` with >= 8 keys, half of them gate-ish (Stripe `C.oX`).
- gate definition: `{name:"x", description:"...", default:!1}` (Spotify Remote Config registry); value = default,
  context = the description.
- proto field named like a gate: `{no:53, name:"x_enabled", kind:"enum"}` (Dropbox); value None, confidence low.
- named config: a key matching `*_config`, `*_configs`, `*_models`, `*_per_feature` or `dynamic_configs` whose
  value is a literal, plus every child of a `dynamic_configs`/`*_configs` object. Context and value are a compact
  rendering (<= 200 chars) of the literal so a later run can diff it by value.

Pure function; no network, no file writes. Noise is a later stage's job (noise.py); only the obvious is avoided here.
"""
from __future__ import annotations
import re
from schema import Observation, Source
import scanner

VERSION = "0.1.0"

MIN_KEYS = 8            # a gate map needs this many keys
BOOL_SHARE = 0.9        # ... and this share of boolean / 0-1 values
LIST_MIN = 30           # an unnamed array needs this many uniform strings to count as a gate list
CONTEXT_MAX = 200

_CONFIG_KEY = re.compile(r"(?:_config|_configs|_models|_per_feature)$|^dynamic_configs$")
_CONFIG_PARENT = re.compile(r"(?:^|_)configs$")
_FLAG_LIST_KEY = re.compile(r"(?:^|[_\-])(?:flag|gate)s?$|(?:Flag|Gate)s?$|^(?:FLAG|GATE)S?$")
_GATEISH_NAME = re.compile(r"(?:_enabled|_disabled|_variant|_rollout|_flag|_gate|_beta|_alpha|_beta_\d+|_alpha_\d+|_experiment|_exp)$|^(?:enable|is|show|use|ff)_")
_KEBAB_SNAKE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)+$")
_IDENT = re.compile(r"^[A-Za-z0-9][\w.:-]*$")
_NAME_BEFORE = re.compile(r"""(?:"((?:\\.|[^"\\])+)"|'((?:\\.|[^'\\])+)'|([A-Za-z_$][\w$]*))\s*[:=]\s*$""")
_WS = re.compile(r"\s+")


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


def _name_before(body: str, start: int) -> str:
    """The key or identifier that names a literal: `"statsig":{`, `experiments=[`, `window.X = {`."""
    m = _NAME_BEFORE.search(body[max(0, start - 80):start])
    if not m:
        return ""
    return next(g for g in m.groups() if g is not None)


def _value_offset(body: str, key_off: int, value: str) -> int:
    """Offset of the quoted string `value` that follows the key at `key_off` (the receipt points at the name itself)."""
    i = body.find(value, key_off, key_off + len(value) + 80)
    return i if i != -1 else key_off


def _is_bool01(v) -> bool:
    return isinstance(v, bool) or v in (0, 1)


def _compact(text: str, limit: int = CONTEXT_MAX) -> str:
    t = _WS.sub(" ", text).strip()
    return t if len(t) <= limit else t[:limit - 1] + "…"


# --- the extractor -----------------------------------------------------------------------------------------

def extract(body: str, artifact: Source) -> list[Observation]:
    lits = list(scanner.iter_literals(body))
    by_span = {(l.start, l.end): l for l in lits}
    parent_of: dict[tuple[int, int], scanner.Literal] = {}
    for l in lits:
        for span in l._children:
            parent_of[span] = l
    names: dict[tuple[int, int], str] = {}

    def path(l: scanner.Literal) -> str:
        """Dotted names of the literal and up to two ancestors: `labmate_data.statsig`."""
        parts, cur, hops = [], l, 0
        while cur is not None and hops < 3:
            span = (cur.start, cur.end)
            if span not in names:
                names[span] = _name_before(body, cur.start)
            if names[span]:
                parts.append(names[span])
            cur = parent_of.get(span); hops += 1
        return ".".join(reversed(parts))

    out: list[Observation] = []
    seen: set[tuple[str, str, int]] = set()

    def emit(kind, key, offset, value=None, context="", group="", confidence="high", **kw):
        if not key or (kind, key, offset) in seen:
            return
        seen.add((kind, key, offset))
        src = Source(url=artifact.url, sha256=artifact.sha256, offset=offset,
                     first_party=artifact.first_party, attribution=artifact.attribution)
        out.append(Observation(id="", kind=kind, key=key, source=src, value=value, context=context[:CONTEXT_MAX],
                               group=group, extractor="gatemap", confidence=confidence, **kw))

    for lit in lits:
        if lit.kind == "object":
            pairs = _pairs(lit)
            if not pairs:
                continue
            keys = [p[0] for p in pairs]
            values = [p[1] for p in pairs]
            n = len(pairs)

            # gate map: >= 8 keys, >= 90% boolean / 0-1 values
            nb = sum(1 for v in values if _is_bool01(v))
            if n >= MIN_KEYS and nb >= BOOL_SHARE * n:
                name = path(lit)
                on = sum(1 for v in values if v is True or v == 1)
                ctx = f"{name or 'gate map'}: {n} keys, {on} on"
                for k, v, off, span in pairs:
                    if span is None and v not in ("fn", "ref"):
                        emit("gate", k, off, value=v, context=ctx, group=name)
                continue

            # enabled map: >= 8 keys whose values are `{enabled: bool}` objects
            child_pairs = [(k, by_span.get(span), off) for k, v, off, span in pairs if span is not None and v == "{}"]
            if n >= MIN_KEYS and len(child_pairs) >= BOOL_SHARE * n:
                enabled = []
                for k, child, off in child_pairs:
                    if child is None:
                        continue
                    cp = {ck: cv for ck, cv, _, _ in _pairs(child)}
                    if "enabled" in cp and _is_bool01(cp["enabled"]) and len(cp) <= 4:
                        enabled.append((k, cp["enabled"], off))
                if len(enabled) >= BOOL_SHARE * len(child_pairs):
                    name = path(lit)
                    on = sum(1 for _, v, _ in enabled if v is True or v == 1)
                    ctx = f"{name or 'enabled map'}: {len(enabled)} keys, {on} on"
                    for k, v, off in enabled:
                        emit("gate", k, off, value=v, context=ctx, group=name)
                    continue

            # identity enum of gate names: {x_beta_1:"x_beta_1", ...}
            if n >= MIN_KEYS and sum(1 for k, v in zip(keys, values) if v == k) >= BOOL_SHARE * n \
                    and sum(1 for k in keys if _GATEISH_NAME.search(k)) >= 0.5 * n:
                name = path(lit)
                ctx = f"{name or 'gate name enum'}: {n} names"
                for k, v, off, _ in pairs:
                    if v == k:
                        emit("gate", k, off, value=None, context=ctx, group=name, confidence="medium")
                continue

            kv = dict(zip(keys, values))

            # gate definition: {name:"x", description:"...", default:!1}
            dname = kv.get("name") if isinstance(kv.get("name"), str) else kv.get("key") if isinstance(kv.get("key"), str) else None
            dflt = kv["default"] if "default" in kv else kv.get("defaultValue")
            if dname and _IDENT.match(dname) and _is_bool01(dflt) and n <= 8:
                desc = kv.get("description") if isinstance(kv.get("description"), str) else ""
                off = _value_offset(body, next(o for k, _, o, _ in pairs if k in ("name", "key")), dname)
                emit("gate", dname, off, value=dflt, context=desc or f"gate definition in {path(lit) or 'registry'}",
                     group=path(lit), default=dflt)
                continue

            # proto field descriptor named like a gate: {no:53, name:"x_enabled", kind:"enum"}
            if {"no", "name", "kind"} <= set(keys) and isinstance(kv["name"], str) and _GATEISH_NAME.search(kv["name"]):
                off = _value_offset(body, next(o for k, _, o, _ in pairs if k == "name"), kv["name"])
                emit("gate", kv["name"], off, value=None, context=f"proto field no={kv['no']} kind={kv['kind']}",
                     group=path(lit), confidence="low")
                continue

            # named configs: *_config / *_models / *_per_feature / dynamic_configs keys with literal values,
            # and every child of a dynamic_configs / *_configs object
            own = _name_before(body, lit.start)
            parent_is_configs = bool(own and _CONFIG_PARENT.search(own))
            for k, v, off, span in pairs:
                if span is None:
                    if parent_is_configs and v not in ("fn", "ref", None):
                        emit("config", k, off, value=v, context=_compact(repr(v)), group=own)
                    continue
                if parent_is_configs or _CONFIG_KEY.search(k):
                    child = by_span.get(span)
                    rendering = _compact(child.text if child else body[span[0]:span[1]])
                    emit("config", k, off, value=rendering, context=rendering, group=own if parent_is_configs else path(lit))

        else:  # array
            items = _items(lit)
            if not items:
                continue
            name = _name_before(body, lit.start)
            named = bool(name and _FLAG_LIST_KEY.search(name))
            idents = [s for s, _ in items if _IDENT.match(s)]
            if named and len(idents) == len(items):
                for s, off in items:
                    emit("gate", s, off, value=None, context=f"{name}: list of {len(items)}", group=name, confidence="medium")
                continue
            if len(items) >= LIST_MIN and len(idents) == len(items):
                uniform = sum(1 for s, _ in items if _KEBAB_SNAKE.match(s))
                avg = sum(len(s) for s, _ in items) / len(items)
                if uniform >= BOOL_SHARE * len(items) and avg >= 8:
                    ctx = f"{name or 'string list'}: list of {len(items)}"
                    for s, off in items:
                        emit("gate", s, off, value=None, context=ctx, group=name, confidence="medium")
    return out
