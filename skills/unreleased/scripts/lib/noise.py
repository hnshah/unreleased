"""Noise (R8): vendor stop-list, SDK detection by init call, and tier assignment.

Tier rules, in order: drop (DOM props, SDK method names, RegExp flags, locale tags, keyword tables, version
enums, Emscripten/SDK sample paths, anything inside vendor code); key-list (entitlement/vendor toggles with no
feature noun, low-confidence pattern matches); codename (a bare name with no readable words and no human
string nearby); finding (everything else).
"""
from __future__ import annotations
import glob, json, os, re
from schema import Observation

VENDOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendors")

_DOM_PROP = re.compile(r"^(?:data-|aria-|enable-background$|accent-height$|arabic-form$)")
_SDK_METHODS = {"getFeatureFlag", "getFeatureFlags", "onFeatureFlags", "reloadFeatureFlags", "getFlags", "onReloading", "setPersonPropertiesForFlags",
                "isFeatureEnabled", "getFlag", "getVariation", "variation", "allFlags", "identify", "track", "capture", "init", "initialize",
                "includes", "split", "every", "forEach", "some", "map", "filter", "flags", "flag", "gates", "experiments", "experiment",
                "overrideFeatureFlags", "resetFlagCallReported", "getEarlyAccessFeatures", "updateEarlyAccessFeatureEnrollment",
                "gate_evaluation", "experiment_evaluation", "feature_gates", "dynamic_configs", "layer_configs", "feature_flags", "featureFlags"}
_LOCALE = re.compile(r"^[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-[A-Z]{2}|-\d{3})?$")
_KEYWORD_TABLE = re.compile(r"(?:_lpmf|_lpdf|_lcdf|_lccdf|_rng|_cdf)$")
_VERSION_ENUM = re.compile(r"^[a-z]+(?:-[a-z]+)*-v\d+$|^(?:uuid|md5|sha\d*)-v\d+$|^tracesSampleRate")
_SAMPLE_PATH = re.compile(r"^/(?:dev|proc|foo|bar|tmp|usr|etc|aws/lambda)(?:/|$)")
_HEXISH = re.compile(r"^[0-9a-f]{8,}$|^[A-Za-z0-9_-]{22,}$")
_ENTITLEMENT = re.compile(r"^(?:sprig|segment|intercom|hubspot|zendesk|drift|pendo|fullstory|hotjar|clarity|datadog|sentry|gtm|ga4?|rum|saml|scim|sso|oidc|mfa|captcha|recaptcha|turnstile|cookie|consent|gdpr|ccpa|logging|log|debug|perf|metrics|telemetry|tracing|a11y|accessibility|rtl|i18n|locale)[_-]", re.I)
_WORDS = re.compile(r"[A-Za-z]{3,}")


def load_vendors() -> list[dict]:
    out = []
    for p in sorted(glob.glob(os.path.join(VENDOR_DIR, "*.json"))):
        with open(p, encoding="utf-8") as f:
            v = json.load(f); v["name"] = os.path.basename(p)[:-5]; out.append(v)
    return out


def _init_present(init: str, body: str) -> bool:
    """`new StatsigClient(` is `new r.StatsigClient(` once minified: a namespace may sit between `new` and the name."""
    if init in body:
        return True
    m = re.match(r"new\s+([A-Za-z_$][\w$]*)\(", init)
    if m:
        return re.search(r"new\s+(?:[A-Za-z_$][\w$]*\.)+" + re.escape(m.group(1)) + r"\(", body) is not None
    return False


def detect_sdks(body: str, vendors: list[dict]) -> list[str]:
    found = []
    for v in vendors:
        sdk = v.get("sdk")
        if not sdk:
            continue
        inits = [i for i in v.get("init", []) if i]
        if not inits:
            continue
        has_init = any(_init_present(i, body) for i in inits)
        if not has_init:
            continue
        if v.get("requires_marker_for_init") and not any(m in body for m in v.get("markers", [])):
            continue
        found.append(sdk)
    return sorted(set(found))


