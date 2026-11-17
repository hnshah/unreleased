"""enums extractor: non-proto enums and string tables. Emits kind "enum" (and "i18n" for copy tables).

Shapes claimed:
  E1 assignment runs  `e.AGENTS_WAITLIST="Agents Waitlist",e.CONTACT_SALES="Contact Sales"` (TS enum IIFEs, Linear;
                      `l.LOCAL_AGENT_FLOW_DOWNLOAD_MODAL="Local Agent Flow Download Modal"`, Figma): >= 3 entries.
                      The constant name is the key when the value is prose; the value is the key when it is an
                      identifier. Runs of >= 20 identifier values are the registry shape and are left to it.
  E2 string tables    an object of >= 20 non-UPPER keys whose values are identifier strings (Notion's webpack export
                      map `r.d(t,{},{a8w:"marketplace_custom_agent_version",…})` of record types): values are keys.
  E3 model tables     an object or array naming >= 2 known model ids (`gpt-*`, `claude`, `gemini`, …): every entry
                      is a model id, including the opaque ones (Figma's `robin-1`, `hawk-1`, `velvet`, `goldenrod`),
                      grouped by the table's key.
  E4 remote config    `{name:"passkeys_enabled",description:"Enable passkey login",default:!1}` property objects
                      (Spotify): key = name, value = default, context = description, group "remote-config".
  E5 i18n tables      `{"key":{"string":"…"}}` entries, keyed by look-back, as kind "i18n" with the copy as
                      context; capped at 500 per body with copy that mentions beta / early access / coming soon /
                      waitlist / new / preview / alpha first.
"""
from __future__ import annotations
import hashlib
import re
from dataclasses import replace

from schema import Observation, Source
import scanner

VERSION = "0.1.0"
NAME = "enums"
_CTX = 200
_MIN_RUN = 3
_MIN_TABLE = 20
_REGISTRY_RUN = 20
_I18N_CAP = 500
_UPPER = re.compile(r"^[A-Z][A-Z0-9_]*$")
_IDENT = re.compile(r"^[A-Za-z0-9][\w.:/-]{0,119}$")
_LOWER_IDENT = re.compile(r"^[a-z][a-z0-9_.:/-]{0,119}$")                  # snake / kebab / single word
_IDENT_SEP = re.compile(r"^[a-z][a-z0-9]*(?:[-_.:/][a-z0-9]+)+$")          # kebab / snake with a separator
_ASSIGN = re.compile(r'\b([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)\s*=\s*(?:"((?:\\.|[^"\\\n])*)"|\'((?:\\.|[^\'\\\n])*)\'|`((?:\\.|[^`\\$])*)`)')
# `opus` alone is an audio codec (HLS codec tables), `nova`/`phi`/`titan` alone are words: the short names need a
# version or a vendor beside them to count as a model id
_MODEL = re.compile(r"(?:^|[-_./:\s])(?:gpt|claude|gemini|anthropic|openai|llama|mistral|grok|deepseek|qwen|kimi|"
                    r"(?:sonnet|opus|haiku)(?=[-_ ]?\d)|claude[-_ ](?:sonnet|opus|haiku)|"
                    r"o[1-9](?=[-_ ]?(?:mini|pro|preview|$))|stability|flux(?=[-_.]?\d|[-_]schnell|[-_]dev|[-_]pro)|imagen|dall-?e|whisper|codex|"
                    r"(?:nova|titan)(?=[-_.](?:\d|[a-z]))|(?:phi|gemma)(?=[-_.]?\d)|command-r|veo(?=[-_]?\d)|sora)(?:$|[-_./:\s0-9])", re.I)
_HOT = re.compile(r"(?i)\b(?:beta|early access|coming soon|waitlist|new|preview|alpha)\b")
_KEY_BEFORE = re.compile(r'(?:"((?:\\.|[^"\\])*)"|\'((?:\\.|[^\'\\])*)\'|([A-Za-z_$][\w$]*))\s*:\s*$')
_VAR_BEFORE = re.compile(r'(?:\b(?:var|let|const)\s+)?([A-Za-z_$][\w$]*)\s*=\s*$')
_RC_KEYS = frozenset({"name", "description", "default", "defaultValue", "type", "key"})


