# Perfecting round 00: baseline

- Date: 2026-11-17T10:43:42
- Target: `<copy of unreleased>` at a pre-release build
- Fresh host: `claude` (`clean+fresh-config`); cost so far $2.94

## Measures

| | bar | eval pass | blocking | major | judge serious |
|---|---|---|---|---|---|
| before | 20/22 | - | 3 | 7 | 5 |

Decision: **baseline**, measured before any change.

## Fresh-host trial findings

- **blocking** (notion-marketplace): The brief says no flag provider exists. The expected answer requires naming `checkGate`, which is a Statsig-style gate call. Either the engine's provider detector missed it, or the call sits in a chunk the agent never read. The brief then states the absence as a fact when it should have been a coverage gap.. Cause: engine flag-provider detection, together with the 60-script cap (scripts: capped, read 60 of 2841). Quote: "No runtime flag provider was detected."
- **blocking** (notion-marketplace): The agent read 2% of the enumerated scripts. The expected 'marketplace' finding appears nowhere in the 12 unannounced items. The cap was hit on script count while byte use was only 8 MB of the 120 MB budget, so most of the budget went unused.. Cause: plan.md script-cap defaults / engine script prioritisation. Quote: "scripts: capped (read 60 of 2841 enumerated; cap 60 scripts / 120,000,000 bytes / 180 requests)"
- **major** (notion-marketplace): No plan.json was saved from the earlier run, so the agent rebuilt the plan from the old manifest and coverage.. Cause: SKILL.md / plan.md (no rule for where plan.json is kept); engine does not write plan into manifest. Quote: "SKILL.md: "the second run on a product opens with 'since <date>'" — manifest.json has "plan": null"
- **major** (notion-marketplace): Nine of the ten flips were enum values in data-type tables. Diff.md calls flips 'the strongest launch signals', so the agent had to decide for itself to set them aside.. Cause: diff.md flips section; engine flip classifier. Quote: "The engine reports data-type enum values (`page`, `created_time`) as "flipped" at `high` confidence"
- **major** (notion-marketplace): 297 removals were reported, mostly marketing-site build-chunk file names from a redeploy. The agent had to explain them away by hand.. Cause: diff.md removed-key rule; engine key extraction treats hashed chunk names as keys. Quote: "diff.md: `removed` is withheld only "when this run read far fewer bytes than the baseline""
- **minor** (notion-marketplace): The two files put the Since block in different places. The agent had to choose one.. Cause: diff.md vs brief.md layout. Quote: "diff.md: "the brief opens, after coverage, with: Since…" vs brief.md layout placing "**Since <date>**" after Campaigns"
- **minor** (notion-marketplace): The two rules contradict each other. The agent excluded the arms but still reported trial variants (14d/1m, reverse trial), which are arguably arms.. Cause: SKILL.md LAW 4 vs brief.md. Quote: "SKILL.md LAW 4: "Codenames, A/B arms, entitlements and internal tooling stay out" vs brief.md: "an experiment with arms may be 'under test'""
- **minor** (notion-marketplace): evidence.md was about 40k tokens, above the Read tool's cap, so the agent had to read it in parts.. Cause: brief.md / engine evidence.md size. Quote: "brief.md: "`evidence.md` is addressed to you. Read it whole""
- **minor** (notion-marketplace): brief.md's layout has no Jobs block. The agent invented one, which breaks the fixed layout.. Cause: brief.md layout vs evidence.md Jobs section. Quote: "**Jobs**: Job signal: most of the 164 open roles are go-to-market."
- **minor** (notion-marketplace): The fixed wording reads 'the docs index (N pages)', but plan.md recommends a docs sitemap. The agent reworded the line on its own.. Cause: brief.md Checked: template vs plan.md docs source. Quote: "Checked: The pricing text, the help sitemap (484 pages) and the changelog index"
- **minor** (notion-marketplace): The routing names skills and files that are not installed. Nothing says what to do when they are missing.. Cause: SKILL.md routing section. Quote: "SKILL.md: "Reactions: last30days … REA (`references/deep.md`) … LMTY `competitive-deep-dive`""
- **minor** (notion-marketplace): LAW 6 requires web searches, and the search tool requires a sources list. The brief's 'same text, nothing added' rule leaves nowhere to put that list.. Cause: brief.md layout / report rule vs LAW 6. Quote: "Sources for the three web checks: … (placed after the brief)"
- **minor** (notion-marketplace): Item 1's Raises line is a question. Every other Raises line is a statement, so the agent was unsure of the form.. Cause: brief.md Raises: guidance. Quote: "Raises: Will meeting notes take video next, not only audio?"
- **minor** (notion-marketplace): The baseline was the same day, 11 hours earlier, yet the run still produced a full diff block. Nothing says what to do when the baseline is under a day old.. Cause: diff.md baseline selection. Quote: "**Since 2026-11-17 (07:09Z, 0 days)**"
- **major** (cursor-blocked-page): Cursor's llms.txt has 535 lines of bare URLs, not markdown links. The engine returned "no links: no pages found", so the docs cross-check failed without any error. The agent caught it only after the stored run and had to rerun against the docs sitemap.. Cause: plan.md, docs source section; the engine's llms.txt parser only accepts markdown links. Quote: "plan.md: "Try `<docs host>/llms.txt` first… any of the three works" / only prefer the sitemap "when it lists fewer than about 80 pages""
- **major** (cursor-blocked-page): The --no-store rerun stamped its badge "first run" and wrote no diff.json, but earlier Cursor runs from the same day were already stored. The agent made up its own Since line ("This run was not stored (rerun with a corrected docs source)...") and described a diff from a different run. That breaks the exact-text contract, and the badge says "first run" even though stored history exists.. Cause: brief.md Since rule plus plan.md --no-store rerun instruction; the engine computes first-run status from its own store flag rather than from the library. Quote: "brief.md: Since line must be "exactly: `**Since**: First run; the next run opens with what moved.`"; plan.md: re-run with `--no-store` after fixing a plan"
- **major** (cursor-blocked-page): Lines in evidence.md for certificate-log subdomains have no receipt. The agent cited "crt.sh certificate logs… (signals.json in the run folder)" with no hash or offset. The required disclaimer then claims byte-level receipts the brief doesn't actually have.. Cause: Engine evidence.md generation for crt signals; brief.md receipt rule. Quote: "brief.md: "Every finding gets a footnote… copy receipts from `evidence.md`"; closing disclaimer: "Every line links to the bytes it came from.""
- **major** (cursor-blocked-page): The engine only cross-checks code findings against pricing, docs and changelog. For subdomain and job items the agent checked changelog titles by hand and wrote its own Checked lines, which are only partly verified ("by title").. Cause: brief.md numbered-findings rule; the engine's cross-check step only covers code findings. Quote: "brief.md: "the numbered findings may be subdomain, job and pricing lines in their own vocabulary" vs. each item requiring "Checked: The pricing text, the docs index…""
- **minor** (cursor-blocked-page): `usage-xai.internal.cursor.com` came through unredacted and the agent printed it in the brief (redactions: 0). It couldn't tell whether a partner's name inside the product's own hostname counts as a company-named host. This may be a contract breach.. Cause: LAW 7 wording; the engine's redaction pass. Quote: "LAW 7: "company-named hosts are removed from the evidence""
- **minor** (cursor-blocked-page): The engine's codenames appendix (8) held CSS values (`2px`, `1.75rem`). Hostnames that look like codenames or internal tools (`aqueduct.internal`, `wideband.internal`, `gkw-reader.internal`) were listed as plain subdomains and printed in the brief, which may break LAW 4.. Cause: Engine codename detector; LAW 4 doesn't mention hostnames. Quote: "LAW 4: "Codenames, A/B arms, entitlements and internal tooling stay out""
- **minor** (cursor-blocked-page): ashby/cursor came back unverified (ats: partial) even though cursor.com/careers links straight to it. The partial verdict line also lists only /dashboard and /agents, not the unverified board.. Cause: Engine ATS ownership check; it doesn't follow the careers page link. Quote: "plan.md: "The engine verifies the board belongs to the product (own-domain job links…)""
- **minor** (cursor-blocked-page): All 29 compare and migrate sitemap matches were user-published `/marketplace/` listings, not Cursor's own pages. The agent had to override the signal by hand.. Cause: Engine campaign-signal heuristic over sitemap URLs. Quote: "brief.md: "listed but not linked names who the next campaign targets""
- **minor** (cursor-blocked-page): The engine ranked a video player's registry, a code table, a weighting demo and an animation's sample file tree as findings. The agent had to set almost all of them aside by hand.. Cause: Engine first-party vs. vendor classification and finding ranking. Quote: ""26 of the 28 ranked code findings are vendor or demo material""

