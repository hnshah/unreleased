"""proto extractor: protobuf-JS descriptors embedded in bundles (protobuf-es / bufbuild runtime style).

Emits kind "enum" for every enum value (group = the enum's short name, context = `package.Enum PROTO_NAME`,
value = the number) and kind "proto" for every message type (key = `package.Message`, params/context = its
field names). Enum values are where product names live (Dropbox: `coding_agent.AgentRuntime = {CODEX, PI,
UNIFIED_HARNESS}`), so the short, un-prefixed name is the key:
  - TS-enum style  `var ey=((y={})[y.CODEX=1]="CODEX",…,y);util.setEnumType(ey,"pkg.AgentRuntime",[{no,name}])`
    the short names come from the TS enum object declared just above the registration;
  - protobuf-es    `proto3.makeEnum("pkg.Enum",[{no,name,localName?}])` / `makeMessageType("pkg.Msg",()=>[…])`
    the short name is `localName` when present, else the proto name with the enum's SCREAMING prefix removed.
The `*_UNSPECIFIED` zero value is proto3 boilerplate and is not emitted. Call sites are matched by regex;
the descriptor arrays are read from balanced literals, so confidence is "high".
"""
from __future__ import annotations
import hashlib
import re
from dataclasses import replace

from schema import Observation, Source
import scanner

VERSION = "0.1.0"
NAME = "proto"
_CTX = 200
_MAX_FIELDS_IN_CONTEXT = 10

_TYPE = r'"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+)"'
# setEnumType(var, "pkg.Enum", [   |   makeEnum("pkg.Enum", [   |   makeEnumType("pkg.Enum", [
_ENUM_CALL = re.compile(r'(?:setEnumType\(\s*([A-Za-z_$][\w$]*)\s*,\s*|makeEnum(?:Type)?\(\s*)' + _TYPE + r'\s*,\s*(\[)')
# X.typeName="pkg.Msg", X.fields=…newFieldList(function(){return[  |  …newFieldList(()=>[
_MSG_FIELDS = re.compile(r'typeName\s*=\s*' + _TYPE + r'.{0,120}?newFieldList\(\s*(?:function\s*\(\s*\)\s*\{\s*return\s*|\(\s*\)\s*=>\s*)(\[)', re.S)
# proto3.makeMessageType("pkg.Msg", () => [   |   function(){return[
_MSG_MAKE = re.compile(r'makeMessageType\(\s*' + _TYPE + r'\s*,\s*(?:\(\s*\)\s*=>\s*|function\s*\(\s*\)\s*\{\s*return\s*)(\[)')
_TS_PAIR = re.compile(r'\[\s*([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)\s*=\s*(-?\d+)\s*\]\s*=\s*"([^"\\]*)"')
_ENUM_NAME_OK = re.compile(r'^[A-Z][A-Z0-9_]*$')


def _oid(kind: str, key: str, src: Source) -> str:
    return hashlib.sha1(f"{kind}|{key}|{src.sha256}|{src.offset}".encode("utf-8")).hexdigest()[:16]


