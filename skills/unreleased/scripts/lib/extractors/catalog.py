"""catalog extractor: arrays, sibling runs or keyed maps of object literals that share an identity key and
metadata (team, scope, fallback, variants, description, …). One observation per entry, with the entry's
fallback/default as the value and its metadata compacted into `context`. See plan-v1.md U2, GLOSSARY "Catalog".

Shapes claimed (all read from balanced literals, so confidence is "high"):
  A. entries     `[{key:"x",team:"t",scope:"s",fallback:{…}}, …]` — an array, or sibling top-level objects
                 (Lovable's flag-catalog chunk is `var a={key:…},b={key:…}` with no array around them).
  B. keyed map   `{"x":{team:…,statsigLink:…}, [v]:{…}}` — an object whose values are objects sharing >= 2
                 metadata keys; the entry's identity is the parent's key (Loom's LD→Statsig migration map).
A cluster needs >= 3 entries with the same identity key and >= 2 shared metadata keys.
"""
from __future__ import annotations
import hashlib
import re
from dataclasses import replace

from schema import Observation, Source
import scanner

VERSION = "0.1.0"
NAME = "catalog"

IDENTITY = ("key", "name", "id", "flag", "flagKey", "slug", "experimentId", "gateName", "featureKey")
META = ("team", "scope", "fallback", "defaultValue", "default", "variants", "description", "statsigLink",
        "owner", "type", "enabled", "rollout", "tags", "category", "newControlType", "useNewResult", "newKey",
        "authOnly", "experimentInclusion", "label", "title", "status", "createdAt", "updatedAt", "percentage",
        "allocation", "audience", "component", "ucrTicket")
_META_SET = frozenset(META)
_VALUE_KEYS = ("fallback", "defaultValue", "default")
_MIN_ENTRIES = 3
_CTX = 200

# What precedes a child literal when it is the value of a key: "k":{ | 'k':{ | k:{ | [v]:{
_KEY_BEFORE = re.compile(r'(?:"((?:\\.|[^"\\])*)"|\'((?:\\.|[^\'\\])*)\'|([A-Za-z_$][\w$]*)|\[([A-Za-z_$][\w$]*)\])\s*:\s*$')
_IDENT_LIKE = re.compile(r"^[A-Za-z0-9][\w.:/-]*$")


def _oid(kind: str, key: str, src: Source) -> str:
    return hashlib.sha1(f"{kind}|{key}|{src.sha256}|{src.offset}".encode("utf-8")).hexdigest()[:16]


def _parents(lits: list[scanner.Literal]) -> dict[tuple[int, int], scanner.Literal]:
    out = {}
    for p in lits:
        for span in p._children:
            out[span] = p
    return out


def _raw_pair(text: str, key: str) -> str | None:
    """The raw right-hand side of `key:` inside one object's text (for refs the scanner records as 'ref')."""
    m = re.search(r'(?:^|[,{])\s*"?' + re.escape(key) + r'"?\s*:\s*([^,}]+)', text)
    return m.group(1).strip() if m else None


def _display(v: object, raw: str | None) -> str:
    if v == "ref" and raw:
        return raw.split(".")[-1].strip("()")
    if isinstance(v, bool):
        return "on" if v else "off"
    if v is None:
        return "null"
    return str(v)


def _child_value(lit: scanner.Literal, parents: dict, by_span: dict, key: str):
    """The parsed value of `key` when it is a child literal (object -> dict, array -> list)."""
    for span in lit._children:
        cs = span[0]
        m = _KEY_BEFORE.search(lit.text[: cs - lit.start][-120:])
        if not m:
            continue
        k = next(g for g in m.groups() if g is not None)
        if k != key:
            continue
        child = by_span.get(span)
        if child is None:
            return None
        if child.kind == "object":
            return dict(zip(child.keys, child.values))
        return list(child.items)
    return None


def _context(lit: scanner.Literal, pairs: dict, skip: set[str]) -> str:
    parts = []
    for k in ("team", "scope", "owner", "category", "type", "status", "statsigLink", "jira"):
        if k in pairs and k not in skip:
            parts.append(f"{k}={_display(pairs[k], _raw_pair(lit.text, k))}")
    for k in ("description", "label", "title"):
        if k in pairs and isinstance(pairs[k], str) and pairs[k] not in ("fn", "ref", "{}", "[]"):
            parts.append(pairs[k])
    ctx = " ".join(parts)
    return ctx[:_CTX]


def _group(pairs: dict, lit: scanner.Literal, key: str) -> str:
    for k in ("team", "owner", "category"):
        if k in pairs and pairs[k] not in (None, "fn", "{}", "[]"):
            return _display(pairs[k], _raw_pair(lit.text, k))
    return re.split(r"[-_./:]", key, maxsplit=1)[0] if key else ""


