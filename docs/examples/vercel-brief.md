# Worked example: the Vercel brief (live, footnoted layout)

The current layout (`references/brief.md`): badge and one line, the shape paragraph, findings as fact / checked / raises with a confidence word, receipts as footnotes, full coverage last, and the copy rules (sentence case, no em or en dashes). Written by a fresh host from nothing but the skill, from a live run on 2026-11-07 that read 4.5 MB of first-party code in 78 seconds. The eval case `vercel-footnoted` checks this file. `vercel-report.html` is the same brief rendered as a shareable file.

---
🔎 unreleased 0.1.0 · vercel · 2026-11-07 · rich · first run
Read as Vercel the deployment platform at vercel.com. Read 4,456,597 bytes of first-party code in 60 scripts, 2 pages, the certificate logs, 87 Greenhouse postings, the pricing page, 200 changelog entries, 28 docs pages and robots.txt. The gap that matters: the engine enumerated 110 scripts and read 60 under its cap, and the docs index was the 28-page llms.txt, so a feature described only on a deeper docs page can look unmentioned here. Full coverage at the end.

**The shape of it** (my reading): The dashboard code is thickest around AI Gateway and agents: a gated private inference area, a marketplace model playground, an agent builder with a free credit tier, an MCP chat with upgrade prompts, and Vercel Agent credits and bulk suggestion handling. A second cluster is money and movement inside the account: a support chat that handles refunds and invoice changes, project transfers that check for storage and paid features that will not move, integration configurations that transfer between teams, and an automatic refund event. The job board leans the same way (Agent Auth, Connect, Agentic Infrastructure, Software Factory, Scheduled Tasks), while the sitemap carries 130 compare and alternatives pages that no public page read links to yet.

