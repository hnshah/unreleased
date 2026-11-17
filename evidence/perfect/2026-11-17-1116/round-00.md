# Perfecting round 00: baseline

- Date: 2026-11-17T11:29:10
- Target: `<copy of unreleased>` at a pre-release build
- Fresh host: `claude` (`clean+fresh-config`); cost so far $3.41

## Measures

| | bar | eval pass | blocking | major | judge serious |
|---|---|---|---|---|---|
| before | 22/22 | - | 2 | 7 | 4 |

Decision: **baseline**, measured before any change.

## Fresh-host trial findings

- **blocking** (notion-marketplace): The expected answer had to name `checkGate`, which is the gate-check call of a runtime flag SDK. The brief instead says no flag SDK was seen. The engine read 60 of 2,841 scripts and stopped at the cap, so the SDK's code was probably never loaded. The agent reported the gap but did nothing to close it, and the brief still reached a 'rich' verdict.. Cause: engine script cap (60 scripts / 180 requests) and the evidence.md / SKILL.md coverage rules. Quote: "flag SDKs: none seen in the 60 scripts read; the other 2,781 enumerated were not read and may load one"
- **major** (notion-marketplace): The coverage verdict calls the run 'rich' even though two sources were capped and 98% of the scripts went unread. The verdict line is also broken across two bullets ('sitemap' / 'pages read 2 of 2'), which breaks the coverage block's format.. Cause: verdict rules in brief.md/evidence.md, and the engine's coverage rendering. Quote: "rich: every source answered; under the budget cap: scripts read 60 of 2841 enumerated, sitemap
- pages read 2 of 2"
- **major** (notion-marketplace): The agent reused /tmp/unrel-notion and overwrote another session's plan.json without reading it. One of its brief writes failed, and the report step then quietly rendered the earlier session's brief. Nothing flagged the mismatch, and data from another run was destroyed.. Cause: plan.md (output location) and report.md (overwrite rule). Quote: "plan.md: write plan.json (no location, no existence check); report.md: "Overwrite the file on a rerun; do not keep versions""
- **major** (notion-marketplace): There were six earlier Notion runs that day, and nothing showed which one the person had read. The default compared against the 19:00Z run from 16 minutes earlier, which produced an empty 'since 0 days' section. The diff also labelled four October subdomains as new, because the earlier run's certificate-log data was incomplete.. Cause: diff.md baseline selection. Quote: "diff.md: "the run the person last read … pass `--since <run id>`""
- **minor** (notion-marketplace): The two files place the since line in different spots. The agent put it at the top and left a pointer in the lower slot, so the brief repeats itself ('**Since**: Quiet; see the since line above').. Cause: diff.md vs brief.md layout. Quote: "diff.md: "the brief opens, after coverage, with: `Since <previous run date> …`" vs brief.md: "**Since <date>**: … (second run on; diff.md)" placed after Campaigns"
- **minor** (notion-marketplace): The engine ranked A/B arms and trial gates as high-confidence findings. brief.md only allows setting items aside for vendor or demo material, so the agent had to guess whether dropping A/B arms counted as reordering.. Cause: brief.md set-aside rule and the engine's ranking. Quote: "SKILL.md LAW 4: "Codenames, A/B arms, entitlements and internal tooling stay out" vs brief.md: "Do not reorder product findings among themselves""
- **minor** (notion-marketplace): The agent had to work out what the offset convention means and compute the robots.txt offset @259 by hand.. Cause: evidence.md 'other' section and the engine's robots extraction. Quote: "LAW 4: "a footnote receipt (`file sha256 @offset`)" on every item; evidence.md lists robots.txt prefixes under 'other' with no receipt"
- **blocking** (cursor-blocked-page): While planning, the agent sent a GET to /dashboard before it had read robots.txt. That broke the skill's hard rule against probing disallowed paths. The request redirected to login and nothing was read, but the forbidden request was still made.. Cause: plan.md probing section: lists URLs to probe but never says to fetch robots.txt first. Quote: "plan.md: "You may not … probe anything robots.txt disallows" / also suggests probing "`/login`, `/pricing`, `/changelog`, `app.<domain>`"; transcript: "I sent one GET to `cursor.com/dashboard` before "
- **major** (cursor-blocked-page): Cursor's llms.txt is 535 lines of bare URLs ('- https://cursor.com/docs/...md'). The docs reader only parses link syntax, so it found zero pages. No finding could be checked against the docs, which weakened every 'Checked:' line.. Cause: engine docs/llms.txt parser; plan.md docs step. Quote: "plan.md: "Try `<docs host>/llms.txt` first"; engine: "text: no links: no pages found""
- **major** (cursor-blocked-page): Most items came from certificate logs, jobs and the sitemap, and none of these have a script hash or offset. The agent made up its own receipt format, so the brief's receipt contract was not met as written.. Cause: brief.md receipt rule; evidence output has no receipt IDs for CT/jobs/sitemap lines. Quote: "brief.md: every item needs "a footnote receipt (`file sha256 @offset`)"; transcript: "I had to invent a footnote ('crt.sh certificate logs … coverage.json')""
- **major** (cursor-blocked-page): Almost all of the 28 ranked findings were video-player library keys (hls*, media_preview), a crc32 picker and a demo file tree. The agent had to put the ranking aside and build the brief from subdomains and jobs. That works around the ordering rule.. Cause: engine third-party/demo filter; brief.md ordering rules. Quote: "brief.md: "Do not reorder product findings among themselves" vs "Lead with 5 to 12 a person would recognise as product work""
- **major** (cursor-blocked-page): The skill does not say where brief.md goes, so the agent used a shared /tmp folder. A stale brief from another session was rendered into the report before the agent noticed, moved it aside and re-rendered.. Cause: SKILL.md/brief.md: no output path for brief.md; report.md overwrite rule. Quote: "report.md: "Overwrite the file on a rerun; do not keep versions"; transcript: "`/tmp/unrel-cursor/brief.md` from an earlier session was there and got rendered once by mistake.""
- **minor** (cursor-blocked-page): The Ashby board was clearly Cursor's, but the engine marked it unverified. With no rule on overriding that, the agent downgraded job-based items to 'low (board not verified)'.. Cause: engine jobs board verification; brief.md confidence rules. Quote: "engine: "the company could not be matched to cursor.com (titles)""
- **minor** (cursor-blocked-page): The only app shell was disallowed, so the run could only be partial. Neither file says what to do in that case, such as which alternative app host to try, so the agent spent time working out whether a fallback existed.. Cause: plan.md app-page section; SKILL.md. Quote: "plan.md: list a disallowed app page "(`Disallow: /dashboard`), still list the app page"; SKILL.md: app shell is "the richest page""
- **minor** (cursor-blocked-page): No first-party announcement URL was found for Origin, so the agent invented its own 'per press' label to fill LAW 6's format.. Cause: LAW 6 (announced format). Quote: "LAW 6: "announced <date> <url>"; transcript: "Origin's announcement date came from press, not a first-party page. I labelled it 'per press'.""

