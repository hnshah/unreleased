"""S1 seam: gatemap.extract(body, artifact) finds the readers' gates and named configs from corpus fixtures.

Expected keys and values come from tests/goldens/<product>.json and the readers' notes
(tests/goldens/<product>.json), never from running the extractor.
"""
import unittest
from helpers import fixture, fixture_meta, golden  # sets sys.path
from schema import Source
from extractors import gatemap


def src(meta):
    return Source(url=meta["url"] or "", sha256=meta["sha256_full"])


def run(shape, name):
    body = fixture(shape, name)
    return body, gatemap.extract(body, src(fixture_meta(shape, name)))


class GatemapFigma(unittest.TestCase):
    """Figma login page: `labmate_data.statsig` holds 2,149 gates with values (401 true, 1,748 false)."""

    def test_statsig_gate_map_yields_every_golden_gate_with_its_value(self):
        body, obs = run("gatemap", "figma-1.html")
        gates = {o.key: o for o in obs if o.kind == "gate"}
        for k in golden("figma")["expect"]["gate"]:
            self.assertIn(k, gates, k)
        # the reader: make_local_* are statsig-false; the false set is the product
        self.assertIs(gates["make_local_native_ios_preview"].value, False)
        self.assertIs(gates["make_local_claude_agent_sdk_sandbox"].value, False)
        self.assertIs(gates["make_local_github_pr_api"].value, False)
        self.assertGreaterEqual(len(gates), 2100)
        self.assertEqual(sum(1 for o in gates.values() if o.value is True), 401)
        self.assertTrue(all(isinstance(o.value, bool) for o in gates.values()))

    def test_gate_observations_carry_receipt_context_and_confidence(self):
        body, obs = run("gatemap", "figma-1.html")
        o = next(o for o in obs if o.kind == "gate" and o.key == "figjam_code_layers")
        self.assertEqual(o.extractor, "gatemap")
        self.assertEqual(o.confidence, "high")
        self.assertIn("statsig", o.context)
        self.assertIn("statsig", o.group)
        self.assertEqual(o.source.url, "https://www.figma.com/login")
        self.assertTrue(body[o.source.offset:].startswith('"figjam_code_layers"'), body[o.source.offset:o.source.offset + 40])

    def test_dynamic_configs_yield_one_config_per_key_with_compact_value(self):
        body, obs = run("gatemap", "figma-2.html")
        cfg = {o.key: o for o in obs if o.kind == "config"}
        for k in golden("figma")["expect"]["config"]:
            self.assertIn(k, cfg, k)
        # the reader counted 73 named configs under dynamic_configs (nested *_config keys inside them are extra)
        self.assertEqual(sum(1 for o in cfg.values() if o.group == "dynamic_configs"), 73)
        self.assertIn('"slack-agent":"alpha"', cfg["assistant_monetization_config"].context)
        self.assertIn("velvet", cfg["figmake_model_picker_enabled_models"].context)
        self.assertIn("2026-10-06T09:30:00", cfg["announce_agent_weave_ga_date"].context)
        self.assertTrue(all(len(o.context) <= 200 for o in cfg.values()))
        self.assertTrue(all(o.confidence == "high" for o in cfg.values()))
        o = cfg["assistant_monetization_config"]
        self.assertTrue(body[o.source.offset:].startswith('"assistant_monetization_config"'))

    def test_small_boolean_configs_are_not_mistaken_for_gate_maps(self):
        # figmake_model_picker_enabled_models has 7 boolean values: below the 8-key floor, so a config, not a gate map
        body, obs = run("gatemap", "figma-2.html")
        self.assertNotIn("anthropic-claude-5.5-sonnet", {o.key for o in obs if o.kind == "gate"})


class GatemapClarity(unittest.TestCase):
    """Clarity pages inline `config={"features":{k:{"enabled":true},...}}`: 107 keys, all enabled for a visitor."""

    def test_enabled_map_yields_every_golden_gate_with_its_value(self):
        body, obs = run("gatemap", "clarity-1.html")
        gates = {o.key: o for o in obs if o.kind == "gate"}
        for k in golden("clarity")["expect"]["gate"]:
            self.assertIn(k, gates, k)
            self.assertIs(gates[k].value, True)
        self.assertEqual(len(gates), 107)
        o = gates["coworkerwaitlistdeployment"]
        self.assertEqual(o.confidence, "high")
        self.assertIn("features", o.context)
        self.assertTrue(body[o.source.offset:].startswith('"coworkerwaitlistdeployment"'))
        self.assertNotIn("enabled", gates)


