"""report: a shareable file from a run folder and the host's brief.

Two outputs from the same material, so a reader gets the same thing in a browser, in print, in Slack or a wiki:

- `report.html` — one self-contained file. No JavaScript, no external assets (a system font stack that picks up
  Inter and JetBrains Mono when they are installed), `<details>` for folding, a print stylesheet, light and
  dark from `prefers-color-scheme`. Every design decision is a CSS custom property in `TOKENS`; a design
  system is a `--theme tokens.css` away. docs/report-design.md is the system and the reasons.
- `report.md` — the brief followed by the appendix as Markdown.

Three readers, three layers (docs/report-design.md):
  the 30-second reader gets the verdict strip and the shape paragraph;
  the 5-minute reader gets the findings as components (noun · confidence · fact · raises);
  the verifier gets evidence on demand — the engine's own context line for every key the brief names,
  folded under the finding, plus coverage as a source grid and every receipt.

The brief is parsed, not guessed: brief.md's layout is a small grammar (badge line, one-line read, the shape
paragraph, `N. **Noun** · confidence` items with `Raises:` lines, bold-led blocks, a Receipts block, a fenced
footer). Anything the parser does not recognise renders as plain Markdown, never dropped. Nothing is
reworded; receipts stay receipts (text, no local paths — a shareable file carries nothing of the author's).
"""
from __future__ import annotations

import html
import json
import os
import re

from schema import partial_sources

# ---- design tokens (extracted from the reference campaign brief; see docs/report-design.md) ---------------------

TOKENS = """
:root {
  /* design tokens, measured from the reference campaign brief (docs/design-system.md). Override with --theme tokens.css. */
  --canvas: #f9fafb;        --surface: #ffffff;       --panel: #f9fafb;         --panel-2: #f3f4f6;
  --ink-900: #111827;       --ink-800: #1f2937;       --ink-700: #374151;       --ink-600: #4b5563;       --ink-500: #6b7280;       --ink-400: #9ca3af;       --ink-300: #d1d5db;
  --rule: #e5e7eb;          --rule-2: #f3f4f6;
  --info-bg: #eff6ff;       --info-ink: #1e40af;      --info-accent: #3b82f6;   --info-badge: #1d4ed8;
  --ok-bg: #ecfdf5;         --ok-ink: #065f46;        --ok-dot: #10b981;        --ok-text: #059669;       --ok-border: #a7f3d0;
  --warn-bg: #fefce8;       --warn-ink: #a16207;      --warn-dot: #facc15;      --warn-text: #d97706;     --warn-border: #fef08a;
  --bad-bg: #fef2f2;        --bad-ink: #991b1b;       --bad-dot: #f87171;       --bad-text: #b91c1c;      --bad-border: #fecaca;
  --font: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  --size: 16px;             --line: 24px;             --sm: 14px;               --sm-line: 20px;          --xs: 12px;               --xs-line: 16px;
  --h1: 24px;               --h1-line: 32px;          --h2: 20px;               --h2-line: 28px;          --h3: 16px;               --h3-line: 24px;
  --measure: 66ch;          --rail: 224px;            --page-max: 1280px;       --gutter: 24px;
  --radius-card: 12px;      --radius: 8px;            --radius-s: 6px;          --card-pad: 32px;         --card-gap: 32px;
  --label-tracking: .05em;
}
"""