def _oid(kind: str, key: str, src: Source) -> str:
    return hashlib.sha1(f"{kind}|{key}|{src.sha256}|{src.offset}".encode("utf-8")).hexdigest()[:16]


def _prefix(key: str) -> str:
    return re.split(r"[-_./:]", key, maxsplit=1)[0] if key else ""


def _is_str(v) -> bool:
    return isinstance(v, str) and v not in ("fn", "ref", "{}", "[]")


def _scalar(v) -> bool:
    """A literal scalar value (not a function, identifier reference or child literal): what a data table holds."""
    return isinstance(v, (bool, int, float)) or _is_str(v)


def _name_before(text: str, pos: int, limit: int = 80) -> str:
    head = text[max(0, pos - limit):pos]
    m = _KEY_BEFORE.search(head) or _VAR_BEFORE.search(head)
    return next((g for g in m.groups() if g is not None), "") if m else ""


_RUN_NAME = re.compile(r'(?:([A-Za-z_$][\w$]*)\s*=\s*function\s*\([^)]*\)\s*\{\s*return\s*'      # Rn=function(e){return e.A=…
                       r'|\(\s*[A-Za-z_$][\w$]*\s*=\s*([A-Za-z_$][\w$]*)\s*\|\|\s*\(\s*\2\s*=\s*\{\s*\}\s*\)\s*\)\.?'   # (i=o||(o={})).A=…
                       r'|\(\s*function\s*\(\s*[A-Za-z_$][\w$]*\s*\)\s*\{\s*)$')


def _run_name(body: str, pos: int) -> str:
    """The name a TS-enum IIFE is assigned to (`Rn=function(e){return e.A=…`) or seeds from (`(i=o||(o={}))`)."""
    m = _RUN_NAME.search(body[max(0, pos - 80):pos])
    return (m.group(1) or m.group(2) or "") if m else ""


_MAX_MODEL_TABLE = 60


def _model_like(names: list[str]) -> bool:
    """A short table where at least two entries, and two in five, name a known model: a model table. A gate map
    that happens to mention `llama` in two of 2,000 keys is not."""
    hits = sum(1 for n in names if _MODEL.search(n))
    return hits >= 2 and hits >= 0.4 * len(names) and all(_IDENT.match(n) for n in names)


def _find_key(body: str, key: str, lo: int, hi: int) -> int:
    """Offset of `key` spelled as a quoted string or a bare property name inside [lo, hi), else lo."""
    for q in ('"', "'", "`"):
        off = body.find(q + key + q, lo, hi)
        if off != -1:
            return off + 1
    pos = lo
    while True:
        pos = body.find(key, pos, hi)
        if pos == -1:
            return lo
        before = body[pos - 1] if pos > 0 else ""
        after = body[pos + len(key):pos + len(key) + 1]
        if (before in "{,[" or before.isspace()) and (after in ":,]" or after.isspace()):
            return pos
        pos += len(key)


