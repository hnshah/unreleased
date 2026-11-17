# State machines

Every state the engine, the library and the host contract can be in, with the invariants each must hold and
the transitions the code allows. Written from the code on 2026-11-06, then tested at the edges: each
"reachable invalid state" below was confirmed by a failing test in `tests/test_state_machines.py` before it
was fixed, and that test is the regression guard. The document is kept current with the code; a change to a
transition changes this file in the same commit.

The engine is single-threaded and one run is one process, so "concurrency" here means two runs sharing a
library or a run folder, and retries inside one run.

## 1. A run

The pipeline is a straight line; the order is load-bearing (SM-5).

| Step | What | Fetches | Can fail into |
|---|---|---|---|
| 0 | validate run id and `--since` | none | `ValueError` before any request (SM-2, SM-3) |
| 1 | pages | each planned page | `page:<url>` outcome per page |
| 2 | scripts by role under caps | ≤ `max_scripts`, ≤ `max_requests` | `script:<url>` outcomes; `scripts capped` |
| 3 | extraction, tiers, salience | none | `extractor:<name> error` |
| 4 | signals: crt, ats, pricing, changelog, docs | 1 + ≤5 + 1 + ≤2 + ≤9 | one outcome per source |
| 4b | site: robots, sitemaps, ≤3 landing pages | ≤ 1 + 12 + 3 | `robots`, `sitemap`, `landing` outcomes |
| 4c | route probes | ≤ 25 | `routes` outcome |
| 5 | redact, cross-check, novelty, queries | none | |
| 6 | coverage | none | |
| 7 | store, diff | none | one transaction; rollback on any error (SM-1) |

**Invariants.**
- A run id is a UTC second (`2026-11-04T161005Z`) and is never reused: the library refuses it, the run folder
  refuses it, and `fresh_run_id` moves a colliding id forward one second at a time (SM-3).
- No fetch happens before validation; a bad `--since` costs nothing.
- Signals (pricing, changelog, crt, jobs) are fetched before anything that might trip a host's rate limit on the
  product's own domain (site pages, route probes). The least valuable fetches come last (SM-5).
- A source never kills a run: `_call_source` turns an exception into an `error` outcome. The site source is
  wrapped the same way.
- A page the engine read is a public page: its links make routes "live". That includes landing pages the
  site source opened (SM-6). Links found only in script bodies are candidates until an anonymous GET decides.

## 2. Source outcome states

`schema.RunOutcomeState`: `ok` · `no-results` · `partial` · `rate-limited` · `auth-failed` · `payment-required`
· `unreachable` · `timeout` · `schema-drift` · `skipped-unconfigured` · `error` · `blocked-403` · `challenge`
· `runtime-only` · `capped`.

| Source | Terminal states it can produce | Notes |
|---|---|---|
| page | ok, blocked-403, challenge, rate-limited, timeout, unreachable, error, no-results (404), partial (off-domain redirect) | a challenge or 403 stops the host for the run; never retried |
| script | ok, schema-drift (HTML on a script URL), the HTTP states | identical bodies are read once |
| crt | ok, error, unreachable, timeout | three tries with backoff on 502 |
| ats | ok, partial (unverified board or careers page), no-results, rate-limited | a rate-limited board with nothing else found is `rate-limited`, not `no-results` (Raycast round) |
| pricing | ok, client-rendered, 404, redirect, blocked-403, challenge | |
| changelog | ok, no-results, the HTTP states | feeds are never HTML-parsed; truncated feeds reparsed |
| docs | ok, capped, no-results, skipped-unconfigured (no url in the plan), the HTTP states | llms.txt, a sitemap (≤8 children) or an HTML index; ≤2,000 pages |
| robots | ok, no-results, blocked-403, challenge | a refused robots.txt ends the site source |
| sitemap | ok, capped, no-results (none found, or every file redirected elsewhere) | marketing-shaped children first; locales skipped |
| landing | ok, blocked-403, challenge | only sitemap-listed, robots-allowed pages |
| routes | ok | one outcome summarising live / gated / not routable |
| sdk:<name> | runtime-only | appended when a flag SDK is present and fewer than five valued gates were read |
| scripts | capped | appended when candidates remained at the cap |