CSS = """
*, *::before, *::after { box-sizing: border-box; }
html { background: var(--canvas); color: var(--ink-800); font: var(--size)/var(--line) var(--font); -webkit-text-size-adjust: 100%; font-feature-settings: "tnum" 1; }
body { margin: 0; }
a { color: inherit; text-decoration: underline; text-decoration-color: var(--ink-300); text-underline-offset: 2px; } a:hover { text-decoration-color: var(--ink-700); }
code { font-family: var(--mono); font-size: var(--xs); line-height: var(--xs-line); background: var(--panel-2); border-radius: 4px; padding: 1px 5px; color: var(--ink-700); }
pre { font-family: var(--mono); font-size: var(--xs); line-height: var(--xs-line); background: var(--panel); border: 1px solid var(--rule); border-radius: var(--radius); padding: 16px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; margin: 0; color: var(--ink-800); }
pre code { background: none; padding: 0; }
p { margin: 0 0 12px; max-width: var(--measure); font-size: var(--sm); line-height: var(--sm-line); } ul, ol { margin: 0 0 12px; padding-left: 1.4em; max-width: var(--measure); font-size: var(--sm); line-height: var(--sm-line); } li { margin: 4px 0; }
h1, h2, h3 { margin: 0; color: var(--ink-900); }
h1 { font-size: var(--h1); line-height: var(--h1-line); font-weight: 700; } h2 { font-size: var(--h2); line-height: var(--h2-line); font-weight: 700; } h3 { font-size: var(--h3); line-height: var(--h3-line); font-weight: 600; color: var(--ink-800); }
sup { font-size: .7em; color: var(--ink-500); font-weight: 600; line-height: 0; margin-left: .15em; }
.label { font-size: var(--xs); line-height: var(--xs-line); font-weight: 600; letter-spacing: var(--label-tracking); text-transform: uppercase; color: var(--ink-400); }
.mono { font-family: var(--mono); font-size: var(--xs); }
.muted { color: var(--ink-500); } .small { font-size: var(--sm); line-height: var(--sm-line); } .xs { font-size: var(--xs); line-height: var(--xs-line); }

/* header: product · document · set, with a status pill on the right */
.topbar { position: sticky; top: 0; z-index: 2; background: var(--surface); border-bottom: 1px solid var(--rule); }
.topbar .inner { max-width: var(--page-max); margin: 0 auto; padding: 12px var(--gutter); display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.topbar .left, .topbar .right { display: flex; align-items: center; gap: 12px; }
.topbar .product { font-weight: 600; color: var(--ink-900); } .topbar .sep { color: var(--ink-300); } .topbar .doc { font-size: var(--sm); color: var(--ink-500); } .topbar .set { font-size: var(--sm); font-weight: 500; color: var(--ink-700); }
.topbar .date { font-size: var(--xs); color: var(--ink-400); }
.pill { display: inline-flex; align-items: center; gap: 4px; padding: 4px 8px; border-radius: 9999px; font-size: var(--xs); line-height: var(--xs-line); font-weight: 500; border: 1px solid var(--rule); color: var(--ink-600); background: var(--surface); white-space: nowrap; }
.pill.rich, .pill.high-x { background: var(--ok-bg); color: var(--ok-ink); border-color: var(--ok-border); }
.pill.partial, .pill.medium { background: var(--warn-bg); color: var(--warn-ink); border-color: var(--warn-border); }
.pill.could-not-see, .pill.low { background: var(--bad-bg); color: var(--bad-ink); border-color: var(--bad-border); }
.pill.high { color: var(--ink-500); }

/* layout: rail + main */
.layout { max-width: var(--page-max); margin: 0 auto; padding: 32px var(--gutter); display: flex; gap: 32px; align-items: flex-start; }
.rail { width: var(--rail); flex: none; position: sticky; top: 64px; }
.rail .label { margin-bottom: 12px; display: block; } .rail a { display: block; font-size: var(--sm); line-height: var(--sm-line); color: var(--ink-500); padding: 4px 0; text-decoration: none; transition: color .15s; } .rail a:hover { color: var(--ink-900); }
.rail a.sub { font-size: var(--xs); line-height: var(--xs-line); color: var(--ink-400); padding: 3px 0 3px 12px; }
.rail hr { border: 0; border-top: 1px solid var(--rule); margin: 12px 0; }
main { flex: 1; min-width: 0; }
.card { background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius-card); padding: var(--card-pad); margin-top: var(--card-gap); scroll-margin-top: 24px; }
.card:first-child { margin-top: 0; }
.card > h2 { margin-bottom: 24px; } .card > h2 + .lead { margin-top: -16px; }
.lead { color: var(--ink-500); font-size: var(--sm); line-height: var(--sm-line); margin-bottom: 24px; }
.title-doc { color: var(--ink-500); font-weight: 400; }

/* key / value grid (the reference's two- and three-column facts) */
.kv { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px 24px; margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--rule-2); }
.kv .k { display: block; margin-bottom: 4px; } .kv .v { font-size: var(--sm); line-height: var(--sm-line); color: var(--ink-800); max-width: none; }
.kv .big { font-size: var(--h1); line-height: var(--h1-line); font-weight: 700; color: var(--ink-900); font-variant-numeric: tabular-nums; } .kv .big small { font-size: var(--sm); font-weight: 400; color: var(--ink-500); margin-left: 6px; }
.kv .v.ok { color: var(--ok-text); } .kv .v.warn { color: var(--warn-text); } .kv .v.bad { color: var(--bad-text); }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ink-300); flex: none; display: inline-block; position: relative; top: -1px; } .dot.ok { background: var(--ok-dot); } .dot.warn { background: var(--warn-dot); } .dot.bad { background: var(--bad-dot); }
.readline { color: var(--ink-500); font-size: var(--sm); line-height: var(--sm-line); margin: 16px 0 0; max-width: none; }

/* callouts: info (the reading), ok / warn / bad panels */
.callout { border-radius: var(--radius); padding: 16px; font-size: var(--sm); line-height: var(--sm-line); margin-top: 24px; max-width: none; }
.callout.info { background: var(--info-bg); color: var(--info-ink); } .callout.info .label { color: var(--info-badge); display: block; margin-bottom: 6px; }
.callout.info p { color: inherit; margin: 0; max-width: none; font-size: var(--sm); } .callout.info code { background: rgba(255,255,255,.6); color: inherit; }
.callout.warn { background: var(--warn-bg); color: var(--warn-ink); } .callout.ok { background: var(--ok-bg); color: var(--ok-ink); } .callout.bad { background: var(--bad-bg); color: var(--bad-ink); }

/* findings: numbered rows with a mono id chip */
.group { margin: 24px 0 8px; } .group:first-of-type { margin-top: 16px; }
.finding { display: grid; grid-template-columns: 40px minmax(0, 1fr); gap: 0 12px; padding: 20px 0; border-top: 1px solid var(--rule-2); scroll-margin-top: 24px; }
.finding:last-child { padding-bottom: 0; }
.finding .n { font-family: var(--mono); font-size: var(--xs); font-weight: 500; color: var(--ink-600); background: var(--panel); border: 1px solid var(--rule); border-radius: var(--radius-s); height: 24px; min-width: 32px; padding: 0 6px; display: inline-flex; align-items: center; justify-content: center; }
.finding .head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 6px; } .finding .noun { font-weight: 600; font-size: var(--size); line-height: var(--line); color: var(--ink-900); }
.finding .fact { color: var(--ink-800); max-width: var(--measure); font-size: var(--sm); line-height: var(--sm-line); } .finding .fact code { white-space: nowrap; }
.finding .checked { color: var(--ink-500); font-size: var(--sm); line-height: var(--sm-line); max-width: var(--measure); margin-top: 6px; display: grid; grid-template-columns: auto 1fr; gap: 8px; } .finding .checked .label { padding-top: 2px; }
.finding .raises { color: var(--ink-700); font-size: var(--sm); line-height: var(--sm-line); max-width: var(--measure); margin-top: 8px; display: grid; grid-template-columns: auto 1fr; gap: 8px; } .finding .raises .label { padding-top: 2px; }
.finding details { margin-top: 10px; border: 1px solid var(--rule-2); border-radius: var(--radius); } .finding summary { padding: 10px 12px; font-size: var(--xs); color: var(--ink-600); font-weight: 500; }
.ev { margin: 0; padding: 0 12px 12px; list-style: none; } .ev li { font-family: var(--mono); font-size: var(--xs); line-height: var(--xs-line); color: var(--ink-700); background: var(--panel); border: 1px solid var(--rule); border-radius: var(--radius-s); padding: 8px 10px; margin: 6px 0 0; word-break: break-word; }
.ev li .k { color: var(--ink-900); font-weight: 600; } .ev li mark { background: var(--warn-border); color: inherit; border-radius: 2px; padding: 0 1px; } .ev li .meta { color: var(--ink-400); display: block; margin-top: 3px; }
.block { margin-top: 24px; max-width: var(--measure); } .block .label { display: block; margin-bottom: 6px; } .block p { margin: 0; }

/* tables, grids, folds */
table { border-collapse: collapse; width: 100%; font-size: var(--sm); line-height: var(--sm-line); margin: 8px 0 0; }
th { text-align: left; font-size: var(--xs); line-height: var(--xs-line); font-weight: 700; color: var(--ink-400); padding: 0 16px 8px 0; border-bottom: 1px solid var(--rule); }
td { vertical-align: top; padding: 8px 16px 8px 0; border-bottom: 1px solid var(--rule-2); color: var(--ink-800); } tr:last-child td { border-bottom: 0; }
td.k, td .mono { font-family: var(--mono); font-size: var(--xs); color: var(--ink-600); word-break: break-all; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px 16px; margin-top: 16px; }
.grid .cell { display: flex; gap: 8px; align-items: baseline; font-size: var(--sm); line-height: var(--sm-line); color: var(--ink-800); padding: 10px 12px; background: var(--panel); border-radius: var(--radius); }
.grid .cell b { font-weight: 600; color: var(--ink-900); margin-right: 4px; } .grid .cell { min-width: 0; overflow-wrap: anywhere; } .grid .cell span { color: var(--ink-500); }
.since { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; } .since .chip { font-size: var(--sm); color: var(--ink-800); background: var(--panel); border-radius: var(--radius-s); padding: 6px 10px; } .since .chip b { color: var(--ink-900); font-variant-numeric: tabular-nums; }
details { border: 0; } summary { cursor: pointer; list-style: none; display: flex; align-items: center; justify-content: space-between; gap: 8px; } summary::-webkit-details-marker { display: none; } summary::marker { content: ""; }
summary .chev { display: inline-block; transition: transform .2s; color: var(--ink-400); font-size: 12px; } details[open] summary .chev { transform: rotate(180deg); }
.fold { border: 1px solid var(--rule-2); border-radius: var(--radius); margin-top: 12px; } .fold > summary { padding: 16px; font-weight: 500; font-size: var(--sm); color: var(--ink-700); } .fold > *:not(summary) { padding: 0 16px 16px; }
.receipts { font-size: var(--xs); line-height: var(--xs-line); color: var(--ink-500); max-width: none; } .receipts .line { display: block; padding: 2px 0; } .receipt { font-family: var(--mono); font-size: var(--xs); color: var(--ink-500); word-break: break-all; }
.boiler { color: var(--ink-500); font-size: var(--xs); line-height: var(--xs-line); max-width: none; border-top: 1px solid var(--rule); padding-top: 16px; margin-top: 24px; }
.footer { margin-top: 16px; }
.md > *:last-child { margin-bottom: 0; }

@media (max-width: 860px) { .layout { display: block; padding: 16px; } .rail { display: none; } .card { padding: 20px; } .topbar .inner { padding: 10px 16px; } .kv .big { font-size: var(--h2); }
  .topbar .doc, .topbar .doc + .sep, .topbar .date { display: none; } .topbar .set { white-space: nowrap; } }
@media print { html { font-size: 11pt; background: #fff; } .topbar, .rail { display: none; } .layout { display: block; padding: 0; max-width: none; }
  .card { border: 0; padding: 0; margin: 0 0 18pt; break-inside: avoid; } details:not([open]) > *:not(summary) { display: block; } summary .chev { display: none; } a { text-decoration: none; } .no-print { display: none; } }
"""


