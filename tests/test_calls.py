"""S1 seam: calls.extract(body, artifact) finds flag reads by call convention in corpus fixtures.

Expected keys come from tests/goldens/<product>.json and the readers' notes, never from running the code.
"""
import unittest
from helpers import fixture, fixture_meta, golden  # sets sys.path
from schema import Source
from extractors import calls


def src(meta):
    return Source(url=meta["url"] or "", sha256=meta["sha256_full"])


def run(name):
    body = fixture("calls", name)
    return body, calls.extract(body, src(fixture_meta("calls", name)))


class CallsNotion(unittest.TestCase):
    """notion.so app bundle: Statsig reads `checkGate({gateName:"x"})`, `getEligibleGroup({experimentId:"x"})`,
    `this.checkGate("x")`, and names held in a module-level `let n="x"` before the call."""

    def test_checkgate_object_argument(self):
        body, obs = run("notion-1.js")
        found = {o.key: o for o in obs if o.kind == "call"}
        for k in ("marketplace_agent", "agent_in_meetings_route", "new_custom_agent_setup_and_editing"):
            self.assertIn(k, found, k)
        o = found["marketplace_agent"]
        self.assertEqual(o.extractor, "calls")
        self.assertEqual(o.confidence, "high")
        self.assertEqual(o.group, "checkGate")
        self.assertIn("checkGate", o.context)
        self.assertTrue(body[o.source.offset:].startswith('"marketplace_agent"'))
        self.assertEqual(len(found), 3)

    def test_checkgate_positional_string(self):
        body, obs = run("notion-2.js")
        found = {o.key for o in obs if o.kind == "call"}
        self.assertIn("notion_mail_connector", found)
        self.assertIn("outlook_ai_connector_business_plan_bypass", found)

    def test_gate_name_held_in_a_variable_is_resolved_at_medium_confidence(self):
        for name, key in (("notion-3.js", "meeting_notes_video_file_upload_enabled"),
                          ("notion-4.js", "meeting_notes_replay_enabled"),
                          ("notion-5.js", "seat_bundling_starter_pack_v2")):
            body, obs = run(name)
            found = {o.key: o for o in obs if o.kind == "call"}
            self.assertIn(key, found, key)
            self.assertEqual(found[key].confidence, "medium")
            self.assertTrue(body[found[key].source.offset:].startswith(f'"{key}"'))
        body, obs = run("notion-5.js")
        o = next(o for o in obs if o.key == "seat_bundling_starter_pack_v2")
        self.assertEqual(o.group, "getEligibleGroup")

    def test_config_reads_are_reported_too(self):
        body, obs = run("notion-3.js")
        found = {o.key: o for o in obs if o.kind == "call"}
        self.assertIn("meeting_notes_video_file_upload_config", found)
        self.assertEqual(found["meeting_notes_video_file_upload_config"].group, "getConfig")

    def test_notion_golden_calls_covered_by_fixtures(self):
        found = set()
        for name in ("notion-1.js", "notion-2.js", "notion-3.js", "notion-4.js", "notion-5.js", "notion-6.js", "notion-7.js"):
            found |= {o.key for o in run(name)[1]}
        # Three golden `call` keys are not call sites in the corpus: `diarized_transcript_ui_enabled` is read through a
        # minified hook `(0,i(83208).X)("...")` whose 39 call sites are spread across a 3.7 MB chunk (the frequency
        # detector needs the whole body), and `plus_lock_waitlist` / `workspace_encryption_key` occur only in the
        # record-type enum (the enums shape).
        not_call_sites = {"diarized_transcript_ui_enabled", "plus_lock_waitlist", "workspace_encryption_key"}
        for k in golden("notion")["expect"]["call"]:
            if k in not_call_sites:
                continue
            self.assertIn(k, found, k)


class CallsReplit(unittest.TestCase):
    """replit.com: `(0,y.useGetExperimentParam)("exp","param",!1)` and `(0,o.useFeatureGate)("flag-razorpay-checkout",!1)`."""

    def test_experiment_param_read_yields_experiment_with_param_and_default(self):
        body, obs = run("replit-1.js")
        found = {o.key: o for o in obs}
        self.assertIn("disable_max_for_core_subscribers", found)
        o = found["disable_max_for_core_subscribers"]
        self.assertEqual(o.params, ["max_upgrade_discounted"])
        self.assertIs(o.value, False)
        self.assertIs(o.default, False)
        self.assertEqual(o.group, "useGetExperimentParam")
        self.assertTrue(body[o.source.offset:].startswith('"disable_max_for_core_subscribers"'))

    def test_feature_gate_read_yields_key_and_default(self):
        body, obs = run("replit-2.js")
        found = {o.key: o for o in obs}
        self.assertIn("flag-razorpay-checkout", found)
        self.assertIs(found["flag-razorpay-checkout"].value, False)
        self.assertEqual(found["flag-razorpay-checkout"].group, "useFeatureGate")

    def test_replit_golden_calls_covered_by_fixtures(self):
        found = set()
        for name in ("replit-1.js", "replit-2.js"):
            found |= {o.key for o in run(name)[1]} | {p for o in run(name)[1] for p in o.params}
        # Four golden `call` keys are not call sites in the corpus: `canvas_media_generation`, `reverse_trial_banner`,
        # `self_serve_enterprise` sit in the subscription entry-point enum (found by gatemap's list rule, see
        # test_gatemap.GatemapReplit) and `amazon-selling-partner-beta` in the 469-slug connector catalogue (strings).
        not_call_sites = {"canvas_media_generation", "reverse_trial_banner", "self_serve_enterprise", "amazon-selling-partner-beta"}
        for k in golden("replit")["expect"]["call"]:
            if k in not_call_sites:
                continue
            self.assertIn(k, found, k)


