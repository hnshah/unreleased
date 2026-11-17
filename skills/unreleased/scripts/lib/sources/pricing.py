"""pricing source: the plan's pricing page as a parsed artifact (R15), with honest statuses (R14).

Contract (shared across `sources/`): `fetch(plan, fetcher) -> (snapshots, outcomes)`: at most one
`PricingSnapshot` and exactly one `SourceOutcome`; `health(fetcher) -> SourceOutcome`.

The text a browser would show is extracted by the pure function `visible_text(html)`: scripts, styles,
noscript, templates, svg, comments and the head are removed; block elements become line breaks, inline
elements join on one line (GitLab's `<span>$</span><span>12,000</span>` is one line); entities are
unescaped; decorative glyph runs (icon-font private-use characters, dingbats, stars) are dropped
(Hugging Face's text was 57% glyphs); whitespace collapses; lines under 3 characters go. `sha256_text`
hashes that normalised text so a diff does not fire on markup or glyph churn (Asana "changed" on 43 chars);
the snapshot's `text` carries it in full for the run's cross-check (empty for 403 / challenge / 404).

`chip_lines(text)` keeps the lines that carry a chip or a price: `New`, `Beta`/`(beta)`, `Preview`,
`Coming soon`, `not yet available`, `Early access`, `Waitlist`, a currency amount (`$`, `€`, `£` + digits,
or `USD`/`EUR`/`GBP`), or a unit (`per user`, `per seat`, `/mo`). A line that is only a chip (a badge in
its own element) is attached to the line it labels: `Coming soon: Advanced Capacity`; a bare amount followed
by its unit line becomes one line: `$ 12,000 per top-level group per year`.

Statuses: `404`; `blocked-403`; `challenge`; `redirect` when the final host is another registrable domain
(Hotjar -> Contentsquare: recorded, never silently read as Hotjar's prices); `client-rendered` when the
visible text has no currency amount and under 1,500 characters (HubSpot's 36-character shell) or is
dominated by template placeholders; else `ok`. An `ok` page with zero amounts is reported as `partial`
("cards not visible without a browser"), which is what Lovable's 7,509 characters were.
"""
from __future__ import annotations

import hashlib
import html as htmlmod
import re
import unicodedata
import urllib.parse

from schema import PricingSnapshot, SourceOutcome

SOURCE = "pricing"
LIMIT = 4_000_000
HEALTH_URL = "https://example.com/"
CLIENT_RENDERED_CHARS = 1500