# ---- sentence case: the renderer's guarantee ----------------------------------------------------------------

_KEEP_LOWER = {"iOS", "iPadOS", "macOS", "watchOS", "tvOS", "visionOS", "iCloud", "iPhone", "iPad", "iMessage", "eBay", "npm", "npx",
               "pip", "pnpm", "yarn", "gRPC", "oEmbed", "webhooks", "ffmpeg", "llms.txt", "robots.txt", "sitemap.xml", "localhost"}
_ABBREV = {"e.g", "i.e", "vs", "etc", "approx", "no", "fig", "cf", "al", "v", "ver", "min", "max", "sec", "ca"}
_BOUNDARY = re.compile(r"(^|[.!?](?:[\"')\]]|\*\*|\*)*\s+)((?:\*\*|\*|\[|\"|\(|')*)([a-z])")
_WORD_AFTER = re.compile(r"[A-Za-z][\w.\-/@+:]*")
_WORD_BEFORE = re.compile(r"([A-Za-z0-9][A-Za-z0-9.]*)[.!?]$")


def sentence_case(text: str) -> str:
    """Every sentence starts with a capital letter. Code spans are opaque; a word with its own capitals (iOS,
    macOS), a path or url (contains . / @ :), a known lowercase name (npm, robots.txt) and the word after an
    abbreviation (e.g., vs., etc.) or a version number are left as the author wrote them."""
    parts = _INLINE_CODE.split(text)
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:
            out.append(f"`{p}`"); continue

        def fix(m: re.Match) -> str:
            head, marks, ch = m.group(1), m.group(2), m.group(3)
            if head == "" and i > 0:
                return m.group(0)                                 # continues a sentence after a code span
            if head:
                prev = _WORD_BEFORE.search(p[:m.start() + len(head)].rstrip(" \"')]*"))
                if prev and (prev.group(1).lower() in _ABBREV or len(prev.group(1)) == 1 or any(c.isdigit() for c in prev.group(1))):
                    return m.group(0)                             # "e.g. x", "J. x", "v0.1.0 x"
            word = _WORD_AFTER.match(p, m.start(3))
            w = word.group(0).rstrip(".,;:") if word else ch
            if w in _KEEP_LOWER or any(c in w for c in "/@:") or "." in w.rstrip(".") or (len(w) > 1 and any(c.isupper() for c in w)):
                return m.group(0)
            return head + marks + ch.upper()
        out.append(_BOUNDARY.sub(fix, p))
    return "".join(out)


