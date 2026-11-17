"""Tolerant scanner for object/array literals in minified JS and page JSON (internal seam).

`iter_literals(text)` yields a `Literal` for every balanced object or array literal, innermost first, with
its depth. Keys and crude values at depth 1 are parsed lazily. The scanner is string-aware (single, double
and template quotes with escapes), treats function bodies as opaque nested braces, and gives up on one
unbalanced literal (never on the file). Classifiers in `extractors/` decide what a literal *is*.

Performance: one compiled-regex pass that only visits quotes and brackets (strings are consumed whole),
so an 8 MB bundle scans in about a second.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from functools import cached_property
from typing import Iterator
import re

# Strings consumed whole; template literals are approximated as plain strings (braces inside `${}` are
# then invisible, which is the tolerant choice); brackets drive the stack.
_TOK = re.compile(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`|[{}\[\]]')
_NEXT = re.compile(r'[{}\[\]"\'`/]')
# a regex literal or a comment is consumed whole, like a string, so a quote inside `/'/` or `/*! don't */`
# cannot flip the string phase and hide the rest of the line (Dropbox: 659 "strings" holding structural JS)
_REGEX = re.compile(r'/(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\n\[])+/[gimsuyd]*')
_REGEX_AFTER = re.compile(r'(?:^|[=(,:\[!&|?{};+\-*%<>~^]|\breturn|\btypeof|\bcase|\bin|\bof|\bvoid|\bdelete|\bnew|\bthrow|\byield|\bawait)\s*$')
_STR = {'"': re.compile(r'"(?:\\.|[^"\\\n])*"'), "'": re.compile(r"'(?:\\.|[^'\\\n])*'"), "`": re.compile(r'`(?:\\.|[^`\\])*`')}


def _tokens(text: str) -> Iterator[tuple[int, int, str]]:
    """(start, end, token) for every string and bracket. A quote that never closes (a bundle cut by the byte
    cap inside a `JSON.parse('…')` string, or a stray apostrophe in a regex) is a plain character — and so
    is every later quote of that kind up to the next newline (or the end), because no closing quote exists
    past this point either. Without that memo, `finditer` rescans to the end from each of the 2,696 `\\'`
    in one PostHog bundle: 62 s for one file; with it, milliseconds."""
    pos, n = 0, len(text)
    dead = {'"': -1, "'": -1, "`": -1}      # quote kind -> position before which that kind cannot open
    while pos < n:
        m = _NEXT.search(text, pos)
        if not m:
            return
        c = m.group(0); p = m.start()
        if c == "/":
            nxt = text[p + 1: p + 2]
            if nxt == "/":                                   # line comment
                nl = text.find("\n", p); pos = n if nl < 0 else nl + 1; continue
            if nxt == "*":                                   # block comment
                e = text.find("*/", p + 2); pos = n if e < 0 else e + 2; continue
            if _REGEX_AFTER.search(text, max(0, p - 12), p):
                rm = _REGEX.match(text, p)
                if rm:
                    pos = rm.end(); continue
            pos = p + 1; continue
        if c in '"\'`':
            if p < dead[c]:
                pos = p + 1; continue
            sm = _STR[c].match(text, p)
            if sm is None:
                nl = text.find("\n", p) if c != "`" else -1
                dead[c] = n if nl < 0 else nl + 1
                pos = p + 1; continue
            yield sm.start(), sm.end(), sm.group(0)
            pos = sm.end()
        else:
            yield p, p + 1, c
            pos = p + 1
_OPEN = {"{": "object", "[": "array"}
_CLOSE = {"}": "object", "]": "array"}

_KEY = r'(?:"((?:\\.|[^"\\])*)"|\'((?:\\.|[^\'\\])*)\'|(?<![\w$])([A-Za-z_$][\w$]*))'   # the lookbehind stops a bare-key retry at every position of a long word run (review S5)
_SCALAR = r'(true|false|!0|!1|null|void 0|undefined|-?\d+(?:\.\d+)?(?:e[+-]?\d+)?|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`)'
_PAIR = re.compile(_KEY + r'\s*:\s*' + _SCALAR + r'?', re.S)
_ITEM = re.compile(_SCALAR, re.S)
_FN_HINT = re.compile(r'^\s*(?:function\b|async\b|\(|[A-Za-z_$][\w$]*\s*=>|[A-Za-z_$][\w$]*\s*\()')


def _scalar(tok: str):
    if tok in ("true", "!0"): return True
    if tok in ("false", "!1"): return False
    if tok in ("null", "void 0", "undefined"): return None
    if tok[0] in "\"'`": return tok[1:-1]
    try:
        return int(tok) if re.fullmatch(r"-?\d+", tok) else float(tok)
    except ValueError:
        return tok


@dataclass
class Literal:
    start: int
    end: int
    kind: str                 # "object" | "array"
    depth: int
    _text: str = field(repr=False)
    _children: list = field(default_factory=list, repr=False)   # (start, end) of direct child literals

    @property
    def text(self) -> str:
        return self._text[self.start:self.end]

    def _gaps(self) -> list[tuple[int, int]]:
        """Depth-1 text ranges between direct child literals (absolute offsets)."""
        out, pos = [], self.start + 1
        for cs, ce in self._children:
            out.append((pos, cs)); pos = ce
        out.append((pos, self.end - 1))
        return out

    @cached_property
    def _parsed(self):
        keys, values, items = [], [], []
        src = self._text
        children = list(self._children)
        if self.kind == "object":
            # Walk gaps; a key whose value is missing in the gap is followed by a child literal or a function.
            for (gs, ge), nxt in zip(self._gaps(), children + [None]):
                gap = src[gs:ge]
                for m in _PAIR.finditer(gap):
                    k = m.group(1) if m.group(1) is not None else m.group(2) if m.group(2) is not None else m.group(3)
                    if k is None: continue
                    k = unescape(k) if "\\" in k else k
                    v = m.group(4)
                    if v is not None:
                        keys.append(k); values.append(_scalar(v))
                    else:
                        tail = gap[m.end():m.end() + 40]
                        if _FN_HINT.match(tail):
                            keys.append(k); values.append("fn")
                        elif m.end() >= len(gap.rstrip()) and nxt is not None:
                            keys.append(k); values.append("{}" if src[nxt[0]] == "{" else "[]")
                        elif re.match(r"\s*[A-Za-z_$][\w$.]*", tail):
                            keys.append(k); values.append("ref")
                        else:
                            keys.append(k); values.append(None)
        else:
            for (gs, ge), nxt in zip(self._gaps(), children + [None]):
                for m in _ITEM.finditer(src[gs:ge]):
                    items.append(_scalar(m.group(1)))
                if nxt is not None:
                    items.append("{}" if src[nxt[0]] == "{" else "[]")
        return keys, values, items

    @property
    def keys(self) -> list[str]:
        return self._parsed[0]

    @property
    def values(self) -> list[object]:
        return self._parsed[1]

    @property
    def items(self) -> list[object]:
        return self._parsed[2]


def unescape(s: str) -> str:
    """JS escapes in a key or value, with surrogate pairs rejoined (an emoji written as \\ud83d\\ude80 must not
    become two lone surrogates that SQLite and a UTF-8 file refuse; review S6)."""
    try:
        t = s.encode("utf-8").decode("unicode_escape", "ignore")
    except UnicodeDecodeError:
        return s
    try:
        return t.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    except UnicodeError:
        return t


_CACHE: dict = {}        # up to four bodies: (id(text), len(text), max_len, min_len) -> (text, list[Literal]); extractors and
_CACHE_MAX = 4           # their JSON.parse / inline sub-texts scan the same few texts in turn (review S13)


def iter_literals(text: str, max_len: int = 4_000_000, min_len: int = 6) -> Iterator[Literal]:
    """Every balanced literal, innermost first. One scan per body: the eleven extractors each ask for the same
    body's literals in turn, and the lazily parsed keys/values on each Literal are shared with them too."""
    key = (id(text), len(text), max_len, min_len)
    if key in _CACHE and _CACHE[key][0] is text:
        yield from _CACHE[key][1]; return
    lits = list(_scan(text, max_len, min_len))
    if len(_CACHE) >= _CACHE_MAX:
        del _CACHE[next(iter(_CACHE))]
    _CACHE[key] = (text, lits)      # holding `text` keeps id(text) from being reused
    yield from lits


