import unittest
from helpers import *  # noqa: F401,F403
import noise, redact, crosscheck
from schema import Observation, Source


def ob(key, value=None, kind="gate", context="", offset=100, extractor="gatemap", confidence="high", sha="ab" * 32):
    return Observation(id="x-" + key, kind=kind, key=key, value=value, context=context, extractor=extractor, confidence=confidence,
                       source=Source(url="https://x.com/a.js", sha256=sha, offset=offset))


class Noise(unittest.TestCase):
    def test_sdk_detection_needs_an_init_call_not_a_name(self):
        v = noise.load_vendors()
        self.assertEqual(noise.detect_sdks('var a="statsig is great"; x.launchdarkly=1;', v), [])
        self.assertIn("Statsig", noise.detect_sdks('const c=new StatsigClient("client-abc",{});c.initializeAsync()', v))
        self.assertIn("PostHog", noise.detect_sdks('posthog.init("phc_123",{api_host:"https://us.i.posthog.com"})', v))
        self.assertNotIn("LaunchDarkly", noise.detect_sdks('foo.initialize(1)', v), "generic initialize without the marker is not LD")
        self.assertIn("LaunchDarkly", noise.detect_sdks('import*as LD from"launchdarkly-js-client-sdk";LD.initialize("x")', v))

    def test_tiers_drop_dom_props_sdk_methods_locale_tags_and_keyword_tables(self):
        obs = [ob("data-sonner-toaster", True, kind="inline"), ob("enable-background"), ob("getFeatureFlag", kind="call"), ob("ff-Adlm-BF"),
               ob("beta_binomial_lpmf"), ob("includes", kind="call"), ob("/dev/tty", kind="route"), ob("uuid-v4"),
               ob("make_local_native_ios_preview", False, context='"Local Agent Flow Download Modal"'),
               ob("campfire", True), ob("sprig_enabled", True)]
        tiers = {o.key: o.tier for o in noise.assign_tiers(obs, bodies={"ab" * 32: "x" * 1000})}
        for dropped in ("data-sonner-toaster", "enable-background", "getFeatureFlag", "ff-Adlm-BF", "beta_binomial_lpmf", "includes", "/dev/tty", "uuid-v4"):
            self.assertNotIn(dropped, tiers, dropped)
        self.assertEqual(tiers["make_local_native_ios_preview"], "finding")
        self.assertEqual(tiers["campfire"], "codename")
        self.assertEqual(tiers["sprig_enabled"], "key-list", "an entitlement/vendor toggle with no feature noun is key-list")

    def test_observations_inside_vendor_code_are_dropped(self):
        body = 'x={my_real_feature_flag:!1,label:"My Real Feature"};' + "a" * 2000 + 'Sentry.init({_experiments:{traceInternals:!0,captureExceptions:!1}})' + "b" * 200
        obs = [ob("traceInternals", True, offset=body.find("traceInternals")), ob("my_real_feature_flag", False, offset=3, context='"My Real Feature"')]
        tiers = {o.key: o.tier for o in noise.assign_tiers(obs, bodies={"ab" * 32: body})}
        self.assertNotIn("traceInternals", tiers)
        self.assertIn("my_real_feature_flag", tiers)

    def test_vendor_markers_inside_a_first_party_map_do_not_wipe_its_neighbours(self):
        # Figma's dynamic_configs: "datadog_rum_site":"datadoghq.com" sits 300 bytes from announce_agent_weave_ga_date;
        # Figma's gate ce_al_experiments_on contains Sentry's `_experiments` marker as a substring
        body = '{"ce_al_experiments_on":true,"ff_ai_credit_requests":true,"datadog_rum_site":"datadoghq.com","announce_agent_weave_ga_date":{"date":"2026-10-06"}}'
        obs = [ob("ff_ai_credit_requests", True, offset=body.find("ff_ai_credit_requests")), ob("announce_agent_weave_ga_date", "{...}", kind="config", offset=body.find("announce_agent"))]
        for o in obs: o.group = "feature_flags"
        tiers = {o.key: o.tier for o in noise.assign_tiers(obs, bodies={"ab" * 32: body})}
        self.assertEqual(set(tiers), {"ff_ai_credit_requests", "announce_agent_weave_ga_date"})
        spans = noise.vendor_spans(body, noise.load_vendors())
        self.assertFalse(any(n == "sentry" for _, _, n in spans), spans)

    def test_a_vendor_table_inside_a_parsed_map_is_still_the_vendors(self):
        # Cursor's marketing bundle: gt-next's warning enum and hls.js's key-system registry topped the brief
        obs = [ob("APIKeyMissingWarn", 1, kind="enum", context="r.typesFileError = gt-next Error: There is no scenario", offset=5),
               ob("keySystemNoAccess", None, kind="registry", context="ub.KEY_SYSTEM_NO_ACCESS", offset=50),
               ob("ai_credits_plan_add_on", True, context="feature_flags", offset=90)]
        for o in obs: o.group = "r"
        tiers = {o.key: o.tier for o in noise.assign_tiers(obs, bodies={"ab" * 32: "x" * 200})}
        self.assertEqual(set(tiers), {"ai_credits_plan_add_on"})

    def test_a_flag_hosting_sdk_marker_in_context_keeps_the_products_own_flags(self):
        # PostHog's own registry sits in posthog-js's `persisted_feature_flags`; vercel's in flags-sdk — the marker
        # rule above dropped 800 PostHog keys (corpus recall 1.0 -> 0.357) until these SDKs were exempted
        obs = [ob("session-risk-detection", False, context="persisted_feature_flags", offset=5),
               ob("project-bluebird", False, context="__posthog.featureFlags", offset=40)]
        for o in obs: o.group = "flags"
        tiers = {o.key: o.tier for o in noise.assign_tiers(obs, bodies={"ab" * 32: "x" * 200})}
        self.assertEqual(set(tiers), {"session-risk-detection", "project-bluebird"})

    def test_low_confidence_pattern_matches_never_become_findings(self):
        o = ob("some_thing_enabled", None, extractor="strings", confidence="low", context="beta")
        tiers = {x.key: x.tier for x in noise.assign_tiers([o], bodies={})}
        self.assertIn(tiers.get("some_thing_enabled"), ("key-list", "codename"))