def extract(body: str, artifact: Source) -> list[Observation]:
    out: list[Observation] = []
    seen: set[tuple[str, str, int]] = set()

    def emit(kind, key, off, **kw):
        if (kind, key, off) in seen:
            return
        seen.add((kind, key, off))
        src = replace(artifact, offset=off)
        kw.setdefault("group", _prefix(key))
        kw["context"] = kw.get("context", "")[:_CTX]
        out.append(Observation(id=_oid(kind, key, src), kind=kind, key=key, source=src, extractor=NAME, **kw))

    # --- E1 assignment runs
    run, last_end, last_obj = [], -1, None

    def flush():
        if _MIN_RUN <= len(run):
            vals = [v for _, _, v, _, _ in run]
            ident = sum(1 for v in vals if _IDENT.match(v))
            if not (len(run) >= _REGISTRY_RUN and ident >= 0.9 * len(vals)):      # that run is the registry's
                obj = run[0][0]
                group = _run_name(body, run[0][3] - len(obj) - 1) or obj
                for obj, prop, v, prop_off, val_off in run:
                    if _IDENT.match(v):
                        emit("enum", v, val_off, value=v, context=f"{group}.{prop}", group=group, confidence="medium")
                    else:
                        emit("enum", prop, prop_off, value=v, context=f"{group}.{prop} = {v}", group=group, confidence="medium")
        run.clear()

    for m in _ASSIGN.finditer(body):
        obj, prop = m.group(1), m.group(2)
        v = next(g for g in m.groups()[2:] if g is not None)
        if m.start() - last_end > 3 or obj != last_obj:
            flush()
        run.append((obj, prop, v, m.start(2), m.end() - 1 - len(v)))
        last_end, last_obj = m.end(), obj
    flush()

    # --- structural shapes
    lits = list(scanner.iter_literals(body))
    i18n: list[tuple[int, str, str, int]] = []       # (hot-rank, key, copy, offset)
    for l in lits:
        if l.kind == "object":
            ks, vs = l.keys, l.values
            if not ks:
                continue
            # E5 i18n entry: {"string":"…"} keyed by the property before it
            if ks == ["string"] and _is_str(vs[0]):
                head = body[max(0, l.start - 160):l.start]
                m = _KEY_BEFORE.search(head)
                if m:
                    key = next((g for g in m.groups() if g is not None), "")
                    if key and _IDENT.match(key):
                        off = l.start - len(head) + m.start() + (1 if head[m.start()] in "\"'" else 0)
                        i18n.append((0 if _HOT.search(vs[0]) else 1, key, vs[0], off))
                continue
            # E4 remote-config property
            kset = set(ks)
            if "name" in kset and "description" in kset and kset <= _RC_KEYS and 3 <= len(ks) <= 6:
                pairs = dict(zip(ks, vs))
                name, desc = pairs["name"], pairs["description"]
                if _is_str(name) and _IDENT.match(name) and _is_str(desc):
                    dflt = next((pairs[k] for k in ("default", "defaultValue") if k in pairs), None)
                    emit("enum", name, _find_key(body, name, l.start, l.end), value=dflt, context=desc, group="remote-config", confidence="high")
                continue
            # E3 model table (object keys)
            if 2 <= len(ks) <= _MAX_MODEL_TABLE:
                strv = [v for v in vs if _is_str(v)]
                table = _name_before(body, l.start) or "models"
                if len(strv) == len(vs) and all(_IDENT_SEP.match(v) for v in strv) and _model_like(strv):
                    for k, v in zip(ks, vs):           # {GPT_5_6_LUNA:"gpt-5-6-luna"}: the value is the model id
                        emit("enum", v, _find_key(body, v, l.start, l.end), value=v, context=f"model table {table} · {k}", group=table, confidence="high")
                    continue
                if _model_like(ks) and all(_scalar(v) for v in vs):
                    for k, v in zip(ks, vs):           # {"robin-1":16, "velvet":true}: the key is the model id
                        emit("enum", k, _find_key(body, k, l.start, l.end), value=v if not isinstance(v, str) or _is_str(v) else None,
                             context=f"model table {table}" + (f" = {v}" if v not in (None, "fn", "ref", "{}", "[]") else ""), group=table, confidence="high")
                    continue
            # E2 string table: non-UPPER keys, identifier values
            if len(ks) >= _MIN_TABLE:
                strs = [(k, v) for k, v in zip(ks, vs) if _is_str(v) and _LOWER_IDENT.match(v)]
                upper = sum(1 for k in ks if _UPPER.match(k))
                if len(strs) >= 0.9 * len(ks) and upper < 0.9 * len(ks):
                    table = _name_before(body, l.start)
                    for k, v in strs:
                        emit("enum", v, _find_key(body, v, l.start, l.end), value=v,
                             context=f"{k} in {table}" if table else f"{k} in string table", group=_prefix(v), confidence="high")
        else:
            items = [i for i in l.items if _is_str(i)]
            if 2 <= len(items) <= _MAX_MODEL_TABLE and len(items) == len(l.items) and _model_like(items):
                table = _name_before(body, l.start) or "models"
                for i in items:
                    emit("enum", i, _find_key(body, i, l.start, l.end), value=None, context=f"model table {table}", group=table, confidence="high")

    i18n.sort(key=lambda r: (r[0], r[3]))
    for _, key, copy, off in i18n[:_I18N_CAP]:
        emit("i18n", key, off, value=None, context=copy, group=_prefix(key), confidence="high")
    out.sort(key=lambda o: o.source.offset)
    return out
