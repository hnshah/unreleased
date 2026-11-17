"""calls extractor: flag reads by call convention (kind "call"; value = the default when the call carries one).

Shapes (see plan-v1.md U2 and the Notion/Replit/Vercel/Retool readers):

- named reads with a literal key: `checkGate({gateName:"x"})`, `getEligibleGroup({experimentId:"x",defaultGroup:"control"})`,
  `getConfig({configName:"x"})`, `this.checkGate("x")`, `(0,A.useServerFlag)("x",!1)`, `useFeatureGate("x",!1)`,
  `useGetExperimentParam("exp","param",!1)` (the experiment, with params=["param"]), `useFlag("x")`,
  `isFeatureEnabled("x")`, `getFeatureFlag("x")`, `variation("x")`, `hasFeature("x")`. Confidence high.
- the same reads with the key held in a nearby variable (`let n="x"; ... checkGate({gateName:n})`): the last assignment
  of that identifier to a string within the preceding 2,500 bytes is taken as the key. Confidence medium.
- `gateName:"x"` / `experimentName:"x"` / `experimentId:"x"` / `flagName:"x"` / `flag:"x"` inside any object literal.
- `namespace::key` strings (`governance::projects`). Confidence low.
- a minified-hook detector: `(0,X.Y)("string")` or `X.Y("string")` call shapes whose callee is used with >= 10 distinct
  flag-looking string arguments (snake/kebab, >= 2 segments) in one body; emitted with confidence low, context = callee.

Regex only (call sites are not literals); the receipt offset points at the key string. Pure function; no network.
"""
from __future__ import annotations
import re
from collections import defaultdict
from schema import Observation, Source

VERSION = "0.1.0"

CONTEXT_MAX = 200
HOOK_MIN_DISTINCT = 10
HOOK_FLAGLIKE_SHARE = 0.8
RESOLVE_WINDOW = 2500

NAMES = ["checkGate", "getGate", "getEligibleGroup", "useGetFeatureGate", "useFeatureGate", "useScopedFeatureGate",
         "useGetExperimentParam", "getExperimentParam", "useServerFlag", "useFlag", "useFeatureFlag", "isFeatureEnabled",
         "isFeatureFlagEnabled", "getFeatureFlag", "getFeatureFlagPayload", "variation", "hasFeature", "getExperiment",
         "useExperiment", "getConfig", "useGate", "getVariant", "useVariation", "useVariant", "getFeatureValue",
         "useFeatureValue", "getBooleanValue", "getStringValue", "getLayer", "useLayer"]
_KEY_FIELDS = ["gateName", "experimentName", "experimentId", "experimentKey", "configName", "flagName", "flagKey",
               "featureFlag", "gate", "experiment", "flag", "key", "name"]
_DEFAULT_FIELDS = ["defaultGroup", "defaultValue", "default", "fallback"]
_PARAM_NAMES = {"useGetExperimentParam", "getExperimentParam"}
_EXPERIMENT_CALLEES = {"getEligibleGroup", "getExperiment", "useExperiment", "useGetExperimentParam", "getExperimentParam"}

_DQ = r'"((?:[^"\\\n]|\\.)+)"'
_SQ = r"'((?:[^'\\\n]|\\.)+)'"
_SCALAR = r"""(!0|!1|true|false|null|void 0|undefined|-?\d+(?:\.\d+)?|"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')"""
_CALL = re.compile(r"(?<![\w$])(?:\(0,\s*[^()\s,]*?\.)?(" + "|".join(NAMES) + r")\)?\(\s*")
# string first argument, optional string second argument, optional scalar third argument
_ARG_STR = re.compile(r"(?:" + _DQ + "|" + _SQ + r")\s*(?:,\s*(?:" + _DQ + "|" + _SQ + r"))?\s*(?:,\s*" + _SCALAR + r")?")
_ARG_IDENT = re.compile(r"([A-Za-z_$][\w$]*)\s*(?:,\s*" + _SCALAR + r")?\s*[,)]")
_FIELD = re.compile(r"(?<![\w$])(" + "|".join(_KEY_FIELDS + _DEFAULT_FIELDS) + r")\s*:\s*(?:" + _DQ + "|" + _SQ
                    + r"|([A-Za-z_$][\w$]*)|(!0|!1|true|false|-?\d+(?:\.\d+)?))")
