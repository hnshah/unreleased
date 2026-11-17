# Perfecting round 01: kept

- Date: 2026-11-17T11:42:35
- Target: `<copy of unreleased>` at a pre-release build
- Fresh host: `claude` (`clean+fresh-config`); cost so far $6.94

## Measures

| | bar | eval pass | blocking | major | judge serious |
|---|---|---|---|---|---|
| before | 22/22 | - | 2 | 7 | 4 |
| after | 22/22 | - | 2 | 5 | 4 |

Decision: **kept**, better on major stumbles.

## What was fixed

- Problem: The skill makes the agent probe URLs while planning but never tells it to read robots.txt first, and gives it no way to check a URL against robots.txt. This contradicts POLICY.md's 'read first' rule, and in the Cursor trial the agent made the forbidden request to /dashboard. It is the only stumble where the skill led the agent to break its own published policy against a real site.
- Where: skills/unreleased/references/plan.md (the 'Finding the URLs is in policy' paragraph); skills/unreleased/scripts/unreleased.py (subcommands)
- Fix asked: In plan.md, make step 0 'Fetch https://<host>/robots.txt for each host you will probe (with the `ua` user agent) before any other request to that host; never probe a path under a Disallow line; list such a page in the plan instead (the engine records it as could-not-see).' Also add a small `unreleased.py robots <url>...` subcommand that reuses fetch.robots_rules/robots_disallows and prints allowed or disallowed for each URL. Then change plan.md's probe list to say 'check with `robots` first'.
- Fixer: Added an `unreleased.py robots <url>...` command that reads each host's robots.txt with the project user agent and prints allowed/disallowed per URL, and changed plan.md so planning first checks robots.txt, never probes a disallowed path, and lists such a page in the plan for the engine to record as could-not-see.

## Fresh-host trial findings