class GatemapPosthog(unittest.TestCase):
    """PostHog login page `persisted_feature_flags`: an array of 409 flag keys, no values for a visitor."""

    def test_gate_list_yields_every_golden_gate_with_no_value(self):
        body, obs = run("gatemap", "posthog-1.html")
        gates = {o.key: o for o in obs if o.kind == "gate"}
        for k in golden("posthog")["expect"]["gate"]:
            self.assertIn(k, gates, k)
            self.assertIsNone(gates[k].value)
        self.assertEqual(len(gates), 409)
        o = gates["project-bluebird"]
        self.assertEqual(o.confidence, "medium")
        self.assertIn("persisted_feature_flags", o.context)
        self.assertEqual(o.group, "persisted_feature_flags")
        self.assertTrue(body[o.source.offset:].startswith('"project-bluebird"'))
        # the readers' noise for posthog is SDK docs vocabulary, not in this list
        for k in golden("posthog")["noise"]:
            self.assertNotIn(k, gates)


class GatemapSpotify(unittest.TestCase):
    """accounts.spotify.com: an inline `featureFlags` payload and a Remote Config registry with descriptions."""

    def test_inline_payload_is_a_gate_map_with_values(self):
        body, obs = run("gatemap", "spotify-1.html")
        gates = {o.key: o for o in obs if o.kind == "gate"}
        self.assertIs(gates["passkeysEnabled"].value, False)
        self.assertIs(gates["unifiedPasswordlessLoginEnabled"].value, True)
        self.assertEqual(gates["signupMode"].value, "default")   # every key is reported, even the odd string
        self.assertEqual(len(gates), 14)
        self.assertEqual(gates["passkeysEnabled"].group, "featureFlags")

    def test_gate_definitions_carry_default_and_description(self):
        body, obs = run("gatemap", "spotify-2.js")
        gates = {o.key: o for o in obs if o.kind == "gate"}
        for k in golden("spotify")["expect"]["gate"]:
            self.assertIn(k, gates, k)
        self.assertIs(gates["passkeys_enabled"].value, False)
        self.assertEqual(gates["passkeys_enabled"].context, "Enable passkey login")
        self.assertEqual(gates["naver_login_enabled"].context, "Enable Naver as a Login option")
        self.assertEqual(gates["naver_login_enabled"].confidence, "high")
        self.assertEqual(len(gates), 6)
        self.assertTrue(body[gates["passkeys_enabled"].source.offset:].startswith("passkeys_enabled"))


class GatemapStripe(unittest.TestCase):
    """js.stripe.com/v3: `{x_beta_1:"x_beta_1",...}` enum of 136 beta gates, plus per-method `betaFlags:[...]`."""

    def test_beta_enum_yields_gates_without_values(self):
        body, obs = run("gatemap", "stripe-1.js")
        gates = {o.key: o for o in obs if o.kind == "gate"}
        for k in ("ng_ussd_pm_beta_1", "kr_market_pm_beta_1"):
            self.assertIn(k, gates, k)
            self.assertIsNone(gates[k].value)
            self.assertEqual(gates[k].confidence, "medium")
        self.assertEqual(len(gates), 136)

    def test_named_beta_flags_list_yields_its_gate(self):
        body, obs = run("gatemap", "stripe-2.js")
        gates = {o.key: o for o in obs if o.kind == "gate"}
        self.assertIn("toss_pay_pm_beta_1", gates)
        self.assertEqual(gates["toss_pay_pm_beta_1"].group, "betaFlags")
        self.assertEqual(len(gates), 1)

    def test_stripe_golden_gates_are_covered_by_the_two_fixtures(self):
        found = set()
        for name in ("stripe-1.js", "stripe-2.js"):
            found |= {o.key for o in run("gatemap", name)[1] if o.kind == "gate"}
        for k in golden("stripe")["expect"]["gate"]:
            self.assertIn(k, found, k)


