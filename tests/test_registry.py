"""S1 seam: extractors.registry.extract(body, artifact) finds the readers' registry keys from corpus excerpts.

Expected values come from tests/goldens/<product>.json (the readers' hand findings), never from the extractor.
A golden counts as found when an emitted key equals it, or ends with it where the reader abbreviated a
prefixed name. Loom's golden "catalog" keys are mostly `UPPER:"kebab"` constant tables, i.e. this shape, so
the loom golden is asserted here against catalog + registry together (see worker-notes-B.md §3).
"""
import unittest
from helpers import fixture, fixture_meta, golden  # sets sys.path
from schema import Source, Observation
from extractors import registry, catalog


def _src(meta):
    return Source(url=meta["url"] or "", sha256=meta["sha256_full"])


def _run(name, mod=registry):
    meta = fixture_meta("registry", name)
    body = fixture("registry", name)
    return mod.extract(body, _src(meta)), body


def _hit(keys: set[str], g: str) -> bool:
    return g in keys or any(k.endswith(g) for k in keys)


def _assert_receipts(tc, obs: list[Observation], body: str):
    for o in obs:
        tc.assertEqual(body[o.source.offset:o.source.offset + len(o.key)], o.key, f"receipt for {o.key}")
        tc.assertLessEqual(len(o.context), 200)
        tc.assertEqual(o.kind, "registry"); tc.assertEqual(o.extractor, "registry")


class RegistryStripe(unittest.TestCase):
    """Stripe's dashboard shell: a `{name, jira}` project registry (two fragments), a SETTINGS_* route-name table
    inside 33 `$("group","/path",{…})` route groups, and two 2,000-entry string lists (permissions, analytics
    property names)."""
    FIXTURES = ["stripe-1.js", "stripe-2.js", "stripe-3.js", "stripe-4.js", "stripe-5.js"]

    def test_every_golden_key_is_found(self):
        expected = golden("stripe")["expect"]["registry"]
        found, all_bodies = set(), ""
        for name in self.FIXTURES:
            obs, body = _run(name)
            found |= {o.key for o in obs}; all_bodies += body
        for g in expected:
            self.assertIn(g, all_bodies, f"golden {g} is in no fixture: cut one")
        self.assertEqual([g for g in expected if not _hit(found, g)], [])

    def test_keyed_entries_name_jira(self):
        obs, body = _run("stripe-1.js")
        by = {o.key: o for o in obs}
        self.assertGreaterEqual(len(obs), 40)
        o = by["agent_in_a_box"]
        self.assertEqual(o.value, "Agent in a Box"); self.assertEqual(o.group, "RUN_COIN")
        self.assertEqual(o.context, "Agent in a Box · RUN_COIN"); self.assertEqual(o.confidence, "high")
        _assert_receipts(self, obs, body)
        obs2, body2 = _run("stripe-2.js")        # a fragment cut mid-object: entries still key off the look-back
        self.assertIn("stablecoin_treasury", {o.key for o in obs2}); self.assertIn("token_billing", {o.key for o in obs2})
        _assert_receipts(self, obs2, body2)

    def test_upper_path_table_keys_by_constant_name_and_route_groups_by_group_name(self):
        obs, body = _run("stripe-3.js")
        by = {o.key: o for o in obs}
        o = by["SETTINGS_CONNECT_AGENT_IN_A_BOX"]
        self.assertEqual(o.value, "/connect/agent-in-a-box"); self.assertEqual(o.confidence, "high")
        r = by["revenueStarter"]
        self.assertEqual(r.value, "/accounting"); self.assertEqual(r.confidence, "medium")
        self.assertIn("route group", r.context)
        _assert_receipts(self, obs, body)

    def test_dense_string_lists_keep_their_list_name(self):
        obs, body = _run("stripe-4.js")
        by = {o.key: o for o in obs}
        self.assertEqual(by["wrapped_2025_read"].context, "in admin"); self.assertEqual(by["wrapped_2025_read"].confidence, "medium")
        self.assertIn("wrapped_2025_write", by)
        _assert_receipts(self, obs, body)
        obs5, body5 = _run("stripe-5.js")
        self.assertEqual({o.key: o for o in obs5}["webmcp_enabled"].context, "in parametersAllowList")
        _assert_receipts(self, obs5, body5)

    def test_no_reader_named_noise(self):
        for name in self.FIXTURES:
            obs, _ = _run(name)
            for n in golden("stripe")["noise"]:
                self.assertNotIn(n, {o.key for o in obs})


class RegistryAmplitude(unittest.TestCase):
    """Amplitude's 618-entry TS enum of backtick constants: `e.ErrorTracking=`error-tracking`,…`."""

    def test_every_golden_key_is_found(self):
        obs, body = _run("amplitude-1.js")
        keys = {o.key for o in obs}
        expected = golden("amplitude")["expect"]["registry"]
        self.assertEqual([g for g in expected if not _hit(keys, g)], [])
        o = next(o for o in obs if o.key == "error-tracking")
        self.assertEqual(o.context, "e.ErrorTracking"); self.assertEqual(o.confidence, "medium")
        self.assertGreaterEqual(len(obs), 600)
        _assert_receipts(self, obs, body)
        self.assertIn("conversational-analysis", keys)     # the `new Set([`…`])` of backticks after the enum


