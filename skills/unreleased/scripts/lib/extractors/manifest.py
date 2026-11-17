"""manifest extractor: chunk and module names from bundler manifests and lazy imports. See plan-v1.md U2.

A bundler leaks the product map in its file names: `NewContainerImageForm-Tz8MZHAJ.js` says a form exists
before any route or flag does. The human name (hash and extension stripped) is the key; the file name is
the context; the receipt is the offset of the name inside the file string.

Shapes claimed, in order:
  M1 chunk arrays   Vite `__vite__mapDeps` / Rollup `m.f=[…]` arrays of `Name-hash.js` (or `dir/name.hash.js`,
                    `.css`) strings, >= 10 items of which >= 80% carry a hash — balanced literal, "high".
  M2 id→name maps   webpack chunk maps `{123:"ComponentName",456:"kebab-name"}`: >= 20 numeric keys whose
                    values are names — balanced literal, "high".
  M3 lazy imports   `import("./Name-hash.js")` / ``import(`./Name-hash.js`)`` call sites — "medium".
Dropped: `Icon*` / `icon-*` / `*Icon` chunks and a short list of plumbing names (index, vendor, runtime…).
Capped at 800 names per body. `group` is the name's noun (first camel/kebab word after stop words).
"""
from __future__ import annotations
import hashlib
import re
from dataclasses import replace

from schema import Observation, Source
import scanner

VERSION = "0.1.0"
NAME = "manifest"

_CAP = 800
_CTX = 200
_PLACEHOLDERS = ("fn", "ref", "{}", "[]")

# `dir/Name-hash.ext`, `Name.hash.ext`: the hash is Vite's 8 base64url chars, webpack's 6–24 hex, or any 6–24 mixed run
_FILE = re.compile(r"^(?:\.?/?(?:[\w@.-]+/)*)?([A-Za-z_$][\w$.-]*?)(?:\.chunk)?\.(m?js|css)$")
_HASH_TAILS = (re.compile(r"[-.]([A-Za-z0-9_-]{8})$"), re.compile(r"[-.]([a-f0-9]{6,24})$"), re.compile(r"[-.]([A-Za-z0-9_]{6,24})$"))
_NAME_VALUE = re.compile(r"^(?:[A-Z][A-Za-z0-9]+|[a-z][a-z0-9]*(?:[-_][a-z0-9]+)+)$")
_FILE_STRING = re.compile(r'"((?:\.?/?(?:[\w@.-]+/)*)?[A-Za-z_$][\w$.-]*\.(?:m?js|css))"')
_ID_NAME = re.compile(r'(?<![\w$.])(\d{1,8})\s*:\s*"([A-Za-z][\w-]{2,80})"')
_LAZY_IMPORT = re.compile(r'import\(\s*[`"\']((?:\./|/|\.\./)?[\w@./-]+\.(?:m?js|css))[`"\']\s*\)')
_ICON = re.compile(r"^(?:Icons?(?:[A-Z0-9]|$)|icons?[-_])|Icons?$")
_PLUMBING = frozenset(("index", "vendor", "vendors", "runtime", "polyfill", "polyfills", "main", "app", "chunk", "common",
                       "commons", "shared", "src", "esm", "cjs", "browser", "style", "styles", "types", "schemas",
                       "utils", "helpers", "constants", "hooks", "lib", "core", "client", "server", "entry", "module",
                       "framework", "webpack", "rolldown-runtime", "react", "react-dom", "en", "de", "fr", "es"))
_STOP = frozenset(("use", "get", "set", "is", "has", "new", "edit", "create", "delete", "update", "view", "show", "list",
                   "add", "remove", "on", "with", "app", "page", "pages", "route", "routes", "the", "a", "to", "for"))
_WORD = re.compile(r"[A-Z]{2,}(?=[A-Z][a-z]|\b|\d)|[A-Z]?[a-z]+|[A-Z]+|\d+")


def _oid(kind: str, key: str, src: Source) -> str:
    return hashlib.sha1(f"{kind}|{key}|{src.sha256}|{src.offset}".encode("utf-8")).hexdigest()[:16]


def _looks_hash(tail: str) -> bool:
    if re.search(r"\d", tail):
        return True
    upper = [i for i, c in enumerate(tail) if c.isupper()]
    return len(upper) >= 2 and any(c.islower() for c in tail)      # `BopHSQDa` yes, `Settings` no


def _split(file: str, assume_hash: bool = False) -> tuple[str, bool] | None:
    """(stem without hash, had_hash) for a chunk file name, or None when it is not one. `assume_hash` strips
    any 8-char tail (inside an array that is >= 80% hashed, `DatasetLibraryIcon-Dmtbomjr` is hashed too)."""
    m = _FILE.match(file)
    if not m:
        return None
    stem = m.group(1)
    for pat in _HASH_TAILS:
        h = pat.search(stem)
        if h and h.start() > 0 and (_looks_hash(h.group(1)) or (assume_hash and pat is _HASH_TAILS[0])):
            return stem[: h.start()], True
    return stem, False