class GatemapDropbox(unittest.TestCase):
    """Dropbox storefront proto (`StorefrontPlatformConfiguration`): fields named like gates, no values in code."""

    def test_proto_fields_named_like_gates_are_low_confidence_gates(self):
        body, obs = run("gatemap", "dropbox-1.js")
        gates = {o.key: o for o in obs if o.kind == "gate"}
        for k in golden("dropbox")["expect"]["gate"]:
            self.assertIn(k, gates, k)
            self.assertIsNone(gates[k].value)
            self.assertEqual(gates[k].confidence, "low")
        self.assertIn("proto field", gates["ai_credit_price_variant"].context)
        self.assertTrue(body[gates["one_license_standard_plan_enabled"].source.offset:].startswith('one_license_standard_plan_enabled"'))


class GatemapReplit(unittest.TestCase):
    """Replit's subscription entry-point enum: an unnamed array of 200+ snake strings (the reader's `canvas_media_generation`,
    `reverse_trial_banner`, `self_serve_enterprise` live here, not in a call site; the golden files them under `call`)."""

    def test_unnamed_uniform_string_list_is_a_gate_list(self):
        body, obs = run("gatemap", "replit-1.js")
        gates = {o.key: o for o in obs if o.kind == "gate"}
        for k in ("canvas_media_generation", "reverse_trial_banner", "self_serve_enterprise"):
            self.assertIn(k, gates, k)
            self.assertIsNone(gates[k].value)
            self.assertEqual(gates[k].confidence, "medium")
        self.assertEqual(len(gates), 156)   # json.loads of the array in the fixture


class GatemapShapes(unittest.TestCase):
    """Hand-written boundaries of the classifiers."""

    def test_seven_booleans_are_not_a_gate_map_but_eight_are(self):
        seven = "x={" + ",".join(f"f{i}:!0" for i in range(7)) + "};"
        eight = "x={" + ",".join(f"f{i}:!0" for i in range(8)) + "};"
        self.assertEqual(gatemap.extract(seven, Source("u", "s")), [])
        self.assertEqual(len(gatemap.extract(eight, Source("u", "s"))), 8)

    def test_mixed_values_below_ninety_percent_are_not_a_gate_map(self):
        js = 'o={a:!0,b:!1,c:"x",d:1,e:!0,f:!1,g:"y",h:!0,i:!1,j:2};'   # 7 of 10 boolean/0-1
        self.assertEqual([o for o in gatemap.extract(js, Source("u", "s")) if o.kind == "gate"], [])

    def test_zero_one_maps_count_as_gates(self):
        js = 'window.experimentVariants = {"a_1":0,"b_2":0,"c_3":1,"d_4":0,"e_5":0,"f_6":1,"g_7":0,"h_8":0};'
        gates = {o.key: o.value for o in gatemap.extract(js, Source("u", "s")) if o.kind == "gate"}
        self.assertEqual(gates["c_3"], 1); self.assertEqual(gates["a_1"], 0); self.assertEqual(len(gates), 8)

    def test_short_locale_like_lists_are_not_gate_lists(self):
        js = "l=[" + ",".join(f'"{a}-{b}"' for a in ("en", "fr", "de", "es", "pt", "it") for b in ("us", "gb", "ca", "au", "br", "mx")) + "];"
        self.assertEqual(gatemap.extract(js, Source("u", "s")), [])

    def test_arrays_under_words_that_merely_end_in_gate_are_not_named_gate_lists(self):
        js = 'x.aggregates=["sum_total","avg_value"];y.delegates=["on_click"];'
        self.assertEqual(gatemap.extract(js, Source("u", "s")), [])

    def test_identity_enum_without_gate_like_names_is_not_a_gate_map(self):
        js = "T={" + ",".join(f'{k}:"{k}"' for k in ("ADD_TODO", "DEL_TODO", "SET_USER", "RESET", "OPEN", "CLOSE", "LOAD", "SAVE")) + "};"
        self.assertEqual(gatemap.extract(js, Source("u", "s")), [])


if __name__ == "__main__":
    unittest.main()