**Verdict** (`Coverage.verdict`): `could-not-see` when no first-party bytes, or no scripts and no observations;
`partial` when any source is in {blocked-403, challenge, runtime-only, error, unreachable, timeout,
rate-limited}; else `rich`. `capped` and `no-results` do not lower the verdict. Invariant: a `could-not-see`
run stores no observations, no signals, no checks, and diffs against nothing.

## 3. The fetcher's host state

Per host, per run:

```
(first request) ──▶ robots.txt read once (4xx: allow all; 5xx/timeout: disallow all); a page or script under a binding Disallow returns `skipped-unconfigured` without a request
3xx ──▶ the Location is a new request: robots.txt and host state apply to every hop, at most MAX_HOPS (5)
fresh ──429──▶ rate-limited (sticky: every later request on the host returns 429 without a request)
fresh ──403 / challenge──▶ stopped (sticky: every later request on the host returns that state without a request)
fresh ──timeout/unreachable ×DEAD_AFTER(3) in a row──▶ dead (sticky: returns `unreachable` without a request)
fresh ──any other answer──▶ fresh (the failure count resets)
```

Neither a 403 nor a challenge is retried, and neither is routed around: the host is stopped (POLICY). APIs that
exist to be queried (`kind="api"`: crt.sh, job board APIs) are not gated on robots.txt. Reachable invalid state fixed: a dead host was asked up to `max_requests` times at a 30 s
timeout each (SM-7).

The script loop has its own small machine over discovered chunks (pipeline.py, SM-8):

```
fetching ──404 on a discovered chunk ×MISS_STREAK(8) in a row──▶ stale manifest (the rest are skipped, no request; coverage `chunks capped`)
fetching ──any ok──▶ fetching (the streak resets)
```

Entry scripts (named by the page itself) are never part of the streak and are always tried.

## 4. An observation's tier

```
extracted ─▶ assign_tiers ─▶ finding | key-list | codename
          noise: vendor spans, vendor markers in own key/context, grouped-observation rule
finding ─▶ key-list        salience.apply (below FINDING_MIN; KEEP_KINDS exempt; wordless hidden keys)
finding ─▶ key-list        a route linked from a public page ("live page")
finding ─▶ key-list        redact: A/B arm, internal tooling, customer-named gate (logged "demoted")
any     ─▶ redacted        redact: secret-like value, token-shaped key, ids, company-named host (logged "redacted")
```

**Invariants.**
- `redacted` is terminal; nothing re-tiers after `redact.redact` (cross-check and novelty only read tiers).
- Site kinds (`robots`, `sitemap`, `headline`) keep the tier the source set; noise and salience leave them.
- `salience.novelty` changes salience, never tier; it touches only clusters with an announced member.
- A route marked `[gated]` or `[in code, 404 to a visitor today]` keeps the finding tier; `[linked from a
  public page]` always means key-list.
- Every observation has a receipt (`source.sha256`, `offset`) into a body that is in `manifest.blobs`.

## 5. A cross-check

```
unchecked  — no changelog index was read (every finding stays unchecked)
announced  — a dated changelog entry names it (date, url), or a docs page does (url, note "docs", no date)
partial    — part of the key's words match, under the thresholds in crosscheck.py
none       — a changelog index exists and nothing matched inside the window
```

A docs match needs at least two of the key's words (one word matches a docs index too easily); a route's
words are its last two segments without parameters. Order: docs first (it is the most specific), then the
changelog, then the pricing page. Words match as words, never as substrings (`ai` is inside "available");
words in more than 15 % of a changelog's entries carry no weight on that feed (`ai`, `agent`, `gateway` on
Vercel's); `announced` from a changelog needs the words together in one passage, one of them in no more than
3 % of entries, and one of them in the entry's title; a one-word key is at most `partial`, and only from a
title.