## Judge

- serious (#10): POLICY.md says robots.txt is read before any other request to a host. plan.md tells the planner to probe `/login`, `/pricing`, `/changelog` and `app.<domain>` and never says to read robots.txt first. No CLI command lets the planner check a URL against robots.txt either. In the Cursor trial the agent sent a GET to the disallowed `/dashboard` path, which breaks the skill's own policy.. Evidence: skills/unreleased/references/plan.md:26-30 ('send HEAD or GET requests to candidate URLs (/login, /pricing, /changelog, app.<domain>) ... You may not ... probe anything robots.txt disallows') vs POLICY.md:13 ('robots.txt is honoured, and read first. Before any other request to a host, its robots.txt is read'); unreleased.py:210-224 has `ua` but no robots command; trial: 'I sent one GET to cursor.com/dashboard before checking robots.txt'
- serious (#5): The notion-marketplace eval expects the brief to name `checkGate`. The 60-script cap reads scripts with no regard to whether they look like a flag SDK, so the gate-check SDK went unread in a run of 2,841 scripts. The brief said 'no flag SDK seen' and still got a 'rich' verdict. The core answer misses what the eval expects.. Evidence: evals/evals.json case notion-marketplace must_state 'checkGate'; trial quote 'flag SDKs: none seen in the 60 scripts read; the other 2,781 enumerated were not read'
- serious (#None): Nothing says where brief.md or plan.json should be written, and report.md says to overwrite on a rerun. In both trials the agent used a shared /tmp folder and rendered another session's stale brief. The `report` command looks up the run named in the brief's footer, so it rendered the old run without raising an error. In the Notion trial another session's plan.json was also overwritten.. Evidence: skills/unreleased/references/report.md:9-10 ('Overwrite the file on a rerun; do not keep versions'); unreleased.py:151-158 resolves run_dir from the brief's own footer; report.py:465 'still rendered, with a note'
- serious (#None): The llms.txt docs parser only reads markdown links. Cursor's 535-line llms.txt of bare `- https://...` URLs gave zero pages and no parser-failure warning, so every 'Checked:' line lost the docs as a source.. Evidence: trial cursor-blocked-page: 'text: no links: no pages found'; plan.md:78-79 'Try <docs host>/llms.txt first'
- note: Conflicts with ADR 0005/0007 (a cap is a budget and never changes the verdict). The Notion run read 60 of 2,841 scripts (2%) and was still 'rich', so the verdict on a heavily capped run tells the reader very little. A threshold, such as partial below some share read, may need a human decision. Putting likely flag-SDK scripts first in the read order does not conflict with these ADRs.
- note: The trial also found the 'rich ... under the budget cap' coverage line split across two bullets ('sitemap' / 'pages read 2 of 2'). That is a renderer bug.
- note: Receipts: LAW 4 requires `file sha256 @offset` on every item, but certificate-log, jobs, sitemap and robots evidence has no receipt format, so agents make one up. brief.md should document a receipt form for each evidence type, and the engine should emit it.
- note: The rule against reordering in brief.md conflicts with the vendor and demo noise (HLS player keys, demo file trees) and with LAW 4's exclusion of A/B arms. Both trials worked around the ranking.
- note: diff.md's default baseline compared against a run from 16 minutes earlier, which produced an empty since-section, and reported old certificate hosts as new.
- note: Output evals were not run this round (--no-evals), so I cannot say from here how the model-written output scores against evals.json.

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
      + 3 dated trial log(s), e.g. evidence/perfect/2026-11-17-1028/round-00.md
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
