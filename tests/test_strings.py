"""S1 seam: strings.extract(body, artifact) — the last-resort extractor — finds the readers' string keys.

Expected values come from tests/goldens/<product>.json (the readers' hand findings), never from the code.
"""
import unittest
from helpers import fixture, fixture_meta, golden  # sets sys.path
from schema import Source
from extractors import strings


def _artifact(shape, name):
    meta = fixture_meta(shape, name)
    return Source(url=meta["url"] or "https://example.invalid/" + name, sha256=meta["sha256_full"], offset=-1)


def _run(name):
    body = fixture("strings", name)
    return body, strings.extract(body, _artifact("strings", name))


class FigmaModelIdsAndLabelEnums(unittest.TestCase):
    """(a) model-id maps `{"robin-1":16,"hawk-1":0,…}` / `{"velvet":true,…}` keyed by a config name;
    (b) label enums `l.LOCAL_AGENT_FLOW_DOWNLOAD_MODAL="Local Agent Flow Download Modal"` whose value is the
    key's Title Case form."""

    @classmethod
    def setUpClass(cls):
        cls.body1, cls.obs1 = _run("figma-1.html")
        cls.body2, cls.obs2 = _run("figma-2.js")
        cls.keys = {o.key: o for o in cls.obs1 + cls.obs2}

    def test_golden_strings_are_found_at_low_confidence(self):
        want = golden("figma")["expect"]["string"]
        missing = [k for k in want if k not in self.keys]
        self.assertEqual(missing, [], f"missing {missing}")
        for k in want:
            self.assertEqual(self.keys[k].kind, "string")
            self.assertEqual(self.keys[k].extractor, "strings")
            self.assertEqual(self.keys[k].confidence, "low")

    def test_model_ids_carry_the_config_name_and_value(self):
        self.assertIn("figmake_model_picker_enabled_models", self.keys["velvet"].context)
        self.assertEqual(self.keys["velvet"].value, True)
        self.assertEqual(self.keys["velvet"].group, "model-ids")
        self.assertEqual(self.keys["hawk-1"].value, 0)
        self.assertIn("generate-image", self.keys["hawk-1"].context)
        self.assertEqual(self.body1[self.keys["robin-1"].source.offset:][:7], "robin-1")

    def test_label_enum_values_carry_their_constant(self):
        o = self.keys["Local Agent Flow Download Modal"]
        self.assertEqual(o.context, "LOCAL_AGENT_FLOW_DOWNLOAD_MODAL")
        self.assertEqual(o.group, "label-enum")
        self.assertEqual(self.body2[o.source.offset:o.source.offset + len(o.key)], o.key)

    def test_reader_named_noise_is_absent(self):
        for n in golden("figma")["noise"]:
            self.assertNotIn(n, self.keys)

    def test_context_is_bounded(self):
        for o in self.obs1 + self.obs2:
            self.assertLessEqual(len(o.context), 200)


class OtherProducts(unittest.TestCase):

    def test_notion_coupon_campaign_ids(self):
        body, obs = _run("notion-1.js")
        keys = {o.key: o for o in obs}
        want = golden("notion")["expect"]["string"]
        self.assertEqual([k for k in want if k not in keys], [])
        o = keys["business_annual_bundle_3_for_1_seats"]
        self.assertEqual(o.group, "coupon")
        self.assertIn("seat_count", o.context)
        self.assertEqual(body[o.source.offset:o.source.offset + len(o.key)], o.key)
        for n in golden("notion")["noise"]:
            self.assertNotIn(n, keys)

    def test_zoom_optimizely_url_targeting_name(self):
        # `apiName:"20917322331_url_targeting_for_hotfix_bonsai_url_tracking_params"` -> the experiment name;
        # the reader's other zoom string, `app-new-experience-portal`, is a chunk name (see test_manifest).
        body, obs = _run("zoom-1.js")
        keys = {o.key: o for o in obs}
        self.assertIn("hotfix_bonsai_url_tracking_params", keys)
        o = keys["hotfix_bonsai_url_tracking_params"]
        self.assertEqual(o.group, "url-targeting")
        self.assertIn("zoom.us/bonsai", o.context)
        self.assertEqual(body[o.source.offset:o.source.offset + len(o.key)], o.key)
        for n in golden("zoom")["noise"]:
            self.assertNotIn(n, keys)

    def test_discord_settings_tab_names(self):
        # `(C={}).CONJURE="conjuring",…,C.GUILD_OFFICIAL_MESSAGES="official-messages"`: the slug values
        body, obs = _run("discord-1.js")
        body2, obs2 = _run("discord-2.js")          # the shop-tab enum `(u={}).HOME="home",…,u.GAME_SHOPS="game-shops"`
        keys = {o.key: o for o in obs + obs2}
        want = golden("discord")["expect"]["string"]
        self.assertEqual([k for k in want if k not in keys], [])
        self.assertEqual(keys["official-messages"].context, "GUILD_OFFICIAL_MESSAGES")
        self.assertEqual(keys["official-messages"].group, "enum")
        for n in golden("discord")["noise"]:
            self.assertNotIn(n, keys)

    def test_hint_phrases_carry_context(self):
        body = 'var a={title:"Agents (coming soon)",cta:"Join the waitlist"};hljs.registerLanguage("beta",x);'
        obs = strings.extract(body, Source(url="u", sha256="x"))
        keys = {o.key: o for o in obs}
        self.assertIn("Agents (coming soon)", keys)
        self.assertEqual(keys["Agents (coming soon)"].value, "coming soon")
        self.assertEqual(keys["Agents (coming soon)"].group, "hint")
        self.assertIn("Join the waitlist", keys)
        self.assertFalse([k for k in keys if k == "beta"], "a bare vendor token is not a hint")


if __name__ == "__main__":
    unittest.main()