Invariant: `none` is only produced when a changelog index exists; the `searched` list carries the window
("changelog-index since <date> (N entries)"). The brief's `Checked: <sources>; nothing.` is the host's form of
`none`. Novelty: inside a sibling cluster with an announced member, `none` rises and `announced` falls.

## 6. The library (SQLite)

Tables: `products`, `runs`, `artifacts`, `run_artifacts`, `observations` (latest per product/kind/key),
`run_observations` (per run), `checks`, `subdomains`, `jobs`, `pricing`, `redactions`, `briefs`.

**A run's lifecycle in the library.**

```
absent ─▶ (BEGIN) artifacts, redactions, observations, signals, checks ─▶ runs row ─▶ (COMMIT) stored
                                        any error ─▶ (ROLLBACK) absent
stored ─▶ usable     verdict != could-not-see AND no blocked/challenged page AND has run_observations
stored ─▶ unusable   otherwise (never a baseline, never a --since target)
```

**Invariants.**
- The `runs` row is written last and inside the same transaction as everything else, so a run that is
  visible is complete (SM-1). Before this, four separate commits left a "rich" run with no observations
  reachable as a baseline after any failure in between.
- `previous_usable_run` and `is_usable_run` apply the same rule; `--since` must satisfy it (SM-2).
- Per-run writers delete their run's rows before inserting (`checks`, `subdomains`, `jobs`, `pricing`,
  `redactions`), so a retried write is idempotent (SM-3). `run_observations` and `run_artifacts` are
  `INSERT OR REPLACE` on their primary keys.
- `observations.first_seen_run` is never overwritten; `last_seen_run` and `sighting_count` are.
- `--no-store` runs write a run folder and `last-run.json` but no library row; `--since` requires the library.

**Two runs at once.** SQLite serialises writers; a second process blocks on the first's transaction (default
5 s timeout) and then errors, which rolls its own transaction back. Two processes given the same run id
cannot both succeed: the second fails `has_run` or the primary key on `runs`. Two runs of the same product in
the same second get different ids from `fresh_run_id`.

## 7. A diff

Computed only when a usable baseline exists and this run is not `could-not-see`.

| Section | Rule |
|---|---|
| flipped | same key, boolean value changed |
| added / removed | keys present in one run and not the other, finding or key-list tiers, non-string kinds, not live pages, not nav routes |
| new_scripts_read / added_in_new_scripts | keys whose script the baseline never read are "newly read", not "newly present" |
| routes_added, pages_added, pages_removed, subdomains_added, jobs ± | per kind |
| note | engine version differs; or "removed withheld" when a page was blocked or this run read < 60 % of the baseline's bytes |
| redaction | `redact_diff` drops keys sensitive under today's rules before the lists are written |

Invariant: `diff.since_run` is a usable run. `--since` names the run the person last read; otherwise the
previous usable run. Headlines are never "removed" (three pages read per run).

## 8. The host contract (SKILL.md)

```
request ─▶ disambiguate ─▶ plan ─▶ run ─exit 0─▶ read evidence.md ─▶ brief ─▶ (report)
                 │              └─exit 2 (no --plan under an agent) / 3 (bad plan, bad --since, reused id) / 4 (python < 3.11)
                 └─ ambiguous name: one question, then stop
```

Invariants the eval enforces: badge first, footer last, a receipt on every finding, no forbidden words, no
motive, no dashes, sentence case, every receipt resolves in the run (`--run`).

## 9. The report

```
brief.md ─parse_brief─▶ {badge, lead, shape, groups[items], blocks, footer, rest}
run folder ─▶ {manifest, coverage, diff, observations, checks, evidence.md sections}
```

Invariants: the run rendered is the one the brief's footer names (resolved by `report` without `--run-dir`);
a mismatch is rendered with a note, never refused; nothing from the brief is dropped (unparsed lines render
as Markdown); receipts are text, never local links.

