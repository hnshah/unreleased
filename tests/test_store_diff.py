import os, tempfile, unittest
from helpers import *  # noqa: F401,F403
import store, diff
from schema import Observation, Source, Manifest, Subdomain, Job, PricingSnapshot


def ob(key, value=None, kind="gate", tier="finding", run="r1"):
    return Observation(id=f"{run}-{key}", kind=kind, key=key, value=value, tier=tier, extractor="t",
                       source=Source(url="https://x.com/a.js", sha256="ab" * 32, offset=1))


class StoreAndDiff(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(); self.s = store.Store(os.path.join(self.dir, "u.db"))

    def tearDown(self):
        self.s.close()

    def man(self, run_id, verdict="rich"):
        m = Manifest(run_id=run_id, product="acme", engine_version="t")
        self.s.record_run(m, verdict=verdict, seconds=1.0, first_party_bytes=10)
        return m

    def test_sightings_accumulate_first_and_last_seen(self):
        self.man("r1"); self.s.upsert_observations("acme", "r1", [ob("ff_a", False), ob("ff_b", True)])
        self.man("r2"); self.s.upsert_observations("acme", "r2", [ob("ff_a", True, run="r2"), ob("ff_c", False, run="r2")])
        rows = {o.key: o for o in self.s.observations("acme", "r2")}
        self.assertEqual(set(rows), {"ff_a", "ff_c"})
        meta = self.s.sightings("acme", "ff_a")
        self.assertEqual((meta["first_seen_run"], meta["last_seen_run"], meta["sighting_count"]), ("r1", "r2", 2))

    def test_previous_usable_run_skips_could_not_see(self):
        self.man("r1", "rich"); self.man("r2", "could-not-see"); self.man("r3", "partial")
        for rid in ("r1", "r3"):                                   # a baseline must have observations (SM-4)
            self.s.upsert_observations("acme", rid, [ob("ff_a", False, run=rid)])
        self.assertEqual(self.s.previous_usable_run("acme", before_run_id="r3"), "r1")
        self.assertEqual(self.s.previous_usable_run("acme", before_run_id="r4"), "r3")
        self.assertIsNone(self.s.previous_usable_run("acme", before_run_id="r1"))

    def test_diff_flips_added_removed_and_signals(self):
        prev = [ob("ff_a", False), ob("ff_b", True), ob("ff_gone", True), ob("/old", kind="route")]
        cur = [ob("ff_a", True), ob("ff_b", True), ob("ff_new", False), ob("/old", kind="route"), ob("/new", kind="route")]
        d = diff.compute(prev, cur,
                         [Subdomain("a.x.com", "2026-01-01")], [Subdomain("a.x.com", "2026-01-01"), Subdomain("b.x.com", "2026-10-01")],
                         [Job("ashby", "acme", "1", "PM, Coordinate")], [Job("ashby", "acme", "2", "Eng, Adapt")],
                         PricingSnapshot("u", "h1", 100, "ok", ["$10"]), PricingSnapshot("u", "h2", 100, "ok", ["$12", "New"]),
                         since_run="r1")
        self.assertEqual(d.flipped, [{"key": "ff_a", "from": False, "to": True}])
        self.assertEqual(d.added, ["ff_new"]); self.assertEqual(d.removed, ["ff_gone"])
        self.assertEqual(d.routes_added, ["/new"])
        self.assertEqual(d.subdomains_added, ["b.x.com"])
        self.assertEqual((d.jobs_added, d.jobs_removed), (["Eng, Adapt"], ["PM, Coordinate"]))
        self.assertTrue(d.pricing_changed); self.assertEqual(d.pricing_lines_changed, ["+$12", "+New", "-$10"])

    def test_store_signals_round_trip(self):
        self.man("r1")
        self.s.save_signals("acme", "r1", [Subdomain("a.x.com", "2026-01-01", "a", "", "x.com")], [Job("ashby", "acme", "1", "PM")], PricingSnapshot("u", "h", 5, "ok", ["$1"]))
        subs, jobs, pricing = self.s.signals("acme", "r1")
        self.assertEqual(subs[0].name, "a.x.com"); self.assertEqual(jobs[0].title, "PM"); self.assertEqual(pricing.sha256_text, "h")

    def test_brief_library_search(self):
        self.man("r1"); self.s.save_brief("acme", "r1", "/tmp/b.md", "Acme is testing a Cofounder surface with voice memory.")
        hits = self.s.search_briefs("cofounder")
        self.assertEqual(hits[0]["product"], "acme")


if __name__ == "__main__":
    unittest.main()
