"""S1 seam: routes.extract(body, artifact) finds the readers' route-table keys from corpus excerpts.

Expected values come from tests/goldens/<product>.json (the readers' hand findings), never from the code.
"""
import unittest
from helpers import fixture, fixture_meta, golden  # sets sys.path
from schema import Source
from extractors import routes


def _artifact(shape, name):
    meta = fixture_meta(shape, name)
    return Source(url=meta["url"] or "https://example.invalid/" + name, sha256=meta["sha256_full"], offset=-1)


def _run(name):
    body = fixture("routes", name)
    return body, routes.extract(body, _artifact("routes", name))


class VercelRouteTable(unittest.TestCase):
    """Next.js-style `{ "/path": { label, group, flag, aliases } }` table; the `flag:` names are the goldens."""

    @classmethod
    def setUpClass(cls):
        cls.body, cls.obs = _run("vercel-1.js")
        cls.keys = {o.key: o for o in cls.obs}

    def test_golden_flag_names_are_found_as_route_flags(self):
        want = golden("vercel")["expect"]["route"]
        missing = [k for k in want if k not in self.keys]
        self.assertEqual(missing, [], f"missing {missing}")
        for k in want:
            o = self.keys[k]
            self.assertEqual(o.kind, "route")
            self.assertEqual(o.group, "route-flag")
            self.assertEqual(o.extractor, "routes")
            self.assertEqual(o.confidence, "high")

    def test_flag_observation_carries_label_and_group_as_context(self):
        o = self.keys["enablePrivateInference"]
        self.assertIn("Private Models", o.context)
        self.assertIn("AI Gateway", o.context)
        self.assertIsNone(o.value)

    def test_path_key_is_emitted_with_its_label_and_flag(self):
        o = self.keys["/[teamSlug]/~/ai-gateway/private-inference"]
        self.assertEqual(o.kind, "route")
        self.assertIn("Private Models", o.context)
        self.assertIn("enablePrivateInference", o.context)
        self.assertEqual(o.group, "AI Gateway")
        self.assertEqual(o.confidence, "high")

    def test_receipt_offset_points_at_the_key_in_the_body(self):
        o = self.keys["/[teamSlug]/~/ai-gateway/private-inference"]
        self.assertEqual(self.body[o.source.offset:o.source.offset + len(o.key)], o.key)
        f = self.keys["enablePrivateInference"]
        self.assertEqual(self.body[f.source.offset:f.source.offset + len(f.key)], f.key)

    def test_reader_named_noise_is_absent(self):
        for n in golden("vercel")["noise"]:
            self.assertNotIn(n, self.keys)

    def test_context_is_bounded(self):
        for o in self.obs:
            self.assertLessEqual(len(o.context), 200)


class ReplitTypedRouteTable(unittest.TestCase):
    """Typed table `name:(0,a.pageRoute)({path:{tanstack:"/x",express:"/x"},screen:"…",source:"pages/x.page.tsx"})`:
    both the path and the page source are keys; `missingPageRoute` is carried as context."""

    @classmethod
    def setUpClass(cls):
        cls.body, cls.obs = _run("replit-1.js")
        cls.keys = {o.key: o for o in cls.obs}

    def test_golden_paths_and_page_sources_are_found(self):
        want = golden("replit")["expect"]["route"]
        missing = [k for k in want if k not in self.keys]
        self.assertEqual(missing, [], f"missing {missing}")
        for k in want:
            self.assertEqual(self.keys[k].confidence, "high")

    def test_missing_page_route_wrapper_is_context(self):
        o = self.keys["/evaluations"]
        self.assertIn("missingPageRoute", o.context)
        self.assertIn("missingEvaluations", o.context)

    def test_page_source_context_names_the_route(self):
        o = self.keys["pages/metric-observatory.page.tsx"]
        self.assertIn("/metric-observatory", o.context)
        self.assertEqual(self.body[o.source.offset:o.source.offset + len(o.key)], o.key)

    def test_reader_named_noise_is_absent(self):
        for n in golden("replit")["noise"]:
            self.assertNotIn(n, self.keys)