def chunk_name(file: str, assume_hash: bool = False) -> str | None:
    """`assets/cofounder-BopHSQDa.js` -> `cofounder`; `app-side-menu.CcxsPVp9.js` -> `app-side-menu`; None if not a chunk."""
    sp = _split(file, assume_hash)
    return sp[0] if sp else None


def has_hash(file: str) -> bool:
    sp = _split(file)
    return bool(sp and sp[1])


def keep(name: str | None) -> bool:
    if not name or len(name) < 3 or len(name) > 80:
        return False
    if _ICON.search(name) or name.lower() in _PLUMBING:
        return False
    if re.fullmatch(r"[0-9a-f]{6,}|\d+", name):
        return False
    return bool(re.search(r"[A-Za-z]{3}", name))


def noun(name: str) -> str:
    words = [w.lower() for w in _WORD.findall(name.replace("-", " ").replace("_", " "))]
    words = [w for w in words if w not in _STOP] or words
    if not words:
        return ""
    if len(words[0]) <= 3 and len(words) > 1:
        return words[0] + words[1]
    return words[0]


class _Sink:
    def __init__(self, artifact: Source):
        self.artifact, self.out, self.seen = artifact, [], set()

    def add(self, name: str, offset: int, context: str, confidence: str) -> None:
        if len(self.out) >= _CAP or name in self.seen or not keep(name):
            return
        self.seen.add(name)
        src = replace(self.artifact, offset=offset)
        self.out.append(Observation(id=_oid("manifest", name, src), kind="manifest", key=name, source=src, group=noun(name),
                                    context=context[:_CTX], extractor=NAME, confidence=confidence))


def _item_offset(body: str, lit: scanner.Literal, item: str, name: str, after: int) -> int:
    """Offset of `name` inside the quoted `item` as it sits in the literal, searching forward from `after`."""
    for q in ('"', "'", "`"):
        i = body.find(q + item + q, after, lit.end)
        if i != -1:
            j = body.find(name, i, i + len(item) + 2)
            return j if j != -1 else i + 1
    return lit.start


def extract(body: str, artifact: Source) -> list[Observation]:
    sink = _Sink(artifact)
    lits = list(scanner.iter_literals(body))

    # --- M1 chunk arrays
    for l in lits:
        if l.kind != "array":
            continue
        items = [v for v in l.items if isinstance(v, str) and v not in _PLACEHOLDERS]
        if len(items) < 10 or len(items) * 2 < len(l.items):
            continue
        hashed = sum(1 for v in items if has_hash(v))
        if hashed * 5 < len(items) * 4:
            continue
        pos = l.start
        for v in items:
            name = chunk_name(v, assume_hash=True)
            if name is None:
                continue
            off = _item_offset(body, l, v, name, pos)
            pos = max(pos, off)
            sink.add(name, off, v, "high")

    # --- M1b the same arrays as text runs (an excerpt, or an array the scanner could not balance)
    run: list = []
    last_end = -1

    def flush_files(run):
        files = [m.group(1) for m in run]
        if len(files) < 10 or sum(1 for f in files if has_hash(f)) * 5 < len(files) * 4:
            return
        for m in run:
            name = chunk_name(m.group(1), assume_hash=True)
            if name is not None:
                off = body.find(name, m.start(1), m.end(1))
                sink.add(name, off if off != -1 else m.start(1), m.group(1), "medium")

    for m in _FILE_STRING.finditer(body):
        if run and m.start() - last_end > 3:
            flush_files(run); run = []
        run.append(m)
        last_end = m.end()
    flush_files(run)

    # --- M2 id -> name maps, read as text runs: the scanner does not parse bare numeric keys
    # (`{10026:"SimpleTableEditUI",1005:"icon-aws"}` yields no keys), so a run of >= 20 `digits:"name"` pairs is the shape.
    run: list = []
    last_end = -1

    def flush(run):
        if len(run) < 20:
            return
        for m in run:
            sink.add(m.group(2), m.start(2), f"{m.group(1)}:{m.group(2)}", "high")

    for m in _ID_NAME.finditer(body):
        if run and m.start() - last_end > 3:
            flush(run); run = []
        run.append(m)
        last_end = m.end()
    flush(run)

    # --- M3 lazy imports
    for m in _LAZY_IMPORT.finditer(body):
        file = m.group(1)
        name = chunk_name(file)
        if name is None:
            continue
        off = body.find(name, m.start(1), m.end(1))
        sink.add(name, off if off != -1 else m.start(1), file, "medium")
    return sink.out