def _scan(text: str, max_len: int, min_len: int) -> Iterator[Literal]:
    stack: list[list] = []          # [open_pos, kind, children]
    for tstart, tend, c in _tokens(text):
        if c in _OPEN:
            stack.append([tstart, _OPEN[c], []])
        elif c in _CLOSE:
            kind = _CLOSE[c]
            if not stack:
                continue
            if stack[-1][1] != kind:
                # Mismatch: drop frames until a matching open (tolerant), else ignore this close.
                idx = next((i for i in range(len(stack) - 1, -1, -1) if stack[i][1] == kind), None)
                if idx is None:
                    continue
                del stack[idx + 1:]
            start, _, children = stack.pop()
            end = tend
            if stack:
                stack[-1][2].append((start, end))
            if end - start >= min_len and end - start <= max_len:
                yield Literal(start, end, kind, len(stack), text, children)


def children(all_literals: list[Literal], parent: Literal) -> list[Literal]:
    spans = set(parent._children)
    return [l for l in all_literals if (l.start, l.end) in spans]


def parse_object_shallow(text: str) -> tuple[list[str], list[object]]:
    """Keys and crude values at depth 1 of one balanced object literal."""
    ls = [l for l in iter_literals(text) if l.kind == "object" and l.depth == 0]
    if not ls:
        return [], []
    big = max(ls, key=lambda l: l.end - l.start)
    return big.keys, big.values