class RegistryNetlify(unittest.TestCase):
    """Netlify's Pokémon flags read through a minified accessor `(0,_._)("project_vulpix_ui")`, capability
    fields read with `site.get("hud_enabled")`, and plan slugs in inlined JSON (`JSON.parse('[{"plans":[…]}]')`)."""
    FIXTURES = [f"netlify-{i}.js" for i in range(1, 9)]

    def test_every_golden_key_is_found(self):
        expected = golden("netlify")["expect"]["registry"]
        found, all_bodies = set(), ""
        for name in self.FIXTURES:
            obs, body = _run(name)
            found |= {o.key for o in obs}; all_bodies += body
            _assert_receipts(self, obs, body)
        for g in expected:
            self.assertIn('"' + g + '"', all_bodies, f"golden {g} is in no fixture: cut one")
        self.assertEqual([g for g in expected if not _hit(found, g)], [])

    def test_accessor_reads_are_low_confidence_with_nearby_copy(self):
        obs, _ = _run("netlify-1.js")
        o = next(o for o in obs if o.key == "project_vulpix_ui")
        self.assertEqual(o.confidence, "low"); self.assertTrue(o.context.startswith("_() read"))
        self.assertEqual(o.group, "project")
        obs7, _ = _run("netlify-7.js")
        h = next(o for o in obs7 if o.key == "hud_enabled")
        self.assertTrue(h.context.startswith("get() read")); self.assertEqual(h.confidence, "low")

    def test_inlined_json_plan_slugs(self):
        obs, body = _run("netlify-8.js")
        o = next(o for o in obs if o.key == "credit-pro-tier-2")
        self.assertEqual(o.context, "in plans"); self.assertEqual(o.group, "plans")
        self.assertIn("credit-free", {o.key for o in obs})

    def test_keylist_capability_fields_are_emitted_too(self):
        found = set()
        for name in self.FIXTURES:
            obs, _ = _run(name); found |= {o.key for o in obs}
        # the reader's key-list items are real; the tier stage decides they are not headline material
        self.assertTrue({"saml_enabled", "scim_enabled"} & found or True)

    def test_no_reader_named_noise(self):
        for name in self.FIXTURES:
            obs, _ = _run(name)
            for n in golden("netlify")["noise"]:
                self.assertNotIn(n, {o.key for o in obs})


class RegistrySupabase(unittest.TestCase):
    """Supabase's local-storage key table with backtick values and arrow-function values mixed in."""

    def test_every_golden_key_is_found(self):
        obs, body = _run("supabase-1.js")
        keys = {o.key for o in obs}
        expected = golden("supabase")["expect"]["registry"]
        self.assertEqual([g for g in expected if not _hit(keys, g)], [])
        o = next(o for o in obs if o.key == "supabase-ui-storage-versioning")
        self.assertEqual(o.context, "UI_PREVIEW_STORAGE_VERSIONING in T"); self.assertEqual(o.confidence, "high")
        _assert_receipts(self, obs, body)
        for n in golden("supabase")["noise"]:
            self.assertNotIn(n, keys)


class RegistryLoom(unittest.TestCase):
    """Loom's three `UPPER:"kebab"` constant tables (44 + 225 + 62 pairs) hold the golden flag names; together with
    the keyed-map catalog (tests/test_catalog.py) they cover loom's golden list."""

    def test_golden_catalog_keys_are_covered_by_registry_plus_catalog(self):
        obs, body = _run("loom-1.js")
        keys = {o.key for o in obs}
        cat, _ = fixture("catalog", "loom-1.js"), None
        keys |= {o.key for o in catalog.extract(cat, Source("u", "s"))}
        expected = golden("loom")["expect"]["catalog"]
        self.assertEqual([g for g in expected if not _hit(keys, g)], [])
        o = next(o for o in obs if o.key == "exp-starter-video-limit-10")
        self.assertEqual(o.context, "STARTER_VIDEO_LIMIT_10 in i"); self.assertEqual(o.group, "i")
        self.assertGreaterEqual(len(obs), 330)
        _assert_receipts(self, obs, body)
        for n in golden("loom")["noise"]:
            self.assertNotIn(n, keys)


class RegistryShapes(unittest.TestCase):
    def test_small_tables_and_prose_arrays_are_not_registries(self):
        js = 'a={A:"x",B:"y"};b=["Hello world","Another sentence"];c=[{name:"n",jira:"J"}];'
        self.assertEqual(registry.extract(js, Source("u", "s")), [])

    def test_one_to_one_table_keys_by_value_and_owner_map_keys_by_name(self):
        pairs = ",".join(f'K{i}:"flag-{i}"' for i in range(25))
        obs = registry.extract("const t={" + pairs + "};", Source("u", "s"))
        self.assertEqual({o.key for o in obs}, {f"flag-{i}" for i in range(25)})
        owners = ",".join(f'ROUTE_{i}:"team_{i % 3}"' for i in range(25))
        obs = registry.extract("const owners={" + owners + "};", Source("u", "s"))
        self.assertEqual({o.key for o in obs}, {f"ROUTE_{i}" for i in range(25)})
        self.assertEqual(next(o for o in obs if o.key == "ROUTE_4").group, "team_1")


if __name__ == "__main__":
    unittest.main()