_OBJ_FIELD = re.compile(r"(?<![\w$])(gateName|experimentName|experimentId|experimentKey|flagName|flagKey|featureFlag|flag)\s*:\s*(?:" + _DQ + "|" + _SQ + ")")
_NS_KEY = re.compile(r"""["'`]([a-z][A-Za-z]+::[A-Za-z]+)["'`]""")
_HOOK = re.compile(r"""(?:\(0,\s*((?:[\w$]+(?:\(\d+\))?\.)+[\w$]+)\)|(?<![\w$.])([\w$]+(?:\(\d+\))?\.[\w$]+))\(\s*"([^"\\\n]+)"\s*[,)]""")
_FLAGLIKE = re.compile(r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)+$")
_KEYISH = re.compile(r"^[A-Za-z0-9][\w.:-]*$")
# method names that take snake/kebab strings but are not flag reads: event buses, analytics, i18n, routing, styling
_NOT_HOOK_RE = re.compile(r"^_*(?:on|once|off|emit|trigger|listen|fire|addListener|removeListener)$|track|analytic|telemetry|metric|log|event|"
                          r"literal|translat|i18n|locale|intl|format|route|navigat|href|path|url|icon|class|style|color|theme|"
                          r"assert|invariant|warn|error|throw|require|import|define|register|lookup|hash", re.I)
_NOT_HOOKS = {"add", "remove", "toggle", "contains", "has", "get", "set", "push", "delete", "querySelector", "querySelectorAll",
              "getElementById", "getAttribute", "setAttribute", "removeAttribute", "createElement", "getItem", "setItem",
              "removeItem", "on", "off", "once", "emit", "addEventListener", "removeEventListener", "dispatch", "require",
              "log", "warn", "error", "info", "debug", "test", "exec", "match", "replace", "split", "join", "indexOf",
              "includes", "startsWith", "endsWith", "resolve", "extend", "prop", "attr", "css", "data", "hasClass",
              "addClass", "removeClass", "toggleClass", "track", "capture", "identify", "register", "subscribe", "publish",
              "bind", "call", "apply", "createElementNS", "getPropertyValue", "setProperty", "removeProperty", "t", "d", "n",
              "r", "e", "i", "o", "a", "s", "l", "u", "c", "f", "p", "h", "m", "v", "g", "y", "b", "w", "x", "k", "j", "q", "z"}


def _scalar(tok):
    if tok is None:
        return None
    if tok in ("true", "!0"): return True
    if tok in ("false", "!1"): return False
    if tok in ("null", "void 0", "undefined"): return None
    if tok[0] in "\"'": return tok[1:-1]
    try:
        return int(tok) if re.fullmatch(r"-?\d+", tok) else float(tok)
    except ValueError:
        return tok


def _resolve(body: str, ident: str, pos: int):
    """The last `let x="..."` / `x="..."` for `ident` in the window before `pos`: (key, offset) or None."""
    lo = max(0, pos - RESOLVE_WINDOW)
    pat = re.compile(r"(?:\b(?:let|const|var)\s+|[,;({]\s*)" + re.escape(ident) + r"\s*=\s*(?:" + _DQ + "|" + _SQ + ")")
    last = None
    for m in pat.finditer(body, lo, pos):
        last = m
    if last is None:
        return None
    g = 1 if last.group(1) is not None else 2
    return last.group(g), last.start(g) - 1


class _Emitter:
    def __init__(self, artifact: Source):
        self.artifact, self.out, self.seen = artifact, [], set()

    def emit(self, key, offset, context, group, confidence, default=None, params=()):
        if not key or not _KEYISH.match(key) or (key, offset) in self.seen:
            return
        self.seen.add((key, offset))
        src = Source(url=self.artifact.url, sha256=self.artifact.sha256, offset=offset,
                     first_party=self.artifact.first_party, attribution=self.artifact.attribution)
        self.out.append(Observation(id="", kind="call", key=key, source=src, value=default, default=default,
                                    params=list(params), group=group, context=context[:CONTEXT_MAX], extractor="calls",
                                    confidence=confidence))