_DROP = re.compile(r"<(script|style|noscript|template|svg|head)\b[^>]*>.*?</\1\s*>", re.S | re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_BLOCK = re.compile(r"</?(?:p|div|section|article|header|footer|nav|main|aside|h[1-6]|ul|ol|li|table|thead|tbody|tfoot|tr|td|th|br|hr|blockquote|pre|figure|figcaption|dl|dt|dd|form|fieldset|legend|details|summary|address|option|select|button|body|html)\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v\xa0 -​  　]+")
_PLACEHOLDER = re.compile(r"\{\{.*?\}\}|\{[A-Za-z_][\w.]*\}|__[A-Z][A-Z_]+__|^loading(?:\.\.\.|…)?$|^\.\.\.$|^undefined$|^null$|^nan$", re.I)
_TWO_LEVEL = {"co.uk", "com.au", "com.br", "co.jp", "co.in", "co.nz", "com.mx", "co.za", "org.uk", "ac.uk", "com.sg"}

CHIP = re.compile(r"\bNew\b|\bBeta\b|\(beta\)|\bPreview\b|(?i:coming soon|not yet available|early access|waitlist)")
AMOUNT = re.compile(r"[$€£]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|EUR|GBP)\b")
UNIT = re.compile(r"(?i)\bper (?:user|seat|editor|member|month|year)\b|/\s?(?:mo|month|yr|year|user|seat)\b")
_BARE_CHIP = re.compile(r"^\W*(?:New|Beta|Preview|(?i:coming soon|not yet available|early access|waitlist))\W*$")
_BARE_AMOUNT = re.compile(r"^\W*(?:[$€£]\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:USD|EUR|GBP))\W*$")
_UNIT_START = re.compile(r"(?i)^\W*(?:per\b|/|a month|a year|month|year|user|seat|editor|billed|annually|monthly)")


# --- pure text ---------------------------------------------------------------------------------------

def _is_glyph(ch: str) -> bool:
    cat = unicodedata.category(ch)
    return cat in ("So", "Sk", "Co", "Cn", "Cs", "Cf") or (cat == "Sm" and ord(ch) > 127 and ch not in "×∞")


def visible_text(html: str) -> str:
    """The text a browser shows, one block per line, normalised for hashing and for chip_lines."""
    t = _COMMENT.sub(" ", html)
    t = _DROP.sub(" ", t)
    t = _BLOCK.sub("\n", t)
    t = _TAG.sub(" ", t)
    t = htmlmod.unescape(t)
    t = "".join(" " if _is_glyph(ch) else ch for ch in t)
    lines = []
    for raw in t.split("\n"):
        line = _WS.sub(" ", raw).strip()
        if len(line) >= 3:
            lines.append(line)
    return "\n".join(lines)


def amounts(text: str) -> int:
    return len(AMOUNT.findall(text))


def chip_lines(text: str) -> list[str]:
    """Lines carrying a chip, a currency amount or a per-unit; a bare chip is attached to the next line."""
    lines = [l for l in text.split("\n") if l.strip()]
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if _BARE_CHIP.match(line) and i + 1 < len(lines) and not _BARE_CHIP.match(lines[i + 1]):
            out.append(f"{line.strip(' :-–—')}: {lines[i + 1]}")
            i += 2
            continue
        if _BARE_AMOUNT.match(line) and i + 1 < len(lines) and _UNIT_START.match(lines[i + 1]):
            out.append(f"{line.strip()} {lines[i + 1]}")      # a price card: the amount and its unit are one line
            i += 2
            continue
        if CHIP.search(line) or AMOUNT.search(line) or UNIT.search(line):
            out.append(line)
        i += 1
    # a visible and a screen-reader copy of one price land on one line twice ("$10 per user/month $10 per user/month")
    out = [m.group(1) if (m := re.fullmatch(r"(.+?) \1", l)) else l for l in out]
    return list(dict.fromkeys(out))      # a page renders its tiers twice (mobile and desktop); one line each


def registrable(host: str) -> str:
    host = host.lower().split(":")[0]
    labels = host.split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in _TWO_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def same_site(final_url: str, domain: str, apexes: list[str]) -> bool:
    host = urllib.parse.urlparse(final_url).netloc
    if not host:
        return True
    r = registrable(host)
    return r == registrable(domain) or any(r == registrable(a) for a in apexes)


def placeholder_dominated(text: str) -> bool:
    lines = text.split("\n")
    if len(lines) < 10:
        return False
    return sum(1 for l in lines if _PLACEHOLDER.search(l)) >= 0.3 * len(lines)


# --- the seam ----------------------------------------------------------------------------------------

def snapshot(fetched, domain: str, apexes: list[str]) -> tuple[PricingSnapshot | None, SourceOutcome]:
    """Classify one fetched pricing page. Pure: no network."""
    url = fetched.url
    if fetched.state == "blocked-403":
        return PricingSnapshot(url, "", 0, "blocked-403", [], fetched.final_url), SourceOutcome(SOURCE, "blocked-403", 0, True, f"{url}: HTTP 403, not retried")
    if fetched.state == "challenge":
        return PricingSnapshot(url, "", 0, "challenge", [], fetched.final_url), SourceOutcome(SOURCE, "challenge", 0, True, f"{url}: interstitial challenge")
    if fetched.status == 404:
        return PricingSnapshot(url, "", 0, "404", [], fetched.final_url), SourceOutcome(SOURCE, "no-results", 0, True, f"{url}: HTTP 404")
    if fetched.state != "ok" or fetched.status != 200:
        return None, SourceOutcome(SOURCE, fetched.state, 0, True, f"{url}: HTTP {fetched.status}")
    text = visible_text(fetched.body)
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    lines, n_amounts, chars = chip_lines(text), amounts(text), len(text)
    final = fetched.final_url or url
    if not same_site(final, domain, apexes):
        host = urllib.parse.urlparse(final).netloc
        snap = PricingSnapshot(url, sha, chars, "redirect", lines, final, text=text)
        return snap, SourceOutcome(SOURCE, "partial", len(lines), True, f"{url}: redirected off-domain to {host}; the text is {host}'s pricing page ({chars} chars, {n_amounts} amounts)")
    if (n_amounts == 0 and chars < CLIENT_RENDERED_CHARS) or placeholder_dominated(text):
        snap = PricingSnapshot(url, sha, chars, "client-rendered", lines, final, text=text)
        return snap, SourceOutcome(SOURCE, "partial", len(lines), True, f"{url}: client-rendered shell ({chars} chars, {n_amounts} amounts): cards not visible without a browser")
    snap = PricingSnapshot(url, sha, chars, "ok", lines, final, text=text)
    if n_amounts == 0:
        return snap, SourceOutcome(SOURCE, "partial", len(lines), True, f"{url}: 0 currency amounts in {chars} chars: cards not visible without a browser")
    return snap, SourceOutcome(SOURCE, "ok", len(lines), True, f"{url}: {chars} chars, {n_amounts} amounts, {len(lines)} chip/amount lines")


def fetch(plan, fetcher) -> tuple[list[PricingSnapshot], list[SourceOutcome]]:
    if not plan.pricing:
        return [], [SourceOutcome(SOURCE, "skipped-unconfigured", 0, False, "no pricing URL in the plan")]
    snap, out = snapshot(fetcher.get(plan.pricing, LIMIT, kind="page"), plan.domain, plan.apexes)
    return ([snap] if snap else []), [out]


def health(fetcher) -> SourceOutcome:
    """One small public page: says whether page fetching and text extraction work right now."""
    f = fetcher.get(HEALTH_URL, 200_000, kind="page")
    if f.state != "ok":
        return SourceOutcome(SOURCE, f.state, 0, True, f"{HEALTH_URL}: HTTP {f.status}")
    chars = len(visible_text(f.body))
    return SourceOutcome(SOURCE, "ok" if chars else "error", chars, True, f"{HEALTH_URL}: {chars} chars of visible text")
