"""Salience (R7): the readers' hand-picked Figma/Loom/Cursor findings must rank above plumbing keys from the
same maps. Expected values come from the readers' write-ups, not from the implementation."""
import os, sys, unittest
from helpers import FakeFetcher  # noqa: F401 (sets sys.path to the skill)
import salience
from schema import Observation, Source

SRC = Source(url="https://example.com/app.js", sha256="0" * 64, offset=10, first_party=True, attribution="domain")


def gate(key, value=False, context="", kind="gate"):
    return Observation(id="e1", kind=kind, key=key, source=SRC, value=value, context=context, tier="finding", confidence="high")


READER_FINDINGS = [   # the readers' hand findings (tests/goldens)
    "make_local_ai_gateway", "sites_code_layers_code_only", "weave_ai_models_plan", "ai_agent_waitlist", "make_cloud_github_code_panel",
    "loom-agentic-workflows", "cursor_background_agents_pricing", "slides_ai_credits_starter", "figjam_whiteboard_mcp", "weave_video_trim",
]
READER_PLUMBING = [   # the readers skipped these as mechanics
    "perf_log_sampling_rate", "cache_hydration_v2_rollout", "sentry_trace_sample_pct", "ds_lint_fix_migration", "render_virtualized_list_fallback",
    "webpack_chunk_prefetch", "debug_timeout_retry_batch", "legacy_polyfill_shim", "ws_poll_interval_ms", "gc_memory_pressure_guard",
]


class TestSalience(unittest.TestCase):
    def test_reader_findings_are_findings(self):
        for k in READER_FINDINGS:
            self.assertGreaterEqual(salience.score(gate(k)), salience.FINDING_MIN, k)

    def test_plumbing_is_not(self):
        for k in READER_PLUMBING:
            self.assertLess(salience.score(gate(k)), salience.FINDING_MIN, k)

    def test_every_finding_outranks_every_plumbing_key(self):
        lo = min(salience.score(gate(k)) for k in READER_FINDINGS)
        hi = max(salience.score(gate(k)) for k in READER_PLUMBING)
        self.assertGreater(lo, hi)

    def test_analytics_events_and_site_navigation_are_not_findings(self):
        # Linear live run: a tracking-event table and the marketing nav outranked the waitlists
        for k, kind in [("SIGN_UP_CLICKED", "enum"), ("QUALITY_VIDEO_HEARTBEAT", "enum"), ("PRICING_CYCLE_TOGGLED", "enum"), ("ASKS_BOOK_DEMO_CLICKED", "enum"),
                        ("/login", "route"), ("/signup", "route"), ("/pricing", "route"), ("/changelog/2026-10-22-slack-and-github-loops", "route"), ("/docs/api", "route")]:
            self.assertLess(salience.score(gate(k, kind=kind)), salience.FINDING_MIN, k)
        for k, kind in [("MOBILE_DIFFS_WAITLIST", "hidden"), ("/mobile-diffs", "route"), ("AGENTS_WAITLIST", "hidden"), ("/agents-waitlist", "route")]:
            self.assertGreaterEqual(salience.score(gate(k, kind=kind)), salience.FINDING_MIN, k)

    def test_human_context_lifts_a_codename(self):
        bare = gate("prj_zephyr_2", context="")
        named = gate("prj_zephyr_2", context='title: "Zephyr beta: Share drafts with your team"')
        self.assertLess(salience.score(bare), salience.FINDING_MIN)
        self.assertGreaterEqual(salience.score(named), salience.FINDING_MIN)

    def test_apply_demotes_in_place_and_keeps_signals(self):
        obs = [gate("make_local_ai_gateway"), gate("perf_log_sampling_rate"), gate("eng-hiring-2026", kind="job")]
        salience.apply(obs)
        self.assertEqual([o.tier for o in obs], ["finding", "key-list", "finding"])
        self.assertTrue(all(o.salience == salience.score(o) for o in obs))

    def test_cluster_is_first_two_segments(self):
        self.assertEqual(salience.cluster("make_local_ai_gateway"), "make_local")
        self.assertEqual(salience.cluster("loom-agentic-workflows"), "loom_agentic")
        self.assertEqual(salience.cluster("weaveAiModelsPlan"), "weave_ai")
        self.assertEqual(salience.cluster("x"), "x")


if __name__ == "__main__":
    unittest.main()


class Novelty(unittest.TestCase):
    def test_the_unannounced_sibling_rises_above_announced_ones(self):
        from schema import Observation, Source
        S = Source("u", "a" * 64, 0)
        sib = [Observation(f"o{i}", "route", f"/settings/organizations/:handle/{k}", S, tier="finding", salience=5)
               for i, k in enumerate(["ai-api-keys", "mcp-servers", "external-agents", "billing"])]
        lone = Observation("o9", "route", "/extension-issues", S, tier="finding", salience=4)
        salience.novelty(sib + [lone], {"o0": "announced", "o1": "announced", "o2": "none", "o3": "partial", "o9": "none"})
        self.assertEqual([o.salience for o in sib], [2, 2, 8, 5]); self.assertEqual(lone.salience, 4)   # a cluster of one is left alone

    def test_a_cluster_with_nothing_announced_is_not_reordered(self):
        from schema import Observation, Source
        S = Source("u", "a" * 64, 0)
        sib = [Observation(f"o{i}", "gate", f"weave_{k}", S, tier="finding", salience=5) for i, k in enumerate(["shaders", "motion"])]
        salience.novelty(sib, {"o0": "none", "o1": "unchecked"})
        self.assertEqual([o.salience for o in sib], [5, 5])