class DiscordRoutesAndConstants(unittest.TestCase):
    """`Routes` object: `UPPER:"/path"` pairs emit the path (constant as context) and the constant; route
    builders `UPPER:e=>`/x/${e}`` emit the constant with the template path; SKU/settings-tab enums
    `(c={}).UPPER="…"` emit the constant with its value (medium confidence)."""

    @classmethod
    def setUpClass(cls):
        cls.body, cls.obs = _run("discord-1.js")
        cls.keys = {o.key: o for o in cls.obs}

    def test_golden_paths_and_constants_are_found(self):
        want = golden("discord")["expect"]["route"]
        missing = [k for k in want if k not in self.keys]
        self.assertEqual(missing, [], f"missing {missing}")

    def test_path_pair_carries_constant_name_and_constant_carries_path(self):
        self.assertEqual(self.keys["/conjure"].context, "CONJURE")
        self.assertEqual(self.keys["/conjure"].confidence, "high")
        self.assertEqual(self.keys["MESSAGE_REQUESTS"].value, "/message-requests")
        self.assertEqual(self.keys["MESSAGE_REQUESTS"].confidence, "medium")

    def test_route_builder_constant_carries_template_path(self):
        self.assertIn("/quest-preview/", self.keys["QUEST_PREVIEW"].context)
        self.assertIn("/game-sho", self.keys["GAME_SHOP"].context)

    def test_enum_chain_constants_carry_values_and_prefix_group(self):
        o = self.keys["PREMIUM_TIER_2_1_HOUR"]
        self.assertEqual(o.value, "1271583180566036480")
        self.assertEqual(o.group, "PREMIUM_TIER_2")
        self.assertEqual(self.keys["GUILD_OFFICIAL_MESSAGES"].value, "official-messages")
        self.assertEqual(self.body[o.source.offset:o.source.offset + len(o.key)], o.key)

    def test_reader_named_noise_is_absent(self):
        for n in golden("discord")["noise"]:
            self.assertNotIn(n, self.keys)


class SupabaseTanStackTree(unittest.TestCase):
    """TanStack route tree: ``C(`/project/$ref/settings/webhooks/$endpointId`)({…staticData:{settingsLayoutTitle:`…`}})``."""

    @classmethod
    def setUpClass(cls):
        cls.body, cls.obs = _run("supabase-1.js")
        cls.keys = {o.key: o for o in cls.obs}

    def test_webhook_routes_are_found_with_layout_title_and_chunk_as_context(self):
        for p in ("/project/$ref/settings/webhooks/", "/project/$ref/settings/webhooks/$endpointId"):
            self.assertIn(p, self.keys, p)
            o = self.keys[p]
            self.assertEqual(o.confidence, "high")
            self.assertEqual(o.group, "project")
            self.assertEqual(self.body[o.source.offset:o.source.offset + len(p)], p)
        self.assertIn("Webhooks", self.keys["/project/$ref/settings/webhooks/"].context)
        self.assertIn("chunk=webhooks", self.keys["/project/$ref/settings/webhooks/"].context)
        self.assertIn("chunk=_endpointId", self.keys["/project/$ref/settings/webhooks/$endpointId"].context)

    def test_reader_named_noise_is_absent(self):
        for n in golden("supabase")["noise"]:
            self.assertNotIn(n, self.keys)


