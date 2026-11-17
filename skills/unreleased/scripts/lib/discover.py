"""Discover: scripts, inline scripts and JSON blocks on a page; chunk maps inside scripts; selection by role (R5)."""
from __future__ import annotations
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
import html as htmlmod
import json
import re

_SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"'][^>]*>", re.I)
_SCRIPT_BLOCK = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.I | re.S)
_LINK = re.compile(r"<link\b[^>]*>", re.I)
_ATTR = re.compile(r"\b([a-zA-Z-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))")
# a hashed chunk name: a hex run, or a random-looking token that mixes digits and letters (Cc1RikHU, 2w685fod4in7o);
# `settings`, `billing-page`, `workspace_admin` are named (letters, words) and read first
_HASHY = re.compile(r"(?:^|[-._])[0-9a-f]{6,}(?:[-._]|$)|(?:^|[-._])(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{6,}(?=\.m?js$)")
_VENDORISH = re.compile(r"vendor|framework|polyfill|runtime|react|node_modules|gtm|analytics|sentry|tracking|locale/|/locales?/|intl", re.I)


@dataclass
class Discovered:
    scripts: list[str] = field(default_factory=list)
    modulepreload: list[str] = field(default_factory=list)
    inline_scripts: list[str] = field(default_factory=list)
    json_blocks: list[str] = field(default_factory=list)
    importmap: dict = field(default_factory=dict)
    icon_hosts: list[str] = field(default_factory=list)


def _attrs(tag: str) -> dict:
    return {m.group(1).lower(): htmlmod.unescape(m.group(2) or m.group(3) or m.group(4) or "") for m in _ATTR.finditer(tag)}


def page(page_url: str, html: str) -> Discovered:
    """Everything a page points at. Relative URLs resolve against `page_url` (pass the *final* URL after redirects)."""
    d = Discovered()
    seen = set()
    for m in _SCRIPT_SRC.finditer(html):
        u = urljoin(page_url, htmlmod.unescape(m.group(1)).strip())
        if u not in seen and u.startswith("http"):
            seen.add(u); d.scripts.append(u)
    for m in _SCRIPT_BLOCK.finditer(html):
        attrs, body = _attrs(m.group(1)), m.group(2)
        if "src" in attrs:
            continue
        t = attrs.get("type", "").lower()
        if t == "importmap":
            try:
                im = json.loads(body).get("imports", {})
                d.importmap = {k: urljoin(page_url, v) for k, v in im.items() if isinstance(v, str)}
            except (ValueError, AttributeError):
                pass
        elif t in ("application/json", "application/ld+json") or t.endswith("+json"):
            d.json_blocks.append(body.strip())
        elif body.strip():
            d.inline_scripts.append(body)
    for tag in _LINK.findall(html):
        a = _attrs(tag)
        rel, href = a.get("rel", "").lower(), a.get("href", "")
        if not href:
            continue
        u = urljoin(page_url, href)
        if ("modulepreload" in rel or ("preload" in rel and a.get("as", "").lower() == "script")) and re.search(r"\.m?js(\?|$)", u):
            if u not in seen:
                seen.add(u); d.modulepreload.append(u)
        if "icon" in rel or rel == "manifest":
            h = urlparse(u).netloc
            if h: d.icon_hosts.append(h)
    return d


# --- chunk maps ------------------------------------------------------------------------------

_ABS_JS = re.compile(r"[\"'](https?://[^\"'\s<>()]+?\.m?js(?:\?[^\"'\s]*)?)[\"']")
_REL_JS = re.compile(r"[\"'](/(?:_next|static|assets|build|js|dist|bundles?|chunks?|_app|app|webpack-artifacts)[^\"'\s<>()]*?\.m?js(?:\?[^\"'\s]*)?)[\"']")
_DOT_REL_JS = re.compile(r"import\(\s*[\"'](\.{1,2}/[^\"'\s]+?\.m?js)[\"']\s*\)")
_WEBPACK_U = re.compile(r"\.u\s*=\s*(?:function\s*\(\s*(\w+)\s*\)\s*\{\s*return\s*|(\w+)\s*=>\s*)", re.S)
_VITE_MAPDEPS = re.compile(r"__vite__mapDeps\s*=\s*\([^)]*?\(m\.f\|\|\(m\.f\s*=\s*(\[.*?\])\)\)", re.S)
_OBJ_LIT = re.compile(r"\{(?:\s*(?:\"[^\"]*\"|'[^']*'|[\w$]+)\s*:\s*(?:\"[^\"]*\"|'[^']*'|[\w$]+)\s*,?\s*)+\}", re.S)


def _parse_map(obj_text: str) -> dict:
    out = {}
    for m in re.finditer(r"(?:\"([^\"]*)\"|'([^']*)'|([\w$]+))\s*:\s*(?:\"([^\"]*)\"|'([^']*)'|([\w$]+))", obj_text):
        k = m.group(1) if m.group(1) is not None else m.group(2) if m.group(2) is not None else m.group(3)
        v = m.group(4) if m.group(4) is not None else m.group(5) if m.group(5) is not None else m.group(6)
        out[k] = v
    return out


