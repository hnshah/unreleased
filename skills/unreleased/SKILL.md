---
name: unreleased
description: "What a product is building, working on, about to launch or testing quietly - read from what is already public: feature flags and experiment names in its JavaScript, strings for UI that doesn't exist yet, new subdomains in certificate logs, job posts, the pricing page. A dated brief with a receipt on every line. Use for 'what is X building', 'what's coming from X', 'what changed quietly at X', 'what is a competitor testing', or a second look at a product run before. Not for reactions, logged-in views or the business itself."
license: MIT
compatibility: "Runs scripts/unreleased.py with python3 3.11+ (standard library only, no keys) and fetches the product's public pages; keyless and offline from any vendor."
allowed-tools: Bash Read Write WebSearch WebFetch
metadata:
  version: "0.1.0"
  argument-hint: "unreleased <product> | unreleased <domain> | unreleased <product> since last run"
  homepage: "https://github.com/hnshah/unreleased"
---

# /unreleased <product>

Keyless. Public pages only. The engine reads; you plan and you write. Every run leaves a run folder and a
library row; the second run on a product opens with "since <date>".

## Do not use this skill when

Reactions: last30days. A login, runtime flags, gated UI: REA (`references/deep.md`).
The company as a business: LMTY `competitive-deep-dive`.

## Reference routing

`SKILL_DIR` holds this file. Read the named file in full when its row applies.

| Situation | Read | Then |
|---|---|---|
| Before any engine command | `references/runtime.md` | python3, home dir, exit codes, caps; `doctor` when fetches fail |
| Resolving a product into a plan (always, first run) | `references/plan.md` | write `plan.json`; never guess a company |
| Writing the brief from `evidence.md` | `references/brief.md` | vocabulary, layout, boilerplate, self-check |
| Verdict `could-not-see`, or a 403/challenge page | `references/could-not-see.md` | the blocked-target brief |
| `diff.json` exists (second run on) | `references/diff.md` | lead with since; quiet is allowed |
| The request also wants what this skill does not own | `references/deep.md` | your half, then the owner of the rest |
| After the brief, every run | `references/report.md` | `report --brief`: report.html and report.md beside the brief |

## Contract

**LAW 1 - YOU ARE THE PLANNER.** The engine refuses to run under an agent host without `--plan` (exit 2).
Resolve `<product>` into pages (login or app shell, marketing home), apexes, CDN hosts, pricing, changelog,
docs, job board. If the name could mean two companies, ask one question offering the likely one, or
proceed and state the premise when it is near-certain (plan.md); never run on a guess.

**LAW 2 - COVERAGE FIRST, IN ONE LINE; IN FULL AT THE END.** The brief opens with the engine's badge and
one line on what was read and the gap that matters (a runtime-only SDK, a blocked page); the full coverage
closes it. A failed source is not absence. Never route around a 403 or a challenge.

**LAW 3 - CERTAINTY VOCABULARY ONLY; FACT, THEN READING, THEN WHAT IT RAISES.** *present in code*,
*newly present since*, *flipped on/off since*, *removed since*, *referenced in strings*,
*new subdomain <date>*, *job signal*, *on the pricing page*, *disallowed from search*, *in the sitemap*,
*headline on landing pages*, *announced <date> <url>*, *partially announced*, *no public mention found
(searched: …)* (in a finding, `Checked: <sources>; nothing.`), *could not see*. Forbidden without the
record: confirmed, launching, will ship.
Never a motive ("because", "to compete with"), never a recommendation ("should", "the move is"): the brief
ends at what the evidence raises.

**LAW 4 - NAMEABLE NOUNS FIRST; RECEIPT ON EVERY ITEM.** A shape paragraph (your reading), then findings
as fact / checked / raises, in the engine's order, siblings clustered, each with a footnote receipt (`file
sha256 @offset`). Codenames, A/B arms, entitlements and internal tooling stay out. An empty section says
what would fill it.

**LAW 5 - NEVER PASTE `evidence.md`.** It is addressed to you. Relay only its fenced `text` footer, fence
included, at the end of the brief.

**LAW 6 - CHECK BEFORE "UNANNOUNCED".** Items `announced` go under "Announced, for calibration". Items
`unchecked` are labelled unchecked, or you run the engine's bounded `web_queries.json` (one search each,
plus one per item you relabel) and relabel with the url. Never present an unchecked item as unannounced.

**LAW 7 - RESPECT REDACTIONS.** Keys, org/customer ids, customer-named gates and company-named hosts are
removed from the evidence, run folder and library, and counted. Blobs are the public bytes verbatim: open
one to check a receipt; never reconstruct what was removed.

**LAW 8 - ANSWER YOUR HALF.** A request joined by "and" gets this skill's half in full and one line naming
who owns the rest (`deep.md`).

## Run

```bash
python3 "$SKILL_DIR/scripts/unreleased.py" run <slug> --plan plan.json --emit evidence   # 1–4 min; stages on stderr
python3 "$SKILL_DIR/scripts/unreleased.py" report <slug> --brief brief.md   # after the brief: html + md beside it
python3 "$SKILL_DIR/scripts/unreleased.py" diff <slug>        # last run vs previous usable run
python3 "$SKILL_DIR/scripts/unreleased.py" library "<query>"  # earlier briefs
python3 "$SKILL_DIR/scripts/unreleased.py" doctor             # health checks
```

Exit 0 is a result, including could-not-see. Exit 2: no `--plan`. Exit 3: invalid plan (the message names it).

## Pre-present self-check

1. Badge and the one-line read first. 2. A certainty phrase and a receipt on every item. 3. No forbidden
words, motives or recommendations. 4. Announced items under calibration. 5. Footer relayed, fence included.
6. The `brief.md` boilerplate closes it. 7. The brief in the reply in full; run folder and report paths once.

## Policy (full text in POLICY.md)

Public pages only; no logins; no circumvention; one request per second per host with the project user agent
(`ua` prints it); first-party attribution; redaction; credit and link; honour exclusion requests.
