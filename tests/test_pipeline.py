"""End to end: plan -> FakeFetcher -> pipeline -> emit, with a store, over two runs. The review (U13) found every
honesty hole in this seam, so each is pinned here: no secret in any run-folder file, a page-only read is not
rich, an empty read never diffs, a 429 stops the host, HTML on a script URL is not code, a redirect to another
company is a signal not first-party code, an extractor that raises is an outcome not a crash."""
import json, os, re, sys, tempfile, unittest
from helpers import FakeFetcher  # noqa: F401 (sets sys.path)
import pipeline, emit, plan as planmod, store as storemod, redact
import extractors

SK = "sk_" + "live_" + "0Example0Example0Example00"      # built at runtime: no scanner-shaped literal in the repo
PAGE = """<!doctype html><html><head><link rel="icon" href="/favicon.ico"></head><body>
<script id="boot" type="application/json">{"feature_flags": {"make_local_ai_gateway": false, "ai_credits_plan_add_on": true,
 "cache_hydration_v2_rollout": true, "bobs_specials": true, "perf_log_sampling_rate": false, "weave_video_trim": false}}</script>
<script src="https://acme.com/static/app.js"></script>
<script src="https://acme.com/static/chunk-1.js"></script>
</body></html>"""
APP = ('window.__FLAGS__={ai_assistant_mcp_client:!1,ai_assistant_websearch:!1,ai_assistant_slides:!0,sites_code_layers_code_only:!1,'
       'billing_lifecycle_v2:!1,checkout_step_1:!1,checkout_step_2:!1};'
       'const r=[{path:"/billing/invoices",name:"Invoices"},{path:"/ai-gateway/private-inference",name:"Private Inference",flag:"enablePrivateInference"}];'
       '(0,a.checkGate)({gateName:"ai_credit_plans"});const k="' + SK + '";' + "x".ljust(3000, "x") + ';')
CHUNK = ('export const t={weave_ai_models_plan:!1,weave_ai_models_page:!1,weave_mcp_file_browser_promo:!1,weave_video_chapters:!0,'
         'weave_audio_tools:!1,weave_print_ratio:!1,weave_storyboard:!1,weave_motion_export:!0,weave_shaders:!1};' + "y" * 2000)   # ≥ 8 keys: a gate map


def plan():
    return planmod.validate({"slug": "acme", "domain": "acme.com", "pages": ["https://acme.com/login"], "pricing": "https://acme.com/pricing",
                             "cdn_hosts": ["acme.com"]})