## Confirmed bugs, in impact order, and their fixes

| # | State the code reached | Evidence | Impact | Fix | Guard |
|---|---|---|---|---|---|
| SM-1 | A `runs` row with verdict `rich` and no `run_observations`, chosen as the next run's baseline | `store.record_run` committed first, three more commits followed; a failure between left the row. Test: monkeypatched `upsert_observations` raising → `previous_usable_run` returned the broken run and the next diff listed every key as added | A wrong "since" brief on the next run, silently | One transaction per run, `runs` row last, rollback on error; `is_usable_run` requires observations | `test_sm1`, `test_sm4` |
| SM-2 | A diff against a run that does not exist, is could-not-see, is blocked, or is this run | `since` was passed straight to `store.run_urls` / `observations`; both return empty for an unknown id → everything "added" | Same as SM-1, on demand | Validate before any fetch; `ValueError`, CLI exit 3 | `test_sm2` |
| SM-3 | Two runs sharing an id: `runs` replaced, `run_observations` the union of both, `checks` and signals inserted twice | `INSERT OR REPLACE` on `runs`; plain `INSERT` on `checks`, `subdomains`, `jobs`, `pricing`; reachable by two runs in one second or a replayed corpus | A run that never happened as recorded | `has_run` refuses; `fresh_run_id` moves forward; per-run writers delete first; the CLI refuses an existing run folder | `test_sm3` |
| SM-5 | `pricing` and `changelog` reported `rate-limited` without a request | Route probes ran before the signals; one 429 on the product's host put the host in `rate_limited`; the fetcher then answered every later request on that host with 429 unasked. Test: a probe target answering 429 → pricing `rate-limited`, never called | A `partial` verdict and no pricing cross-check on a product whose pricing page was fine | Signals first; site and probes last | `test_sm5` |
| SM-7 | A down host asked `max_requests` (180) times at a 30 s timeout | No per-host failure memory in `LiveFetcher.get` | A run that takes an hour and then reports what it could have reported in a minute | `DEAD_AFTER` consecutive failures mark the host dead for the run | `test_sm7` |
| SM-8 | 129 discovered chunk urls answering 404, each spending one of 180 requests; 51 scripts read of a 60 cap | A page whose manifest names chunks another deploy serves; no memory of consecutive misses in the script loop (Notion, 2026-11-07) | A thinner run and a 225 s wall clock, most of it 404s | After `MISS_STREAK` consecutive 404s on discovered chunks the rest are skipped; coverage says `chunks capped` | `test_sm8` |
| CC-1 | A key `announced` by a changelog entry that does not name it: `/api/ai-chat` by "OpenAI ultrafast mode", `orb_billing.v0.invoice` by "Mem0 joins the marketplace"; 149 of 1,311 Vercel findings `announced`, most wrongly | Substring matching (`ai` in "available"), no weighting of words common to every entry, no title requirement | A real finding filed under calibration, or an unrelated url offered as its announcement | Word-boundary matching, common-word weighting per feed, a distinctive word in the title for `announced`; 38 announced on the same run, all correct on inspection | `test_words_match_as_words_not_substrings`, `test_common_feed_words_carry_no_weight_and_titles_decide_announced` |
| SM-6 | A link found on a landing page the engine itself read was probed as if found in code | Site bodies were pooled with script bodies for `in_scripts` | Needless probes; a public page's link labelled from "code" | Landing pages join `page_bodies`; `in_scripts` excludes site bodies | `test_sm6` |

Earlier bugs of the same family, fixed before this document and guarded elsewhere: a `could-not-see` run as a
baseline (ADR 0005, `test_empty_second_run_never_diffs_and_is_not_a_baseline`); a blocked run as a baseline
(R11); "removed" reported when this run read a fraction of the baseline (the withheld note); keys "added"
because their script was newly read (`new_scripts_read`); the diff command and the run's `diff.json`
computed differently (Linear round 2).