class Redact(unittest.TestCase):
    def test_secrets_and_ids_are_removed_and_logged_without_values(self):
        obs = [ob("statsig_figma_app_client_api_key", "client-" + "A" * 40, kind="config"), ob("acmeOrgs", "[123456,234567]", kind="config"),
               ob("cortex_single_tenant", "{}", kind="config", context="acmeOrgs:[123456,234567]"), ob("bobs_specials", True), ob("alices_specials", True),
               ob("normal_feature_gate", False, context="Normal Feature")]
        kept, log = redact.redact(obs, "figma.com")
        keys = {o.key for o in kept}
        self.assertNotIn("statsig_figma_app_client_api_key", keys); self.assertNotIn("acmeOrgs", keys); self.assertNotIn("cortex_single_tenant", keys)
        self.assertNotIn("bobs_specials", keys); self.assertNotIn("alices_specials", keys)
        self.assertIn("normal_feature_gate", keys)
        self.assertTrue(log and all("client-A" not in line and "123456" not in line for line in log))
        self.assertTrue(all("bobs_specials" not in line and "acmeOrgs" not in line for line in log), log)   # the key is the customer's name

    def test_secrets_next_to_any_key_are_scrubbed_from_context_and_values(self):
        # review B1: a call site's context window carried a live key; a route's value carried one
        sk = "sk_" + "live_" + "0Example0Example0Example00"      # built at runtime: no scanner-shaped literal in the repo
        obs = [ob("ai_credit_plans", None, kind="call", context=f'checkGate({{gateName:"ai_credit_plans"}});const k="{sk}";', extractor="calls"),
               ob("/billing/invoices", None, kind="route", extractor="routes", context=f'apiKey:"{sk}",a:"/billing/invoices"'),
               ob("netflix_dedicated_cluster_enabled", True), ob("enterprise_org_id", "123456789", kind="config")]
        kept, log = redact.redact(obs, "acme.com")
        self.assertEqual({o.key for o in kept}, {"ai_credit_plans", "/billing/invoices"}, log)
        for o in kept:
            self.assertNotIn(sk, o.context or ""); self.assertNotIn(sk, str(o.value))
        self.assertTrue(all("netflix" not in l for l in log), log)
        # integrations and model names are the product's own work, not a customer's arrangement
        obs = [ob("login_google_sso", False), ob("anthropic-claude-5.5-opus", 1, kind="enum"), ob("stripe_checkout_v2", True), ob("apple_custom_fonts", False)]
        kept, log = redact.redact(obs, "figma.com")
        self.assertEqual([o.key for o in kept], ["login_google_sso", "anthropic-claude-5.5-opus", "stripe_checkout_v2"], log)

    def test_common_token_formats_are_secrets(self):
        """GitHub, Google API, Anthropic, OpenAI project, GitLab, npm and Stripe restricted keys passed
        redaction. Each literal is assembled at runtime so the repo itself holds no scanner-shaped token."""
        tail = "Ab12" * 10
        tokens = ["gh" + "p_" + tail[:36], "github" + "_pat_" + (tail * 2)[:82], "AI" + "za" + tail[:35], "sk-" + "ant-api03-" + tail,
                  "sk-" + "proj-" + tail, "gl" + "pat-" + tail[:20], "np" + "m_" + tail[:36], "rk_" + "live_" + tail[:24]]
        for t in tokens:
            obs = [ob("feature_x", None, kind="call", context=f'gate("feature_x");const k="{t}";', extractor="calls"),
                   ob("api_config", t, kind="config")]
            kept, log = redact.redact(obs, "acme.com")
            self.assertEqual([o.key for o in kept], ["feature_x"], (t[:8], log))
            self.assertNotIn(t, kept[0].context or "", t[:8])
            self.assertTrue(all(t not in line for line in log))
        # words that merely start like a prefix are not tokens
        kept, _ = redact.redact([ob("npm_install_banner", True), ob("ghp_like_name", False),
                                 ob("nav", None, kind="call", context='class="sk-proj-header-navigation-item glpat-settings-panel-toggle"', extractor="calls"),
                                 ob("docs", "github_pat_placeholder_for_docs_here", kind="config")], "acme.com")
        self.assertEqual(len(kept), 4)
        self.assertIn("sk-proj-header-navigation-item", kept[2].context)      # a kebab-case class name is not a key

    def test_feature_gates_that_mention_password_org_or_allowlist_are_kept(self):
        obs = [ob("password", False), ob("code_layers_open_beta_allowlist", False), ob("tanstack_router_org_admin_billing", True), ob("get_mcp_token", False, context="MCP token modal")]
        kept, log = redact.redact(obs, "figma.com")
        self.assertEqual(len(kept), 4, log)

    def test_a_redacted_gate_is_scrubbed_from_its_neighbours_context(self):
        obs = [ob("alices_specials", True, kind="call"), ob("ai_image_generation", None, kind="call", context='checkGate({gateName:"ai_image_generation"}),a=checkGate({gateName:"alices_specials"})')]
        kept, log = redact.redact(obs, "notion.so")
        self.assertEqual([o.key for o in kept], ["ai_image_generation"])
        self.assertNotIn("alices_specials", kept[0].context); self.assertIn("[redacted]", kept[0].context)

    def test_labels_and_quotas_are_not_secrets_or_ids(self):
        # Figma: an enum whose value is a human label, and configs whose values are quotas, were redacted
        obs = [ob("check_email_magic_link_sign_in_after_password", "Check Email Magic Link Sign In After Password", kind="enum"),
               ob("ai_metering_quotas_with_seat_type", '{"full":100000,"window":86400}', kind="config"),
               ob("statsig_client_sdk_key", "client-" + "k" * 40, kind="config"), ob("acmeOrgs", "[1234567890,2345678901]", kind="config")]
        kept, log = redact.redact(obs, "figma.com")
        self.assertEqual({o.key for o in kept}, {"check_email_magic_link_sign_in_after_password", "ai_metering_quotas_with_seat_type"}, log)

    def test_token_shaped_and_identifier_keys_are_removed(self):
        # Linear's app bundle: a Salesforce consumer key, a Google OAuth client id, Stripe price ids and a UUID as map keys
        obs = [ob("3MVGQ0x9SyNthEtiCQ0x9SyNthEtiCQ0x9SyNthEtiCQ0x9SyNthEtiCQ0x9SyNthEtiCQ0x9SyNthEtiCQ0x", True, kind="registry"),
               ob("123456789012-abcdefghijklmnopqrstuvwxyz012345.apps.googleusercontent.com", True, kind="registry"),
               ob("price_1Exampl3SynthEtic0000x", "pro", kind="registry"), ob("2019c0de-aaaa-483a-9243-d2b86ea22048", 1, kind="enum"),
               ob("mobile_diffs_waitlist_enabled", False), ob("AI_GATEWAY_API_KEY_CREATED", 1, kind="enum")]
        kept, log = redact.redact(obs, "linear.app")
        self.assertEqual([o.key for o in kept], ["mobile_diffs_waitlist_enabled", "AI_GATEWAY_API_KEY_CREATED"], log)

    def test_diff_lists_are_redacted_too(self):
        from schema import Diff
        d = Diff(since_run="r1", added=["mobile_diffs", "price_1Exampl3SynthEtic0000x"], removed=["3MVGQ0x9SyNthEtiCQ0x9SyNthEtiCQ0x9SyNthEtiCQ0x9SyNthEtiCQ0x9SyNthEtiCQ0x9SyNthEtiCQ0x"],
                 flipped=[{"key": "bobs_specials", "from": False, "to": True}, {"key": "ai_agent_waitlist", "from": False, "to": True}])
        self.assertEqual(redact.redact_diff(d), 3)
        self.assertEqual((d.added, d.removed, [x["key"] for x in d.flipped]), (["mobile_diffs"], [], ["ai_agent_waitlist"]))

    def test_webpack_module_ids_in_context_are_not_customer_ids(self):
        # Notion: i(218744).default.checkGate({gateName:"custom_blocks"})&&(0,i(216260).y4)() — two 6-digit numbers, zero ids
        obs = [ob("custom_blocks", None, kind="call", context='i(218744).default.checkGate({gateName:"custom_blocks"})&&(0,i(216260).y4)()', extractor="calls")]
        kept, log = redact.redact(obs, "notion.so")
        self.assertEqual([o.key for o in kept], ["custom_blocks"], log)

    def test_ab_arms_and_internal_tooling_are_demoted_not_removed(self):
        obs = [ob("half-price", kind="catalog"), ob("first-month-one", kind="catalog"), ob("pro0-price-test-a", kind="catalog"), ob("pro0-price-test-b", kind="catalog"),
               ob("admin_app_panel_migration_config", kind="config"), ob("cofounder", kind="catalog", context="team: app-success")]
        for o in obs: o.tier = "finding"
        kept, _ = redact.redact(obs, "lovable.dev")
        t = {o.key: o.tier for o in kept}
        self.assertEqual(t["half-price"], "key-list"); self.assertEqual(t["pro0-price-test-b"], "key-list"); self.assertEqual(t["admin_app_panel_migration_config"], "key-list")
        self.assertNotEqual(t["cofounder"], "key-list")

    def test_company_label_anywhere_below_the_apex_is_withheld(self):
        from schema import Subdomain
        subs = [Subdomain("errors.apple.acme-design.com", "2026-09-15", "errors", "", "acme-design.com"), Subdomain("weave.staging.acme-design.com", "2026-09-14", "weave", "staging", "acme-design.com"),
                Subdomain("apple.acme-design.com", "2026-09-15", "apple", "", "acme-design.com"), Subdomain("target.staging.acme-design.com", "2026-09-15", "target", "staging", "acme-design.com")]
        kept, flagged = redact.redact_subdomains(subs)
        self.assertEqual([s.name for s in kept], ["weave.staging.acme-design.com"]); self.assertEqual(len(flagged), 3)

    def test_customer_named_hosts_are_demoted(self):
        from schema import Subdomain
        subs = [Subdomain("apple.acme-design.com", "2026-09-15"), Subdomain("weave.staging.acme-design.com", "2026-09-14")]
        kept, flagged = redact.redact_subdomains(subs)
        self.assertEqual([s.name for s in kept], ["weave.staging.acme-design.com"])
        self.assertEqual(flagged, ["apple.acme-design.com"])