class RouteTableExcerpts(unittest.TestCase):
    """Excerpts of tables too large to commit whole: the outer object is not balanced in the fixture, so the
    pairs are read as runs. Golden keys are exact observation keys unless noted."""

    def _check(self, product, name, confidence=None):
        body, obs = _run(name)
        keys = {o.key: o for o in obs}
        want = golden(product)["expect"]["route"]
        # the scorecard's rule: the golden literal is the key, or a substring of it (the readers quoted the
        # distinctive tail of a longer path, e.g. `/configuration/ai-enablement` of `/projects/:name/…`)
        found = {g: (keys.get(g) or next((o for k, o in keys.items() if g in k), None)) for g in want}
        missing = [g for g, o in found.items() if o is None]
        self.assertEqual(missing, [], f"{product}: missing {missing}")
        for g, o in found.items():
            self.assertEqual(body[o.source.offset:o.source.offset + len(o.key)], o.key, f"{product}: receipt for {g}")
            if confidence:
                self.assertEqual(o.confidence, confidence, f"{product}: {g}")
        for n in golden(product)["noise"]:
            self.assertNotIn(n, keys)
        return keys

    def test_netlify_upper_path_map(self):
        keys = self._check("netlify", "netlify-1.js", "high")
        self.assertEqual(keys["/edge-access"].context, "EDGE_ACCESS")
        self.assertIn("SITES_CONFIGURATON_AI_ENABLEMENT", keys["/projects/:name/configuration/ai-enablement"].context)

    def test_posthog_scene_routes(self):
        keys = self._check("posthog", "posthog-1.js", "high")
        self.assertIn("engineeringAnalyticsPullRequestList", keys["/engineering-analytics/pull-requests"].context)
        self.assertIn("DecisionPlayground", keys["/ml-inference/playground"].context)

    def test_lovable_camel_path_map(self):
        keys = self._check("lovable", "lovable-1.js", "high")
        self.assertEqual(keys["/chats/cofounder"].context, "cofounderChat")
        self.assertEqual(keys["/goblin"].context, "goblinMode")

    def test_linear_rewrite_entries(self):
        keys = self._check("linear", "linear-1.js", "high")
        self.assertIn("/mobile-diffs/success", keys["/mobile-diffs"].context)

    def test_huggingface_nav_objects_and_html_hrefs(self):
        body1, obs1 = _run("huggingface-1.js")
        k1 = {o.key: o for o in obs1}
        self.assertIn("New Kernel", k1["/new-kernel"].context)
        self.assertEqual(k1["/new-kernel"].confidence, "high")
        body2, obs2 = _run("huggingface-2.js")
        k2 = {o.key: o for o in obs2}
        self.assertIn("New Container image", k2["/new-container"].context)
        self.assertEqual(k2["/new-container"].confidence, "medium")
        want = golden("huggingface")["expect"]["route"]
        self.assertEqual([g for g in want if g not in (k1 | k2)], [])

    def test_notion_marketing_path_map(self):
        keys = self._check("notion", "notion-1.js", "high")
        self.assertEqual(keys["/product/aimn-v2"].context, "aimnv2")

    def test_spotify_page_id_enum(self):
        # `o.MARTINI_CHAT="martini/chat"`: a 1,095-entry page-id enum; the ids are routes, confidence medium
        keys = self._check("spotify", "spotify-1.js", "medium")
        self.assertEqual(keys["martini/chat"].context, "MARTINI_CHAT")
        self.assertEqual(keys["martini/chat"].group, "martini")
        self.assertEqual(keys["kid-account-selection"].group, "kid-account-selection")

    def test_asana_html_href(self):
        keys = self._check("asana", "asana-1.html", "medium")
        self.assertIn("AI Teammates", keys["/product/ai/ai-teammates"].context)

    def test_retool_static_route_entries(self):
        keys = self._check("retool", "retool-1.js", "high")

    def test_dropbox_bare_literal_fallback(self):
        keys = self._check("dropbox", "dropbox-1.js", "low")
        self.assertIn("includes", keys["/waitlist/dash-for-teams"].context)

    def test_stripe_route_groups(self):
        # `$("name","/base",{SUB:"/x"})` groups; the sub-paths are composed onto the base. The reader's
        # `/agentic-commerce/agents` is the tail of `SETTINGS_CONNECT_AGENTIC_COMMERCE_AGENTS:"/connect/agentic-commerce/agents"`.
        body1, obs1 = _run("stripe-1.js")
        keys1 = {o.key: o for o in obs1}
        self.assertEqual(keys1["/metronome-login"].context, "metronomeLogin")
        self.assertEqual(keys1["/metronome-login"].confidence, "high")
        body2, obs2 = _run("stripe-2.js")
        keys2 = {o.key: o for o in obs2}
        self.assertEqual(keys2["/accounting"].context, "revenueStarter")
        self.assertIn("/accounting/statements", keys2)
        self.assertIn("REVENUE_STARTER_STATEMENTS", keys2["/accounting/statements"].context)
        self.assertTrue(any("/agentic-commerce/agents" in k for k in keys2), "agentic-commerce agents route")
        want = golden("stripe")["expect"]["route"]
        found = keys1 | keys2
        missing = [g for g in want if not any(g == k or g in k for k in found)]
        self.assertEqual(missing, [])
        for n in golden("stripe")["noise"]:
            self.assertNotIn(n, found)


if __name__ == "__main__":
    unittest.main()