**Unannounced** (12)
*AI Gateway*
1. **AI Gateway private inference** · high
   Present in code (routes): `/[teamSlug]/~/ai-gateway/private-inference` ("Private Models group=AI Gateway flag=enablePrivateInference"), `/[teamSlug]/~/ai-gateway/private-inference/providers` ("Private Providers"), `/[teamSlug]/~/ai-gateway/private-inference/models` and the per-model and per-provider pages beneath them, 5 routes behind one flag. Checked: pricing-text, docs-index (28 pages), changelog-index since 2026-09-11 (200 entries), plus one web search ("vercel private inference models"); nothing. ¹
   Raises: What a private model or private provider is in AI Gateway terms (a customer's own endpoint, or a dedicated one), and who the `enablePrivateInference` gate opens for.
*Dashboard, support and docs*
2. **Support chat with billing forms** · medium
   Present in code (enums), 34 keys: `SUPPORT_CHAT_REFUND_INVOICE_FORM_SUBMITTED`, `SUPPORT_CHAT_MODIFY_INVOICE_FORM_CONFIRMED`, `SUPPORT_CHAT_CASE_SAML_AUTH_INITIATED`, `SUPPORT_CHAT_UI_TOOL_RENDERED`, `SUPPORT_CHAT_UNBLOCK_HOBBY_USAGE_CLICKED`. Checked: pricing-text, docs-index (28 pages), changelog-index since 2026-09-11 (200 entries), plus one web search; community threads about refund requests only, nothing from Vercel. ²
   Raises: Whether support chat is becoming a self-service billing surface (refunds, invoice edits, unblocking Hobby usage, SAML cases) rendered as tools inside the conversation.
3. **Integration configuration transfer between teams** · medium
   Present in code (enums), 18 keys: `INTEGRATION_CONFIGURATION_TEAM_TRANSFER_MODAL_OPENED`, `INTEGRATION_CONFIGURATION_TEAM_TRANSFER_SUCCEEDED`, `INTEGRATION_CONFIGURATION_TRANSFER_CANCELED`, `INTEGRATION_CONFIGURATION_ACCESS_MODAL_PROJECTS_CHANGED`. Checked: the same, plus one web search ("vercel modal projects changed"); nothing. ³
   Raises: Whether an installed marketplace integration can move from one team to another with its projects, and what happens to its access scope on the way.
4. **Shareable docs AI chat** · high
   Present in code (routes): `/api/ai-chat/share` and `/api/ai-chat/title` on the vercel.com page, beside `/api/ai-chat` (the key list also carries `/api/ai-chat/share/og`). Checked: pricing-text, docs-index (28 pages), changelog-index since 2026-09-11 (200 entries), plus one web search; partially announced 2025-10-24 https://vercel.com/changelog/ai-chat-now-available-on-vercel-docs (the docs chat, with copy as Markdown; no share link or title route). ⁴
   Raises: Whether a docs chat gets a public share URL with its own title and preview image.
*Agents and projects*
5. **Vercel Agent credits and bulk suggestions** · medium
   Present in code (enums and registry), 17 keys plus 2 `AI_CREDITS` siblings: `VERCEL_AGENT_CREDITS_CHECKOUT_ERROR`, `VercelAgentAddCreditsModalOpened`, `VercelAgentUpsellImpression`, `VERCEL_AGENT_SUGGESTIONS_ACCEPTED_ALL`, `VERCEL_AGENT_SUGGESTIONS_IGNORED_ALL`, `VERCEL_AGENT_DIFF_VIEW_MODE_CHANGED`, `AI_CREDITS_CHECKOUT_SUCCESS`. Checked: the same, plus one web search ("vercel agent credits checkout"); partially announced (docs) https://vercel.com/docs/cli/buy and https://vercel.com/docs/rest-api/billing/purchase-credits (buying credits is documented; the upsell modal and accept-all or ignore-all suggestion handling are not). ⁵
   Raises: Whether agent suggestions become a bulk review flow, and where the credits upsell appears for teams that have not bought any.
6. **Project transfer preflight for storage and paid features** · medium
   Present in code (enums), 15 keys: `PROJECT_TRANSFER_INITIATED_WITH_MISSING_BLOB_STORAGE`, `PROJECT_TRANSFER_INITIATED_WITH_MISSING_POSTGRES_DATABASE`, `PROJECT_TRANSFER_INITIATED_WITH_MISSING_EDGE_CONFIG`, `PROJECT_TRANSFER_INITIATED_WITH_MISSING_INTEGRATIONS`, `PROJECT_TRANSFER_ADDED_BILLING_METHOD`, `PROJECT_TRANSFER_CONFIRMED_PAID_FEATURES`, `PROJECT_TRANSFER_DECLINED_PAID_FEATURES`. Checked: the same, plus one web search ("vercel added billing method"); partially announced 2026-09-28 https://vercel.com/changelog/vercel-sandbox-now-supports-memory-observability (transfer initiation and team creation match that page; the missing-storage and paid-features steps do not). ⁶
   Raises: Whether project transfer gains a checklist of what will not move (Blob, Postgres, KV, Edge Config, integrations) and a billing-method step on the receiving team.
7. **Agent builder free tier credits** · medium
   Present in code (registry), 9 keys: `agent_builder_free_tier_credits_add_card_impression`, `agent_builder_free_tier_credits_add_card_click`, `agent_builder_signed_out_prompt_entered`, `agent_builder_connection_setup_reused`, `agent_builder_draft_applied`. Checked: the same, plus one web search; partially announced 2026-08-28 https://vercel.com/changelog/build-and-deploy-eve-agents-from-the-vercel-dashboard (the dashboard agent builder; no free tier credits or signed-out prompt). ⁷
   Raises: Whether the agent builder gets a signed-out entry point and a free credit allowance that ends in an add-card prompt.
8. **MCP chat with upgrade prompts** · medium
   Present in code (enums), 13 keys: `mcp_chat_message_sent`, `mcp_chat_tool_call_presented`, `mcp_chat_tool_call_executed`, `mcp_chat_tool_input_viewed`, `mcp_chat_upgrade_prompt_viewed`, `mcp_chat_upgrade_cta_clicked`. Checked: the same, plus one web search (it returned the Vercel MCP server docs, not a chat surface); nothing. ⁸
   Raises: Whether a chat surface that drives Vercel MCP tool calls is plan-gated, since an upgrade prompt sits in the same event set.
9. **AI marketplace model playground and provider management** · medium
   Present in code (enums), 8 keys: `AI_MARKETPLACE_MODEL_PLAYGROUND_SUBMIT`, `AI_MARKETPLACE_MODEL_PLAYGROUND_ADD_MODEL_CLICKED`, `AI_MARKETPLACE_MODEL_EXPLORE_CLICKED`, `AI_MARKETPLACE_PROVIDER_ADDED`, `AI_MARKETPLACE_PROVIDER_REMOVED`. Checked: the same, plus one web search; nothing. ⁹
   Raises: Whether the AI marketplace gets an in-dashboard playground for trying a model and a provider list users add to and remove from.
*Plans and billing*
10. **Pro trial onboarding checklist** · medium
   Present in code (enums): `PRO_TRIAL_ONBOARDING`, `PRO_TRIAL_ONBOARDING_RESET`, `PRO_TRIAL_ONBOARDING_CHECKLIST_DISMISSED`, with `UPGRADE_PRO_TRIAL` and `DOC_PRO_UPGRADE_CTA_CLICK` nearby. Checked: the same, plus one web search; partially announced (docs) https://vercel.com/docs/plans/pro/trials (the trial itself; no checklist). ¹⁰
   Raises: Whether the Pro trial gets a guided checklist that can be reset, and whether docs pages carry a Pro upgrade call to action.
11. **Automatic billing refunds** · medium
   Present in code (registry), among 149 `vercel_api` event schemas: `vercel_api.v0.billing_automatic_refund`, `vercel_api.v0.marketplace_refund_received`, `vercel_api.v0.marketplace_invoice_payment_failed`, `vercel_api.v0.billing_subscription_patched`. Checked: the same; nothing. ¹¹
   Raises: Whether some refunds are issued without a support case, and how marketplace refunds flow back to the buyer.
*Agents*
12. **Agent code review with auto-merge** · medium
   Present in code (registry), 13 keys: `AgentCodeReviewAutoMergeEnabled`, `AgentCodeReviewAutoMergeDisabled`, `AgentCodeReviewPRMarkedReady`, `AgentCodeReviewGroupedDiffGenerated`, `AgentCodeReviewSettingChanged`. Checked: the same, plus one web search; partially announced 2026-11-02 https://vercel.com/blog/vercel-security-review and (docs) https://vercel.com/kb/guide/vercel-agent-code-review (review and diff views are public; auto-merge and marking a PR ready are not). ¹²
   Raises: Whether Vercel Agent moves from reviewing pull requests to marking them ready and merging them under a setting.

**Partially announced** (1): AI Gateway API keys, `AI_GATEWAY_API_KEY_CREATED` matched 2026-11-07 https://vercel.com/changelog/deepseek-v4-1-flash-1017-ultrafast-now-available-on-ai-gateway by keyword, while `AI_GATEWAY_API_KEY_CREATION_ERROR` and `AI_GATEWAY_API_KEY_DELETION_ERROR` had no public mention found in the same sources. ¹³

**Campaigns**: In the sitemap: 130 compare and alternatives pages, all under `/i/`, all lastmod 2026-11-07, none linked from the pages read, among them `/i/heroku-alternatives`, `/i/railway-alternatives`, `/i/render-alternatives`, `/i/fly-io-alternatives`, `/i/e2b-alternatives`, `/i/vercel-ai-gateway-vs-openrouter`, `/i/v0-vs-lovable` and `/i/v0-vs-cursor`. Checked: the two pages read for links; none. ¹⁴ Raises: Which of these hosting, sandbox and AI gateway comparisons a campaign will point at first. Disallowed from search: 10 prefixes in robots.txt, none campaign-shaped (`/api/`, `/oauth`, `/confirm`, `/notifications`, `/preauthorize`, `/signup?*`, `/invites/`, `/blog/authors`, `/changelog/authors`, `/old-browser.html`); never fetched. The engine reported no shared headline across landing pages. Searched `site:go.vercel.com` and `site:info.vercel.com`: no pages on either host returned.

**Since <date>**: First run; a second run opens with flips, new keys, new hosts and jobs since 2026-11-07.

**New subdomains**: 2026-07-31 `customerio.vercel.com` (my reading: a vendor host for a messaging tool, not a product surface). One name in 120 days from 1,825 certificates for the apex.

**Job signals**: 2026-11-03 Software Engineer, Agent Auth; 2026-11-03 Software Engineer, Connect; 2026-11-02 Software Engineer, Compute; 2026-10-21 Engineering Director, Vercel for Platforms; 2026-10-22 Member of Technical Staff, Financial Data; 2026-10-20 Product Manager, Storage; 2026-09-29 Product Manager, Software Factory; 2026-09-24 Software Engineer, Scheduled Tasks; 2026-09-17 Software Engineer, Agentic Infrastructure. ¹⁵ Raises: What Agent Auth and Software Factory name as products, since neither appears as a route in the code read.

**Announced, for calibration**: AI Gateway bring your own key routes `/[teamSlug]/~/ai-gateway/byok` and `/[teamSlug]/[project]/ai-gateway/byok` (announced (docs) https://vercel.com/docs/ai-gateway/byok); AI Gateway budgets route behind `enableAiGatewayBudgets` (announced 2026-07-31 https://vercel.com/changelog/ai-gateway-spend-budgets-and-alerts); Speed Insights routes and the new versus legacy switch (announced 2026-10-01 https://vercel.com/changelog/speed-insights-deprecates-first-input-delay-on-november-first); dashboard agent builder (announced 2026-08-28 https://vercel.com/changelog/build-and-deploy-eve-agents-from-the-vercel-dashboard); Vercel MCP `tool_call` and `oauth_event` (announced (docs) https://vercel.com/docs/agent-resources/vercel-mcp.md); Observability Plus enable and disable (announced 2026-10-28 https://vercel.com/changelog/agents-can-now-enable-web-analytics-and-observability-plus-with-vercel-cli); private registry login (announced 2026-09-30 https://vercel.com/changelog/vercel-agent-now-installs-private-packages-from-npm-and-custom-registries); expiring projects (announced 2026-11-06 https://vercel.com/changelog/vercel-cli-can-now-set-new-projects-to-expire); Schedules (announced 2026-11-04 https://vercel.com/blog/introducing-vercel-schedules). On the pricing page: "$20 /mo.", "$20 of included usage credit", "then $250 per additional project", "50K routed requests / month included", "$2 per 1M routed requests", "4 hours / month included". ¹⁶ The engine's `/api/ai-chat` match to 2026-10-08 https://vercel.com/changelog/openai-ultrafast-mode-now-available-on-ai-gateway reads as a keyword coincidence; the 2025-10-24 docs chat entry above is the apt source.

**Not read / set aside**: 50 of 110 enumerated scripts were not read (60-script cap), so routes and enums in lazy chunks may be missing. The docs index was llms.txt (28 pages); deeper docs pages were reached only by the web searches above. No runtime flag provider was detected, so no flag values were fetched at runtime. The identifier table `A` (461 analytics event descriptions) and the 149 `vercel_api` schemas were read by the engine, not line by line by me. The 217 codenames are mostly CSS colour names and pointer event fields (engine noise, no receipts quoted). 50 redactions and 9 demotions are counted in redactions.log and not reconstructed here.

**Coverage**:
- verdict: rich: every source read
- pages read 2 of 2
- first-party code 4,456,597 bytes in 60 scripts (enumerated 110; cap hit: yes)
- attribution: plan cdn_hosts: vercel.com, assets.vercel.com
- crt: ok (vercel.com: 170 names from 1825 certificates), 170 items
- ats: ok (board found on greenhouse as `vercel` (verified: name:Vercel, titles); 87 jobs), 87 items
- pricing: ok (https://vercel.com/pricing: 15255 chars, 67 amounts, 91 chip/amount lines), 91 items
- changelog: ok (https://vercel.com/atom: feed: 200 entries, newest 2026-11-07), 200 items
- scripts: capped (read 60 of 110 enumerated; cap 60 scripts / 120,000,000 bytes / 180 requests), 60 items
- redactions: 50; demoted to the key list: 9 (both in redactions.log)
- docs: ok (https://vercel.com/llms.txt: llms.txt: 28 pages in 1 file(s)), 28 items
- robots: ok (10 Disallow lines, 1 sitemap pointers), 10 items

**Receipts**: host https://vercel.com/_next/static/immutable/chunks/ (path prefix unless noted) · run folder ~/.local/share/unreleased/runs/vercel/2026-11-07T233556Z
¹ 0742ubyqhhmnz.js sha256:8e6fc6a7d5c4@14318 · 0742ubyqhhmnz.js sha256:8e6fc6a7d5c4@14437 · 0742ubyqhhmnz.js sha256:8e6fc6a7d5c4@14569
² 1miyeircwoekg.js sha256:9dcb78849293@27635 · 1miyeircwoekg.js sha256:9dcb78849293@28073 · 1miyeircwoekg.js sha256:9dcb78849293@27477
³ 1miyeircwoekg.js sha256:9dcb78849293@13310 · 1miyeircwoekg.js sha256:9dcb78849293@13411 · 1miyeircwoekg.js sha256:9dcb78849293@12801
⁴ https://vercel.com/ sha256:178b545ac0df@19048 · https://vercel.com/ sha256:178b545ac0df@19002 · https://vercel.com/ sha256:178b545ac0df@18962
⁵ 1miyeircwoekg.js sha256:9dcb78849293@39859 · 1mx5dd-8l73r0.js sha256:d3143fa92fba@31462 · 1miyeircwoekg.js sha256:9dcb78849293@42942
⁶ 1miyeircwoekg.js sha256:9dcb78849293@23930 · 1miyeircwoekg.js sha256:9dcb78849293@23072 · 1miyeircwoekg.js sha256:9dcb78849293@23162
⁷ 1mx5dd-8l73r0.js sha256:d3143fa92fba@26787 · 1mx5dd-8l73r0.js sha256:d3143fa92fba@26883 · 1mx5dd-8l73r0.js sha256:d3143fa92fba@25516
⁸ 1miyeircwoekg.js sha256:9dcb78849293@43245 · 1miyeircwoekg.js sha256:9dcb78849293@43471 · 1miyeircwoekg.js sha256:9dcb78849293@43954
⁹ 1miyeircwoekg.js sha256:9dcb78849293@38231 · 1miyeircwoekg.js sha256:9dcb78849293@38393 · 1miyeircwoekg.js sha256:9dcb78849293@38497
¹⁰ 1miyeircwoekg.js sha256:9dcb78849293@19546 · 1miyeircwoekg.js sha256:9dcb78849293@19607 · 1miyeircwoekg.js sha256:9dcb78849293@32739
¹¹ 0jg4c6f-ki3i4.js sha256:804cdb38e6bf@8799 · 0jg4c6f-ki3i4.js sha256:804cdb38e6bf@17162 · 0jg4c6f-ki3i4.js sha256:804cdb38e6bf@16486
¹² 1mx5dd-8l73r0.js sha256:d3143fa92fba@34921 · 1mx5dd-8l73r0.js sha256:d3143fa92fba@35118 · 1mx5dd-8l73r0.js sha256:d3143fa92fba@35387
¹³ 1miyeircwoekg.js sha256:9dcb78849293@40079 · 1miyeircwoekg.js sha256:9dcb78849293@39935 · 1miyeircwoekg.js sha256:9dcb78849293@40007
¹⁴ https://vercel.com/crawled-sitemap.xml sha256:2599c018836a@1271663 · https://vercel.com/crawled-sitemap.xml sha256:2599c018836a@1274571 · https://vercel.com/crawled-sitemap.xml sha256:2599c018836a@1278140
¹⁵ https://job-boards.greenhouse.io/vercel/jobs/6242246004 · https://job-boards.greenhouse.io/vercel/jobs/6242244004 · https://job-boards.greenhouse.io/vercel/jobs/6210353004 · https://job-boards.greenhouse.io/vercel/jobs/6207796004
¹⁶ https://vercel.com/pricing sha256(text):f88750d1dbd0

These are strings present in public code; a flag or route is evidence that something is being built, not that it will ship, and the reading of what a name refers to may be wrong. Every line links to the bytes it came from. Items marked announced are already public; the rest had no public mention found as of the run date in the sources listed.

```text
unreleased 0.1.0 · vercel · run 2026-11-07T233556Z · rich · findings 1311 · key-list 1854 · codenames 217 · redactions 50 · 78.1s
```
