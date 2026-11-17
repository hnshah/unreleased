"""strings extractor: the last resort, confidence "low". See plan-v1.md U2 ("A kept only as strings").

Everything here is a pattern over text or a small literal, read when no structured shape claimed the
bytes. The noise stage filters further; this module only skips the obvious (vendor tables, CSS tokens).

Shapes claimed, in order:
  S1 hint phrases    "coming soon", "early access", "waitlist", "beta", "preview", "internal only",
                     "not yet available", "sneak peek", … inside a string literal (the literal is the key,
                     the phrase the value) with 90 chars of context either side. Bare tokens (`"beta"`) and
                     matches inside vendor code (highlight.js, elliptic, CSS, `experimental_*` API names) are skipped.
  S2 model-id maps   objects whose keys are model ids (`gpt-image-2`, `gemini-3-pro-image`, `robin-1`,
                     `velvet`) with number/boolean values: each key, with the parent config name as context.
  S3 label enums     `l.LOCAL_AGENT_FLOW_DOWNLOAD_MODAL="Local Agent Flow Download Modal"`: a Title Case value
                     whose UPPER_SNAKE form is the constant — UI copy naming a surface.
  S4 typed records   `{type:"coupon",campaign:"business_annual_bundle_3_for_1_seats",…}`: the identifier
                     field of a small typed record, grouped by its type.
  S5 url targeting   Optimizely datafile `…_url_targeting_for_<name>` api names: the experiment name.
  S6 enum slugs      `(C={}).CONJURE="conjuring",C.GUILD_SPACE="guild-space"`: the slug values of a constant
                     enum that is not route-like (routes claims the route-like ones).
"""
from __future__ import annotations
import hashlib
import re
from dataclasses import replace

from schema import Observation, Source
import scanner
from extractors.routes import _CHAIN, _SLUG_VALUE, _key_before, _key_offset, _clip

VERSION = "0.1.0"
NAME = "strings"

_CTX = 200
_CAP_HINTS = 300
_PLACEHOLDERS = ("fn", "ref", "{}", "[]")

_HINTS = ("coming soon", "early access", "join the waitlist", "waitlist", "private alpha", "private beta", "closed beta",
          "open beta", "public beta", "beta", "preview", "internal only", "not yet available", "sneak peek", "invite only",
          "request access", "limited availability", "unreleased", "experimental")
_HINT = re.compile(r"(?<![\w-])(" + "|".join(re.escape(h) for h in sorted(_HINTS, key=len, reverse=True)) + r")(?![\w-])", re.I)
_STRING = re.compile(r'"((?:\\.|[^"\\\n]){3,240})"|\'((?:\\.|[^\'\\\n]){3,240})\'|`([^`\n]{3,240})`')
_VENDOR_NEAR = re.compile(r"hljs|highlight\.js|registerLanguage|elliptic|secp256k1|--tw-|tailwind|@media|rgba?\(|"
                          r"experimental_|unstable_|__experimental|React\.|react-dom|sentry|apollo|datadog|optimizely\.", re.I)
_CSS_TOKEN = re.compile(r"^[\w-]+$")

_MODEL_ID = re.compile(r"^(?:gpt-|gemini-|claude|anthropic-|openai-|google-|meta-|llama|mistral|flux|stability|imagen|"
                       r"amazon\.|accounts/|o[1-9](?:-|$)|grok|deepseek|qwen|sonnet|opus|haiku)", re.I)
_MODELISH = re.compile(r"^[a-z][a-z0-9.:/_-]*$")
_TITLE = re.compile(r"^(?:[A-Z][A-Za-z0-9]*|[0-9]+)(?: (?:[A-Za-z0-9][A-Za-z0-9]*))+$")
_TYPED_ID_KEYS = ("campaign", "id", "key", "name", "slug", "code", "sku", "plan", "coupon", "promo", "offer")
_TYPED_ID = re.compile(r"^[a-z][a-z0-9]*(?:[_-][a-z0-9]+){2,}$")
_TEXT_NODE = re.compile(r">([^<>{}]{3,200})<")
_URL_TARGETING = re.compile(r"url_targeting_for_([a-z][a-z0-9_]{3,120})")


def _oid(kind: str, key: str, src: Source) -> str:
    return hashlib.sha1(f"{kind}|{key}|{src.sha256}|{src.offset}".encode("utf-8")).hexdigest()[:16]


class _Sink:
    def __init__(self, artifact: Source):
        self.artifact, self.out, self.seen = artifact, [], set()

    def add(self, key: str, offset: int, *, value=None, context: str = "", group: str = "") -> bool:
        key = re.sub(r"\s+", " ", key).strip()
        if not key or key in self.seen:
            return False
        self.seen.add(key)
        src = replace(self.artifact, offset=offset)
        self.out.append(Observation(id=_oid("string", key, src), kind="string", key=key, source=src, value=value, group=group,
                                    context=_clip(context, _CTX), extractor=NAME, confidence="low"))
        return True


def _hint_window(body: str, start: int, end: int) -> str:
    return body[max(0, start - 90): start] + "«" + body[start:end] + "»" + body[end: end + 90]