_IDENT = re.compile(r"[A-Za-z0-9_$]")


# SDKs that host the product's own flags: a key in their tables is first-party work, not the vendor's
_HOSTS_FIRST_PARTY = ("vercel-flags", "posthog-js", "protobuf-runtime")


_JUNK = re.compile(r"[(){};=<>]|\s{2,}")
_CSS_HASH = re.compile(r"(?:sx|css|jsx|emotion|sc)-[a-z0-9]{4,}", re.I)
_LOCALE_KEY = re.compile(r"[a-z]{2}(?:[-_]?[A-Z]{2})?")
# web-platform vocabulary that a bundle carries whatever the product is: the CSS named colours (a colour library
# ships all 148), PointerEvent fields, react-spring and animation props, CSS property names, input types. Dropped,
# not even listed (Vercel: 217 "codenames", 190 of them this)
_PLATFORM_WORDS = set("""aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown burlywood
cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey
darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey
darkturquoise darkviolet deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite
gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender lavenderblush lawngreen lemonchiffon
lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen lightskyblue
lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen magenta maroon mediumaquamarine mediumblue mediumorchid
mediumpurple mediumseagreen mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin
navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff
peru pink plum powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown seagreen seashell sienna silver
skyblue slateblue slategray slategrey snow springgreen steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow
yellowgreen transparent currentcolor burntsienna
pointerid pressure tiltx tilty twist isprimary pointertype clientx clienty pagex pagey screenx screeny offsetx offsety movementx movementy
button buttons which keycode charcode altkey ctrlkey metakey shiftkey
datetime month number range week tel
flex opacity order orphans widows zindex zoom animation transition transform translate rotate scale
loop reset pause reverse immediate delay trail onprops onstart onchange onpause onresume onrest onresolve onrest ondestroyed initial enter update leave
maxx maxy minx miny progressx progressy visiblex visibley""".split())
_COORD = re.compile(r"^(?:max|min|progress|visible|offset|client|page|screen|delta|start|end)[XYZ]$")

_PLAIN_WORDS = set("""email password username name title value type size color colour user users id date time text image file files
login logout signup signin register search home page pages button label error errors loading open close save cancel submit delete edit
new next prev previous back width height left right top bottom center start end first last none null true false yes no ok done
default settings profile account help about contact terms privacy status admin dashboard inbox menu nav footer header body main
light dark theme language locale country region currency phone address city state zip url link links tag tags note notes comment
comments list lists item items row rows column columns table tables card cards modal dialog toast tooltip icon icons avatar""".split())


def _marker_in(text: str, vendors: list[dict]) -> str | None:
    for v in vendors:
        if v["name"] in _HOSTS_FIRST_PARTY:
            continue
        for m in v.get("markers", []):
            i = text.find(m)
            while i != -1:
                if _bounded(text, m, i):
                    return v["name"]
                i = text.find(m, i + len(m))
    return None


def _bounded(text: str, m: str, i: int) -> bool:
    """A marker matches at identifier boundaries; a marker ending in `_`/`-` is a prefix (`KEY_SYSTEM_` in
    `KEY_SYSTEM_NO_ACCESS`), one starting with them a suffix."""
    before = text[i - 1] if i > 0 else ""; after = text[i + len(m)] if i + len(m) < len(text) else ""
    left_ok = m[0] in "_-" or not (_IDENT.match(before) and _IDENT.match(m[0]))
    right_ok = m[-1] in "_-" or not (_IDENT.match(after) and _IDENT.match(m[-1]))
    return left_ok and right_ok