def _emit(body: str, artifact: Source, lit: scanner.Literal, key: str, offset: int, pairs: dict,
          value, params: list[str], skip: set[str]) -> Observation:
    src = replace(artifact, offset=offset)
    return Observation(
        id=_oid(NAME, key, src), kind="catalog", key=key, source=src, value=value, params=params,
        group=_group(pairs, lit, key), context=_context(lit, pairs, skip), extractor=NAME, confidence="high")


def extract(body: str, artifact: Source) -> list[Observation]:
    lits = list(scanner.iter_literals(body))
    objs = [l for l in lits if l.kind == "object"]
    parents = _parents(lits)
    by_span = {(l.start, l.end): l for l in lits}
    out: list[Observation] = []
    seen: set[tuple[str, int]] = set()

    # --- A. entries: objects with an identity key and >= 2 metadata keys, clustered by parent + identity key
    clusters: dict[tuple, list] = {}
    for o in objs:
        ks = o.keys
        if len(ks) < 3 or len(ks) > 60:
            continue
        kset = set(ks)
        ident = next((k for k in IDENTITY if k in kset), None)
        if ident is None:
            continue
        meta = kset & _META_SET
        if len(meta) < 2:
            continue
        pairs = dict(zip(ks, o.values))
        val = pairs.get(ident)
        if not isinstance(val, str) or val in ("fn", "ref", "{}", "[]") or not _IDENT_LIKE.match(val) or len(val) > 120:
            continue
        p = parents.get((o.start, o.end))
        pkey = (p.start, p.end) if p is not None else None
        clusters.setdefault((pkey, ident), []).append((o, pairs, meta))
    for (pkey, ident), entries in clusters.items():
        if len(entries) < _MIN_ENTRIES:
            continue
        shared = set.intersection(*(m for _, _, m in entries))
        if len(shared) < 2:
            continue
        for o, pairs, _ in entries:
            key = pairs[ident]
            q = '"' + key + '"'
            off = body.find(q, o.start, o.end)
            if off == -1:
                q = "'" + key + "'"; off = body.find(q, o.start, o.end)
            off = off + 1 if off != -1 else o.start
            if (key, off) in seen:
                continue
            seen.add((key, off))
            value = None
            for vk in _VALUE_KEYS:
                if vk in pairs:
                    value = pairs[vk]
                    if value in ("{}", "[]"):
                        value = _child_value(o, parents, by_span, vk)
                    break
            params = _child_value(o, parents, by_span, "variants") if pairs.get("variants") == "[]" else []
            params = [str(x) for x in params] if isinstance(params, list) else []
            out.append(_emit(body, artifact, o, key, off, pairs, value, params, {ident}))

    # --- B. keyed map: an object whose child objects share >= 2 metadata keys; identity = the parent's key
    for p in objs:
        kids = [by_span[s] for s in p._children if s in by_span and by_span[s].kind == "object"]
        if len(kids) < _MIN_ENTRIES:
            continue
        metas = [set(k.keys) & _META_SET for k in kids]
        good = [(k, m) for k, m in zip(kids, metas) if len(m) >= 2]
        if len(good) < _MIN_ENTRIES or len(good) < 0.6 * len(kids):
            continue
        shared = set.intersection(*(m for _, m in good))
        if len(shared) < 2:
            continue
        for k, _ in good:
            head = body[max(p.start, k.start - 160):k.start]
            m = _KEY_BEFORE.search(head)
            if not m:
                continue
            name, var = (m.group(1) if m.group(1) is not None else m.group(2) if m.group(2) is not None else m.group(3)), m.group(4)
            off = k.start - len(head) + m.start() + (1 if head[m.start()] in "\"'" else 0)
            if var:   # [v]:{…}: resolve `v="…"` declared in the preceding few KB; the receipt is that declaration
                decl_from = max(0, p.start - 4000)
                dm = None
                for dm in re.finditer(r'(?:[,;(]|\b(?:let|var|const)\s+)' + re.escape(var) + r'\s*=\s*"([^"\n]{1,120})"', body[decl_from:p.start]):
                    pass
                if dm is None:
                    continue
                name, off = dm.group(1), decl_from + dm.start(1)
            if not name or not _IDENT_LIKE.match(name) or len(name) > 120:
                continue
            if (name, off) in seen:
                continue
            seen.add((name, off))
            pairs = dict(zip(k.keys, k.values))
            value = None
            for vk in _VALUE_KEYS:
                if vk in pairs:
                    value = pairs[vk]
                    if value in ("{}", "[]"):
                        value = _child_value(k, parents, by_span, vk)
                    break
            out.append(_emit(body, artifact, k, name, off, pairs, value, [], set()))
    out.sort(key=lambda o: o.source.offset)
    return out