# ---- inline + markdown subset ----------------------------------------------------------------------------------

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITAL = re.compile(r"(?<![*\w])\*([^*\n]+?)\*(?!\w)")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_URL = re.compile(r"(?<![\"'(>=])\b(https?://[^\s<>()\]]+[^\s<>()\].,;:!?])")
_SUP = re.compile(r"([¹²³⁴⁵⁶⁷⁸⁹⁰]+)")
_RECEIPT = re.compile(r"sha256:([0-9a-f]{12})@(\d+)")
_SUPMAP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def inline(text: str, blob_dir: str | None = None, prose: bool = True) -> str:
    """Escape, then the brief's inline forms. Code spans are opaque to everything else. Receipts are text.
    Prose is sentence-cased before anything else (the renderer's guarantee; see sentence_case)."""
    if prose:
        text = sentence_case(text)
    parts = _INLINE_CODE.split(text)
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:
            out.append(f"<code>{html.escape(p)}</code>"); continue
        s = html.escape(p, quote=False)
        s = _LINK.sub(lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', s)
        s = _URL.sub(lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>', s)
        s = _BOLD.sub(r"<strong>\1</strong>", s)
        s = _ITAL.sub(r"<em>\1</em>", s)
        s = _SUP.sub(r"<sup>\1</sup>", s)
        s = _RECEIPT.sub(r'<span class="receipt" title="blob sha256 prefix @ byte offset">sha256:\1@\2</span>', s)
        out.append(s)
    return "".join(out)


def markdown(md: str, blob_dir: str | None = None) -> str:
    """The subset the brief contract uses; unknown constructs become paragraphs, never dropped."""
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []; i = 0; para: list[str] = []

    def flush():
        nonlocal para
        if para:
            joined = para[0].strip()
            for x in para[1:]:
                joined += ("\n" if _SUP.match(x.strip()) else " ") + x.strip()
            cls = ' class="receipts"' if joined.startswith("**Receipts**") else ""
            prose = not (joined.startswith("**Receipts**") or joined.startswith("🔎") or _SUP.match(joined))
            out.append(f"<p{cls}>" + "<br>".join(inline(t, blob_dir, prose and not _SUP.match(t)) for t in joined.split("\n")) + "</p>"); para = []

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            flush(); j = i + 1; buf = []
            while j < len(lines) and not lines[j].startswith("```"):
                buf.append(lines[j]); j += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(buf))}</code></pre>"); i = j + 1; continue
        m = re.match(r"^(#{1,3})\s+(.*)$", ln)
        if m:
            flush(); out.append(f"<h{len(m.group(1))}>{inline(m.group(2), blob_dir)}</h{len(m.group(1))}>"); i += 1; continue
        if re.match(r"^\s*(?:-{3,}|\*{3,})\s*$", ln):
            flush(); out.append("<hr>"); i += 1; continue
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            flush(); head = [c.strip() for c in ln.strip("|").split("|")]; i += 2; rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")]); i += 1
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table>"); continue
        m = re.match(r"^(\s*)([-*]|\d+[.)])\s+(.*)$", ln)
        if m:
            flush(); ordered = m.group(2)[0].isdigit(); tag = "ol" if ordered else "ul"; items = []
            start = int(re.match(r"\d+", m.group(2)).group()) if ordered else None
            while i < len(lines):
                m2 = re.match(r"^(\s*)([-*]|\d+[.)])\s+(.*)$", lines[i])
                if m2 and (m2.group(2)[0].isdigit() == ordered):
                    items.append([m2.group(3)]); i += 1
                    while i < len(lines) and lines[i].startswith("   ") and not re.match(r"^\s*([-*]|\d+[.)])\s+", lines[i]):
                        items[-1].append(lines[i].strip()); i += 1
                    continue
                break
            body = "".join("<li>" + "<br>".join(inline(x, blob_dir) for x in it) + "</li>" for it in items)
            out.append(f"<{tag}{f' start={chr(34)}{start}{chr(34)}' if ordered and start not in (None, 1) else ''}>{body}</{tag}>"); continue
        if not ln.strip():
            flush(); i += 1; continue
        para.append(ln); i += 1
    flush()
    return "\n".join(out)


# ---- the brief grammar ------------------------------------------------------------------------------------------

_ITEM = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*(?:·\s*(high|medium|low)\b\s*(?:\(([^)]*)\))?)?\s*(.*)$")
_GROUP = re.compile(r"^\*([A-Za-z][^*]{1,60})\*\s*$")
_BOLD_GROUP = re.compile(r"^\*\*([A-Za-z][^*:(]{1,40})\*\*\s*$")     # a bold label directly followed by numbered items is a group, not a block
_BLOCK = re.compile(r"^\*\*([^*]{2,60})\*\*\s*(?:\((\d+)\))?\s*(?:—|-|:)?\s*(.*)$")
_RAISES = re.compile(r"^Raises:\s*(.*)$")


def parse_brief(md: str) -> dict:
    """badge, lead, shape, groups[{name, items[{n, noun, conf, conf_note, fact[], raises}]}], blocks[{title, count, text}],
    footer, rest (lines the grammar did not claim, kept in order under 'rest' as markdown)."""
    lines = md.replace("\r\n", "\n").strip().split("\n")
    b: dict = {"badge": "", "lead": "", "shape": "", "groups": [], "blocks": [], "footer": "", "rest": []}
    i = 0
    if lines and lines[0].startswith("🔎"):
        b["badge"] = lines[0].strip(); i = 1
        lead = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith("**"):
            lead.append(lines[i].strip()); i += 1
        b["lead"] = " ".join(lead)
    cur_group = None
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```text"):
            j = i + 1; buf = []
            while j < len(lines) and not lines[j].startswith("```"):
                buf.append(lines[j]); j += 1
            b["footer"] = "\n".join(buf); i = j + 1; continue
        if ln.startswith("**The shape of it**"):
            para = [ln]; i += 1
            while i < len(lines) and lines[i].strip():
                para.append(lines[i].strip()); i += 1
            b["shape"] = " ".join(para); continue
        m = _ITEM.match(ln)
        if m:
            if cur_group is None:
                cur_group = {"name": "", "items": []}; b["groups"].append(cur_group)
            item = {"n": int(m.group(1)), "noun": m.group(2), "conf": m.group(3) or "", "conf_note": m.group(4) or "", "fact": [], "raises": ""}
            if m.group(5).strip():
                item["fact"].append(m.group(5).strip())
            i += 1
            while i < len(lines) and lines[i].startswith("   ") and lines[i].strip():
                t = lines[i].strip(); r = _RAISES.match(t)
                if r: item["raises"] = r.group(1)
                else: item["fact"].append(t)
                i += 1
            cur_group["items"].append(item); continue
        g = _GROUP.match(ln.strip()) or _BOLD_GROUP.match(ln.strip())
        if g and (i + 1 < len(lines)) and any(_ITEM.match(x) for x in lines[i + 1:i + 4]):
            cur_group = {"name": g.group(1).strip(), "items": []}; b["groups"].append(cur_group); i += 1; continue
        mb = _BLOCK.match(ln)
        if mb and not ln.startswith("**The shape of it**"):
            title = mb.group(1).strip(); text = [mb.group(3).strip()] if mb.group(3).strip() else []
            i += 1
            while i < len(lines) and lines[i].strip() and not _BLOCK.match(lines[i]) and not lines[i].startswith("```") and not _ITEM.match(lines[i]):
                text.append(lines[i].strip()); i += 1
            if title == "Unannounced":
                cur_group = None; b["unannounced_count"] = mb.group(2); continue
            b["blocks"].append({"title": title, "count": mb.group(2), "text": "\n".join(text)})
            cur_group = None if title not in ("Unannounced",) else cur_group
            continue
        if ln.strip():
            if ln.startswith("These are strings present in public code"):
                i += 1; continue             # the boilerplate is printed once, by the engine, at the end
            b["rest"].append(ln)
        i += 1
    return b


