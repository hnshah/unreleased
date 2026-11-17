"""S1 seam: extractors.enums.extract(body, artifact) finds the readers' enum values from non-proto enums and
string tables in corpus excerpts. Expected values come from tests/goldens/<product>.json; the i18n and
remote-config expectations are read by hand from the fixture bytes (no golden lists them)."""
import unittest
from helpers import fixture, fixture_meta, golden  # sets sys.path
from schema import Source
from extractors import enums


def _run(name):
    meta = fixture_meta("enums", name)
    body = fixture("enums", name)
    return enums.extract(body, Source(meta["url"] or "", meta["sha256_full"])), body


def _receipts(tc, obs, body):
    for o in obs:
        tc.assertEqual(body[o.source.offset:o.source.offset + len(o.key)], o.key, f"receipt for {o.key}")
        tc.assertLessEqual(len(o.context), 200); tc.assertEqual(o.extractor, "enums")


class EnumsNotion(unittest.TestCase):
    """A webpack export map `r.d(t,{},{$$c:"google_token",…,a8w:"marketplace_custom_agent_version"})`: 232
    mangled keys whose values are the record-type names."""

    def test_every_golden_value_is_found(self):
        obs, body = _run("notion-1.js")
        keys = {o.key for o in obs if o.kind == "enum"}
        expected = golden("notion")["expect"]["enum"]
        self.assertEqual([g for g in expected if g not in keys], [])
        o = next(o for o in obs if o.key == "marketplace_coupon")
        self.assertEqual(o.group, "marketplace"); self.assertEqual(o.confidence, "high")
        self.assertIn("QOF", o.context)                       # the export name it is bound to
        self.assertGreaterEqual(len(obs), 200)
        _receipts(self, obs, body)
        for n in golden("notion")["noise"]:
            self.assertNotIn(n, keys)


class EnumsLinear(unittest.TestCase):
    """A TS enum IIFE `Rn=function(e){return e.AGENTS_WAITLIST="Agents Waitlist",…,e}({})`: prose values, so the
    constant name is the key and the prose is the value."""

    def test_every_golden_name_is_found(self):
        obs, body = _run("linear-1.js")
        by = {o.key: o for o in obs if o.kind == "enum"}
        expected = golden("linear")["expect"]["enum"]
        self.assertEqual([g for g in expected if g not in by], [])
        self.assertEqual(by["AGENTS_WAITLIST"].value, "Agents Waitlist")
        self.assertEqual(by["AGENTS_WAITLIST"].group, "Rn")
        self.assertEqual(by["AGENTS_WAITLIST"].confidence, "medium")
        _receipts(self, obs, body)
        for n in golden("linear")["noise"]:
            self.assertNotIn(n, by)


class EnumsFigma(unittest.TestCase):
    """Model tables in the bootstrap JSON: `"figmake_model_picker_enabled_models":{"anthropic-claude-5.5-sonnet":true,
    …,"velvet":true}` and `"generate-image":{…,"robin-1":16,"hawk-1":0}`. A table naming known models is a model
    table, so its opaque entries are emitted too. And the i18n table `{"key":{"string":"…"}}`."""

    def test_model_ids_are_enum_values_grouped_by_their_table(self):
        obs, body = _run("figma-1.html")
        by = {(o.group, o.key): o for o in obs if o.kind == "enum"}
        expected = [s for s in golden("figma")["expect"]["string"] if " " not in s]   # robin-1, hawk-1, hawk-3, velvet, goldenrod
        keys = {k for _, k in by}
        self.assertEqual([g for g in expected if g not in keys], [])
        self.assertEqual(by[("generate-image", "robin-1")].value, 16)
        self.assertEqual(by[("figmake_model_picker_enabled_models", "velvet")].value, True)
        self.assertIn("model table", by[("generate-image", "hawk-1")].context)
        _receipts(self, obs, body)
        for n in golden("figma")["noise"]:
            self.assertNotIn(n, keys)

    def test_i18n_entries_keep_their_copy_as_context(self):
        obs, body = _run("figma-2.js")
        i18n = {o.key: o for o in obs if o.kind == "i18n"}
        self.assertEqual(i18n["agenda.default_agenda_item_title"].context, "Agenda item")
        self.assertEqual(i18n["analytics.error.no_data"].context, "Analytics data not found for org")
        self.assertGreaterEqual(len(i18n), 20)
        _receipts(self, obs, body)

    def test_i18n_is_capped_and_hot_copy_comes_first(self):
        rows = ",".join(f'"k.{i}":{{"string":"Plain copy {i}"}}' for i in range(600)) + ',"k.hot":{"string":"Join the beta waitlist"}'
        obs = enums.extract("{" + rows + "}", Source("u", "s"))
        i18n = [o for o in obs if o.kind == "i18n"]
        self.assertEqual(len(i18n), 500)
        self.assertIn("k.hot", {o.key for o in i18n})      # kept over plain copy although it is last in the body


class EnumsSpotify(unittest.TestCase):
    """Remote Config properties `(0,V.m9)({name:"passkeys_enabled",description:"Enable passkey login",default:!1})`."""

    def test_remote_config_properties(self):
        obs, body = _run("spotify-1.js")
        by = {o.key: o for o in obs if o.kind == "enum"}
        self.assertIn("passkeys_enabled", by); self.assertIn("naver_login_enabled", by)
        o = by["passkeys_enabled"]
        self.assertEqual(o.value, False); self.assertEqual(o.context, "Enable passkey login"); self.assertEqual(o.group, "remote-config")
        _receipts(self, obs, body)


class EnumsShapes(unittest.TestCase):
    def test_short_runs_and_registry_runs_are_not_claimed(self):
        two = 'x=function(e){return e.A="Alpha thing",e.B="Beta thing",e}({});'
        self.assertEqual(enums.extract(two, Source("u", "s")), [])
        amp = "f=function(e){return " + ",".join(f'e.P{i}=`flag-{i}`' for i in range(25)) + ",e}({});"
        self.assertEqual(enums.extract(amp, Source("u", "s")), [])     # >= 20 identifier values: the registry shape

    def test_x_name_readable_run(self):
        js = 'l.LOCAL_AGENT_FLOW_DOWNLOAD_MODAL="Local Agent Flow Download Modal",l.MAKE_LOCAL_DESKTOP_HANDOFF="Make Local Desktop Handoff",l.SPELLCHECK_SUCCESS_MODAL="Spellcheck Success Modal";'
        obs = enums.extract(js, Source("u", "s"))
        self.assertEqual([o.key for o in obs], ["LOCAL_AGENT_FLOW_DOWNLOAD_MODAL", "MAKE_LOCAL_DESKTOP_HANDOFF", "SPELLCHECK_SUCCESS_MODAL"])
        self.assertEqual(obs[0].value, "Local Agent Flow Download Modal")


if __name__ == "__main__":
    unittest.main()
