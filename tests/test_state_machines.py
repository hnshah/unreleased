"""The state machines in docs/state-machines.md, tested at their edges: every test here reaches a state or transition
the document says is invalid, and asserts the engine refuses it. Each began as a confirmed bug (the issue number
is in the test name) or as a transition that was reachable and unguarded."""
import os, sqlite3, tempfile, unittest
from helpers import FakeFetcher  # noqa: F401 (sets sys.path)
import pipeline, emit, fetch as fetchmod, store as storemod, plan as planmod
from test_pipeline import plan, routes, APP, CHUNK


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.db = storemod.Store(os.path.join(self.tmp.name, "u.db"))

    def tearDown(self):
        self.db.close(); self.tmp.cleanup()

    def run_once(self, fetcher, run_id, **kw):
        return pipeline.run(plan(), fetcher, self.db, engine_version="test", run_id=run_id, **kw)

    def test_sm1_a_run_that_failed_mid_write_is_not_a_baseline(self):
        """SM-1. Run writes were four separate commits; a failure after `runs` and before `run_observations` left a
        'rich' run with no observations, and the next run diffed against it: everything 'added'."""
        self.run_once(FakeFetcher(routes()), "2026-10-30T100000Z")
        orig = self.db.upsert_observations
        def boom(*a, **k): raise sqlite3.OperationalError("disk I/O error")
        self.db.upsert_observations = boom
        with self.assertRaises(sqlite3.OperationalError):
            self.run_once(FakeFetcher(routes()), "2026-10-30T110000Z")
        self.db.upsert_observations = orig
        self.assertIsNone(self.db.db.execute("SELECT run_id FROM runs WHERE run_id='2026-10-30T110000Z'").fetchone(), "a failed run leaves no row")
        r3 = self.run_once(FakeFetcher(routes()), "2026-10-30T120000Z")
        self.assertEqual(r3.diff.since_run, "2026-10-30T100000Z"); self.assertEqual(r3.diff.added, [])

    def test_sm2_since_must_name_a_usable_run(self):
        """SM-2. `--since` was trusted: a missing, could-not-see or blocked id produced a diff against nothing."""
        self.run_once(FakeFetcher(routes()), "2026-10-30T100000Z")
        with self.assertRaises(ValueError) as cm:
            self.run_once(FakeFetcher(routes()), "2026-10-30T110000Z", since="2026-10-29T000000Z")
        self.assertIn("not a usable run", str(cm.exception))
        with self.assertRaises(ValueError):
            self.run_once(FakeFetcher(routes()), "2026-10-30T110000Z", since="2026-10-30T110000Z")      # itself
        r = self.run_once(FakeFetcher(routes()), "2026-10-30T120000Z", since="2026-10-30T100000Z")
        self.assertEqual(r.diff.since_run, "2026-10-30T100000Z")

    def test_sm3_a_run_id_is_never_reused(self):
        """SM-3. Two runs in one second shared an id: `runs` was replaced, `run_observations` became the union of both,
        checks and signals were inserted twice."""
        self.run_once(FakeFetcher(routes()), "2026-10-30T100000Z")
        before = self.db.db.execute("SELECT count(*) FROM checks WHERE run_id='2026-10-30T100000Z'").fetchone()[0]
        with self.assertRaises(ValueError) as cm:
            self.run_once(FakeFetcher(routes(app=APP.replace("ai_assistant_slides:!0", "ai_assistant_slides:!1"))), "2026-10-30T100000Z")
        self.assertIn("already", str(cm.exception))
        after = self.db.db.execute("SELECT count(*) FROM checks WHERE run_id='2026-10-30T100000Z'").fetchone()[0]
        self.assertEqual(before, after)
        self.assertNotEqual(pipeline.fresh_run_id(self.db, "acme", "2026-10-30T100000Z"), "2026-10-30T100000Z")   # the CLI asks for a free id

    def test_sm4_the_run_row_commits_last(self):
        """SM-1 again from the other side: a run is visible in `runs` only once its observations, signals and checks are."""
        r = self.run_once(FakeFetcher(routes()), "2026-10-30T100000Z")
        n = self.db.db.execute("SELECT count(*) FROM run_observations WHERE run_id=?", ("2026-10-30T100000Z",)).fetchone()[0]
        self.assertGreater(n, 0); self.assertEqual(self.db.previous_usable_run("acme", "2026-10-30T200000Z"), "2026-10-30T100000Z")
        self.db.db.execute("DELETE FROM run_observations WHERE run_id=?", ("2026-10-30T100000Z",)); self.db.db.commit()
        self.assertIsNone(self.db.previous_usable_run("acme", "2026-10-30T200000Z"), "a rich run with no observations is not a baseline")