def routes(page=PAGE, app=APP, chunk=CHUNK, extra=None):
    r = {"https://acme.com/login": (200, page), "https://acme.com/static/app.js": (200, app), "https://acme.com/static/chunk-1.js": (200, chunk),
         "https://acme.com/pricing": (200, "<html><body><h1>Pricing</h1><p>Pro plan $12 per user per month. AI credits add-on for any plan.</p></body></html>")}
    r.update(extra or {})
    return r


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = storemod.Store(os.path.join(self.tmp.name, "u.db"))

    def tearDown(self):
        self.db.close(); self.tmp.cleanup()

    def run_once(self, fetcher, run_id, store=True):
        r = pipeline.run(plan(), fetcher, self.db if store else None, engine_version="test", run_id=run_id)
        out = os.path.join(self.tmp.name, "runs", run_id)
        paths = emit.write_run_folder(r, out)
        return r, paths

    def test_first_run_is_rich_ranked_and_leak_free(self):
        r, paths = self.run_once(FakeFetcher(routes()), "2026-10-30T100000Z")
        self.assertEqual(r.coverage.verdict(), "rich")
        keys = {o.key for o in r.observations}
        self.assertIn("make_local_ai_gateway", keys); self.assertIn("ai_assistant_mcp_client", keys); self.assertIn("weave_ai_models_plan", keys)
        self.assertNotIn("bobs_specials", keys)                                        # customer-named gate removed
        findings = [o.key for o in r.observations if o.tier == "finding"]
        self.assertIn("make_local_ai_gateway", findings); self.assertNotIn("cache_hydration_v2_rollout", findings)   # plumbing demoted
        # (a) no secret anywhere in the run folder; the customer's name not even in the log
        for name, p in paths.items():
            with open(p, encoding="utf-8") as f:
                body = f.read()
            self.assertNotIn(SK, body, name); self.assertNotIn("bobs_specials", body, name)
            self.assertNotIn(SK[8:], body, name)                                           # the whole token, not just its prefix
        md = open(paths["evidence.md"], encoding="utf-8").read()
        self.assertTrue(md.startswith("🔎 unreleased test · acme ·")); self.assertIn("## Coverage", md); self.assertIn("```text", md)
        self.assertIn("ai_credits_plan_add_on", md); self.assertIn("partially announced", md)      # pricing text carries "AI credits add-on"
        self.assertNotIn("## Since", md)
        # (B3) numbered siblings are two lines, and the header counts what is listed
        self.assertIn("`checkout_step_1`", md); self.assertIn("`checkout_step_2`", md)
        n = int(re.search(r"## Findings \((\d+);", md).group(1))
        self.assertEqual(n, len({re.sub(r"[^a-z0-9]+", "_", o.key.lower()) for o in r.observations if o.tier == "finding"}))

    def test_one_route_cluster_cannot_crowd_described_gates_off_the_page(self):
        """Linear's app shell: ~300 `/:orgKey/...` routes outranked the flag registry whose entries carry human descriptions,
        so the first 150 lines of evidence.md were all routes. A cluster gets CLUSTER_CAP lines; the rest is counted."""
        rs = "".join(f'{{path:"/:orgKey/settings/area{i}/thing{i}",name:"Thing {i}"}},' for i in range(400))
        app = 'const r=[' + rs + '];' + "x" * 3000
        r, paths = self.run_once(FakeFetcher(routes(app=app)), "2026-10-30T000000Z")
        md = open(paths["evidence.md"], encoding="utf-8").read()
        body = md.split("## Findings")[1]
        self.assertLess(body.count("/:orgKey/"), emit.CLUSTER_CAP + 2)
        self.assertIn("more `org_key` lines in evidence.jsonl", body)
        self.assertIn("weave_storyboard", body)           # the gate map still makes the page

    def test_since_overrides_the_previous_usable_run(self):
        f = FakeFetcher(routes())
        self.run_once(f, "2026-10-28T000000Z"); self.run_once(f, "2026-10-29T000000Z")
        r = pipeline.run(plan(), f, self.db, engine_version="test", run_id="2026-10-30T000000Z", since="2026-10-28T000000Z")
        self.assertEqual(r.diff.since_run, "2026-10-28T000000Z")


    def test_empty_second_run_never_diffs_and_is_not_a_baseline(self):
        self.run_once(FakeFetcher(routes()), "2026-10-30T100000Z")
        blocked = FakeFetcher({**routes(), "https://acme.com/login": (403, "")})
        r2, paths = self.run_once(blocked, "2026-10-30T110000Z")
        self.assertEqual(r2.coverage.verdict(), "could-not-see")
        self.assertIsNone(r2.diff)                                                       # (c) nothing read: no "removed since"
        self.assertNotIn("## Since", open(paths["evidence.md"], encoding="utf-8").read())
        r3, paths3 = self.run_once(FakeFetcher(routes(app=APP.replace("ai_assistant_slides:!0", "ai_assistant_slides:!1"))), "2026-10-30T120000Z")
        self.assertIsNotNone(r3.diff); self.assertEqual(r3.diff.since_run, "2026-10-30T100000Z")   # baseline skips the empty run
        self.assertEqual([x["key"] for x in r3.diff.flipped], ["ai_assistant_slides"])
        md = open(paths3["evidence.md"], encoding="utf-8").read()
        self.assertIn("flipped on→off since 2026-10-30", md)

    def test_a_moved_sample_is_newly_read_not_newly_present(self):
        # run 1 reads app.js + chunk-1; run 2 also discovers chunk-2 (new keys): those are "newly read", not added
        self.run_once(FakeFetcher(routes()), "2026-10-30T100000Z")
        page2 = PAGE.replace('<script src="https://acme.com/static/chunk-1.js"></script>', '<script src="https://acme.com/static/chunk-1.js"></script>\n<script src="https://acme.com/static/chunk-2.js"></script>')
        chunk2 = 'export const u={billing_credits_v3:!1,billing_wallet_topup:!1,billing_invoice_pdf:!0,billing_seat_cap:!1,billing_trial_extend:!1,billing_tax_ids:!1,billing_usage_alerts:!1,billing_proration_v2:!1};' + "z" * 2000
        r2, paths = self.run_once(FakeFetcher(routes(page=page2, extra={"https://acme.com/static/chunk-2.js": (200, chunk2)})), "2026-10-30T110000Z")
        self.assertIsNotNone(r2.diff)
        self.assertEqual(r2.diff.added, []); self.assertEqual(r2.diff.new_scripts_read, 1); self.assertGreaterEqual(r2.diff.added_in_new_scripts, 8)
        self.assertIn("newly read, not newly present", open(paths["evidence.md"], encoding="utf-8").read())

    def test_partial_read_withholds_removed(self):
        self.run_once(FakeFetcher(routes()), "2026-10-30T100000Z")
        # login blocked but pricing fine: a few observations survive (pricing is a signal), the diff must not call the rest "removed"
        half = FakeFetcher({**routes(), "https://acme.com/static/app.js": (403, ""), "https://acme.com/static/chunk-1.js": (403, "")})
        r2, paths = self.run_once(half, "2026-10-30T110000Z")
        self.assertEqual(r2.coverage.verdict(), "partial")
        if r2.diff is not None:
            self.assertEqual(r2.diff.removed, [], r2.diff.note); self.assertIn("withheld", r2.diff.note)

    def test_page_only_read_is_could_not_see(self):
        shell = '<html><body><script src="https://cdn.website-files.com/w.js"></script></body></html>'
        r, _ = self.run_once(FakeFetcher({"https://acme.com/login": (200, shell), "https://acme.com/pricing": (404, "")}), "2026-10-30T100000Z")
        self.assertEqual(r.coverage.scripts_fetched, 0); self.assertEqual(r.coverage.verdict(), "could-not-see")

    def test_html_on_a_script_url_is_schema_drift_not_code(self):
        r, _ = self.run_once(FakeFetcher(routes(chunk="<!doctype html><html><body>not found</body></html>")), "2026-10-30T100000Z")
        states = {s.source: s.state for s in r.coverage.sources}
        self.assertEqual(states["script:https://acme.com/static/chunk-1.js"], "schema-drift")
        self.assertNotIn("weave_ai_models_plan", {o.key for o in r.observations})

    def test_redirect_to_another_company_is_a_signal_not_first_party(self):
        import fetch as fetchmod, hashlib
        body = '<html><body><script src="https://www.contentsquare.com/app.js"></script></body></html>'
        f = fetchmod.Fetched("https://acme.com/login", "https://www.contentsquare.com/", 200, "ok", body, hashlib.sha256(body.encode()).hexdigest(), len(body), False)
        r, paths = self.run_once(FakeFetcher({**routes(), "https://acme.com/login": f}), "2026-10-30T100000Z")
        self.assertIn("redirect", {o.kind for o in r.observations})
        self.assertFalse(any("contentsquare" in d for d in r.attribution_decisions))
        self.assertIn("redirected off-domain", json.dumps([s.detail for s in r.coverage.sources]))

    def test_extractor_that_raises_is_an_outcome(self):
        import importlib
        mod = importlib.import_module("extractors.strings")
        orig = mod.extract
        mod.extract = lambda body, artifact: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            r, _ = self.run_once(FakeFetcher(routes()), "2026-10-30T100000Z")
        finally:
            mod.extract = orig
        self.assertIn("extractor:strings", {s.source for s in r.coverage.sources})
        self.assertIn("make_local_ai_gateway", {o.key for o in r.observations})      # the other shapes still read the body


class RateLimit(unittest.TestCase):
    def test_429_stops_the_host(self):
        import fetch as fetchmod
        calls = []

        class Resp:
            status = 429
            def read(self): return b""
            def geturl(self): return "https://acme.com/static/c0.js"
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *a): return False
        import urllib.error
        lf = fetchmod.LiveFetcher(min_interval=0, sleep=lambda s: None, now=lambda: 0.0)
        lf._once = lambda url, limit, kind="page": (calls.append(url), fetchmod.Fetched(url, url, 429, "rate-limited"))[1]
        a = lf.get("https://acme.com/static/c0.js", 10, "script"); b = lf.get("https://acme.com/static/c1.js", 10, "script")
        self.assertEqual((a.state, b.state), ("rate-limited", "rate-limited")); self.assertEqual(len(calls), 1)   # (d) one request, then stop


if __name__ == "__main__":
    unittest.main()
