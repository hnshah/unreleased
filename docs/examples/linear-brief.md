# Worked example: the Linear brief (live, current layout)

A fresh host with only SKILL.md and the references, on 2026-11-07, first run, with a docs source (`https://linear.app/llms.txt`). Ten findings from the app shell's flag registry; the run was partial because crt.sh errored. The eval case `linear-fresh-host` checks this file and its receipts were verified against the run with `--run`. The rendered pair is `linear-report.html` and `linear-report.md`.

---
🔎 unreleased 0.1.0 · linear · 2026-11-07 · partial · first run
Read as Linear the issue tracker at linear.app. Read 12.9 MB in 60 of 1,501 first-party scripts (cap hit; the app shell's startup chunks were read), 2 pages, the pricing page, 10 changelog entries back to 2026-07-23, 180 docs pages, the sitemap and 32 Ashby jobs. Not read: the certificate log (crt.sh answered an HTTP error) and the 1,441 chunks past the cap; anything shipped before 2026-07-23 is unsearched in the changelog, not unmentioned. Full coverage at the end.

**The shape of it** (my reading): The code that is not yet public is almost all agent plumbing. Coding sessions are growing admin controls (workspace keys, effort, model, quota), pull requests are getting an agent slot of their own, and the Linear Agent is being given per-team skills, connectors and a standing role on projects. Integration work widens the surface on the code host side: GitLab and GitHub Enterprise. The marketing bundle adds nothing new; the sitemap holds a switch campaign built but not linked.

**Unannounced** (10)

*Coding agent and pull requests*

1. **GitLab code access beta** · high
   Present in code (catalog): `gitlab-code-access` "GitLab beta: read GitLab code and CI output in Linear (code grants, Diffs view, CI job logs, Code Intelligence), act on merge requests as th…"; `gitlab-project-scoped-setup` "Expose the advanced GitLab setup fields (validation project path, read-only override, declared expiry)…". Checked: the same, plus 1 web query and the 2026-05-27 Diffs changelog entry; nothing on GitLab. ¹
   Raises: Whether Diffs, Code Intelligence and the coding agent reach GitLab repositories as one release or feature by feature.

2. **Agents on pull requests** · high
   Present in code (catalog and manifest): `pull-request-agent-selector` "Choose an agent to resolve pull request checks, conflicts, and review comments"; `pull-request-check-summaries` "Generate AI summaries for pull request check logs"; `PullRequestAgentSuggestions`; `pull-request-external-labels`; `github-comment-outside-diff`. Siblings `pull-request-search` and `pull-request-revert` are partially announced 2026-10-08 https://linear.app/changelog/2026-10-08-stacked-pull-requests. Checked: the same; nothing for the 5 keys above. ²
   Raises: Whether a pull request gets an assigned agent the way an issue gets an assignee.

3. **Coding session controls: keys, effort, model, quota** · high
   Present in code (catalog, manifest, enum), 7 keys: `coding-sessions-workspace-keys` "Choose workspace credentials for coding session inference. Coding sessions BYOK"; `coding-session-effort-workspace-setting` "Expose the reasoning effort selector for Coding Sessions in workspace settings"; `CodingAgentModelSelect`; `codingAgentQuotaExceeded`; `coding-session-trusted-external-source`; `agent-session-live-diff`. Sibling `coding-session-dev-server` is announced 2026-08-20 https://linear.app/changelog/2026-08-20-coding-environments. Checked: the same; nothing. ³
   Raises: Whether inference can run on a customer's own keys, and how a coding quota reads once it is on the pricing page.

4. **Usage alerts and spend limits** · high
   Present in code (route and manifest): `/:orgKey/inbox/usage-alert/:usageAlertId`, `UsageLimitLabels`, `usageLimitSpendQuery`; origins count `usage` ×16 including "usageEntitlementEnforcement". The enum `usageLimit` is announced (docs) https://linear.app/docs/usage-and-limits.md. Checked: the same; the alert route and the spend query, nothing. ⁴
   Raises: Whether usage alerts reach the inbox before a spend cap is a setting a reader can find.

*Agents in the workspace*

5. **Team-level agent skills and connectors** · high
   Present in code (route and catalog): `/:orgKey/settings/teams/:teamKey/agent-skills`, `…/agent-connectors`; `mcp-scoped-access` "Let workspace admins limit the teams that Linear MCP connections can access"; `mcp-connectors-dialog` "Open a directory dialog … when adding an MCP connector". A skill here is, my reading, a packaged instruction set for the Linear Agent. Checked: the same, plus 1 web query; nothing. ⁵
   Raises: Whether skills and connectors are scoped per team at launch, and whether the connector directory is Linear's own list or an open one.

6. **Project agent, AI memory, AI reports, agentic search** · high
   Present in code (catalog): `project-agent` "Enable the background project agent from the project developer command"; `ai-project-memory` "Enable AI memory for projects"; `ai-reports` "AI generated reports for views"; `sid-search-agent` "Enable the opt-in agentic search mode in workspace search"; `agent-workspace-onboarding` "Enable the agent-driven workspace onboarding experience". Checked: the same, plus 1 web query; nothing. ⁶
   Raises: Whether the Linear Agent becomes a standing presence on every project rather than something invoked per issue.

7. **Slack: agents addressing the Linear Agent, narrower scopes** · high
   Present in code (catalog and manifest): `linear-ai-integration-users` "Allow certain integrations/agents to be allowed to talk to the Linear Agent in Slack"; `LinearAgentTrustedSourceImage`; `slack-integration-opt-out-of-autojoining-channel` "does not request the channels:join Slack scope"; `slack-integration-opt-out-of-reading-message-history`. Checked: the same; nothing. ⁷
   Raises: Whether third-party agents get to talk to the Linear Agent in Slack as a person does, and whether the reduced-scope install becomes the default.

*Workflow and admin*

8. **Loop templates and automation run history** · high
   Present in code (catalog, manifest, route): `workspace-loop-templates` "Let workspace admins save loops as templates and let members start loops from them"; `WorkspaceLoopTemplateDialog`; `/:orgKey/settings/teams/:teamKey/automation/:automationId/runs`. Loops themselves are announced 2026-09-14 https://linear.app/changelog/2026-09-14-loops-for-product-management. Checked: the same; templates and the run pages, nothing. ⁸
   Raises: Whether loops become a shared template library, and whether a per-run log is what makes them auditable.

9. **Jira projects table with per-project sync** · high
    Present in code (catalog, manifest, route): `jira-projects-unified-ui` "Replace the Jira links list in the Jira settings with a table of Jira projects that shows each project's sync and import…"; `JiraProjectsPage`; `/:orgKey/settings/integrations/jira/projects`. Checked: the same; nothing. ⁹
    Raises: Whether per-project Jira sync replaces the one-time import for teams running both.

10. **GitHub Enterprise Server and Cloud** · high
    Present in code (registry and catalog): `githubEnterpriseServerIntegration`, `githubEnterpriseCloudIntegration`, `githubEnterpriseServerPullRequest`; `github-optional-code-access` "pick between GitHub linking with or without code access". The registry key `githubEnterpriseServer` is partially announced https://linear.app/pricing. Checked: the same; the Cloud key and the pull request key, nothing. ¹⁰
    Raises: Whether Diffs and the coding agent reach self-hosted GitHub Enterprise Server code rather than issue linking only.

**Partially announced** (3): `android-code-review` = off and `android-code-review-guide` = off (gates), the first partially announced 2026-09-24 https://linear.app/changelog/2026-09-24-new-controls-for-linear-coding-agent; `LinearAgentMcpSettings` (manifest), partially announced https://linear.app/pricing; `ImportExport` (registry), partially announced https://linear.app/pricing. ¹¹
**Campaigns**: In the sitemap, `/switch/migration-guide`, `/switch/pilot-guide` and `/switch/pitch-guide` are listed and not linked from the pages read, while `/switch` is linked; `/integrations/vs-code-mcp` (lastmod 2026-03-04) is listed and not linked. Checked: robots.txt disallows only `/api/` and `/cdn-cgi/`; 1 landing page read, so no shared headline. Raises: Whether a push aimed at teams switching tools is the next campaign, with the pitch and pilot guides as its material. ¹²
**Since**: First run; there is no previous run to diff against.
**New subdomains**: Could not see. The certificate log query for linear.app returned an HTTP error; a rerun may fill this section.

**Announced, for calibration**: Coding environments (announced 2026-08-20 https://linear.app/changelog/2026-08-20-coding-environments), new controls for the coding agent (announced 2026-09-24 https://linear.app/changelog/2026-09-24-new-controls-for-linear-coding-agent), stacked pull requests (announced 2026-10-08 https://linear.app/changelog/2026-10-08-stacked-pull-requests), Slack and GitHub loops (announced 2026-10-22 https://linear.app/changelog/2026-10-22-slack-and-github-loops), priority inbox (announced 2026-09-03 https://linear.app/changelog/2026-09-03-priority-inbox), team initiatives (announced 2026-08-13 https://linear.app/changelog/2026-08-13-team-initiatives), the cloud coding agent (announced (docs) https://linear.app/docs/linear-cloud-coding-agent.md). On the pricing page: "$10 per user/month" and "$16 per user/month". Job signal: Senior / Staff Security Engineer posted 2026-10-15; the other 2026 postings are sales, support, solutions and marketing roles, several for APAC and EMEA.
**Not read / set aside**: 1,441 scripts past the 60-script cap, so lazy-loaded settings pages were not read. The `https_linear` registry lines (OAuth redirect URLs for Google, Figma, Jira, Salesforce, Discord, Front) are build configuration for documented integrations, set aside. `AGENTS_WAITLIST` and `REVIEWS_WAITLIST` in the marketing chunk are analytics event names (low confidence: a strings-shape match), set aside. `ApiKeyEditPage`, `desktop-workspace-views`, `oauth-app-all-private-teams-access` and `project-template-dependencies` are ranked lines not expanded here; receipts are in evidence.jsonl. 45 redactions and 5 demotions are counted in redactions.log.
**Coverage**: Pages 2 of 2 ok (https://linear.app/login, https://linear.app/); scripts capped, read 60 of 1,501 enumerated (12,883,407 bytes); crt error (linear.app: HTTP error); ats ok, Ashby board `linear` verified, 32 jobs; pricing ok (4,942 chars, 4 amounts); changelog ok (10 entries, newest 2026-11-05); docs ok (llms.txt, 180 pages); robots ok (2 Disallow lines); sitemap ok (1,007 urls); landing ok (1 of 1); runtime flag providers: none seen; third-party hosts: none; redactions 45.

**Receipts**: host https://static.linear.app (client/assets/ unless noted) · run folder ~/.local/share/unreleased/runs/linear/2026-11-07T031219Z
¹ startup-boot.DZ8OVP0M.js sha256:3418c8202271@46547 · startup-boot.DZ8OVP0M.js sha256:3418c8202271@46296
² startup-boot.DZ8OVP0M.js sha256:3418c8202271@38951 · startup-boot.DZ8OVP0M.js sha256:3418c8202271@38801 · startup-root.jU0ShJRR.js sha256:3436f4c67482@36447
³ startup-boot.DZ8OVP0M.js sha256:3418c8202271@22052 · startup-boot.DZ8OVP0M.js sha256:3418c8202271@47526 · startup-root.jU0ShJRR.js sha256:3436f4c67482@25907
⁴ startup-root.jU0ShJRR.js sha256:3436f4c67482@6638485 · startup-root.jU0ShJRR.js sha256:3436f4c67482@27327 · startup-root.jU0ShJRR.js sha256:3436f4c67482@23193
⁵ startup-root.jU0ShJRR.js sha256:3436f4c67482@6665129 · startup-root.jU0ShJRR.js sha256:3436f4c67482@6665283 · startup-boot.DZ8OVP0M.js sha256:3418c8202271@41149
⁶ startup-boot.DZ8OVP0M.js sha256:3418c8202271@45783 · startup-boot.DZ8OVP0M.js sha256:3418c8202271@42080 · startup-boot.DZ8OVP0M.js sha256:3418c8202271@35454
⁷ startup-boot.DZ8OVP0M.js sha256:3418c8202271@43807 · startup-root.jU0ShJRR.js sha256:3436f4c67482@22587 · startup-boot.DZ8OVP0M.js sha256:3418c8202271@28049
⁸ startup-boot.DZ8OVP0M.js sha256:3418c8202271@34273 · startup-root.jU0ShJRR.js sha256:3436f4c67482@44089 · startup-root.jU0ShJRR.js sha256:3436f4c67482@6665390
⁹ startup-boot.DZ8OVP0M.js sha256:3418c8202271@42353 · startup-root.jU0ShJRR.js sha256:3436f4c67482@47439 · startup-root.jU0ShJRR.js sha256:3436f4c67482@6650292
¹⁰ startup-entry.D_mEZPiO.js sha256:68a6fe43d207@429072 · startup-entry.D_mEZPiO.js sha256:68a6fe43d207@429001 · startup-entry.D_mEZPiO.js sha256:68a6fe43d207@47646
¹¹ startup-boot.DZ8OVP0M.js sha256:3418c8202271@53796 · startup-root.jU0ShJRR.js sha256:3436f4c67482@1581 · startup-root.jU0ShJRR.js sha256:3436f4c67482@4625816
¹² https://linear.app/sitemap.xml sha256:c8a77f8a21e4@2554 · https://linear.app/sitemap.xml sha256:c8a77f8a21e4@2620 · https://linear.app/sitemap.xml sha256:c8a77f8a21e4@89879

These are strings present in public code; a flag or route is evidence that something is being built, not that it will ship, and the reading of what a name refers to may be wrong. Every line links to the bytes it came from. Items marked announced are already public; the rest had no public mention found as of the run date in the sources listed.

```text
unreleased 0.1.0 · linear · run 2026-11-07T031219Z · partial · findings 1540 · key-list 2254 · codenames 146 · redactions 45 · 113.3s
```
