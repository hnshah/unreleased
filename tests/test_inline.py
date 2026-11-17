"""S1 seam: inline.extract(body, artifact) reads values from page-level objects (JSON blocks, window.* assignments,
data-* attributes, experiment arrays, server-prop booleans) in corpus fixtures.

Expected keys and values come from tests/goldens/<product>.json and the readers' notes, never from running the code.
"""
import unittest
from helpers import fixture, fixture_meta, golden  # sets sys.path
from schema import Source
from extractors import inline


def src(meta):
    return Source(url=meta["url"] or "", sha256=meta["sha256_full"])


def run(name):
    body = fixture("inline", name)
    return body, inline.extract(body, src(fixture_meta("inline", name)))


class InlineVercel(unittest.TestCase):
    """vercel.com/login: `<script type="application/json" data-flag-values="true">{...}</script>` with four server flags."""

    def test_data_flag_values_block_yields_every_key_with_its_value(self):
        body, obs = run("vercel-1.html")
        vals = {o.key: o for o in obs if o.kind == "inline"}
        self.assertIn("new-pro-two-ui-phases-2026", vals)
        self.assertEqual(vals["new-pro-two-ui-phases-2026"].value, "phase-1")   # the golden's second inline literal
        self.assertIs(vals["show-platform-status-indicator"].value, True)
        self.assertIs(vals["enable-swr-hooks-in-migration"].value, False)
        self.assertEqual(len(vals), 4)
        o = vals["new-pro-two-ui-phases-2026"]
        self.assertEqual(o.extractor, "inline")
        self.assertEqual(o.confidence, "high")
        self.assertEqual(o.context, "data-flag-values")
        self.assertEqual(o.group, "data-flag-values")
        self.assertTrue(body[o.source.offset:].startswith('"new-pro-two-ui-phases-2026"'))
        self.assertEqual(o.source.url, "https://vercel.com/login")

    def test_vercel_golden_inline_literals_are_found(self):
        body, obs = run("vercel-1.html")
        seen = {o.key for o in obs} | {o.value for o in obs if isinstance(o.value, str)}
        for k in golden("vercel")["expect"]["inline"]:
            self.assertIn(k, seen, k)


class InlineZoom(unittest.TestCase):
    """zoom.us/signin: `window.microsDatas = {...}` and `window.dataForFE = {...}` with unquoted keys and single quotes."""

    def test_window_objects_yield_golden_keys_with_values(self):
        found = {}
        for name in ("zoom-1.html", "zoom-2.html"):
            body, obs = run(name)
            for o in obs:
                found[o.key] = (o, body)
        for k in golden("zoom")["expect"]["inline"]:
            self.assertIn(k, found, k)
        # the reader: isAicForAdminReleased: false (AI Companion for admins, gated as not released)
        self.assertIs(found["isAicForAdminReleased"][0].value, False)
        self.assertIs(found["useSimplifiedPortal"][0].value, False)
        self.assertIs(found["rollbackToClassicSupported"][0].value, False)
        self.assertEqual(found["simplifiedPortalEnabledSource"][0].value, "")
        self.assertIs(found["isPhoneLoginEnable"][0].value, True)
        self.assertEqual(found["isAicForAdminReleased"][0].context, "window.microsDatas")
        self.assertEqual(found["isPhoneLoginEnable"][0].context, "window.dataForFE")
        o, body = found["useSimplifiedPortal"]
        self.assertTrue(body[o.source.offset:].startswith("useSimplifiedPortal:"))

    def test_nested_objects_are_not_flattened_into_the_window_object(self):
        body, obs = run("zoom-1.html")
        keys = {o.key for o in obs}
        self.assertIn("cluster", keys)
        self.assertNotIn("copyright", keys)      # inside the cut-off footConfig assignment, not microsDatas


class InlineSlack(unittest.TestCase):
    """slack.com: `TD.boot_data.experiments = ["name.arm", ...]`, 15 marketing experiments with their arms."""

    def test_experiment_array_yields_name_and_arm(self):
        body, obs = run("slack-1.html")
        vals = {o.key: o for o in obs}
        for k in golden("slack")["expect"]["inline"]:
            self.assertIn(k, vals, k)
        self.assertEqual(vals["entplus_pricing_q3fy27"].value, "control")
        self.assertEqual(vals["integrations_cta_v2_q3fy27"].value, "treatment_a")
        self.assertEqual(vals["slack_trials_tof"].value, "aa_control")
        self.assertEqual(vals["entplus_pricing_q3fy27"].context, "TD.boot_data.experiments")
        self.assertEqual(len([o for o in obs if o.context == "TD.boot_data.experiments"]), 15)
        o = vals["entplus_pricing_q3fy27"]
        self.assertTrue(body[o.source.offset:].startswith('"entplus_pricing_q3fy27.control"'))