class CallsVercel(unittest.TestCase):
    """vercel.com: `(0,A.useServerFlag)("enable-repositories",!1)`."""

    def test_server_flag_reads_yield_key_and_default(self):
        body, obs = run("vercel-1.js")
        found = {o.key: o for o in obs}
        for k in golden("vercel")["expect"]["call"]:
            self.assertIn(k, found, k)
        self.assertIs(found["enable-repositories"].value, False)
        self.assertEqual(found["enable-repositories"].group, "useServerFlag")
        self.assertEqual(found["enable-repositories"].confidence, "high")
        self.assertEqual(len(found), 5)
        for k in golden("vercel")["noise"]:
            self.assertNotIn(k, found)


class CallsShapes(unittest.TestCase):
    """Hand-written boundaries (the Retool `namespace::key` strings are live-only in the goldens, so synthetic here)."""

    def test_namespace_key_strings_are_low_confidence_calls(self):
        js = 'if(f("governance::projects")||g(\'paid::differentiated\')){x("nativeGit::useCandidates")}'
        found = {o.key: o for o in calls.extract(js, Source("u", "s"))}
        self.assertEqual(set(found), {"governance::projects", "paid::differentiated", "nativeGit::useCandidates"})
        self.assertTrue(all(o.confidence == "low" and o.group == "namespace::key" for o in found.values()))

    def test_minified_hook_detected_by_frequency_of_flag_like_arguments(self):
        keys = [f"feat_{i}_enabled" for i in range(10)]
        js = ";".join(f'var v{i}=(0,i(83208).X)("{k}")' for i, k in enumerate(keys)) + ';(0,i(83208).X)("diarized_transcript_ui_enabled");'
        found = {o.key: o for o in calls.extract(js, Source("u", "s"))}
        self.assertIn("diarized_transcript_ui_enabled", found)
        self.assertEqual(found["diarized_transcript_ui_enabled"].confidence, "low")
        self.assertEqual(found["diarized_transcript_ui_enabled"].group, "i(83208).X")
        self.assertEqual(len(found), 11)

    def test_minified_hook_below_ten_distinct_arguments_is_ignored(self):
        js = ";".join(f'(0,i(83208).X)("feat_{i}_enabled")' for i in range(9))
        self.assertEqual(calls.extract(js, Source("u", "s")), [])

    def test_event_bus_analytics_and_i18n_helpers_are_not_hooks(self):
        js = ";".join(f'n._on("row_{i}_changed")' for i in range(12)) + ";" + ";".join(f'(0,i(353615).DO_NOT_USE_trackLegacy)("ev_{i}_fired")' for i in range(12))
        self.assertEqual(calls.extract(js, Source("u", "s")), [])

    def test_dom_and_collection_methods_are_not_hooks(self):
        js = ";".join(f'e.classList.add("is-state-{i}")' for i in range(12)) + ";" + ";".join(f't.push("row-{i}-x")' for i in range(12))
        self.assertEqual(calls.extract(js, Source("u", "s")), [])

    def test_gate_name_fields_inside_objects_and_country_flags_apart(self):
        js = 'a={gateName:"my_gate"};b={experimentName:"exp_one"};c={flag:"us"};d={flag:"new-checkout-flow"}'
        found = {o.key for o in calls.extract(js, Source("u", "s"))}
        self.assertEqual(found, {"my_gate", "exp_one", "new-checkout-flow"})

    def test_experiment_default_group_is_the_value(self):
        js = 'x=i(218744).default.getEligibleGroup({experimentId:"checkout_address_form",defaultGroup:"off"})'
        o = calls.extract(js, Source("u", "s"))[0]
        self.assertEqual((o.key, o.value, o.group), ("checkout_address_form", "off", "getEligibleGroup"))


if __name__ == "__main__":
    unittest.main()