def vendor_spans(body: str, vendors: list[dict], window: int = 600) -> list[tuple[int, int, str]]:
    """Byte ranges around vendor markers; observations whose offset falls inside are vendor code."""
    spans = []
    for v in vendors:
        for m in v.get("markers", []):
            i = body.find(m)
            while i != -1:
                # identifier boundary: `_experiments` is Sentry's only as a whole token, not inside Figma's
                # `ce_al_experiments_on` gate (that match wiped 1.2 KB of first-party flags around it)
                if _bounded(body, m, i):
                    spans.append((max(0, i - window), i + len(m) + window, v["name"]))
                i = body.find(m, i + len(m))
                if len(spans) > 5000: break
    return spans


def _in_spans(offset: int, spans: list[tuple[int, int, str]]) -> str | None:
    for a, b, name in spans:
        if a <= offset <= b:
            return name
    return None


def _readable(key: str) -> int:
    parts = re.split(r"[_\-./:\s]+|(?<=[a-z])(?=[A-Z])", key)
    return sum(1 for p in parts if _WORDS.fullmatch(p) and len(p) >= 3)


def assign_tiers(observations: list[Observation], bodies: dict[str, str], vendors: list[dict] | None = None) -> list[Observation]:
    vendors = vendors if vendors is not None else load_vendors()
    span_cache: dict[str, list] = {}
    out = []
    for o in observations:
        k = o.key
        if o.kind in ("robots", "sitemap", "headline"):
            out.append(o); continue          # the site source tiers its own records
        if o.kind in ("subdomain", "job", "pricing", "redirect", "manifest", "hidden", "proto"):
            o.tier = "finding" if o.kind != "proto" else "key-list"; out.append(o); continue
        if _DOM_PROP.match(k) or k in _SDK_METHODS or _KEYWORD_TABLE.search(k) or _VERSION_ENUM.match(k) or _SAMPLE_PATH.match(k):
            continue
        if _LOCALE.match(k) and o.kind != "route":
            continue
        if _HEXISH.match(k) and _readable(k) == 0:
            continue
        body = bodies.get(o.source.sha256)
        # a key read out of a parsed first-party map is judged by its own name and value; a vendor marker in a
        # neighbouring value ("datadog_rum_site":"datadoghq.com") says nothing about the map's other keys —
        # but a marker in the key itself or in its own context line (gt-next's `APIKeyMissingWarn`, hls.js's
        # `KEY_SYSTEM_NO_ACCESS`) is the vendor's table, whatever map it sits in
        if o.group and _marker_in(k + " " + (o.context or ""), vendors):
            continue
        if body is not None and o.source.offset >= 0 and not o.group:
            if o.source.sha256 not in span_cache:
                span_cache[o.source.sha256] = vendor_spans(body, vendors)
            vn = _in_spans(o.source.offset, span_cache[o.source.sha256])
            if vn and vn not in _HOSTS_FIRST_PARTY:
                continue
        readable = _readable(k)
        human = bool(re.search(r"[A-Z][a-z]+ [A-Za-z]|[a-z]+ [a-z]+ [a-z]+", o.context or ""))
        if _JUNK.search(k) or len(k) > 120 or _CSS_HASH.fullmatch(k):
            continue                                   # a minified fragment or a CSS class hash names nothing (Linear: 90 `sx-…` keys)
        bare = k.strip("/").lower()
        if len(bare) <= 2 or bare in _PLATFORM_WORDS or _COORD.fullmatch(k.strip("/")):
            continue                                   # `x`, `0`, `aliceblue`, `tiltX`: the web platform, not the product
        if o.confidence == "low" or o.extractor == "strings":
            o.tier = "key-list" if readable >= 1 or human else "codename"
        elif _ENTITLEMENT.match(k):
            o.tier = "key-list"
        elif readable >= 2 or human:
            o.tier = "finding"
        elif readable == 1 and o.kind in ("route", "enum", "catalog", "registry", "inline", "config"):
            o.tier = "finding"
        elif k.strip("/").lower() in _PLAIN_WORDS or _LOCALE_KEY.fullmatch(k):
            o.tier = "key-list"                        # `email`, `width`, `/login`, `enGB`: plain UI words and locales are not codenames
        else:
            o.tier = "codename"
        out.append(o)
    return out