# ---- run folder ---------------------------------------------------------------------------------------------------

def _load(run_dir: str):
    def j(name, default):
        p = os.path.join(run_dir, name)
        if not os.path.exists(p):
            return default
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    obs = []
    p = os.path.join(run_dir, "evidence.jsonl")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            obs = [json.loads(l) for l in f if l.strip()]
    checks = {}
    p = os.path.join(run_dir, "checks.jsonl")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for l in f:
                if l.strip():
                    c = json.loads(l); checks[c.get("observation_id")] = c
    ev = ""
    p = os.path.join(run_dir, "evidence.md")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            ev = f.read()
    return j("manifest.json", {}), j("coverage.json", {}), j("diff.json", None), j("signals.json", {}), obs, ev, checks


def _section(ev_md: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}[^\n]*\n(.*?)(?=^## |^These are strings present|^```text|\Z)", ev_md, re.S | re.M)
    return m.group(1).strip() if m else ""


def _footer(ev_md: str) -> str:
    m = re.search(r"```text\n(.*?)\n```", ev_md, re.S)
    return m.group(1) if m else ""


def _verdict(coverage: dict) -> str:
    v = coverage.get("verdict")
    if v:
        return v
    if not coverage.get("first_party_bytes"):
        return "could-not-see"
    return "partial" if partial_sources(coverage.get("sources", [])) else "rich"


def _receipt(o: dict) -> str:
    src = o.get("source", {})
    return f"{src.get('url', '').rsplit('/', 1)[-1]} sha256:{src.get('sha256', '')[:12]}@{src.get('offset')}"


def _val(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "on" if v else "off"
    return str(v)[:60]


def _cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")[:80]


_STATE_CLASS = {"ok": "ok", "no-results": "", "partial": "warn", "capped": "warn", "runtime-only": "warn", "rate-limited": "warn", "timeout": "warn",
                "blocked-403": "bad", "challenge": "bad", "error": "bad", "unreachable": "bad", "schema-drift": "warn", "skipped-unconfigured": ""}


_CHECKED = re.compile(r"(?:^|[—–:.;-])\s*(checked[:,].*)$", re.I | re.S)


def split_checked(fact: str) -> tuple[str, str]:
    """`fact — checked: pricing-text, nothing. ¹` → (fact, "checked: pricing-text, nothing. ¹"). The last dash-led
    checked clause is the checked beat; the fact keeps everything before it."""
    m = None
    for m in _CHECKED.finditer(fact):
        pass
    if not m:
        return fact, ""
    head, chk = fact[:m.start() + (1 if fact[m.start():m.start() + 1] in ".;" else 0)].rstrip(), m.group(1).strip()
    # the checked beat is one sentence; a sentence after it ("My reading: …") belongs to the fact
    sm = re.search(r"(?<=[.!?])(\s*[¹²³⁴⁵⁶⁷⁸⁹⁰]*)\s+(?=[A-Z])", chk)
    if sm:
        tail = chk[sm.end():].strip(); chk = chk[:sm.end()].strip()
        if tail:
            head = (head + ("" if head.endswith((".", ";", ":", "!", "?")) else ".") + " " + tail).strip()
    return head, chk


def _evidence_for(item: dict, by_key: dict) -> list[dict]:
    keys = []
    for line in item["fact"]:
        keys += _INLINE_CODE.findall(line)
    seen, out = set(), []
    for k in keys:
        k = k.strip()
        if k in seen or k not in by_key:
            continue
        seen.add(k); out.append(by_key[k])
        if len(out) >= 4:
            break
    return out


def _snippet(o: dict) -> str:
    ctx = (o.get("context") or "").replace("\n", " ")
    key = str(o.get("key", ""))
    esc = html.escape(ctx[:220])
    if key and key in ctx[:220]:
        esc = esc.replace(html.escape(key), f"<mark>{html.escape(key)}</mark>", 1)
    val = _val(o.get("value"))
    head = f'<span class="k">{html.escape(key)}</span>' + (f" = {html.escape(val)}" if val else "") + f' <span class="muted">({html.escape(str(o.get("kind")))})</span>'
    return f"<li>{head}" + (f"<br>{esc}" if esc else "") + f'<span class="meta">{html.escape(_receipt(o))}</span></li>'


# ---- build -------------------------------------------------------------------------------------------------------

def brief_run_id(brief_md: str) -> str | None:
    """The run id the brief's fenced footer names (`· run 2026-11-04T161005Z ·`)."""
    m = re.search(r"·\s*run\s+(\d{4}-\d{2}-\d{2}T\d{6}Z)\s*·", brief_md)
    return m.group(1) if m else None


def build(run_dir: str, brief_md: str | None, theme_css: str | None = None, blob_dir: str | None = None, top: int = 40) -> tuple[str, str]:
    """Returns (html, markdown). A brief whose footer names a different run than `run_dir` is still rendered, with a note."""
    manifest, coverage, diff, signals, obs, ev, checks = _load(run_dir)
    product = manifest.get("product", os.path.basename(os.path.dirname(run_dir.rstrip("/"))))
    run_id = manifest.get("run_id", os.path.basename(run_dir.rstrip("/")))
    version = manifest.get("engine_version", "")
    verdict = _verdict(coverage)
    campaign = _section(ev, "Campaign signals"); since = _section(ev, "Since"); cov = _section(ev, "Coverage")
    footer = _footer(ev)
    findings = [o for o in obs if o.get("tier") == "finding" and o.get("kind") not in ("robots", "sitemap", "headline")]
    findings.sort(key=lambda o: (-o.get("salience", 0), o.get("key", "")))
    seen_keys, dedup = set(), []                       # the same count as the footer: one line per key
    for o in findings:
        if o.get("key") in seen_keys:
            continue
        seen_keys.add(o.get("key")); dedup.append(o)
    findings = dedup
    by_key = {}
    for o in obs:
        by_key.setdefault(str(o.get("key")), o)
    boiler = ""
    m = re.search(r"^These are strings present in public code.*?$", ev, re.M | re.S)
    if m:
        boiler = m.group(0).split("\n\n")[0]
    sources = _collapse_pages(coverage.get("sources", []))
    bad_states = [s for s in sources if _STATE_CLASS.get(s.get("state"), "") in ("warn", "bad")]
    brief = parse_brief(brief_md) if brief_md else None
    mismatch = brief_run_id(brief_md) if brief_md else None
    mismatch = mismatch if (mismatch and mismatch != run_id) else None
    n_items = sum(len(g["items"]) for g in brief["groups"]) if brief else 0

    # ---------------- markdown
    md: list[str] = []
    if brief_md:
        md.append(brief_md.strip())
    else:
        md += [f"🔎 unreleased {version} · {product} · {run_id[:10]} · {verdict}", "",
               "*Evidence report. No brief was written for this run; what follows is the engine's ranked evidence, not a reading of it.*"]
    md += ["", "---", "", "## Appendix (engine)", ""]
    if since:
        md += ["### Since the previous run", "", since, ""]
    if campaign:
        md += ["### Campaign signals", "", campaign, ""]
    if findings:
        md += [f"### Ranked findings (top {min(top, len(findings))} of {len(findings)}, the engine's raw order with the cross-check verdict)", "", "| # | kind | key | value / group | check | receipt |", "|---|---|---|---|---|---|"]
        for n, o in enumerate(findings[:top], 1):
            ck = checks.get(o.get("id"), {}); st = ck.get("status", "")
            md.append(f"| {n} | {o.get('kind')} | `{_cell(o.get('key'))}` | {_cell(_val(o.get('value')) or (o.get('group') or '')[:40])} | {st}{(' ' + ck['date']) if ck.get('date') and st in ('announced', 'partial') else ''} | {_receipt(o)} |")
        md.append("")
    if cov:
        md += ["### Coverage", "", cov, ""]
    if boiler and not brief_md:
        md += [boiler, ""]
    if footer:
        md += ["```text", footer, "```"]
    markdown_out = "\n".join(md).rstrip() + "\n"

    # ---------------- html
    h: list[str] = []
    date = run_id[:10]
    title = f"unreleased · {product} · {date}"
    h.append(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title>')
    h.append(f"<style>{TOKENS}{theme_css or ''}{CSS}</style></head><body>")
    h.append(f'<div class="topbar"><div class="inner"><div class="left"><span class="product">{html.escape(product)}</span><span class="sep">·</span><span class="doc">Unreleased brief</span><span class="sep">·</span><span class="set">{html.escape(date)}</span></div>'
             f'<div class="right"><span class="date">Engine {html.escape(version)} · run {html.escape(run_id)}</span><span class="pill {verdict}">{verdict}</span></div></div></div>')
    h.append('<div class="layout">')
    # rail
    rail = ['<nav class="rail"><span class="label">Contents</span>', '<a href="#verdict">Verdict</a>']
    if brief:
        if brief["shape"]: rail.append('<a href="#shape">The shape of it</a>')
        if n_items: rail.append(f'<a href="#findings">Unannounced ({n_items})</a>')
        for g in brief["groups"]:
            for it in g["items"]:
                rail.append(f'<a class="sub" href="#f{it["n"]}">{it["n"]}. {html.escape(it["noun"])}</a>')
        for blk in brief["blocks"]:
            if blk["title"] not in ("Receipts", "Coverage"):
                rail.append(f'<a href="#b-{_slug(blk["title"])}">{html.escape(blk["title"])}</a>')
    rail.append("<hr><span class=\"label\">Evidence</span>")
    if campaign: rail.append('<a href="#campaign">Campaign signals</a>')
    if since: rail.append('<a href="#since">Since the previous run</a>')
    rail.append('<a href="#coverage">Coverage</a>')
    if brief and any(b["title"] == "Receipts" for b in brief["blocks"]): rail.append('<a href="#receipts">Receipts</a>')
    if findings: rail.append('<a href="#ranked">Ranked evidence</a>')
    rail.append("</nav>"); h.append("".join(rail))
    h.append("<main>")

    # verdict card
    h.append('<section class="card" id="verdict">')
    domain = ""
    for pg in manifest.get("pages", []) or []:
        u = pg.get("url") if isinstance(pg, dict) else str(pg)
        if u and "://" in u:
            domain = u.split("://", 1)[1].split("/", 1)[0].removeprefix("www."); break
    h.append(f'<h1>{html.escape(domain or product)} <span class="title-doc">· What it is building and hasn\'t announced</span></h1>')
    if not brief:
        h.append('<p class="lead" style="margin-top:6px">Evidence report. No brief was written for this run; what follows is the engine\'s ranked evidence, not a reading of it.</p>')
    kv = ['<div class="kv">']
    kv.append(f'<div><span class="label k">Unannounced</span><span class="v big">{n_items if brief else len(findings)}<small>{"findings" if brief else "ranked keys"}</small></span></div>')
    read_mb = coverage.get("first_party_bytes", 0) / 1e6
    kv.append(f'<div><span class="label k">Read</span><span class="v">{read_mb:.1f} MB first-party code · {coverage.get("scripts_fetched", 0)} of {coverage.get("scripts_enumerated", 0)} scripts{" (capped)" if coverage.get("cap_hit") else ""}</span></div>')
    worst = "bad" if any(_STATE_CLASS.get(x.get("state")) == "bad" for x in bad_states) else ("warn" if bad_states else "ok")
    kv.append(f'<div><span class="label k">In the way</span><span class="v {worst}">' + (", ".join(f"{x.get('source')} {x.get('state')}" for x in bad_states[:4]) if bad_states else "Nothing. Every source was read.") + "</span></div>")
    if diff and diff.get("since_run"):
        changed = len(diff.get("flipped", [])) + len(diff.get("added", [])) + len(diff.get("removed", [])) + len(diff.get("routes_added", [])) + len(diff.get("pages_added", [])) + len(diff.get("subdomains_added", []))
        kv.append(f'<div><span class="label k">Since {html.escape(diff["since_run"][:10])}</span><span class="v">{"Nothing material moved." if changed == 0 else f"{changed} changes."}</span></div>')
    else:
        kv.append('<div><span class="label k">Since</span><span class="v">First run. The next one opens with what moved.</span></div>')
    kv.append("</div>"); h.append("".join(kv))
    if brief and brief["shape"]:
        shape = re.sub(r"^\*\*The shape of it\*\*\s*(\(my reading\))?\s*(—|–|-|:)?\s*", "", brief["shape"])
        h.append(f'<div class="callout info" id="shape"><span class="label">The shape of it · the author\'s reading</span><p>{inline(shape)}</p></div>')
    if brief and brief["lead"]:
        h.append(f'<p class="readline">{inline(brief["lead"])}</p>')
    h.append("</section>")

    # findings
    if brief and n_items:
        h.append('<section class="card" id="findings">')
        h.append(f'<h2>Unannounced <span class="muted" style="font-weight:500">({n_items})</span></h2>')
        h.append('<p class="lead">Each item gives the fact in code, what it was checked against, and what it raises. Confidence is the engine\'s: high is a parsed structure; medium and low are marked. Open <em>Evidence</em> for the line it came from.</p>')
        for g in brief["groups"]:
            if g["name"]:
                h.append(f'<h3 class="group">{html.escape(g["name"])}</h3>')
            for it in g["items"]:
                conf = f'<span class="pill {it["conf"]}">{it["conf"]}</span>' if it["conf"] else ""
                note = f'<span class="muted small">{html.escape(it["conf_note"])}</span>' if it["conf_note"] else ""
                fact, checked = split_checked(" ".join(it["fact"]))
                ev_items = _evidence_for(it, by_key)
                evh = ""
                if ev_items:
                    evh = f'<details><summary><span>Evidence: {len(ev_items)} line{"s" if len(ev_items) != 1 else ""} from the run</span><span class="chev">▾</span></summary><ul class="ev">' + "".join(_snippet(o) for o in ev_items) + "</ul></details>"
                raises = f'<div class="raises"><span class="label">Raises</span><span>{inline(_cap(it["raises"]))}</span></div>' if it["raises"] else ""
                chk_text = re.sub(r"^checked[:,]\s*", "", checked, flags=re.I)
                if re.match(r"^nothing[.\s¹²³⁴⁵⁶⁷⁸⁹⁰]*$", chk_text, re.I):
                    chk_text = re.sub(r"^nothing", "Nothing, in the same sources as above", chk_text, flags=re.I)     # the brief's shorthand (brief.md)
                chk_text = re.sub(r"^the same;\s*", "The same sources as above; ", chk_text, flags=re.I)
                chk = f'<div class="checked"><span class="label">Checked</span><span>{inline(_cap(chk_text))}</span></div>' if checked else ""
                h.append(f'<div class="finding" id="f{it["n"]}"><span class="n">{it["n"]}</span><div><div class="head"><span class="noun">{inline(it["noun"])}</span>{conf}{note}</div>'
                         f'<div class="fact">{inline(fact)}</div>{chk}{raises}{evh}</div></div>')
        h.append("</section>")

    # the brief's other blocks (partially announced, campaigns, since, new subdomains, calibration, not read) as one card; receipts + coverage later
    if brief:
        others = [b for b in brief["blocks"] if b["title"] not in ("Receipts", "Coverage")]
        if others or brief["rest"]:
            h.append('<section class="card" id="context">')
            h.append("<h2>Also in the code, and what is already public</h2>")
            for blk in others:
                cnt = f' <span class="muted">({blk["count"]})</span>' if blk["count"] else ""
                h.append(f'<div class="block" id="b-{_slug(blk["title"])}"><span class="label">{html.escape(blk["title"])}{cnt}</span>{markdown(blk["text"]) if blk["text"] else ""}</div>')
            if brief["rest"]:
                h.append(f'<div class="block md">{markdown(chr(10).join(brief["rest"]))}</div>')
            h.append("</section>")

    # engine evidence card
    h.append('<section class="card" id="evidence">')
    h.append("<h2>Evidence</h2><p class=\"lead\">The engine's own record for this run. Everything above was written from it; nothing here is reworded."
             + (f' <strong>Note:</strong> the brief names run {html.escape(mismatch)}; this appendix is from run {html.escape(run_id)}.' if mismatch else "") + "</p>")
    if campaign:
        h.append(f'<details class="fold" open id="campaign"><summary><span>Campaign signals: robots.txt, sitemap, landing pages</span><span class="chev">▾</span></summary><div class="md">{markdown(campaign)}</div></details>')
    if since:
        h.append(f'<details class="fold" open id="since"><summary><span>Since the previous run</span><span class="chev">▾</span></summary>{_since_html(since)}</details>')
    # coverage grid
    h.append('<details class="fold" open id="coverage"><summary><span>Coverage</span><span class="chev">▾</span></summary>')
    if sources:
        cells = []
        for s in sources:
            cls = _STATE_CLASS.get(s.get("state"), "")
            cells.append(f'<div class="cell"><span class="dot {cls}"></span><div><b>{html.escape(str(s.get("source")))}</b><span>{html.escape(str(s.get("state")))}</span>' + (f'<br><span class="small">{html.escape(str(s.get("detail"))[:140])}</span>' if s.get("detail") else "") + "</div></div>")
        h.append('<div class="grid">' + "".join(cells) + "</div>")
    if cov:
        h.append(f'<div class="md" style="margin-top:16px">{markdown(cov)}</div>')
    covb = next((b for b in (brief["blocks"] if brief else []) if b["title"] == "Coverage"), None)
    if covb:
        h.append(f'<div class="block"><span class="label">As written in the brief</span>{markdown(covb["text"])}</div>')
    h.append("</details>")
    if findings:
        named = set(_INLINE_CODE.findall(brief_md)) if brief_md else set()
        def _row(n, o):
            ck = checks.get(o.get("id"), {}); st = ck.get("status", "")
            label = {"announced": "announced", "partial": "partially announced", "none": "no public mention", "unchecked": "unchecked"}.get(st, "")
            if st in ("announced", "partial") and ck.get("date"): label += f" {ck['date']}"
            val = _val(o.get("value")) or (o.get("group") or "")[:40]
            mark = ' <span class="muted" title="named in the brief">·</span>' if str(o.get("key")) in named else ""
            return (f'<tr><td class="mono muted">{n}</td><td>{html.escape(str(o.get("kind")))}</td><td class="k">{html.escape(str(o.get("key")))}{mark}</td>'
                    f'<td>{html.escape(val)}</td><td class="{"muted" if st == "none" else ""}">{html.escape(label)}</td><td class="receipt">{html.escape(_receipt(o))}</td></tr>')
        rows = "".join(_row(n, o) for n, o in enumerate(findings[:top], 1))
        h.append(f'<details class="fold" id="ranked"><summary><span>Ranked evidence: top {min(top, len(findings))} of {len(findings)} keys in the engine\'s order, with the cross-check verdict. The brief above re-ranks by what is new; this table is the raw order.</span><span class="chev">▾</span></summary>'
                 f'<table><thead><tr><th>#</th><th>kind</th><th>key</th><th>value / group</th><th>check</th><th>receipt</th></tr></thead><tbody>{rows}</tbody></table></details>')
    rec = next((b for b in (brief["blocks"] if brief else []) if b["title"] == "Receipts"), None)
    if rec:
        lines = [l for l in rec["text"].split("\n") if l.strip()]
        h.append('<details class="fold" open id="receipts"><summary><span>Receipts: every footnote above, as file, sha256 prefix and byte offset</span><span class="chev">▾</span></summary><p class="receipts">'
                 + "".join(f'<span class="line">{inline(l, prose=False)}</span>' for l in lines) + "</p></details>")
    if boiler:
        h.append(f'<p class="boiler">{html.escape(boiler)}</p>')
    h.append(f'<pre class="footer"><code>{html.escape((brief["footer"] if brief and brief["footer"] else footer))}</code></pre>' if (footer or (brief and brief["footer"])) else "")
    h.append("</section>")
    h.append("</main></div></body></html>")
    return "\n".join(h), markdown_out


def _since_html(since_md: str) -> str:
    """The engine's since bullets as chips; zero counts are left out, and all-zero is one line."""
    chips, rest = [], []
    for ln in since_md.split("\n"):
        m = re.match(r"^-\s*([^:]+):\s*(.*)$", ln.strip())
        if not m:
            if ln.strip(): rest.append(ln)
            continue
        k, v = m.group(1).strip(), m.group(2).strip()
        if re.fullmatch(r"0|no|\+0 [−-]0|none", v):
            continue
        chips.append(f'<span class="chip"><b>{html.escape(v[:60])}</b> {html.escape(k)}</span>')
    body = ('<div class="since">' + "".join(chips) + "</div>") if chips else '<p class="muted small" style="margin:8px 0 0">Nothing material moved.</p>'
    if rest:
        body += f'<div class="md" style="margin-top:12px">{markdown(chr(10).join(rest))}</div>'
    return body


def _collapse_pages(sources: list[dict]) -> list[dict]:
    """`page:https://…` entries become one `pages` line (3 of 3 read; the bad one named); `script:https://…`
    entries (chunks the manifest named that did not fetch) become one `scripts named` line with file names."""
    out = []
    for prefix, label, keep in (("page:", "pages", 3), ("script:", "named scripts", 4)):
        group = [x for x in sources if str(x.get("source", "")).startswith(prefix)]
        if (prefix == "page:" and len(group) <= 1) or not group:
            continue
        bad = [x for x in group if _STATE_CLASS.get(x.get("state"), "") in ("warn", "bad") or x.get("state") not in ("ok", None)]
        state = bad[0]["state"] if bad else "ok"
        names = [str(x["source"])[len(prefix):].rsplit("/", 1)[-1][:40] + " " + str(x["state"]) for x in bad[:keep]]
        detail = f"{len(group) - len(bad)} of {len(group)} read" + (": " + ", ".join(names) + (f" and {len(bad) - keep} more" if len(bad) > keep else "") if bad else "")
        out.append((prefix, {"source": label, "state": state, "detail": detail, "items": len(group) - len(bad)}))
    merged = dict(out)
    result, done = [], set()
    for x in sources:
        src = str(x.get("source", ""))
        hit = next((pfx for pfx in merged if src.startswith(pfx)), None)
        if hit:
            if hit not in done:
                result.append(merged[hit]); done.add(hit)
            continue
        result.append(x)
    return result


def _cut(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    c = s[:n].rsplit(" ", 1)[0]
    return (c if len(c) > n // 2 else s[:n]) + "…"


def _cap(s: str) -> str:
    """A line after a label starts with a capital letter; a code span or a path is left alone."""
    return s[0].upper() + s[1:] if s and s[0].isalpha() else s


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def write(run_dir: str, brief_path: str | None, out_html: str | None, out_md: str | None, theme: str | None, blob_dir: str | None, top: int = 40) -> tuple[str, str]:
    brief = None
    if brief_path:
        with open(brief_path, encoding="utf-8") as f:
            brief = f.read()
    theme_css = None
    if theme:
        with open(theme, encoding="utf-8") as f:
            theme_css = f.read()
    h, m = build(run_dir, brief, theme_css, blob_dir, top)
    base = os.path.dirname(os.path.abspath(brief_path)) if brief_path else run_dir      # beside the brief, where a person looks
    out_html = os.path.abspath(out_html or os.path.join(base, "report.html"))
    out_md = os.path.abspath(out_md or os.path.join(base, "report.md"))
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(h)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(m)
    return out_html, out_md
