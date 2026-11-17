# Brief: writing from evidence.md

`evidence.md` is addressed to you. Read it whole, then write the brief. Never paste it.

## Vocabulary (the only certainty phrases)

| Phrase | It means | Needs |
|---|---|---|
| present in code | the literal exists in a first-party bundle or page today | a finding line |
| newly present since <date> | absent in the previous run | `diff.added` |
| flipped on/off since <date> | the value changed | `diff.flipped` |
| removed since <date> | present before, gone now | `diff.removed` |
| referenced in strings | human-readable text names it | a `string`/`i18n` line |
| new subdomain <date> | first seen in certificate logs then | a subdomain line |
| job signal | a public posting names it | a job line with a date |
| on the pricing page | quoted from the same-run pricing text | a pricing line |
| disallowed from search | a `Disallow` prefix in robots.txt: pages the company keeps out of search, listed by itself | a `robots` line |
| in the sitemap <lastmod> | listed in the sitemap; "not linked from the pages read" means no public page points to it yet | a `sitemap` line |
| headline on landing pages | the same `<h1>` on two or more landing pages read | a `headline` line |
| announced <date> <url> | a dated public source states it | `announced` check |
| announced (docs) <url> | the product's own documentation describes it today (docs carry no date) | `announced` check, note `docs` |
| partially announced | a public source covers part of it | `partial` check, with the url |
| no public mention found (searched: …) | the named sources were searched and found nothing; in a finding: `Checked: The <sources, window>; nothing.` | `none` check |
| could not see | a source was blocked, challenged, runtime-only, unreachable, errored or misconfigured | a coverage line |

Forbidden without the matching record: *confirmed*, *launching*, *will ship*, *testing* (an experiment
with arms may be "under test"). "Unreleased" is the product's name, never a verdict on a line.

Three rules on every line:

- **Fact, then reading, then what it raises.** The engine's phrase and receipt are the fact. Your reading
  of a name is marked *my reading*. What it raises is as far as a line goes: never an action, never
  "should", "must", "the move is".