def _webpack_chunks(js: str, base_url: str) -> set[str]:
    """Resolve `X.u = e => "prefix" + ({id:"name"}[e]||e) + "." + {id:"hash"}[e] + ".js"` shapes."""
    out = set()
    for m in _WEBPACK_U.finditer(js):
        start = m.end()
        # the expression runs to the next unbalanced ',' / ';' at paren depth 0; take a generous window
        seg = js[start:start + 400_000]
        end = len(seg)
        depth = 0
        in_str = None
        for i, ch in enumerate(seg):
            if in_str:
                if ch == "\\": continue
                if ch == in_str: in_str = None
                continue
            if ch in "\"'": in_str = ch
            elif ch in "({[": depth += 1
            elif ch in ")}]":
                depth -= 1
                if depth < 0: end = i; break
            elif ch in ",;" and depth == 0: end = i; break
        expr = seg[:end]
        strs = re.findall(r"\"([^\"]*)\"|'([^']*)'", expr)
        literals = [a or b for a, b in strs]
        spans = [(o.start(), o.end(), _parse_map(o.group(0))) for o in _OBJ_LIT.finditer(expr)]
        spans = [sp for sp in spans if len(sp[2]) >= 1]
        if not spans:
            continue
        maps = [mp for _, _, mp in spans]
        prefix = next((l for l in literals if l.endswith("/")), "")
        suffix = next((l for l in literals if l.startswith(".") and l.endswith("js")), ".js")
        name_map = next((mp for mp in maps if any(not re.fullmatch(r"[0-9a-f]{8,}", v) for v in mp.values())), {})
        hash_map = next((mp for mp in maps if mp is not name_map and all(re.fullmatch(r"[0-9a-f]{6,}", v) for v in list(mp.values())[:20])), {})
        sep = _separator(expr, spans, name_map, hash_map)
        ids = set(name_map) | set(hash_map)
        for cid in list(ids)[:3000]:
            name = name_map.get(cid, cid)
            h = hash_map.get(cid)
            path = f"{prefix}{name}" + (f"{sep}{h}" if h else "") + suffix
            out.add(urljoin(base_url, path))
    return out


def _separator(expr: str, spans: list, name_map: dict, hash_map: dict) -> str:
    """The literal between the name and the hash: `"."` in most builds, `"-"` in Notion's (`Name-0123abcd.js`).
    Read from the expression itself; a builder that assumes "." asks for 2,800 URLs that do not exist."""
    if not hash_map:
        return "."
    end = next((e for _, e, mp in spans if mp is name_map), None) if name_map else None
    start = next((b for b, _, mp in spans if mp is hash_map), None)
    if start is None:
        return "."
    between = expr[end if end is not None and end <= start else 0:start]
    lits = re.findall(r"\"([^\"]*)\"|'([^']*)'", between)
    # the first literal after the name (a path prefix has a "/"; a ternary's "" or "x" comes later): ".", "-", "_", ".chunk."
    lit = [a or b for a, b in lits if (a or b) and "/" not in (a or b)]
    return lit[0] if lit and len(lit[0]) <= 8 else "."


def _vite_chunks(js: str, base_url: str) -> set[str]:
    out = set()
    for m in _VITE_MAPDEPS.finditer(js):
        try:
            arr = json.loads(m.group(1))
        except ValueError:
            arr = re.findall(r"\"([^\"]+)\"", m.group(1))
        for a in arr:
            if isinstance(a, str) and re.search(r"\.m?js$", a):
                out.add(urljoin(base_url.rsplit("/assets/", 1)[0] + "/" if "/assets/" in base_url else base_url, a))
    return out


def chunks(js: str, base_url: str, is_first_party) -> set[str]:
    """First-party chunk URLs referenced inside a script."""
    found: set[str] = set()
    for m in _ABS_JS.finditer(js):
        found.add(m.group(1))
    for m in _REL_JS.finditer(js):
        found.add(urljoin(base_url, m.group(1)))
    for m in _DOT_REL_JS.finditer(js):
        found.add(urljoin(base_url, m.group(1)))
    found |= _webpack_chunks(js, base_url)
    found |= _vite_chunks(js, base_url)
    return {u for u in found if is_first_party(u)}


def select_by_role(candidates: list[str], entry: list[str] | None = None, cap: int = 60, preferred: set[str] | None = None) -> list[str]:
    """Entry scripts first (document order), then scripts the previous run read (continuity: a diff over a
    different sample is not a diff), then named (non-hash) chunks, then the rest; vendor-looking names last."""
    entry = [e for e in (entry or []) if e in candidates]
    rest = [c for c in candidates if c not in entry]
    preferred = preferred or set()

    def rank(u: str):
        name = urlparse(u).path.rsplit("/", 1)[-1]
        vendor = 1 if _VENDORISH.search(u) else 0
        hashy = 1 if _HASHY.search(name) else 0
        seen = 0 if u in preferred else 1
        return (vendor, seen, hashy)      # stable: within a rank, discovery order (the page's own order) stands
    ordered = entry + sorted(rest, key=rank)
    return ordered[:cap]
