# Perfecting round 02: reverted

- Date: 2026-11-17T11:13:29
- Target: `<copy of unreleased>` at a pre-release build
- Fresh host: `claude` (`clean+fresh-config`); cost so far $10.32

## Measures

| | bar | eval pass | blocking | major | judge serious |
|---|---|---|---|---|---|
| before | 22/22 | - | 3 | 7 | 5 |
| after | 22/22 | - | 0 | 8 | 4 |

Decision: **reverted**, worse on major stumbles.

## What was fixed

- Problem: When the script cap is hit, the engine and the brief rules let the agent say a flag provider is absent, even though only 2% of scripts were read. Provider detection also misses gate call sites such as checkGate, useGate and getFeatureGate, so even scripts that were read can fail to count as a provider. This causes the blocking false-absence stumble on notion-marketplace, and the eval's must_state 'checkGate' cannot pass.
- Where: skills/unreleased/scripts/lib/vendors/statsig-sdk.json, skills/unreleased/scripts/lib/emit.py:127, skills/unreleased/references/brief.md (Not read / set aside, Coverage)
- Fix asked: 1) Add call-signature fingerprints (`checkGate(`, `useGate(`, `getFeatureGate(`, `getExperiment(`) to statsig-sdk.json so any script that was read registers the provider. 2) In emit.py, when cap_hit and no provider was found, print a coverage line: 'runtime flag provider: none found in the N of M scripts read (capped)'. 3) Add one sentence to brief.md: an absence under a cap is written as 'not found in the N scripts read', never as 'not detected'.
- Fixer: Statsig is now detected in any script that was read and calls checkGate(, useGate(, getFeatureGate( or getExperiment(; when the script cap is hit and no provider was found, the coverage block prints 'runtime flag provider: none found in the N of M scripts read (capped)'; and brief.md now says an absence under a cap must be written 'not found in the N scripts read', never 'not detected'. I added the call signatures to the Statsig file's `init` list, not `markers`, because markers also mark the code around each match as vendor code, which would have hidden the product's own gate names next to those calls.

## Fresh-host trial findings

- **major** (notion-marketplace): The brief says 'marketplace' and 'present in code' but never mentions `checkGate`. The run read 60 of 2,841 enumerated scripts ('scripts: capped (read 60 of 2841 enumerated; cap 60 scripts …)') and reported 'runtime flag provider: none found in the 60 of 2841 scripts read'. So the gate check that was expected was never found.. Cause: runtime.md script cap (60 scripts / 180 requests) and the order scripts are picked in. The flag-provider and gate-check chunk is not prioritised before the cap is hit.. Quote: "Must state: marketplace; present in code; checkGate"
- **major** (notion-marketplace): The verdict says 'rich' and 'every source answered'. In the same block the notion.so certificate log is 'no-results (HTTP 404)', notion-static.com returned 0 names, and 98% of scripts were not read. The verdict contradicts its own evidence.. Cause: The engine's coverage verdict rules (runtime.md / brief.md coverage section). Quote: "verdict: rich: every source answered; under the budget cap: scripts read 60 of 2841 enumerated"
- **major** (notion-marketplace): The first render of the report used yesterday's brief.md. The agent had to notice the stale badge, overwrite the file and render again.. Cause: report.md / the report command does not check that the brief matches the run. Quote: "report.md says "Overwrite the file on a rerun" … The report command rendered a `brief.md` dated the day before without warning"
- **major** (notion-marketplace): There were five Notion runs that day. The skill defaults to diffing against the most recent one, a few minutes earlier, so the 'Since' section is empty. The agent had to explain that its findings were 'standing, not news'.. Cause: diff.md: "'Since this morning' means the run the person last read … pass `--since <run id>`" gives no rule for when that run is unknown. Quote: "Since 2026-11-17T184631Z (0 days): Nothing material moved"
- **minor** (notion-marketplace): The engine gave no offset for some robots Disallow lines, so the agent could not follow the receipt contract. It added a parenthetical by hand.. Cause: Engine campaign/robots output vs the receipt rule in brief.md. Quote: "brief.md says "never shorten the hash prefix or drop the offset" … "(the engine gave no offset for `/product/agents-homepage`)""
- **minor** (notion-marketplace): Some generated queries were garbled or named a host that is not in the run. The agent reworded one and skipped two, with no guidance on whether that was allowed.. Cause: web_queries.json generator; LAW 6 calls queries 'bounded' but gives no rule for rewording them. Quote: "web_queries.json produced "notion notion mcp claude", "notion source upgrade analytics" and "site:info.notion.com""
- **minor** (notion-marketplace): The engine's 'none' label conflicts with brief.md's 'unsearched' rule. The agent had to move Notion Calendar to 'announced' by hand.. Cause: Engine labelling vs brief.md / LAW 6. Quote: "labels items like `notion_calendar_launch_promo` as "no public mention found (searched: … changelog-index since 2026-07-30 (10 entries))". But brief.md says "a feature older than that window is not un"
- **minor** (notion-marketplace): The rules conflict on trial or entitlement keys. The agent guessed and included the Business trial keys. The brief also led with meetings, not plans and prices.. Cause: LAW 4 vs brief.md ordering guidance. Quote: "LAW 4 says "Codenames, A/B arms, entitlements and internal tooling stay out". brief.md tells me to lead with "plans, prices, credits"."
- **minor** (notion-marketplace): The final reply starts mid-sentence and the opening framing is lost. There is also a broken line in the coverage block ('sitemap\n- pages read 2 of 2').. Cause: Brief template / delivery instruction: "the brief in the reply, in full" with prose wrapped around it, and coverage line wrapping in the engine output. Quote: "r. So the list below is what is still in the code, not new movement."
- **minor** (notion-marketplace): A command that SKILL.md refers to is missing from the command reference.. Cause: runtime.md Commands and exit codes. Quote: "SKILL.md's Policy says "(`ua` prints it)" … runtime.md's "Commands and exit codes" block … leaves it out."
- **minor** (notion-marketplace): The agent did not know where the required Sources list should go, so it put it after the brief.. Cause: brief.md delivery section. Quote: "brief.md says to deliver "the brief in the reply, in full" and to close it with the boilerplate and footer. The web search tool requires a "Sources:" list"
- **major** (cursor-blocked-page): On the second run the agent could not reuse the earlier plan, so it wrote a new one from scratch. The new plan was worse: 38 of 70 scripts instead of 60, and it pointed docs at llms.txt instead of the 395-page docs sitemap. Coverage dropped against the baseline the brief diffs against.. Cause: plan.md (storing the plan / --since), and the run manifest schema. Quote: "plan.md: "Store the run once the plan is right" … "`--since <that run>` keeps later diffs against it" / agent: "the run folder doesn't keep `plan.json`: `manifest.json` has no `plan` field""
- **major** (cursor-blocked-page): Cursor's llms.txt is 535 lines of bare URLs with no markdown links, so the engine's parser returned zero pages. Every 'Checked' line then had to exclude the docs, and the agent checked items against the docs by hand.. Cause: plan.md docs-source guidance, and the engine's llms.txt parser. Quote: "plan.md: "Try `<docs host>/llms.txt` first" (the only warning is about "fewer than about 80 pages") / engine: "docs: no-results (https://cursor.com/docs/llms.txt: text: no links: no pages found)""
- **major** (cursor-blocked-page): The first render used a brief from an earlier run. The agent overwrote it and only learned afterwards that the earlier run had read more. No check ties brief.md to the run it describes.. Cause: report.md (rerun/overwrite rule), and the render script. Quote: "report.md: "Overwrite the file on a rerun; do not keep versions." / agent: "A stale `brief.md` from another session was sitting in the folder, and the first render used it without any warning""
- **major** (cursor-blocked-page): The Origin waitlist and the playground hosts went in as numbered Unannounced items even though both are marked 'partially announced'. Meanwhile 'Partially announced (1)' lists only /automations, so the counts and sections disagree. The heading 'Unannounced (0 in code…)' sits over six numbered items.. Cause: SKILL.md LAW 6 vs brief.md section on partial announcements. Quote: "LAW 6: "Items `announced` go under 'Announced, for calibration'" vs brief.md: a partially announced item "is a numbered finding when the part that is not public would be a finding on its own""
- **minor** (cursor-blocked-page): The careers page links straight to jobs.ashbyhq.com/cursor, but the engine still marked the board unverified. With no rule for this case, the agent made up the label 'low (board not verified by the engine)' and the run's verdict became partial.. Cause: plan.md ATS section, and the engine's board verification logic. Quote: "plan.md: "The engine verifies ownership, so a wrong guess costs one `unverified` line" / engine: "ats: partial (unverified board ashby/cursor…)""
- **minor** (cursor-blocked-page): The engine gives certificate-log and subdomain findings no receipt, so the agent wrote free-text receipts such as "Certificate logs (crt.sh) for cursor.com". That breaks the receipt format LAW 4 requires.. Cause: SKILL.md LAW 4, brief.md receipts section. Quote: "LAW 4: "receipt on every item (`file sha256 @offset`)""
- **minor** (cursor-blocked-page): This run read 38 scripts against the baseline's 60, yet the engine still reported 280 removed keys and left `note` empty. The agent had to judge for itself whether the removals were real.. Cause: diff.md withholding rule, and its threshold in the engine. Quote: "diff.md: "when this run read far fewer bytes than the baseline, `removed` is withheld" / brief: "The 280 removed keys are media player attributes""
- **minor** (cursor-blocked-page): The file report.md points to does not ship with the skill. The agent could not check the report against it.. Cause: report.md reference to docs/report-design.md. Quote: "report.md: "(`docs/report-design.md` is the system)""

## Judge

- serious (#None): The report command renders an old brief.md without any warning, so the report a user shares can show another run's findings. When --run-dir is left out, cmd_report reads the run id in the brief's own footer and renders against that run. A brief left over from yesterday therefore renders cleanly against yesterday's run. The only mismatch check is a short note inside the HTML Evidence card. The note is missing from report.md and from the JSON the command prints. This hit both trial tasks.. Evidence: skills/unreleased/scripts/unreleased.py:151-158 (picks run_dir from the brief footer's rid); scripts/lib/report.py:491-492,621 (the mismatch shows only in the HTML evidence lead); references/report.md step 1 'Overwrite the file on a rerun'; stumbles notion-marketplace and cursor-blocked-page: 'the first render used it without any warning'
- serious (#None): The llms.txt parser only accepts markdown links. An llms.txt made of bare URLs returns 'text: no links', so the docs source comes back empty and every docs cross-check is lost. plan.md tells the agent to try llms.txt first and gives no fallback.. Evidence: skills/unreleased/scripts/lib/sources/docs.py:67-70 (only _MD_LINK is matched); references/plan.md:66; cursor stumble 'docs: no-results (https://cursor.com/docs/llms.txt: text: no links: no pages found)'
- serious (#None): The run folder does not save plan.json, so a later run cannot reuse the plan behind its baseline. In the trial the rewritten plan read less (38 scripts against 60, and llms.txt in place of the docs sitemap). The diff then reported 280 removed keys and did not withhold them.. Evidence: references/plan.md 'Store the run once the plan is right'; cursor stumble 'manifest.json has no `plan` field'
- serious (#None): SKILL.md LAW 6 and brief.md give different rules for where partly announced items go. The brief then labels a section '(0 in code…)' and puts six numbered items under it.. Evidence: SKILL.md LAW 6 vs references/brief.md partial-announcement rule; cursor stumble
- note: Conflicts with ADR 0005/0007: the verdict reads 'rich: every source answered' even when crt.sh returned no-results (HTTP 404) and 98% of scripts went unread. no-results is not a partial state, so the badge contradicts its own coverage block. The cap rule was chosen on purpose, so a human should decide whether a source error or very low script coverage should downgrade the badge, or at least drop the words 'every source answered'.
- note: Round 2 committed the same fix as round 1 (Statsig checkGate fingerprints, the capped no-provider line, the brief.md wording), and round 1 was reverted as 'worse on judge's serious problems'. Check whether the same regression is back. Also, the coverage line in emit.py is added only when cap_hit and no provider was found. It does not reorder script selection, so checkGate still depends on which 60 scripts are picked.
- note: The CI eval step (tools/eval_brief.py) grades checked-in example briefs under docs/examples. It does not grade model output. The eval suite passing in CI says little about what a fresh agent writes, and this round's eval run was skipped (--no-evals).
- note: report.md and report.py point to docs/report-design.md, but the skill does not ship that file (cursor stumble). The `ua` command is missing from runtime.md's commands table.
- note: When the previous run is minutes old, the diff default leaves 'Since' empty. diff.md gives no rule for choosing a baseline across runs in one session.

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
      + 2 dated trial log(s), e.g. evidence/perfect/2026-11-17-1028/round-00.md
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