def _screaming(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", name).upper()


_LOCAL_SCAN_LIMIT = 400_000


def _array_at(body: str, pos: int, arr_at: dict, by_span: dict) -> tuple[scanner.Literal | None, dict]:
    """The array literal opening at `pos`. Falls back to a local scan from `pos` when the whole-body scan lost
    phase before it (a regex literal with a quote in it, e.g. `/[^']*'/`, reads as an open string; logged as a
    scanner need in worker-notes-B.md). The local scan starts at a known `[`, so its phase is right; its
    literals are shifted to body offsets and all of them are the array's descendants."""
    arr = arr_at.get(pos)
    if arr is not None:
        return arr, by_span
    local: dict[tuple[int, int], scanner.Literal] = {}
    scan = getattr(scanner, "_scan", None)      # the uncached generator: a local re-scan must not evict the body's cache
    lits = scan(body[pos:pos + _LOCAL_SCAN_LIMIT], 4_000_000, 6) if scan else scanner.iter_literals(body[pos:pos + _LOCAL_SCAN_LIMIT])
    for l in lits:
        shifted = scanner.Literal(l.start + pos, l.end + pos, l.kind, l.depth, body, [(a + pos, b + pos) for a, b in l._children])
        local[(shifted.start, shifted.end)] = shifted
        if l.start == 0 and l.kind == "array":
            return shifted, local
    return None, local


def _entries(arr: scanner.Literal, by_span: dict) -> list[dict]:
    """The {no, name, …} objects directly inside a descriptor array."""
    out = []
    for span in arr._children:
        child = by_span.get(span)
        if child is None or child.kind != "object":
            continue
        pairs = dict(zip(child.keys, child.values))
        if "name" in pairs and isinstance(pairs["name"], str):
            pairs["_start"] = child.start; pairs["_end"] = child.end
            out.append(pairs)
    return out


def _ts_short_names(body: str, var: str, before: int) -> dict[int, str]:
    """`var ey=((y={})[y.CODEX=1]="CODEX",…,y)` declared within the 6 KB before `before`: number -> short name."""
    head = body[max(0, before - 6000):before]
    m = None
    for m in re.finditer(r'(?:\bvar\s+|\blet\s+|\bconst\s+|[,;(])\s*' + re.escape(var) + r'\s*=\s*\(\s*\(\s*([A-Za-z_$][\w$]*)\s*=\s*\{\s*\}\s*\)', head):
        pass
    if m is None:
        return {}
    alias = m.group(1)
    out = {}
    for p in _TS_PAIR.finditer(head, m.end()):
        if p.group(1) != alias:
            break
        out[int(p.group(3))] = p.group(4)
        if head.startswith("," + alias + ")", p.end()):   # `…,y)` closes the TS enum expression
            break
    return out


def _strip_prefix(names: list[str], enum_short: str) -> dict[str, str]:
    """Proto names share `ENUM_NAME_`; strip it when every value carries it (how protobuf-es derives localName)."""
    prefix = _screaming(enum_short) + "_"
    if names and all(n.startswith(prefix) and len(n) > len(prefix) for n in names):
        return {n: n[len(prefix):] for n in names}
    return {n: n for n in names}


def extract(body: str, artifact: Source) -> list[Observation]:
    lits = list(scanner.iter_literals(body))
    by_span = {(l.start, l.end): l for l in lits}
    arr_at = {l.start: l for l in lits if l.kind == "array"}
    out: list[Observation] = []
    seen: set[tuple[str, str, int]] = set()

    def emit(kind, key, offset, **kw):
        if (kind, key, offset) in seen:
            return
        seen.add((kind, key, offset))
        src = replace(artifact, offset=offset)
        out.append(Observation(id=_oid(kind, key, src), kind=kind, key=key, source=src, extractor=NAME, confidence="high", **kw))

    # --- enums
    for m in _ENUM_CALL.finditer(body):
        var, full, bracket = m.group(1), m.group(2), m.start(3)
        arr, spans = _array_at(body, bracket, arr_at, by_span)
        if arr is None:
            continue
        entries = [e for e in _entries(arr, spans) if _ENUM_NAME_OK.match(e["name"]) and isinstance(e.get("no"), int)]
        if not entries:
            continue
        pkg, _, short = full.rpartition(".")
        ts = _ts_short_names(body, var, m.start()) if var else {}
        stripped = _strip_prefix([e["name"] for e in entries], short)
        for e in entries:
            proto_name, no = e["name"], e["no"]
            local = e.get("localName") if isinstance(e.get("localName"), str) else None
            key = local or ts.get(no) or stripped[proto_name]
            if no == 0 and key.endswith("UNSPECIFIED"):
                continue
            # receipt: where the short name is spelled — the TS enum string, the localName, or inside the proto name
            off = -1
            if local == key:
                off = body.find('"' + key + '"', e["_start"], e["_end"])
            elif ts.get(no) == key:
                off = body.rfind('"' + key + '"', max(0, m.start() - 6000), m.start())
            if off == -1:
                off = body.find('"' + proto_name + '"', e["_start"], e["_end"])
                if off != -1 and key != proto_name and proto_name.endswith(key):
                    off += len(proto_name) - len(key)
            emit("enum", key, (off + 1) if off != -1 else e["_start"], value=no, group=short,
                 context=f"{full} {proto_name}"[:_CTX])

    # --- messages
    for rx in (_MSG_FIELDS, _MSG_MAKE):
        for m in rx.finditer(body):
            full, bracket = m.group(1), m.start(2)
            arr, spans = _array_at(body, bracket, arr_at, by_span)
            if arr is None:
                continue
            fields = [e["name"] for e in _entries(arr, spans) if isinstance(e.get("no"), int)]
            pkg, _, short = full.rpartition(".")
            off = body.find('"' + full + '"', m.start(), m.end())
            emit("proto", full, (off + 1) if off != -1 else m.start(), params=fields, group=pkg,
                 context=" ".join(fields[:_MAX_FIELDS_IN_CONTEXT])[:_CTX])
    out.sort(key=lambda o: o.source.offset)
    return out