class Fetching(unittest.TestCase):
    """The fetcher's host state: a 429 marks the host stopped for the run. Order of work decides what that costs."""

    def _fetcher(self, table):
        f = fetchmod.LiveFetcher(blobs=None, min_interval=0, sleep=lambda s: None, now=lambda: 0.0)
        import hashlib
        def once(url, limit, kind="page"):
            f.requests += 1; f.sent.append(url)
            r = table.get(url)
            if r is None:
                return fetchmod.Fetched(url, url, 404, "no-results")
            status, body = r
            if status != 200:
                return fetchmod.Fetched(url, url, status, fetchmod.classify_page(status, ""))
            data = body.encode()
            return fetchmod.Fetched(url, url, 200, fetchmod.classify_page(200, body, kind), body, hashlib.sha256(data).hexdigest(), len(data), False, "text/html" if body.startswith("<") else "text/javascript")
        f._once = once; f.calls = []; f.sent = []          # calls: asked of the fetcher; sent: requests actually made
        g = f.get
        def logged(url, limit, kind="page"):
            f.calls.append(url); return g(url, limit, kind)
        f.get = logged
        return f

    def test_sm5_a_route_probe_cannot_starve_pricing_and_changelog(self):
        """SM-5. Route probes ran before the pricing and changelog fetches; one 429 from a probe marked the product's host
        stopped and pricing came back 'rate-limited' without a request. Signals are read first; probes are last."""
        table = routes(app=APP + 'const nav=[{href:"/beta-portal"}];')
        table["https://acme.com/beta-portal"] = (429, "")
        f = self._fetcher(table)
        r = pipeline.run(plan(), f, None, engine_version="test", run_id="2026-10-30T100000Z")
        states = {s.source: s.state for s in r.coverage.sources}
        self.assertEqual(states["pricing"], "ok", states)
        self.assertLess(f.calls.index("https://acme.com/pricing"), f.calls.index("https://acme.com/beta-portal"))

    def test_sm6_a_landing_page_href_is_a_public_link_not_a_probe_candidate(self):
        """SM-6. Landing pages read by the site source were pooled with script bodies, so their links were probed as if
        found in code. A page the engine read is a public page; its links are live."""
        sm = '<urlset><url><loc>https://acme.com/webinars/one</loc><lastmod>2026-10-29</lastmod></url><url><loc>https://acme.com/webinars/two</loc><lastmod>2026-10-28</lastmod></url></urlset>'
        table = routes(app=APP + 'const nav=[{href:"/pricing-secret"}];')
        table.update({"https://acme.com/robots.txt": (200, "User-agent: *\nDisallow:\n"), "https://acme.com/sitemap.xml": (200, sm),
                      "https://acme.com/webinars/one": (200, '<html><body><h1>W</h1><a href="/pricing-secret">x</a></body></html>'),
                      "https://acme.com/webinars/two": (200, '<html><body><h1>W</h1></body></html>')})
        f = self._fetcher(table)
        pipeline.run(plan(), f, None, engine_version="test", run_id="2026-10-30T100000Z")
        self.assertNotIn("https://acme.com/pricing-secret", f.calls)

    def test_sm8_a_manifest_of_missing_chunks_stops_costing_requests(self):
        """SM-8. An app shell named 129 chunks that answered 404 (a manifest from another deploy); each miss cost one of
        the 180 requests and the run read 51 scripts instead of 60. After MISS_STREAK consecutive 404s on discovered
        chunks the rest are skipped without a request, and coverage says so."""
        names = "".join(f'"/static/c{i}.abc{i:04d}.js",' for i in range(40))
        table = routes(app=APP + f"const chunks=[{names}];")
        f = self._fetcher(table)
        r = pipeline.run(plan(), f, None, engine_version="test", run_id="2026-10-30T100000Z")
        misses = [u for u in f.calls if "/static/c" in u and ".abc" in u]
        self.assertEqual(len(misses), 8, misses)
        self.assertIn(("chunks", "partial"), {(s.source, s.state) for s in r.coverage.sources})
        # ADR 0007: a read cut short by a dead chunk map is a failure to read, not a budget; the cap still is one
        self.assertEqual(r.coverage.verdict(), "partial")
        self.assertIn("app.js", r.coverage.verdict_reason())

    def test_robots_disallowed_app_paths_are_could_not_see_never_read_or_clean(self):
        """Review blocker 3 (2026-11-17). Cursor's robots.txt disallows /dashboard and /agents. The policy holds (never requested), but
        the run used to drop them silently: the brief read a gated app as "nothing found". They are now listed as not
        checked, a planned page the robots file keeps us out of makes the run partial, and nothing under them is read."""
        import emit
        p = planmod.validate({"slug": "acme", "domain": "acme.com", "pages": ["https://acme.com/login", "https://acme.com/dashboard"],
                              "pricing": "https://acme.com/pricing", "cdn_hosts": ["acme.com"]})
        table = routes(app=APP + 'const nav=[{href:"/agents"},{href:"/labs-beta"}];')
        table["https://acme.com/robots.txt"] = (200, "User-agent: *\nDisallow: /dashboard\nDisallow: /agents\n")
        f = self._fetcher(table)
        r = pipeline.run(p, f, None, engine_version="test", run_id="2026-10-30T100000Z")
        self.assertFalse([u for u in f.sent if "/dashboard" in u or "/agents" in u], "policy: a disallowed path is never requested")
        self.assertIn("https://acme.com/labs-beta", f.sent)                                    # allowed paths are still probed
        self.assertEqual(r.coverage.verdict(), "partial")
        self.assertIn("could not see", r.coverage.verdict_reason())
        src = {s.source: s for s in r.coverage.sources}
        self.assertIn("/agents", src["routes:robots"].detail)
        md = emit.evidence_md(r)
        self.assertRegex(md, r"- could not see: https://acme.com/dashboard, /agents \(not checked: the site's robots.txt asks crawlers to stay out")
        agents = [o for o in r.observations if o.kind == "route" and o.key == "/agents"]
        self.assertTrue(agents and all("could not see" in o.context for o in agents))

    def test_no_flag_sdk_under_a_cap_is_said_as_unread_not_absent(self):
        """Fresh-host trial (2026-11-17): a brief said "No runtime flag provider was detected" over a read of 60 of 2,841 scripts."""
        from schema import Coverage
        from pipeline import RunResult
        import emit
        r = pipeline.run(plan(), self._fetcher(routes()), None, engine_version="test", run_id="2026-10-30T100000Z")
        r.coverage.cap_hit = True; r.coverage.scripts_enumerated = 2841; r.coverage.runtime_flag_providers = []
        self.assertIn(f"- flag SDKs: none seen in the {r.coverage.scripts_fetched} scripts read; the other", emit.evidence_md(r))
        r.coverage.cap_hit = False
        self.assertNotIn("- flag SDKs:", emit.evidence_md(r))

    def test_sm8_a_dead_chunk_map_stops_only_its_own_chunks(self):
        """2026-11-17 review. The stop was global: after eight 404s from one stale map, every other script's chunks were skipped too,
        and Notion read 52 of 2,836 scripts. A dead map now costs only its own chunks."""
        names = "".join(f'"/static/c{i}.abc{i:04d}.js",' for i in range(40))
        live = "".join(f'"/static/l{i}.def{i:04d}.js",' for i in range(5))        # hashed too: read after the dead ones
        table = routes(app=APP + f"const chunks=[{names}];", chunk=CHUNK + f"const more=[{live}];")
        table.update({f"https://acme.com/static/l{i}.def{i:04d}.js": (200, f"var live{i}=1;") for i in range(5)})
        f = self._fetcher(table)
        r = pipeline.run(plan(), f, None, engine_version="test", run_id="2026-10-30T100000Z")
        self.assertEqual(len([u for u in f.calls if ".abc" in u]), 8)
        self.assertEqual(sorted(u for u in f.calls if ".def" in u), [f"https://acme.com/static/l{i}.def{i:04d}.js" for i in range(5)])

    def test_sm7_a_dead_host_is_asked_three_times_not_a_hundred_and_eighty(self):
        """SM-7. Every script on a host that times out cost a 30 s request; 60 scripts and 180 requests of budget made a
        down CDN an hour-long run. After DEAD_AFTER consecutive failures the host is unreachable without a request."""
        f = fetchmod.LiveFetcher(blobs=None, min_interval=0, sleep=lambda s: None, now=lambda: 0.0)
        calls = []
        def once(url, limit, kind="page"):
            if url.endswith("/robots.txt"):
                return fetchmod.Fetched(url, url, 404, "no-results")      # robots answered; the scripts time out
            calls.append(url); return fetchmod.Fetched(url, url, "error", "timeout")
        f._once = once
        for i in range(10):
            r = f.get(f"https://cdn.acme.com/{i}.js", 1000, "script")
        self.assertEqual(len(calls), fetchmod.DEAD_AFTER); self.assertEqual(r.state, "unreachable")
        f._once = lambda url, limit, kind="page": fetchmod.Fetched(url, url, 200, "ok", "x", "a" * 64, 1, False)
        self.assertEqual(f.get("https://other.acme.com/a.js", 1000, "script").state, "ok")        # another host is unaffected


if __name__ == "__main__":
    unittest.main()