- **No motive.** Never why a company is building something ("because", "to compete with", "in response
  to"). A gate says what exists, not why. A reason stated by a dated public source is quoted as announced.
- **Absence is not evidence.** A pricing page that does not mention a feature says something about the
  page. Write "not observed in the sources checked, as of <date>", never "does not have", "unchanged",
  "none" or "free" without a record that says so.

## Layout

Payoff first, proof after: the verdict in one line, the shape in one paragraph, findings as short tagged
items, every receipt as a footnote, the full coverage block last. `report` parses these forms into
components, so keep them exact.

```
🔎 unreleased <version> · <product> · <date> · <rich | partial | could-not-see> · <first run | since <date>>   (the engine's badge line, verbatim)
<One to three sentences: what was read and the one gap that matters. "Read 2.2 MB in 31 scripts, 3 pages
and the certificate logs. Not read: a flag SDK that fetches its flags at runtime." Under a cap, say "read N
of M" and never turn the unread part into an absence: "no flag SDK in the 60 scripts read", not "no flag
provider". Full coverage at the end.>

**The shape of it** (my reading): Two or three sentences on what the findings add up to, which surface is
growing, what kind of product it is becoming. Reading, not motive.

**Unannounced** (N)
1. **<Nameable noun>** · <high | medium | low>
   <Fact: the keys, quoted strings, routes; first seen <date> on a later run.> Checked: The pricing text, the
   docs index (180 pages) and the changelog index since <date> (N entries); nothing. ¹
   Raises: <The question it opens.>
2. ...
**Partially announced** (N): <noun>, <the public part, announced <date> <url>; the part that is not>. ²
**Campaigns**: from `## Campaign signals`: compare and `-vs-` pages in the sitemap and whether a public
page links to them yet (listed but not linked names who the next campaign targets); robots.txt prefixes
kept out of search (never fetched); the headline shared across landing pages; `site:go.<domain>` queries
from `web_queries.json` when such hosts exist. Fact, checked, raises, as for a finding.
**Since <date>**: flips, new keys, new hosts, jobs ± (second run on; diff.md). First run, exactly:
`**Since**: First run; the next run opens with what moved.`
**New subdomains**: <date> `host` (stem, env; reading if any).

**Announced, for calibration**: <noun> (announced <date> <url>), <noun> (live page), …
**Not read / set aside**: runtime-only providers; vendor or demo lines the engine did not catch (with
receipts, so a fingerprint can be added); what no source could say.
**Coverage**: the engine's coverage lines, in full, including the verdict reason.

**Receipts**: host <url> (path prefix unless noted) · run folder <path>
¹ 13o7…js sha256:fc27b1b9cfa6@26222 · 37fc…js sha256:996cdf1cc44e@16238
² …

<boilerplate paragraph>
<fenced text footer from evidence.md>
```

**Findings.** Lead with 5 to 12 a person would recognise as product work: plans, prices, credits, agents,
integrations, surfaces. Keep the engine's order; it ranked by salience and novelty. Sibling keys describing
one thing (`builder_local_*` ×27) become one line with the count and the two or three most telling keys.
Each item is three parts in that order, fact, checked, raises, and nothing else; the certainty phrase is
written once per item. The confidence word is the one the engine prints on the line (`· high`, `· medium`,
`· low (reason)`); a clustered item takes its lowest member's word, and carries the reason only when it
is not high, in the engine's words, never a reason of your own. More than six items: group by product surface
with a one-line italic label (*Members*, *Admin pipeline*); fewer: no groups. A group opens where its first
member sits in the engine's order and takes that surface's later members with it; the groups keep the
engine's order among themselves. That is the one move allowed, and it is not reordering.

**Where things go.** A *partially announced* item is a numbered finding when the part that is not public
would be a finding on its own; otherwise one sentence in its block. A route a visitor can open today goes
under calibration, never in the findings (the engine keeps such routes in the key list, marked "[linked
from a public page]"; one that reaches the findings is yours to move). When two
public sources disagree (the pricing page says one tier name, the blog another), say so under calibration
with both receipts. When the code yields nothing recognisable (a marketing bundle, a blocked shell), the
numbered findings may be subdomain, job and pricing lines in their own vocabulary; say at the top of the
section that the code gave nothing and why. You may set a ranked line aside when its receipt shows vendor
or demo material the engine did not catch: say so under Not read, with the receipt. Do not reorder product
findings among themselves.

**Windows.** "No public mention found" carries the window searched (`changelog-index since 2026-09-03 (10
entries)`); a feature older than that window is not unmentioned, it is unsearched. Say so, or run one web
query for that item before relabelling (LAW 6 allows one per item on top of `web_queries.json`).

**Empty sections** say what would fill them: "No subdomains in 120 days; the certificate log for the apex
was capped (wildcards). A run with the CDN apex added may show more." A Campaigns block with no compare pages,
a robots.txt of one `Allow: /` and one headline is one sentence saying so. An invented plausible item is
worse than a gap, because it looks finished.

## Copy rules

- **Sentence case, always.** Every sentence, every line after a label (`Raises:`, `Checked:`, a bold block
  title) and every list item starts with a capital letter. A key or a path may open a sentence only inside
  backticks.
- **No em dashes, no en dashes**, anywhere in the brief. Use a comma, a colon, a semicolon, a period or
  parentheses. A dash inside a verbatim string from the code stays, inside its quotes. A hyphen in a word
  (`-vs-`, `could-not-see`) is a hyphen.
- **Full sentences for prose**; fragments only in the badge line and the Receipts block.
- **Checked, the same way every time**, and capitalised like any line after a label: `Checked: The pricing
  text, the docs index (N pages) and the changelog index since <date> (N entries); nothing.` or `Checked: The
  same; partially announced <date> <url>.` A web search you ran is `, plus one web search ("<query>")`. A later
  item may shorten to `Checked: The same; nothing.` The engine's source names (`pricing-text`, `docs-index`)
  are not prose; write them as words.
- **Names as their owners write them** (`AcmeHub`, not `Acmehub`; `iCloud`, not `Icloud`). The product slug
  in the badge is the engine's and stays as it is.
- Numbers as numerals; dates as `YYYY-MM-DD`, the engine's, in UTC, never converted to the person's day;
  no exclamation marks; no rhetorical questions outside `Raises`, where the question is the point.

## Receipts

`[https://host/path.js sha256:149615a0e6ff@146429]` is url, hash prefix, byte offset. Every finding gets a
footnote. Under Receipts, shorten the url to its file name (the host is named once there); never shorten
the hash prefix or drop the offset; copy receipts from `evidence.md`, never retype them (the repository's
eval checks every receipt against the run). Clustered keys keep the receipts of the first two or three.
Pricing lines carry the page's receipt (`[url sha256(text):…]`); job lines carry the posting URL.

## Boilerplate (closes every brief)

These are strings present in public code; a flag or route is evidence that something is being built, not
that it will ship, and the reading of what a name refers to may be wrong. Every line links to the bytes it
came from. Items marked announced are already public; the rest had no public mention found as of the run
date in the sources listed.

## Delivery

The brief goes in the reply, in full; the run folder path is named once, under Receipts. Do not reply with
highlights of a file the person cannot see. About 1,000 words before the receipts for 5 to 8 findings, up
to 1,400 for 12, and up to 1,700 when the quoted strings are the evidence (a description in a flag registry
is worth its words; a reading is not) or every block has content. A reader who wants more has
`evidence.jsonl`. Then render the report (`references/report.md`) and name its paths with the run folder.

## Self-check before presenting

Badge and the one-line read first · the shape paragraph is reading, not motive · fact / checked / raises on
each item · a footnote receipt on every item, copied not retyped · no forbidden words · no em or en dashes ·
every sentence and every line after a label starts with a capital · announced items under calibration ·
unchecked items labelled or checked (LAW 6) · full coverage block at the end · footer relayed with its
fence · boilerplate present · nothing redacted reconstructed.