class Crosscheck(unittest.TestCase):
    def test_pricing_text_marks_partial_and_changelog_marks_announced(self):
        obs = [ob("figjam_code_layers", False), ob("ff_full_seat_plans", False), ob("enable_agora_transcriptions", False), ob("zzz_unknown_thing", False)]
        pricing = "Plans. Full seat plans are available on Organization. Code layers in Design. $15 per editor."
        changelog = [{"date": "2026-06-24", "title": "Code layers come to Design", "url": "https://x.com/changelog/code-layers", "text": "Code layers let you..."},
                     {"date": "2026-10-06", "title": "The Figma agent is generally available", "url": "https://x.com/changelog/agent", "text": ""}]
        checks = {c.observation_id: c for c in crosscheck.check(obs, pricing, changelog, pricing_url="https://x.com/pricing")}
        self.assertEqual(checks["x-ff_full_seat_plans"].status, "partial")
        self.assertEqual(checks["x-ff_full_seat_plans"].url, "https://x.com/pricing")
        self.assertEqual(checks["x-figjam_code_layers"].status, "partial", "code layers is announced for Design, the FigJam key only partially matches")
        self.assertEqual(checks["x-zzz_unknown_thing"].status, "none")
        self.assertIn("pricing-text", checks["x-zzz_unknown_thing"].searched)

    def test_exact_title_match_is_announced(self):
        obs = [ob("agent_weave_ga", True, context="announce_agent_weave_ga_date")]
        changelog = [{"date": "2026-10-06", "title": "Agent and Weave tools are generally available", "url": "https://x.com/c/agent-weave", "text": "agent weave ga"}]
        c = crosscheck.check(obs, "", changelog)[0]
        self.assertEqual((c.status, c.date), ("announced", "2026-10-06"))

    def test_words_match_as_words_not_substrings(self):
        # Vercel: `/api/ai-chat` was "announced" by "OpenAI ultrafast mode now available on AI Gateway" ("ai" inside
        # "openai" and "available", "api" inside "rapid"); `orb_billing.v0.invoice` by a marketplace post
        obs = [ob("/api/ai-chat", kind="route"), ob("orb_billing.v0.invoice", True)]
        changelog = [{"date": "2026-10-08", "title": "OpenAI ultrafast mode now available on AI Gateway", "url": "https://x.com/c/ultra",
                      "text": "Rapid responses are available for OpenAI models through the gateway."},
                     {"date": "2026-09-16", "title": "Mem0 joins the marketplace", "url": "https://x.com/c/mem0",
                      "text": "Billing is unified: one invoice covers every marketplace product."}]
        checks = {c.observation_id: c for c in crosscheck.check(obs, "", changelog)}
        self.assertEqual(checks["x-/api/ai-chat"].status, "none")
        self.assertNotEqual(checks["x-orb_billing.v0.invoice"].status, "announced", "two generic body words are not an announcement")

    def test_common_feed_words_carry_no_weight_and_titles_decide_announced(self):
        # a 200-entry feed where every entry says "ai", "agent" and "gateway": those words cannot match anything;
        # announced needs a distinctive word in the entry's title
        feed = [{"date": f"2026-10-{i % 28 + 1:02d}", "title": f"Model {i} now available on AI Gateway", "url": f"https://x.com/c/{i}",
                 "text": "The AI Gateway agent can route requests to this model."} for i in range(40)]
        feed.append({"date": "2026-11-01", "title": "Secure compute configurations are generally available", "url": "https://x.com/c/secure",
                     "text": "Create a secure compute configuration for static IP builds."})
        feed.append({"date": "2026-11-02", "title": "Faster builds for everyone", "url": "https://x.com/c/builds",
                     "text": "Internal components and shared libraries now build faster on every plan."})
        obs = [ob("AI_GATEWAY_API_KEY_CREATED"), ob("secure_compute_configuration_created"), ob("/internal/components", kind="route")]
        checks = {c.observation_id: c for c in crosscheck.check(obs, "", feed)}
        self.assertEqual(checks["x-AI_GATEWAY_API_KEY_CREATED"].status, "none", "ai, gateway: common on this feed; key, created: nowhere")
        self.assertEqual((checks["x-secure_compute_configuration_created"].status, checks["x-secure_compute_configuration_created"].url),
                         ("announced", "https://x.com/c/secure"))
        self.assertEqual(checks["x-/internal/components"].status, "partial", "both words in one body passage but not in the title: a lead, not an announcement")

    def test_web_queries_are_bounded_and_named(self):
        names = ["alpha", "beta", "gamma", "delta", "eps", "zeta", "eta"]
        obs = [ob(f"{names[i % 7]}_{names[(i * 3) % 7]}_thing_{i}", False, context=f"Feature {i}") for i in range(20)]
        for o in obs: o.tier = "finding"
        q = crosscheck.web_queries(obs, "figma", top_n=6)
        self.assertEqual(len(q), 6); self.assertTrue(all("figma" in s for s in q))
        # siblings share one query: ai_credit_usage_* is one question, not six
        sib = [ob(f"ai_credit_usage_{w}", False) for w in ("code", "figjam", "make", "weave")] + [ob("make_local_ai_gateway", False)]
        for o in sib: o.tier = "finding"
        self.assertEqual(len(crosscheck.web_queries(sib, "figma", top_n=6)), 2)


if __name__ == "__main__":
    unittest.main()
