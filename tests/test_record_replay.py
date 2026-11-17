"""The benchmark is reproducible without the maintainers' corpus: `run --record` keeps what a run read in the layout
the recorded fetcher replays, and tools/run_corpus.py finds the products by the plan.json each recording holds."""
import dataclasses, os, sys, tempfile, unittest
from helpers import FakeFetcher, ROOT  # noqa: F401 (sets sys.path)
import pipeline, fetch as fetchmod
from test_pipeline import plan, routes

sys.path.insert(0, os.path.join(ROOT, "tools"))
import run_corpus  # noqa: E402


class RecordReplay(unittest.TestCase):
    def test_a_recorded_run_replays_to_the_same_findings(self):
        with tempfile.TemporaryDirectory() as corpus:
            run_dir = os.path.join(corpus, "acme", "2026-10-30T100000Z")
            rec = fetchmod.RecordingFetcher(FakeFetcher(routes()), run_dir)
            live = pipeline.run(plan(), rec, None, engine_version="test", run_id="2026-10-30T100000Z")
            rec.finish(live, dataclasses.asdict(plan()))
            for name in ("summary.json", "plan.json"):
                self.assertTrue(os.path.exists(os.path.join(run_dir, name)), name)
            targets = run_corpus.load_targets(corpus)
            self.assertEqual([t["slug"] for t in targets], ["acme"])
            replay = pipeline.run(plan(), fetchmod.RecordedFetcher(run_dir), None, engine_version="test", run_id="2026-10-30T100001Z",
                                  recorded_signals=os.path.join(run_dir, "summary.json"))
            code = lambda r: {o.key for o in r.observations if o.tier == "finding" and o.extractor not in ("site",)}
            self.assertTrue(code(live))
            self.assertEqual(code(replay), code(live))


    def test_a_failed_source_replays_as_failed_not_as_ok(self):
        """Second review: a live crt error replayed as `ok` (and a challenged pricing page as `no-results`)."""
        import json
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "summary.json")
            with open(p, "w") as fh:
                json.dump({"pages": [], "crt": {"recent": []}, "job_titles": [], "pricing": None,
                           "source_states": {"crt": "error", "ats": "rate-limited", "pricing": "challenge"}}, fh)
            _, _, _, outcomes = pipeline._recorded_signals(p, plan())
            self.assertEqual({o.source: o.state for o in outcomes}, {"crt": "error", "ats": "rate-limited", "pricing": "challenge"})

if __name__ == "__main__":
    unittest.main()
