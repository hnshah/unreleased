"""Cross-check (R9): every candidate against the same-run pricing text and the product's changelog index;
emit bounded web queries for the host to run. Conservative by design: a match needs distinctive words.

announced: a changelog entry's title/text carries the key's distinctive words (date + url)
partial:   the pricing page or a changelog entry carries some of them (url; date when known)
none:      the changelog index was searched and nothing found (with the list of what was searched)
unchecked: nothing searchable beyond the pricing page, or nothing at all
"""
from __future__ import annotations
import re
from schema import Observation, Check

_STOP = {"enable", "enabled", "disable", "disabled", "flag", "flags", "feature", "features", "gate", "gates", "exp", "experiment", "rollout", "beta",
         "new", "v2", "v3", "ui", "ux", "page", "pages", "route", "config", "configs", "mode", "modes", "is", "has", "show", "hide", "use", "allow",
         "the", "and", "for", "with", "to", "of", "in", "on", "by", "ff", "ks", "killswitch", "on", "off", "test", "tests", "client", "server", "api"}


def words(key: str, context: str = "") -> list[str]:
    raw = re.split(r"[_\-./:\s]+|(?<=[a-z])(?=[A-Z])", key)
    ws = [w.lower() for w in raw if w]
    ws = [w for w in ws if (len(w) >= 4 or w in _SHORT_NOUNS) and w not in _STOP and not w.isdigit()]
    return list(dict.fromkeys(ws))


_SHORT_NOUNS = {"ai", "mcp", "ios", "sdk", "cli", "sso", "edu", "pdf", "svg", "git", "llm", "gpt", "eu", "uk", "api", "ssh", "sms", "crm"}
WINDOW = 160   # chars: the key's words must co-occur in one passage, not merely somewhere on a long page


_WORD_RE: dict[str, re.Pattern] = {}


def _pat(w: str) -> re.Pattern:
    """A word matches as a word, never as a substring: `ai` is inside "available" and "openai", `api` inside
    "rapid". Five letters and more may carry a short suffix (plural, -ing), so `invoice` finds "invoices"."""
    p = _WORD_RE.get(w)
    if p is None:
        stem = w.rstrip("s") if len(w) >= 5 else w
        p = _WORD_RE[w] = re.compile(r"(?<![a-z0-9])" + re.escape(stem) + (r"[a-z]{0,3}(?![a-z0-9])" if len(w) >= 5 else r"(?![a-z0-9])"))
    return p


def _in(w: str, t: str) -> bool:
    return _pat(w).search(t) is not None


_COMMON_SHARE = 0.15     # a word in more than this share of changelog entries says nothing about any one of them
_COMMON_MIN_ENTRIES = 20


_DISTINCT_SHARE = 0.03


def word_df(index: list[dict]) -> dict[str, int]:
    """How many entries of a changelog or docs index each word appears in (stems of five letters and more)."""
    df: dict[str, int] = {}
    for e in index:
        seen = {w.rstrip("s") if len(w) >= 5 else w for w in re.findall(r"[a-z]{2,}", (e.get("title", "") + " " + e.get("text", "")).lower())}
        for w in seen:
            df[w] = df.get(w, 0) + 1
    return df


def common_words(index: list[dict], df: dict[str, int] | None = None) -> set[str]:
    """Words that appear in a large share of a changelog or docs index: on Vercel's feed "ai", "agent" and
    "gateway" are in most entries, so a key made only of such words can match any entry. They carry no weight."""
    if len(index) < _COMMON_MIN_ENTRIES:
        return set()
    df = df if df is not None else word_df(index)
    return {w for w, n in df.items() if n > _COMMON_SHARE * len(index)}


def _distinct(w: str, df: dict[str, int], n: int) -> bool:
    """A word in a handful of entries at most tells one entry from the rest; "team" or "invoice" do not."""
    if n < _COMMON_MIN_ENTRIES:
        return True
    return df.get(w.rstrip("s") if len(w) >= 5 else w, 0) <= max(2, int(_DISTINCT_SHARE * n))


def _doc_score(ws: list[str], text: str) -> float:
    """A docs title or slug is short and specific: plurals and compounds count (`allowlist` ~ "Allow-List",
    `extension` ~ "Extensions"). Fraction of the key's words found."""
    t = text.lower(); compact = re.sub(r"[\s\-_]+", "", t)
    hit = 0
    for w in ws:
        if _in(w, t) or (len(w) >= 5 and w.rstrip("s") in compact):
            hit += 1
    return hit / len(ws) if ws else 0.0


