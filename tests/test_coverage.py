"""Coverage verdict (ADR 0004): could-not-see when no first-party code was read; partial when something readable
was not (403, challenge, runtime-only flags, a source error); a hit cap is a budget note, not a failure."""
import os, sys, unittest
from helpers import FakeFetcher  # noqa: F401 (sets sys.path to the skill)
from schema import Coverage, SourceOutcome, ROBOTS_NOT_CHECKED, partial_sources
import report


def cov(states, byts=1000, scripts=3, observations=10):
    return Coverage(sources=[SourceOutcome(f"s{i}", st, 0, True, None) for i, st in enumerate(states)], first_party_bytes=byts,
                    scripts_fetched=scripts, observations=observations)


class TestVerdict(unittest.TestCase):
    def test_no_code_is_could_not_see(self):
        self.assertEqual(cov(["ok"], byts=0).verdict(), "could-not-see")
        self.assertEqual(cov(["blocked-403"], byts=0).verdict(), "could-not-see")

    def test_page_only_read_with_nothing_found_is_could_not_see(self):
        # review S1: a marketing shell whose scripts all live on a third-party host is not "rich"
        self.assertEqual(cov(["ok"], byts=129, scripts=0, observations=0).verdict(), "could-not-see")
        self.assertEqual(cov(["ok"], byts=50_000, scripts=0, observations=12).verdict(), "rich")   # inline page JSON counts

    def test_clean_run_is_rich(self):
        self.assertEqual(cov(["ok", "ok", "no-results", "skipped-unconfigured"]).verdict(), "rich")

    def test_budget_is_not_failure(self):
        # Sentry enumerates 1,888 chunks; reading 60 of them by role is the design, not a defect
        self.assertEqual(cov(["ok", "capped"]).verdict(), "rich")

    def test_failures_are_partial(self):
        for bad in ("blocked-403", "challenge", "runtime-only", "error", "unreachable", "timeout", "rate-limited"):
            self.assertEqual(cov(["ok", bad]).verdict(), "partial", bad)


class TestReason(unittest.TestCase):
    """Review blocker 1 (2026-11-17): the badge said "rich: every source read" over a read of 52 of 2,836 scripts. ADR 0005 stands (a
    cap is a budget); the words change: a capped rich run says what the budget left unread."""

    def test_rich_under_a_cap_never_claims_every_source_read(self):
        c = Coverage(sources=[SourceOutcome("crt", "ok"), SourceOutcome("scripts", "capped", 60, True,
                                                                         "read 60 of 2836 enumerated; cap 60 scripts / 120,000,000 bytes / 180 requests"),
                              SourceOutcome("sitemap", "capped")], first_party_bytes=1000, scripts_fetched=60, observations=10)
        self.assertEqual(c.verdict(), "rich")
        self.assertNotIn("every source read", c.verdict_reason())
        self.assertEqual(c.verdict_reason(), "rich: every source answered; under the budget cap: scripts read 60 of 2836 enumerated, sitemap")

    def test_rich_without_a_cap_still_says_every_source_read(self):
        self.assertEqual(cov(["ok", "no-results"]).verdict_reason(), "rich: every source read")

    def test_a_chunk_read_cut_short_is_partial_a_job_board_doubt_is_not(self):
        self.assertEqual(Coverage(sources=[SourceOutcome("chunks", "partial", 0, True, "8 chunk urls named by app.js answered 404 in a row: x")],
                                  first_party_bytes=1000, scripts_fetched=3, observations=10).verdict(), "partial")
        self.assertEqual(Coverage(sources=[SourceOutcome("ats", "partial", 0, True, "unverified board")],
                                  first_party_bytes=1000, scripts_fetched=3, observations=10).verdict(), "rich")

    def test_a_planned_page_robots_keeps_us_out_of_is_could_not_see_and_partial(self):
        c = Coverage(sources=[SourceOutcome("page:https://cursor.com/dashboard", "skipped-unconfigured", 0, False, ROBOTS_NOT_CHECKED),
                              SourceOutcome("page:https://cursor.com/", "ok", 1)], first_party_bytes=1000, scripts_fetched=3, observations=10)
        self.assertEqual(c.verdict(), "partial")
        self.assertIn("could not see", c.verdict_reason())
        self.assertIn("robots.txt", c.verdict_reason())

    def test_an_off_domain_redirect_page_is_a_signal_not_a_partial_run(self):
        c = Coverage(sources=[SourceOutcome("page:https://hotjar.com/x", "partial", 0, True, "redirected off-domain to contentsquare.com; x")],
                     first_party_bytes=1000, scripts_fetched=3, observations=10)
        self.assertEqual(c.verdict(), "rich")
        self.assertEqual(partial_sources([{"source": None, "state": "partial"}]), [])     # a null source never crashes the report

    def test_the_report_and_the_engine_share_one_rule(self):
        srcs = [{"source": "chunks", "state": "partial", "detail": "x"}]
        self.assertEqual(len(partial_sources(srcs)), 1)
        self.assertEqual(report._verdict({"first_party_bytes": 10, "sources": srcs}), "partial")
        self.assertEqual(report._verdict({"first_party_bytes": 10, "sources": [{"source": "scripts", "state": "capped"}]}), "rich")


if __name__ == "__main__":
    unittest.main()
