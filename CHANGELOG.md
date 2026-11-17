# Changelog

All notable changes, in keep-a-changelog form.

## [0.1.0] - 2026-11-17

The first public release. Everything below shipped in it; the sections after "Before the first public
release" record how the engine got there (built 2026-10-30 to 2026-11-17).

### Before the first public release
- Coverage tells the truth about what it read (ADR 0007, keeping ADR 0005). A `rich` run under the script cap
  says "rich: every source answered; under the budget cap: scripts read N of M enumerated"; only an uncapped
  run says "every source read". Webpack chunk URLs take their name/hash separator from the runtime (Notion's is
  `-`; assuming `.` asked for 2,800 URLs that 404). Eight 404s in a row stop only the chunk map that named them,
  recorded as `chunks: partial`, which makes the run partial. App pages and routes under a robots.txt `Disallow`
  are still never requested; they are listed as "could not see … not checked: the site's robots.txt asks
  crawlers to stay out", and a planned page kept out makes the run partial. One rule
  (`schema.partial_sources`) serves the engine and the report.
- The eval grader checks the badge verdict against the case, phrases as whole words in the host's own prose
  (not the footer, the boilerplate or a code key) and real `sha256:<hex>@<offset>` receipts; the old substring
  checks passed wrong answers.
- `references/report.md` agrees with SKILL.md: the report is rendered after every brief.
- `compare` takes run ids as well as run folders; a gzip body cut at the byte cap is inflated up to the cap,
  never scanned as compressed bytes.
- Policy, in code: robots.txt is read before any other request to a host, and a page or script under a
  `Disallow` for `*` or `unreleased` is never requested (`Disallow: /` closes the host; coverage says it was
  not checked because robots.txt asks crawlers to stay out). A 403 or a challenge page stops the host for the run, with no retry and no
  wait-and-retry. Redirects are followed hop by hop, each hop under robots.txt and the host's state; a
  robots.txt that cannot be read (5xx, timeout) disallows the host (RFC 9309), a 4xx allows it. Hosts are one
  host however they are spelled (`A.com:443`). APIs that exist to be queried (crt.sh, job board APIs) are not
  gated on robots.txt.
- Redaction catches GitHub (`ghp_`, `github_pat_`), Google API (`AIza`), Anthropic (`sk-ant-`), OpenAI
  project (`sk-proj-`), GitLab (`glpat-`), npm (`npm_`) and Stripe restricted (`rk_live_`) keys.
- `run --record DIR` keeps what a run read in the replay layout; `tools/run_corpus.py --corpus DIR` scores a
  corpus recorded that way, so the benchmark is reproducible without the maintainers' corpus.
- Fixtures: customer org ids, an AWS account id and customer-named keys replaced with placeholders; real
  client ids and the Stripe docs key in tests replaced with synthetic values assembled at runtime. NOTICE
  covers the third-party excerpts. SECURITY.md routes reports through GitHub private reporting.
- Examples: Vercel (live, 2026-11-07) replaces the earlier small-company example; the Linear example and the
  README lead with Linear's own features. `tools/eval_brief.py` ignores forbidden words inside quoted code.
- Docs: the data folder is `~/.local/share/unreleased` (or `$XDG_DATA_HOME`, `$UNRELEASED_HOME`) everywhere.

### Changed during the private beta (2026-11-01 to 2026-11-15)
- Cross-check accuracy: words match as words (never `ai` inside "available"), words common to a feed carry no
  weight, and `announced` from a changelog needs a distinctive word in the entry's title. On a 200-entry feed
  the wrong announcements went from most of 149 to none of 38.
- Fetching: after eight consecutive 404s on discovered chunks the rest are skipped (a stale manifest cost one
  run 129 of its 180 requests); coverage reports `chunks capped`.
- Codename hygiene: CSS colour names, pointer-event fields, animation props and one-letter keys are dropped.
- The run prints each stage on stderr with elapsed seconds; one findings count everywhere; evidence.md lists
  up to 200 findings; every source appears in the coverage block; `unreleased.py ua` prints the user agent.
