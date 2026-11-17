# Perfecting round 01: reverted

- Date: 2026-11-17T10:58:45
- Target: `<copy of unreleased>` at a pre-release build
- Fresh host: `claude` (`clean+fresh-config`); cost so far $6.44

## Measures

| | bar | eval pass | blocking | major | judge serious |
|---|---|---|---|---|---|
| before | 22/22 | - | 3 | 7 | 5 |
| after | 22/22 | - | 3 | 4 | 6 |

Decision: **reverted**, worse on judge's serious problems.

## What was fixed

- Problem: When the script cap is hit, the engine and the brief rules let the agent say a flag provider is absent, even though only 2% of scripts were read. Provider detection also misses gate call sites such as checkGate, useGate and getFeatureGate, so even scripts that were read can fail to count as a provider. This causes the blocking false-absence stumble on notion-marketplace, and the eval's must_state 'checkGate' cannot pass.
- Where: skills/unreleased/scripts/lib/vendors/statsig-sdk.json, skills/unreleased/scripts/lib/emit.py:127, skills/unreleased/references/brief.md (Not read / set aside, Coverage)
- Fix asked: 1) Add call-signature fingerprints (`checkGate(`, `useGate(`, `getFeatureGate(`, `getExperiment(`) to statsig-sdk.json so any script that was read registers the provider. 2) In emit.py, when cap_hit and no provider was found, print a coverage line: 'runtime flag provider: none found in the N of M scripts read (capped)'. 3) Add one sentence to brief.md: an absence under a cap is written as 'not found in the N scripts read', never as 'not detected'.
- Fixer: Any read script that calls checkGate(, useGate(, getFeatureGate( or getExperiment( now registers Statsig as a provider; when the cap is hit and no provider is found, the coverage block prints 'runtime flag provider: none found in the N of M scripts read (capped)'; and brief.md now says an absence under a cap is written as 'not found in the N scripts read', never as 'not detected'.

## Fresh-host trial findings

- **blocking** (notion-marketplace): The brief never names the flag-evaluation call `checkGate`, which the task expected. The agent read only 60 of 2,841 enumerated scripts. It concluded there was no runtime flag provider, even though the Billing item cites an experiment (`ai_limit_discount_offer`, default group "control"). Some experiment or gate system is plainly in the code.. Cause: Engine script cap and chunk ranking, or the provider-detection step in the skill. Quote: "No runtime flag provider was found in the scripts read."
- **blocking** (notion-marketplace): The brief never mentions a marketplace, though the task expected it. The agent noticed `/explore-consultants` and template-related routes but didn't connect them into a marketplace finding. Most lazy chunks were never read, so marketplace routes or keys were likely missed. The run also carried over the earlier run's framing.. Cause: Script cap of 60 in coverage/budget; the brief.md clustering guidance. Quote: "Notion is mostly building around meetings, connectors and AI billing."
- **major** (notion-marketplace): The diff engine reported false flips because the same key appears in more than one data-type table. The flip evidence line even contradicts itself ('= off: flipped off→on'). The agent had to work out the bug by hand and set the flips aside.. Cause: Diff engine key extraction; diff.md calls flips 'the strongest launch signals the engine produces'. Quote: "The engine reports 10 values flipped... Several flips reverse the flips the previous run reported for the same keys. At the receipt for one of them, the bytes read `edit_reference:!0` (true), while th"
- **minor** (notion-marketplace): On a repeat run the agent had no saved plan and had to rebuild one from coverage.json.. Cause: plan.md (first-run wording); the run folder layout. Quote: "plan.md says "Resolving a product into a plan (always, first run)"... The run folder doesn't save `plan.json`, so I rebuilt it from `coverage.json`."
- **minor** (notion-marketplace): It was unclear whether the web queries were required when no item was marked unchecked. A query the agent ran anyway found that an item the engine called 'no public mention found' is in the help docs.. Cause: LAW 6; the docs check that uses the help sitemap. Quote: "LAW 6 says "or you run the engine's bounded `web_queries.json`""
- **minor** (notion-marketplace): The engine labelled older features such as `notion_calendar_launch_promo` 'no public mention found', and the writer had to catch the mistake.. Cause: Engine announcement classification compared with the changelog window. Quote: "brief.md says "a feature older than that window is not unmentioned, it is unsearched""
- **minor** (notion-marketplace): The footnote grammar had no form for a receipt in the since-last-run section, so the agent made one up.. Cause: brief.md layout/footnote grammar. Quote: "brief.md's layout shows only `¹ …` footnote markers, while the diff section needs a receipt before item 1. I used `[^0]`"
- **minor** (notion-marketplace): The engine supplied no receipt for one robots.txt prefix, which breaks the 'every finding gets a footnote' rule. The agent cited a nearby receipt instead.. Cause: Engine robots.txt evidence emission. Quote: "`/product/agents-homepage` comes with no receipt in the evidence. I cited the nearest robots.txt receipt."
- **major** (cursor-blocked-page): The engine's top-ranked findings were mostly vendor SVG and DOM attribute names marked high confidence. The skill only lets the agent set aside lines one at a time, as exceptions. The agent had to dismiss the whole top of the ranking by hand, which goes against the instruction to keep the engine's order.. Cause: brief.md, ordering and set-aside rules; the engine's vendor-material filter. Quote: "brief.md: "Keep the engine's order; it ranked by salience" / "Do not reorder product findings among themselves"; transcript: "About 150 of the 200 lines shown were SVG and DOM attribute names (`onclic"
- **major** (cursor-blocked-page): The engine marked the Origin waitlist endpoint as having no public mention, even though Origin appears in that run's changelog and docs. Copied as-is, the brief would have called an announced product unannounced. The agent caught it only with its own web search and moved it to Partially announced.. Cause: The engine's announcement matcher, which matches exact keys or paths rather than the product-name stem; LAW 6 doesn't cover false 'none' labels. Quote: "LAW 6: "Never present an unchecked item as unannounced"; transcript: "`/api/origin/waitlist` came back as 'no public mention found', but the same run's docs index and changelog both cover Origin.""
- **major** (cursor-blocked-page): The output folder already held a brief.md and brief.prev-run.md from an earlier session. `report` rendered the stale brief against the new run without any warning, so the first report was wrong and had to be rendered again.. Cause: report.md, file-handling section; the report script has no check that the brief matches the run. Quote: "report.md: "Overwrite the file on a rerun; do not keep versions"; transcript: "The report's first render accidentally used that old brief; I rendered it again from this one.""
- **minor** (cursor-blocked-page): The two files gave conflicting placements, so the agent did both. The since line appears twice in the brief ("Since 2026-11-17T183637Z (0 days): Nothing material moved" and "**Since**: Nothing material moved since 2026-11-17"), which breaks the layout contract.. Cause: diff.md compared with the brief.md layout section. Quote: "diff.md: the brief "opens, after coverage, with" the since line; brief.md layout places `**Since <date>**` after Campaigns"
- **minor** (cursor-blocked-page): Following plan.md forces every Cursor run to come out partial. Earlier runs the same day used a different page set, so the diff reported '430 keys newly read' that weren't actually new. Different samples were being compared.. Cause: plan.md, page-selection rules for apps blocked by robots.txt. Quote: "plan.md: "When robots.txt disallows the app … still list the app page" compared with "a run that reads the app shell is the better baseline""
- **minor** (cursor-blocked-page): The board was correct, and the careers page links to it, but the engine still marked it unverified. The agent had to add its own evidence of ownership without any guidance on whether that was allowed.. Cause: The engine's ATS verification only uses job titles; plan.md doesn't cover this case. Quote: "plan.md: "the engine verifies ownership, so a wrong guess costs one `unverified` line"; output: "95 on Ashby, which the engine could not verify by title, though cursor.com/careers links to this board""
- **minor** (cursor-blocked-page): The search queries the engine generated were built from vendor noise and were useless. The agent had to skip them and write its own query.. Cause: The engine's web_queries.json generator, which inherits the ranking noise; LAW 6 doesn't say how to handle bad queries. Quote: "transcript: "It suggested 'cursor alignment baseline' and 'cursor baseline shift', which are SVG attribute names""
- **minor** (cursor-blocked-page): The agent invented **Jobs** and pricing sections, putting pricing under 'Announced, for calibration', because the layout gave them no place.. Cause: brief.md, layout section. Quote: "brief.md layout has no Jobs or pricing block, yet the vocabulary includes "job signal" and "on the pricing page""
- **minor** (cursor-blocked-page): An item the agent itself thought was ordinary docs search was still listed as Unannounced and marked high confidence, because the engine's label was kept. The headline count of unannounced items is inflated.. Cause: brief.md rules for confidence and set-aside; the engine doesn't recognise routine endpoints in the docs bundle. Quote: "output: "2. **A search endpoint in the docs bundle** · high … My reading is that this is the docs site's own search""

## Judge

- serious (#5): The evals in evals.json describe live cases (notion-marketplace requires 'marketplace' and 'checkGate'), but CI never runs them. CI only grades two hand-written example briefs with tools/eval_brief.py. The trial missed both required terms on the Notion case and CI still passed. Criterion 5 scores 2 points, but the eval that would have caught this regression is not wired into CI.. Evidence: .github/workflows/ci.yml:17-18 (eval_brief.py on docs/examples/linear-brief.md and vercel-brief.md only); evals/evals.json notion-marketplace must_state ["marketplace","present in code","checkGate"]
- serious (#None): The coverage line says no flag provider exists when the run's own evidence shows gate and experiment calls. emit.py only lists vendor SDKs. When the cap is hit and no vendor SDK was found, it prints 'runtime flag provider: none found'. It prints this even when the calls extractor found checkGate or getEligibleGroup call sites in the same run. The brief then repeated that false claim.. Evidence: skills/unreleased/scripts/lib/emit.py:127-128; trial quote "No runtime flag provider was found in the scripts read." next to experiment ai_limit_discount_offer (default group "control")
- serious (#None): The diff engine reports false flips. diff._index keys observations by (kind, key) in a dict, so when the same key appears in several tables the last one silently wins. The value it compares then depends on read order, so a flip can appear that never happened. emit.py adds +10 salience to flipped keys, and diff.md calls flips 'the strongest launch signals'. The result is wrong claims at the top of the brief, with receipts that contradict them.. Evidence: skills/unreleased/scripts/lib/diff.py:13-16,28-30; skills/unreleased/references/diff.md:23; trial: "At the receipt for one of them, the bytes read `edit_reference:!0` (true), while the diff says it went to false."
- serious (#None): Nothing filters SVG, DOM or HTML attribute names. On Cursor, about 150 of the top 200 ranked lines were names like onclick and font-size, all marked high. brief.md tells the agent to keep the engine's order, and web_queries.json built its searches from this noise.. Evidence: grep for svg/onclick/font-size in lib/noise.py and lib/salience.py finds nothing; trial: "About 150 of the 200 lines shown were SVG and DOM attribute names... marked `· high`"
- serious (#None): The announcement matcher only matches exact keys or paths. It labelled /api/origin/waitlist 'no public mention found' even though the same run's changelog and docs cover Origin. A brief that copied it would have called an announced product unannounced, which goes against LAW 6.. Evidence: trial cursor-blocked-page: "`/api/origin/waitlist` came back as 'no public mention found', but the same run's docs index and changelog both cover Origin."
- serious (#None): The report command renders whatever brief.md is in the folder without checking which run it belongs to. In the trial it rendered a brief from an earlier session against the new run, with no warning.. Evidence: trial: "The report's first render accidentally used that old brief; I rendered it again from this one."; references/report.md "Overwrite the file on a rerun"
- note: Conflicts with ADR 0005 (cap-is-a-budget): the 60-script cap (60 of 2,841 Notion chunks read) is why the marketplace finding was missed, the second blocking stumble. The CHANGELOG already lists this under Known gaps ("Notion's minified identifier tables (`QOF:\"marketplace_coupon\"`)"). Reading route-config and gate-client chunks before the cap applies may need a human decision. It changes how chunks are chosen, not the cap itself.
- note: ADR 0006 (salience ranks the brief) is a deliberate decision, but it does not choose to rank vendor SVG and DOM vocabulary high. Adding those words to the plumbing list fits within the ADR.
- note: diff.md and brief.md disagree on where the 'Since' line goes, so the trial brief printed it twice. Small and easy to fix.
- note: The fresh-host evidence is genuine and detailed (evidence/perfect/2026-11-17-1028/round-00.md). The 22/22 checker score overstates quality, because the eval cases that matter are not in CI.
- note: I could not judge from this material whether the notion-marketplace case's corpus_run (results/notion/2026-10-30T200330Z) is present in the repo or can be replayed.

## Bar

```
ucopy: 22/22

 1. Layout                   2/2
      + .claude-plugin/plugin.json name='unreleased'
      + 1 skill(s) under skills/<name>/SKILL.md
 2. Lean SKILL.md            2/2
      + all 1 SKILL.md ≤130 lines
      + every description has 'Use when' and 'Not for'
 3. Deterministic scripts    2/2
      + 37 script file(s), e.g. skills/unreleased/scripts/lib/__init__.py
      + named in skills/unreleased/SKILL.md
 4. Tests                    2/2
      + 34 test file(s), e.g. tests/__init__.py
      + CI runs the tests
 5. Output evals in CI       2/2
      + 1 eval case file(s), e.g. evals/evals.json
      + CI runs the evals
 6. Fresh-host evidence      2/2
      + 1 dated trial log(s), e.g. evidence/perfect/2026-11-17-1028/round-00.md
 7. Output-first README      2/2
      + example output at README line 6, install at line 56
 8. Install CI               2/2
      + CI runs claude plugin validate
      + CI installs the plugin
 9. Version and CHANGELOG    2/2
      + plugin.json version 0.1.0
      + CHANGELOG.md present
10. Policy                   2/2
      + POLICY.md: 44 lines, names what it touches
11. Public-readiness         2/2
      + LICENSE
      + .gitignore
      + no secret-shaped strings
      + no .env or *.db
      + no absolute home paths
```