def extract(body: str, artifact: Source) -> list[Observation]:
    sink = _Sink(artifact)
    lits = list(scanner.iter_literals(body))

    # --- S2 model-id maps
    for l in lits:
        if l.kind != "object" or len(l.keys) < 3 or len(l.keys) > 200:
            continue
        ks, vs = l.keys, l.values
        if not all(isinstance(v, (bool, int, float)) for v in vs):
            continue
        if sum(1 for k in ks if _MODEL_ID.match(k)) < 2 or sum(1 for k in ks if _MODELISH.match(k)) * 10 < 7 * len(ks):
            continue
        parent, _ = _key_before(body, l.start)
        ctx = f"{parent} " if parent else ""
        for k, v in zip(ks, vs):
            sink.add(k, _key_offset(body, l, k), value=v, context=ctx + "model-id map " + " ".join(ks[:8]), group="model-ids")

    # --- S4 typed records
    for l in lits:
        if l.kind != "object" or not (2 <= len(l.keys) <= 12):
            continue
        pairs = dict(zip(l.keys, l.values))
        t = pairs.get("type")
        if not isinstance(t, str) or t in _PLACEHOLDERS or not re.fullmatch(r"[a-z][a-z0-9_-]{1,40}", t):
            continue
        for ik in _TYPED_ID_KEYS:
            v = pairs.get(ik)
            if isinstance(v, str) and v not in _PLACEHOLDERS and _TYPED_ID.match(v):
                extra = " ".join(f"{k}={pv}" for k, pv in pairs.items() if k not in (ik, "type") and isinstance(pv, (str, int, float))
                                 and pv not in _PLACEHOLDERS)
                nested = re.findall(r"type\s*:\s*\"([a-z_]+)\"", l.text)
                sink.add(v, _key_offset(body, l, v), context=f"type={t} {extra} " + " ".join(n for n in nested if n != t),
                         group=t)
                break

    # --- S3 label enums and S6 enum slugs (the chain regex is routes')
    chain: list = []
    last_var, last_end = None, -1

    def flush(ch):
        if len(ch) < 3:
            return
        vals = [v for _, _, v, _ in ch]
        routeish = sum(1 for v in vals if v.startswith("/") or ("/" in v and " " not in v)) * 10 >= 3 * len(vals)
        for name, name_off, v, v_off in ch:
            if _TITLE.match(v) and re.sub(r"[^A-Za-z0-9]+", "_", v).upper().strip("_") == name:
                sink.add(v, v_off, context=name, group="label-enum")
            elif not routeish and _SLUG_VALUE.match(v) and re.search(r"[a-z]", v) and len(v) >= 4 and not re.fullmatch(r"\d+", v):
                sink.add(v, v_off, context=name, group="enum")

    for m in _CHAIN.finditer(body):
        var = m.group(1) or m.group(2)
        opens = m.group(1) is not None
        if chain and (opens or var != last_var or m.start() - last_end > 3):
            flush(chain); chain = []
        chain.append((m.group(3), m.start(3), m.group(4), m.start(4)))
        last_var, last_end = var, m.end()
    flush(chain)

    # --- S5 url targeting names
    for m in _URL_TARGETING.finditer(body):
        name = m.group(1).rstrip("_")
        after = body[m.end(): m.end() + 800]
        url = re.search(r'"value"\s*:\s*"([^"\n]{1,120})"', after)
        ctx = (f"url={url.group(1)} " if url else "") + body[max(0, m.start() - 60): m.end() + 300]
        sink.add(name, m.start(1), context=ctx, group="url-targeting")

    # --- S1 hint phrases inside string literals
    n = 0
    for m in _STRING.finditer(body):
        if n >= _CAP_HINTS:
            break
        s = next(g for g in m.groups() if g is not None)
        h = _HINT.search(s)
        if not h:
            continue
        phrase = h.group(1).lower()
        if _CSS_TOKEN.match(s) and s.lower() in _HINTS:
            continue                                          # a bare token: "beta", "preview"
        if not re.match(r"[\w(/<\[@$#*]", s):
            continue                                          # quote parity slipped (`,l.PREVIEW=`)
        if s.count("{") > 1 or s.count(";") > 2 or len(s) > 200:
            continue                                          # code or CSS in a string
        win = _hint_window(body, m.start(), m.end())
        if _VENDOR_NEAR.search(body[max(0, m.start() - 60): m.start()]):
            continue                                          # the call site is a vendor's (hljs.registerLanguage("…
        if sink.add(s, m.start() + 1, value=phrase, context=win, group="hint"):
            n += 1
    # --- S1 in HTML text nodes (`>Get early access<`)
    if body.count("<") > 50:
        for m in _TEXT_NODE.finditer(body):
            if n >= _CAP_HINTS:
                break
            text = m.group(1).strip()
            h = _HINT.search(text)
            if not h or text.lower() in _HINTS or len(text) > 200:
                continue
            if sink.add(text, m.start(1) + (len(m.group(1)) - len(m.group(1).lstrip())), value=h.group(1).lower(),
                        context=_hint_window(body, m.start(), m.end()), group="hint"):
                n += 1
    return sink.out