- Contract: the report is rendered after every brief; `Checked:` lines are capitalised and written as words;
  first-run `Since` has one fixed form; groups may gather a surface's later members; docs depth and redirecting
  domains in plan.md; file roles and counts in runtime.md.
- Report design system codified from the reference brief: gray-50 canvas, white 12 px cards, Inter 14/20 body,
  12 px tracked labels, sticky top bar with "·" separators and a status pill, 224 px contents rail, a blue-50
  callout for the author's reading, green/yellow/red status hues with one meaning each (`docs/report-design.md`
  has every token and component with its value).
- The renderer guarantees sentence case: `report.sentence_case` capitalises every sentence in prose nodes and
  leaves code spans, urls, names with their own capitals (iOS, iCloud), known lowercase names (npm, robots.txt)
  and the word after an abbreviation alone; receipts, badge, footnotes and table cells are untouched.
#### Added
- `site` source: robots.txt `Disallow` prefixes (reported, never fetched), sitemap pages — compare / `-vs-` /
  alternative and landing pages, with `lastmod` and whether a public page links to them yet — and the headline
  shared across up to three robots-allowed landing pages. A `## Campaign signals` section in `evidence.md`, a
  **Campaigns** block in the brief, `pages_added` in the diff, `site:go.<domain>`-style web queries when
  certificate logs show marketing hosts. Vocabulary: *disallowed from search*, *in the sitemap*, *headline on
  landing pages*. POLICY: robots.txt is honoured and read.
- `report` command: `report.html` (self-contained, no JavaScript, design tokens as CSS custom properties,
  `--theme tokens.css`) and `report.md` from a run folder and the host's brief; an evidence report without
  a brief. The brief is parsed by its grammar into components: a verdict strip, the shape panel, findings
  with confidence pills and *Raises*, and evidence on demand — the engine's context line for every key a
  finding names, folded under it. Coverage as a source grid; a contents rail; print and phone layouts.
  `docs/report-design.md` is the system with its reasons (Tufte, Bringhurst, Tidwell, About Face, Berinato,
  V. Tufte). `references/report.md` routes it; `docs/examples/linear-report.{html,md}`.
- Plugin layout: the skill moved to `skills/unreleased/` (a root `SKILL.md` is not a plugin skill); CI
  checks the skill is registered after install; `agents/openai.yaml`, `gemini-extension.json`.
- Linear round 3 (fresh host, current contract, 26 friction notes) applied: the badge carries "first run" or
  "since <date>"; every evidence line carries its confidence word; `coverage.json` has `verdict_reason`;
  the run folder is printed on stderr and `last-run.json` lives in the engine home; pricing lines that
  repeat themselves are one line; OAuth callback and auth routes are demoted as integration plumbing;
  time zones are not job nouns; URL schemes are not origins; CSS hashes and minified fragments leave the
  codename list and plain UI words go to the key list; crt.sh failures say what came back and how many
  tries; `report` writes beside the brief; one findings count everywhere; `brief.md` tightened by a
  fifth with a Coverage slot and a words budget that counts quoted strings as evidence; `plan.notes`.
- `docs` plan field and source: the product's own documentation index (llms.txt, a docs sitemap or the
  manual's home page) as a third cross-check; a feature the docs describe is *announced (docs) <url>*.
  Route words for cross-checks are the route's last two segments without parameters. On Raycast, four of
  six announced organization settings pages resolve to manual pages and the one unannounced route rises.
- `docs/state-machines.md`: every state machine (run, sources, fetcher host state, observation tier,
  cross-check, library, diff, host contract, report) with invariants and transition tables, and the seven
  reachable invalid states it found, each fixed with a regression test in `tests/test_state_machines.py`:
  one transaction per run with the run row last (a failed write could leave a baseline with no
  observations), `--since` validated before any fetch, run ids never reused, signals fetched before route
  probes (a 429 on a probe silently starved pricing and changelog), a per-host circuit breaker (a down
  host cost 180 requests at 30 s each), landing pages treated as public pages.
- Brief layout: payoff first (badge + one line, the shape paragraph, fact / checked / raises items with a
  confidence word, footnote receipts, coverage last); `tools/eval_brief.py --run` verifies every receipt.

### First end-to-end engine (2026-10-31)