def _score(ws: list[str], text: str, window: int = WINDOW) -> float:
    """Fraction of the key's distinctive words found together within `window` chars of the text (0..1).
    Presence anywhere on a pricing page is not a match: 'ai', 'plan' and 'limit' are all on every pricing page."""
    if not ws:
        return 0.0
    t = text.lower()
    if len(t) <= window:
        return sum(1 for w in ws if _in(w, t)) / len(ws)
    # anchor on the rarest word's occurrences
    counts = [(len(_pat(w).findall(t)), w) for w in ws]
    counts.sort()
    rare_n, rare = counts[0]
    if rare_n == 0:
        rare_n, rare = next(((n, w) for n, w in counts if n), (0, None))
        if rare is None:
            return 0.0
    best = 0.0
    steps = 0
    for m in _pat(rare).finditer(t):
        if steps >= 200:
            break
        seg = t[max(0, m.start() - window // 2): m.start() + window // 2]
        hit = sum(1 for w in ws if _in(w, seg))
        best = max(best, hit / len(ws))
        if best >= 1.0:
            break
        steps += 1
    return best


def check(observations: list[Observation], pricing_text: str, changelog_index: list[dict], pricing_url: str | None = None,
          docs_index: list[dict] | None = None) -> list[Check]:
    out = []
    pt = pricing_text or ""
    df = word_df(changelog_index or []); n_entries = len(changelog_index or [])
    common = common_words(changelog_index or [], df)
    for o in observations:
        ws = route_words(o.key) if o.kind == "route" else words(o.key, o.context)
        ws_c = [w for w in ws if w not in common]            # the words that can tell one changelog entry from another
        distinct = any(_distinct(w, df, n_entries) for w in ws_c)   # at least one word is specific to a few entries
        searched = []
        if pt:
            searched.append("pricing-text")
        if docs_index:
            searched.append(f"docs-index ({len(docs_index)} pages)")
            # a docs page is one feature: its title plus slug carrying the key's words is the feature existing today
            dbest, dentry = 0.0, None
            for e in docs_index:
                s = _doc_score(ws, e.get("title", "") + " " + e.get("text", ""))
                if s > dbest:
                    dbest, dentry = s, e
            # two words at least: one word matches a docs index too easily (`controls` → "Widgets and controls")
            if dentry and len(ws) >= 2 and dbest >= 0.75:
                out.append(Check(o.id, "announced", None, dentry.get("url"), searched, note="docs")); continue
        if changelog_index:
            dates = sorted(e.get("date") for e in changelog_index if e.get("date"))
            # the window is part of the claim: an index of ten entries says nothing about a 2023 launch
            searched.append(f"changelog-index since {dates[0]} ({len(changelog_index)} entries)" if dates else f"changelog-index ({len(changelog_index)} entries, undated)")
        best, best_entry = 0.0, None
        # a key whose every word is common on this feed (`ai`, `agent`, `billing` on Vercel's) cannot match an entry
        for e in (changelog_index or []) if ws_c and len(ws) - len(ws_c) <= 1 else []:
            s = _score(ws_c, (e.get("title", "") + " " + e.get("text", "")))
            if s > best:
                best, best_entry = s, e
        # announced needs the words together in one passage and one of them specific to a few entries: "internal"
        # and "components" are in a dozen v0 posts; "virtual" and "models" name one launch
        # and the entry's title names one of them: the title is the claim, the body is prose that mentions things
        title = (best_entry or {}).get("title", "").lower()
        title_hit = any(_in(w, title) for w in ws_c)
        if best_entry and distinct and title_hit and best >= 0.75 and len(ws_c) >= 2 and (len(ws_c) >= 3 or best >= 1.0):
            out.append(Check(o.id, "announced", best_entry.get("date"), best_entry.get("url"), searched)); continue
        p_score = _score(ws, pt) if pt else 0.0
        # a changelog entry is short and specific: half its words is a lead. The pricing page is long and generic
        # ("ai", "plan", "make" are on every line of Figma's): it needs all of a short key or 3/4 of a long one.
        # the pricing page's nav and footer carry every common word (privacy, plan, video): one word never matches it
        pricing_hit = (len(ws) >= 3 and p_score >= 0.75) or (len(ws) == 2 and p_score >= 1.0)
        # a one-word key needs a word long enough to mean something: "ai" is in every changelog entry
        # a one-word key against a feed of long entries is a lead only when the word is in an entry's title
        one_word_hit = len(ws) == 1 and len(ws[0]) >= 5 and best >= 1.0 and distinct and title_hit
        # a changelog entry is long prose: two generic words (`noInitGTWarn` -> init, warn) are in every entry
        changelog_hit = bool(best_entry) and ((len(ws_c) >= 3 and best >= 0.66) or (len(ws_c) == 2 and best >= 1.0 and all(len(w) >= 5 for w in ws_c)))
        if changelog_hit or pricing_hit or one_word_hit:
            url = best_entry.get("url") if best_entry and best >= p_score else pricing_url
            date = best_entry.get("date") if best_entry and best >= p_score else None
            out.append(Check(o.id, "partial", date, url, searched)); continue
        # "none" is a claim about public mentions; it needs a changelog index, not just the pricing page
        out.append(Check(o.id, "none" if any(x.startswith("changelog-index") for x in searched) else "unchecked", None, None, searched))
    return out


_PARAM = re.compile(r"[:*]\w*|\{[^}]*\}|\[[^\]]*\]")
_ROUTE_STOP = {"settings", "organizations", "organization", "handle", "admin", "page", "pages", "new", "edit", "index", "default", "app", "web", "user", "users", "account", "id"}


def route_words(key: str) -> list[str]:
    """A route's distinctive words: parameters out, plumbing segments out, the last two segments' words
    (`/settings/organizations/:handle/mcp-servers` → mcp servers)."""
    segs = [s for s in _PARAM.sub(" ", key).split("/") if s.strip()]
    tail = segs[-2:] if len(segs) >= 2 else segs
    raw = [w.lower() for w in re.split(r"[_\-.\s]+|(?<=[a-z])(?=[A-Z])", " ".join(tail)) if w]
    ws = list(dict.fromkeys(w for w in raw if len(w) >= 3 and not w.isdigit() and w not in _ROUTE_STOP))   # route segments are nouns; `api-keys` keeps its api
    return ws or words(key)
_SLUGGY = re.compile(r"^[a-z0-9_.-]+/[a-z0-9_.-]+$", re.I)        # `owner/repo`: a store or GitHub slug, not a feature
_QUERY_STOP = {"settings", "organizations", "organization", "handle", "admin", "api", "page", "pages", "new", "edit", "index", "default",
               "config", "core", "main", "app", "web", "site", "user", "users", "account", "id", "key", "keys", "list", "item", "items", "view"}


def web_queries(observations: list[Observation], product: str, top_n: int = 6) -> list[str]:
    """One bounded search per sibling cluster, phrased as a person would type it: the product name plus the two or
    three nouns that name the feature. A route's parameters and plumbing segments are dropped; a store slug, a
    key with no noun and an announced key never become a query (there is nothing to find). Keys whose context
    carries a human description use the description's nouns, which search better than the key's."""
    import salience
    seen, clusters, out = set(), set(), []
    ranked = sorted((o for o in observations if o.tier == "finding"), key=lambda o: (-o.salience, o.key))
    for o in ranked:
        c = salience.cluster(o.key)
        if c in clusters or _SLUGGY.match(o.key) or not re.search(r"[A-Za-z]{3,}", o.key):
            continue
        key = _PARAM.sub(" ", o.key)
        ws = [w for w in words(key) if w not in _QUERY_STOP]
        if len(ws) < 2 and o.context and re.search(r"[A-Z][a-z]{2,} [a-z]{2,}", o.context):   # a one-word key with a human description: use the description's nouns
            cw = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", o.context)]
            ws = [w for w in dict.fromkeys(cw) if w not in _QUERY_STOP and w not in _STOP and w not in salience.PLUMBING][:4] or ws
        if not ws or (len(ws) == 1 and len(ws[0]) <= 3):
            continue                                   # "raycast ai" finds everything and therefore nothing
        ws = [w for w in ws if w not in salience.PLUMBING] or ws
        q = f"{product} " + " ".join(ws[-3:] if len(ws) > 3 else ws)
        if q in seen:
            continue
        seen.add(q); clusters.add(c); out.append(q)
        if len(out) >= top_n:
            break
    return out