- **blocking** (notion-marketplace): The brief was supposed to name `checkGate`, the flag-gate call. It never does. Instead it says "The 60 scripts read show no feature-flag service". The engine read 60 of 2,841 scripts and picked them from the login page and the marketing home page. The script that loads the flag SDK was not among them, so the flag-gating evidence is missing and the brief's statement that there is no flag service is probably wrong.. Cause: engine script selection / script cap (scripts: capped, cap 60 scripts) and flag-SDK detection in scripts/unreleased.py. Quote: "flag SDKs: none seen in the 60 scripts read; the other 2,781 enumerated were not read and may load one"
- **major** (notion-marketplace): plan.json from the earlier run was in neither the run folder nor manifest.json. To repeat the plan, the agent searched the filesystem and found a copy in <a temp folder on the host>/.. Cause: SKILL.md run-folder / library contract; engine does not persist plan.json into the run folder. Quote: "SKILL.md: "Every run leaves a run folder and a library row; the second run on a product opens with 'since <date>'""
- **major** (notion-marketplace): The engine labelled Notion Calendar, a product launched in 2024, as checked with no public mention. The rules don't cover a label that is checked but wrong, so the agent overrode the engine with its own web search and moved the items to calibration.. Cause: SKILL.md rules ("Never present an unchecked item as unannounced", "Items announced go under 'Announced, for calibration'") plus the engine's announcement matcher, which only checks the changelog since 2020, the help sitemap and pricing. Quote: "Agent friction: "notion_calendar_launch_promo and /calendar/desktop/*/download came back 'no public mention found', but Notion Calendar launched in 2024""
- **minor** (notion-marketplace): The two files place the 'since' summary differently, so the agent used both. The brief repeats the 'nothing changed' summary twice.. Cause: references/diff.md vs references/brief.md layout. Quote: "diff.md: "the brief opens, after coverage, with: Since <previous run date>…" vs brief.md layout with a **Since <date>** block after Campaigns"
- **minor** (notion-marketplace): The two receipt rules contradict each other. The agent edited the receipts by hand to shorten them.. Cause: references/brief.md receipts section. Quote: "brief.md: "copy receipts from evidence.md, never retype them" / "shorten the url to its file name""
- **minor** (notion-marketplace): SKILL_DIR is not an environment variable, so the agent had to work out the skill path itself.. Cause: SKILL.md run commands. Quote: "SKILL.md: "$SKILL_DIR/scripts/unreleased.py" … "SKILL_DIR holds this file""
- **minor** (notion-marketplace): The agent added an extra **Jobs** block that the layout doesn't list.. Cause: references/brief.md layout. Quote: "evidence.md has a "## Jobs" section; brief.md layout has no Jobs block"
- **minor** (notion-marketplace): brief.md and SKILL.md LAW 3 list different labels, so the agent had to guess which one is allowed.. Cause: SKILL.md LAW 3 vs references/brief.md. Quote: "brief.md: "announced (docs) <url>" not in SKILL.md LAW 3 vocabulary"
- **minor** (notion-marketplace): The search tool ignored the site: operator in the generated queries for the info, events and info.notion.so hosts. The skill doesn't say what to do in that case, so the agent reported 'no pages' based on searches that never ran as intended.. Cause: SKILL.md LAW 6 / engine web_queries.json generation. Quote: "LAW 6: "run the engine's bounded web_queries.json (one search each)""
- **minor** (notion-marketplace): One coverage line was split across two bullets in the middle of the text. It also calls a run that read 2% of the scripts and found no flag SDK 'rich'.. Cause: engine coverage/verdict formatting and verdict rule. Quote: ""verdict: rich: every source answered; under the budget cap: scripts read 60 of 2841 enumerated, sitemap\n- pages read 2 of 2""
- **major** (cursor-blocked-page): The agent picked a fixed scratch folder, overwrote another session's plan and rendered report, then switched to a new timestamped folder. It ran a destructive overwrite of files it did not create before it looked at the target.. Cause: report.md: 'written beside the brief by default'; no skill file says where brief.md or plan.json should go. Quote: "I wrote my plan to `/tmp/unrel-cursor/plan.json` without checking first, and that folder already held a session's files. This replaced its `plan.json`, and one early render replaced its `report.html` "
- **major** (cursor-blocked-page): All 28 ranked findings were noise: 23 from a third-party HLS/video player library and 5 from marketing demo strings. The agent had to triage them by hand and set them aside, leaving the Unannounced section empty. The skill says the engine drops vendor SDK noise, so the agent could not tell why it failed to.. Cause: engine vendor filter (the skill's 'drops vendor SDK noise' claim); 286nabbhrwlju.js not recognised as vendor. Quote: "Of the 28 lines the engine ranked, 23 come from a video player library and 5 are demo material"
- **major** (cursor-blocked-page): The engine's announcement check said 'none' for items its own docs index covers. The agent caught it and relabelled them by hand. A less careful run would have reported announced products as unannounced, which breaks LAW 6.. Cause: engine docs-index matcher (matches the key path, not nested docs slugs); brief.md has no guidance to second-guess a 'none' check. Quote: "It printed "`/automations` ... no public mention found (searched: ... docs-index (395 pages)...)" while the docs sitemap lists `/docs/cloud-agent/automations` and `/docs/origin`"
- **minor** (cursor-blocked-page): The two rules contradict each other for non-code findings. The agent guessed and moved subdomain and job findings into unnumbered blocks.. Cause: brief.md: confidence-word rule vs numbered-findings rule; report grammar line format. Quote: "brief.md says "The confidence word is the one the engine prints on the line", and the report grammar needs "`N. **Noun** · high`". But subdomain and job lines carry no confidence word, and brief.md al"
- **minor** (cursor-blocked-page): The agent rebuilt the earlier plan by hand from coverage output in order to re-run or diff.. Cause: engine run-folder writer / manifest.json schema. Quote: "diff.md and plan.md talk about re-runs and fixing a plan, but the run folder keeps no copy of the plan (`manifest.json` has no `plan` key). I had to rebuild the plan from coverage lines."
- **minor** (cursor-blocked-page): The diff baseline was a same-day run 14 minutes earlier, apparently the agent's own aborted attempt, so the 'since' section is empty by construction. It also calls a host first seen six weeks ago 'newly seen'. The reader gets a confusing delta.. Cause: diff.md baseline selection (picks the latest prior run, even a same-session or partial one). Quote: "Since 2026-11-17T192347Z (0 days): ... One host is newly seen in the certificate logs (`8afccabb.tunnel.cursor.sh`, first seen 2026-10-05)."
- **minor** (cursor-blocked-page): Origin appears both as a partially announced finding and as announced calibration, and the short answer leads with it as the 'main new product'. The skill gives no rule for a feature that is announced while one sub-route of it is not.. Cause: brief.md section definitions (Partially announced vs Announced). Quote: "**Partially announced** (1) 1. **Origin waitlist** ... / **Announced, for calibration**: - Origin (docs https://cursor.com/docs/origin)"
- **minor** (cursor-blocked-page): The chat brief truncated receipts and coverage lines. That conflicts with the brief's own promise that 'Every line links to the bytes it came from'.. Cause: brief.md receipts contract vs chat length guidance. Quote: "⁴ jobs.ashbyhq.com/cursor/e32955ea… · 5df283dc… (full URLs in the report) / The reply above shortens some coverage lines and receipts"
- **minor** (cursor-blocked-page): The engine could not confirm that the obvious Ashby board belongs to Cursor, so job signals carried a hedge the agent had no way to resolve.. Cause: engine ATS ownership check. Quote: "ats: partial (unverified board ashby/cursor: 95 jobs; greenhouse, lever, workable 404)"

## Judge

- serious (#None): On a large product, the engine picks the scripts it reads with no regard for where a flag SDK might be. On the live Notion trial it read 60 of 2,841 scripts and missed the chunk that holds the flag client. The brief then never named checkGate and said the scripts read showed no feature-flag service. The repo's own eval case says a Notion brief must name checkGate, and this run fails it. This was the trial's only blocking stumble.. Evidence: skills/unreleased/scripts/lib/discover.py:176-190, where select_by_role ranks only on (vendor, seen-last-run, hashy name) and nothing about flag SDKs; evals/evals.json notion-marketplace must_state includes "checkGate"; trial quote: "flag SDKs: none seen in the 60 scripts read; the other 2,781 enumerated were not read"
- serious (#None): The check for whether an item has already been announced misses things the engine has itself indexed. Notion Calendar launched in 2024 and came back 'no public mention found'. Cursor's /automations came back the same while the docs index it searched lists /docs/cloud-agent/automations. A less careful agent would report announced products as unannounced, which breaks LAW 6.. Evidence: skills/unreleased/scripts/lib/crosscheck.py:120-134 (check/docs-index); trial: "`/automations` ... no public mention found (searched: ... docs-index (395 pages)...)"
- serious (#None): The vendor filter let a video-player library through. All 28 ranked Cursor findings were hls/media-player strings or demo copy, even though a vendors/hls-js.json fingerprint exists and SKILL.md says vendor SDK noise is dropped.. Evidence: skills/unreleased/scripts/lib/vendors/hls-js.json exists; trial: "Of the 28 lines the engine ranked, 23 come from a video player library and 5 are demo material"
- serious (#None): No skill file says where the agent should put plan.json or brief.md, and the render step overwrites files without checking. The trial agent overwrote another session's plan.json, report.html and report.md in a shared /tmp folder. The run folder also keeps no copy of plan.json, so a re-run means rebuilding the plan by hand.. Evidence: trial: "This replaced its `plan.json`, and one early render replaced its `report.html` and `report.md`"; manifest.json has no `plan` key
- note: The checker gives 22/22, but no output evals ran this round (--no-evals). The notion-marketplace case in evals/evals.json would probably fail on the live behaviour seen in the trial.
- note: The 60-script cap and the 'rich under a budget cap' verdict were chosen on purpose (ADR 0005, ADR 0007), so I am not asking to change them. The fix below changes only which 60 scripts are read. Conflicts with ADR 0007: a run that is 'rich' and still finds no flag SDK after reading 2% of the scripts may deserve a lower verdict, or at least the word 'unknown'. That is for a human to decide.
- note: The coverage line in emit.py:129 is already worded carefully, and references/brief.md:49-50 already forbids turning unread scripts into an absence. The wording is fine; the miss happens upstream, in which scripts get selected.
- note: Small inconsistencies between reference files (where the 'since' block goes in diff.md vs brief.md, the receipt-shortening rules, the Jobs block, the LAW 3 label list, SKILL_DIR not being resolvable) are real but minor.

## Bar

```
ucopy2: 22/22

 1. Layout                   2/2
      + .claude-plugin/plugin.json name='unreleased'
      + 1 skill(s) under skills/<name>/SKILL.md
 2. Lean SKILL.md            2/2
      + all 1 SKILL.md ≤130 lines and ≤8,000 bytes
      + every description has 'Use when' and 'Not for'
 3. Deterministic scripts    2/2
      + 37 script file(s), e.g. skills/unreleased/scripts/lib/__init__.py
      + skills/unreleased/SKILL.md names skills/unreleased/scripts/unreleased.py
 4. Tests                    2/2
      + 34 test file(s), e.g. tests/__init__.py
      + CI runs the tests
 5. Output evals in CI       2/2
      + 1 eval case file(s), e.g. evals/evals.json
      + CI runs the evals
 6. Fresh-host evidence      2/2
      + 4 dated trial log(s), e.g. evidence/perfect/2026-11-17-1028/round-00.md
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