First end-to-end engine, built from the 39-product manual test, then hardened by four fresh-host rounds
(Linear ×2, Cursor, Canva) against a written definition of done.

#### Added
- CLI `scripts/unreleased.py`: `run` (planner guard: exit 2 under an agent host without `--plan`), `diff`,
  `compare`, `library`, `doctor`, `setup`; run folders; SQLite library on by default (ADR 0001).
- Pipeline: plan → fetch (polite, capped, 403 never retried, challenge once) → attribute → discover
  (webpack and Vite chunk maps) → extract → noise → signals → cross-check → redact → diff → emit.
- Scanner for object/array literals in minified JS, string- and regex-aware, one scan per body.
- Eleven extractors: gatemap, inline, calls, catalog, registry, proto, enums, routes, manifest, hidden,
  strings. Four sources: crt (per apex, floods collapsed), ats (Greenhouse/Lever/Ashby/Workable with
  board verification), pricing (visible text, chips, statuses), changelog (feeds, HTML index, embedded JSON).
- Salience ranking (R7): product nouns first; plumbing, permission scopes, analytics events and site
  navigation to the key list. `evidence.md` capped at 150 ranked lines; everything in `evidence.jsonl`.
- Redaction (R10): value-driven secrets and id lists, customer-named gates, company-named hosts anywhere
  below the apex, A/B arms and internal tooling demoted; removed literals scrubbed from neighbours' contexts.
- Coverage vocabulary (ADR 0004); a hit cap is a budget note, not a partial verdict.
- SKILL.md (5 KB, seven laws) with references; `tests/test_skill_contract.py` ties it to `emit.py`.
- Levers: `tools/run_corpus.py` benchmark, `tools/golden.py`, `tools/make_fixture.py`, `tools/budget.py`,
  `tools/eval_brief.py`; evals skeleton; `docs/solutions/` learnings; CI on Python 3.11–3.13.

#### Hardened by fresh hosts (2026-10-31)
- A host given only SKILL.md wrote briefs on Linear (rich, twice), Cursor (partial, an "and" request) and
  Canva (blocked); every friction note became an engine or reference change: continuity (the next run
  prefers the baseline's scripts; "newly read" is separated from "newly present"), `--since <run>` for
  "since the brief I read", the `diff` command uses the run's exact call, one route cluster gets 12 lines
  of `evidence.md` so a flag registry with descriptions makes the page, nav and live-page routes are not
  diffed, namespaced SDK init detection, gt-next and hls.js fingerprints, token-shaped and identifier keys
  redacted, pricing partials need two words, crt.sh retried twice, truncated feeds reparsed, future dates
  dropped, code-empty runs may number subdomain/job/pricing lines. The three briefs ship as worked
  examples under `docs/examples/` and run through `tools/eval_brief.py` in CI.
- Install the way a user would: `.claude-plugin/` marketplace + plugin manifests (`claude plugin validate
  --strict` clean), `npx skills add` smoke test, `tools/validate_pack.py` as the pack's test suite,
  `tools/package_release.py`, SECURITY.md, SUPPORT.md, issue templates for a wrong finding and an exclusion.

#### Reviewed
- A fresh-context code review (3 blockers, 18 should-fix, 9 nits) was
  applied the same day: secrets scrubbed from every context, empty runs never diff, dedupe keeps digits,
  page-only reads are could-not-see, off-domain redirects are a signal, 429 stops a host, surrogate pairs,
  plan type checks, HTML on script URLs, strict-majority attribution, extractor errors as outcomes, and an
  end-to-end pipeline test. Deferred items are listed in the review's disposition.

#### Numbers
- Corpus benchmark (2026-10-31 final): 20 of 39 rich, golden recall 0.982, noise 0.000, 0 redaction leaks.
- Live: Linear 104 s (rich, app shell 12.8 MB), Vercel 75 s (rich), Cursor partial (challenge page on one host).

#### Known gaps
- Notion's minified identifier tables (`QOF:"marketplace_coupon"`), long slug lists capped by the strings
  shape, mobile/desktop binaries (not in v1), direct flag-vendor endpoints (never; ADR 0003).