class InlineAsana(unittest.TestCase):
    """asana.com: `window.experimentVariants = {name: 0|1, ...}` (19 marketing experiments) and a copy under
    `window.assignedExperimentVariants`."""

    def test_experiment_variants_object_yields_golden_keys_with_arms(self):
        body, obs = run("asana-1.html")
        vals = {o.key: o for o in obs if o.context == "window.experimentVariants"}
        for k in golden("asana")["expect"]["inline"]:
            self.assertIn(k, vals, k)
        self.assertEqual(vals["cmd_site_launch_11_26"].value, 0)
        self.assertEqual(vals["hp_031_hero_persona_video"].value, 1)
        self.assertEqual(len(vals), 19)
        self.assertTrue(any(o.context == "window.assignedExperimentVariants" for o in obs))


class InlineSpotify(unittest.TestCase):
    """accounts.spotify.com `__NEXT_DATA__`: a `featureFlags` object inside page props, read in full."""

    def test_flag_named_object_inside_json_block_is_read_in_full(self):
        body, obs = run("spotify-1.html")
        vals = {o.key: o for o in obs}
        for k in golden("spotify")["expect"]["inline"]:
            self.assertIn(k, vals, k)
        self.assertIs(vals["passkeysEnabled"].value, False)
        self.assertIs(vals["unifiedPasswordlessLoginEnabled"].value, True)
        self.assertEqual(vals["signupMode"].value, "default")
        self.assertEqual(vals["passkeysEnabled"].context, "__NEXT_DATA__.featureFlags")
        self.assertTrue(body[vals["passkeysEnabled"].source.offset:].startswith('"passkeysEnabled"'))
        # translations and page props are not inline values; Next's own page-level booleans are server props
        self.assertNotIn("youAreLoggedInAsUsername", vals)
        self.assertNotIn("recaptchaKey", vals)
        self.assertIn("isFallback", vals)


class InlineHuggingFace(unittest.TestCase):
    """huggingface.co: Svelte hydrater `data-props="{&quot;canCreateKernels&quot;:false,...}"` attributes."""

    def test_entity_encoded_data_props_yield_server_prop_booleans(self):
        body, obs = run("huggingface-1.html")
        vals = {o.key: o for o in obs}
        for k in golden("huggingface")["expect"]["inline"]:
            self.assertIn(k, vals, k)
        self.assertIs(vals["canCreateKernels"].value, False)
        self.assertIs(vals["isPro"].value, False)
        self.assertEqual(vals["canCreateKernels"].context, "data-props")
        self.assertNotIn("classNames", vals)
        self.assertTrue(body[vals["canCreateKernels"].source.offset:].startswith("canCreateKernels"))


class InlineShapes(unittest.TestCase):
    """Hand-written boundaries."""

    def test_plain_json_block_yields_only_server_prop_booleans(self):
        page = '<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"title":"Hi","canEdit":true,"hasTeam":false,"count":3}}}</script>'
        vals = {o.key: o.value for o in inline.extract(page, Source("u", "s"))}
        self.assertEqual(vals, {"canEdit": True, "hasTeam": False})

    def test_gate_maps_inside_json_blocks_are_left_to_gatemap(self):
        gm = ",".join(f'"is_f{i}":true' for i in range(8))
        page = '<script type="application/json">{"statsig":{' + gm + '},"isAdmin":false}</script>'
        keys = {o.key for o in inline.extract(page, Source("u", "s"))}
        self.assertEqual(keys, {"isAdmin"})

    def test_experiments_forEach_array_is_read(self):
        js = 'var experiments=["exp_alpha_q1fy27.treatment","exp_beta.control"];experiments.forEach(function(e){track(e)});'
        vals = {o.key: o.value for o in inline.extract(js, Source("u", "s"))}
        self.assertEqual(vals, {"exp_alpha_q1fy27": "treatment", "exp_beta": "control"})

    def test_words_that_merely_end_in_gate_or_feature_are_not_flag_names(self):
        js = 'r.aggregates={isTotal:!0,count:2};t.navigate={canGoBack:!1};o.delegates=["a_b","c_d"];'
        self.assertEqual(inline.extract(js, Source("u", "s")), [])

    def test_non_global_non_flag_assignments_are_ignored(self):
        js = 'e.exports={isDev:!0,canFoo:!1};t.prototype.x={hasBar:!0};'
        self.assertEqual(inline.extract(js, Source("u", "s")), [])


if __name__ == "__main__":
    unittest.main()