def _object_arg(body: str, start: int):
    """Fields of a flat object argument starting at `start` (the `{`): {field: (kind, text, offset)}; end offset."""
    end = body.find("}", start)
    if end == -1 or end - start > 600:
        return {}, start
    fields = {}
    for m in _FIELD.finditer(body, start, end):
        name = m.group(1)
        if name in fields:
            continue
        if m.group(2) is not None or m.group(3) is not None:
            g = 2 if m.group(2) is not None else 3
            fields[name] = ("str", m.group(g), m.start(g) - 1)
        elif m.group(4) is not None:
            fields[name] = ("ident", m.group(4), m.start(4))
        else:
            fields[name] = ("scalar", m.group(5), m.start(5))
    return fields, end


def extract(body: str, artifact: Source) -> list[Observation]:
    em = _Emitter(artifact)

    # 1. named reads
    for m in _CALL.finditer(body):
        callee, p = m.group(1), m.end()
        ctx = body[m.start():m.start() + CONTEXT_MAX]
        if body.startswith("{", p):
            fields, _ = _object_arg(body, p)
            keyf = next((f for f in _KEY_FIELDS if f in fields), None)
            if keyf is None:
                continue
            kind, text, off = fields[keyf]
            dflt = next((fields[f] for f in _DEFAULT_FIELDS if f in fields), None)
            default = _scalar(dflt[1] if dflt and dflt[0] in ("str", "scalar") else None) if dflt else None
            if dflt and dflt[0] == "str":
                default = dflt[1]
            if kind == "str":
                em.emit(text, off, ctx, callee, "high", default)
            elif kind == "ident":
                r = _resolve(body, text, m.start())
                if r:
                    em.emit(r[0], r[1], ctx, callee, "medium", default)
            continue
        a = _ARG_STR.match(body, p)
        if a:
            g = 1 if a.group(1) is not None else 2
            key, koff = a.group(g), a.start(g) - 1
            second = a.group(3) if a.group(3) is not None else a.group(4)
            third = a.group(5)
            if callee in _PARAM_NAMES and second is not None:
                em.emit(key, koff, ctx, callee, "high", _scalar(third), params=[second])
            else:
                # the second argument is the default when it is a scalar (useServerFlag("x",!1), variation("x","control"))
                tail = body[a.end(g) + 1:a.end(g) + 60]
                dm = re.match(r"\s*,\s*" + _SCALAR, tail)
                em.emit(key, koff, ctx, callee, "high", _scalar(dm.group(1)) if dm else None)
            continue
        a = _ARG_IDENT.match(body, p)
        if a:
            r = _resolve(body, a.group(1), m.start())
            if r:
                em.emit(r[0], r[1], ctx, callee, "medium", _scalar(a.group(2)))

    # 2. gateName:"x" / experimentName:"x" / flag:"x" inside objects anywhere
    for m in _OBJ_FIELD.finditer(body):
        field, g = m.group(1), 2 if m.group(2) is not None else 3
        key = m.group(g)
        if field == "flag" and not _FLAGLIKE.match(key):
            continue
        em.emit(key, m.start(g) - 1, body[max(0, m.start() - 60):m.end() + 60], field, "high")

    # 3. namespace::key strings
    for m in _NS_KEY.finditer(body):
        em.emit(m.group(1), m.start(1) - 1, body[max(0, m.start() - 80):m.end() + 80], "namespace::key", "low")

    # 4. minified hooks by frequency of flag-looking string arguments
    by_callee: dict[str, list] = defaultdict(list)
    for m in _HOOK.finditer(body):
        callee = m.group(1) or m.group(2)
        method = callee.rsplit(".", 1)[-1]
        if method in NAMES or method in _NOT_HOOKS or _NOT_HOOK_RE.search(method):
            continue
        by_callee[callee].append((m.group(3), m.start(3) - 1, m.start()))
    for callee, uses in by_callee.items():
        distinct = {k for k, _, _ in uses}
        flaglike = {k for k in distinct if _FLAGLIKE.match(k)}
        if len(distinct) >= HOOK_MIN_DISTINCT and len(flaglike) >= HOOK_FLAGLIKE_SHARE * len(distinct):
            for key, off, start in uses:
                if key in flaglike:
                    em.emit(key, off, body[start:start + CONTEXT_MAX], callee, "low")
    return em.out