## Judge

- serious (#6): The repo has no fresh-host trial log. There is no evidence/ or trials/ folder, so criterion 6 scores 0. ADR 0007 cites a live trial on 2026-11-16, and this round produced 23 stumbles across two tasks, but neither is written down in the repo. A first-time user cannot see what was tried and fixed.. Evidence: checker: '6. Fresh-host evidence 0/2 - no fresh-host trial protocol or log'; `ls` of repo root shows no evidence/ or trials/; docs/adr/0007-a-read-cut-short-is-partial.md: 'The perfecting loop's live trial (2026-11-16) found...'
- serious (#5): The skill reports a missing flag provider as fact when it only read part of the code. The notion-marketplace eval requires `checkGate`, but the engine read 60 of 2841 scripts and the brief still said 'No runtime flag provider was detected.' Provider detection only checks Statsig init and client strings (`statsig.initialize(`, `StatsigClient(`), not gate call sites such as checkGate, useGate or getFeatureGate. Nothing in the coverage output says that 'none found' is limited by the cap.. Evidence: skills/unreleased/scripts/lib/vendors/statsig-sdk.json:5-13; skills/unreleased/scripts/lib/emit.py:127 (prints a provider line only when one was found); trial quote 'No runtime flag provider was detected.'
- serious (#None): Diff noise is presented as strong signal. Enum values in data-type tables are reported as high-confidence 'flips' (9 of 10), and hashed chunk filenames from a redeploy show up as 297 'removed' keys. diff.md calls flips 'the strongest launch signals', so a first-time user would be misled.. Evidence: trial: 'Nine of the ten flips were enum values in data-type tables'; '297 removals were reported, mostly marketing-site build-chunk file names'
- serious (#None): The brief's closing disclaimer promises byte-level receipts for every line, but evidence.md gives certificate-log (crt.sh) subdomain lines no receipt. The brief therefore claims something it does not have.. Evidence: brief.md: 'Every finding gets a footnote… copy receipts from evidence.md'; disclaimer 'Every line links to the bytes it came from.'; trial cursor-blocked-page
- serious (#None): If a docs llms.txt lists bare URLs, the parser finds zero pages and the source still counts as ok. The docs cross-check then fails without any error.. Evidence: trial cursor-blocked-page: engine returned 'no links: no pages found' on Cursor's 535-line llms.txt
- note: Conflicts with ADR 0005 (cap-is-a-budget): the 60-script cap is a recorded decision, so I have not named it as `worst`. The Notion trial hit the script count with 8 MB of the 120 MB byte budget used, and read 2% of 2841 scripts. The expected marketplace finding was never reached. A human should decide whether bytes should be the binding cap, or whether a second pass should run when the count cap is hit with byte budget left. ADR 0005's 'ends in a minute' reason may not need a 60-script count.
- note: The eval's notion case points at corpus_run 'results/notion/2026-10-30T200330Z', which is not in the repo. I cannot tell from here whether CI actually replays it. The output-eval run was skipped this round (--no-evals).
- note: The evidence.md size (about 40k tokens) conflicts with brief.md's 'Read it whole'. This is minor, but every large-product run will hit it.
- note: Several contract mismatches would each be cheap to fix: where the Since block goes (diff.md vs brief.md), A/B arms (LAW 4 vs brief.md 'under test'), no slot for Jobs or Sources in the brief, and how to write the Since line on a --no-store rerun.

## Bar

```
ucopy: 20/22

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
 6. Fresh-host evidence      0/2
      - no fresh-host trial protocol or log
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
