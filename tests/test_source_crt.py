"""S2 seam: sources.crt.fetch(plan, fetcher) -> (subdomains, outcomes) and sources.crt.health(fetcher).

Expected values come from the corpus (results/linear/<run>/subdomains.tsv: md.sandbox 2026-08-21, orbit
2026-08-24) and from a hand count of the fixture's distinct names, never from running the source.
"""
import datetime as dt
import hashlib
import json
import unittest

from helpers import FakeFetcher, fixture, fixture_meta  # sets sys.path
import fetch as fetchmod
import plan as planmod
from sources import crt

CRT = "https://crt.sh/?q=%25.{}&output=json"




def linear_plan(**kw):
    raw = {"slug": "linear", "domain": "linear.app", "pages": ["https://linear.app/login"], "apexes": ["linear.app"]}
    raw.update(kw)
    return planmod.validate(raw)


class ParseName(unittest.TestCase):
    """Environment conventions from the corpus (R12): -test/-staging/-prod-N, .p./.i./.preview., -dev/-sandbox/-canary."""

    def test_env_conventions(self):
        cases = {
            ("tidewater.preview.claude.ai", "claude.ai"): ("tidewater", "preview"),
            ("git-proxy.origin-test.cursor.com", "cursor.com"): ("git-proxy.origin", "test"),
            ("git-proxy.origin-staging.cursor.com", "cursor.com"): ("git-proxy.origin", "staging"),
            ("api.origin.cursor.com", "cursor.com"): ("api.origin", ""),
            ("ml-environments-staging.internal.cursor.com", "cursor.com"): ("ml-environments", "staging/internal"),
            ("usage-xai.internal.cursor.com", "cursor.com"): ("usage-xai", "internal"),
            ("api.e2b.prod-2.p.perplexity.ai", "perplexity.ai"): ("api.e2b", "prod-2/prod"),
            ("space-api-prod-3.perplexity.ai", "perplexity.ai"): ("space-api", "prod-3"),
            ("cachew.testing.p.perplexity.ai", "perplexity.ai"): ("cachew", "test/prod"),
            ("aster.preview.i.perplexity.ai", "perplexity.ai"): ("aster", "preview/internal"),
            ("wiki.i.perplexity.ai", "perplexity.ai"): ("wiki", "internal"),
            ("loupe.prod.figma.com", "figma.com"): ("loupe", "prod"),
            ("md.sandbox.linear.app", "linear.app"): ("md", "sandbox"),
            ("sandbox.linear.app", "linear.app"): ("sandbox", "sandbox"),
            ("zendesk-dev.linear.app", "linear.app"): ("zendesk", "dev"),
            ("grafana-cloud-obsv-test.duolingo.com", "duolingo.com"): ("grafana-cloud-obsv", "test"),
            ("infra-cicd-events-write-gateway-prod.duolingo.com", "duolingo.com"): ("infra-cicd-events-write-gateway", "prod"),
            ("preprod-terminal-device.stripe.com", "stripe.com"): ("terminal-device", "preprod"),
            ("community-canary.spotify.com", "spotify.com"): ("community", "canary"),
            ("admin-api-europe-west1.linear.app", "linear.app"): ("admin-api", ""),
            ("ap-southeast-1.webhooks.supabase.com", "supabase.com"): ("webhooks", ""),
            ("www.linear.app", "linear.app"): ("www", ""),
        }
        for (name, apex), want in cases.items():
            with self.subTest(name=name):
                self.assertEqual(crt.parse_name(name, apex), want)


class ParseRows(unittest.TestCase):
    def rows(self):
        return json.loads(fixture("sources", "crt-linear.json"))

    def test_fixture_provenance_is_recorded(self):
        meta = fixture_meta("sources", "crt-linear.json")
        self.assertEqual(meta["url"], CRT.format("linear.app"))
        self.assertTrue(meta["sha256_full"] and meta["reduction"])

    def test_first_seen_is_earliest_not_before_and_wildcards_malformed_apex_are_dropped(self):
        subs = crt.parse_rows(self.rows(), "linear.app")
        by_name = {s.name: s for s in subs}
        # the corpus's subdomains.tsv for linear (the readers' run) is the independent expectation
        self.assertEqual(by_name["md.sandbox.linear.app"].first_seen, "2026-08-21")
        self.assertEqual(by_name["orbit.linear.app"].first_seen, "2026-08-24")
        self.assertEqual(by_name["api.linear.app"].first_seen, "2018-07-04")
        self.assertEqual((by_name["md.sandbox.linear.app"].stem, by_name["md.sandbox.linear.app"].env, by_name["md.sandbox.linear.app"].apex),
                         ("md", "sandbox", "linear.app"))
        self.assertEqual(by_name["zendesk-dev.linear.app"].env, "dev")
        self.assertFalse([n for n in by_name if n.startswith("*.")], "wildcards are skipped")
        self.assertFalse([n for n in by_name if "http" in n], "malformed rows are dropped")
        self.assertNotIn("linear.app", by_name, "the apex itself is not a subdomain")
        # 66 distinct name_values in the full response = 13 wildcards + 1 malformed + 1 apex + 51 subdomains
        self.assertEqual(len(subs), 51)
        self.assertEqual(len(by_name), 51, "one record per name")

    def test_machine_generated_labels_collapse_to_a_pattern_with_count_and_range(self):
        rows = [{"name_value": f"preview-{i:06x}abcdef.lovable.app", "not_before": f"2026-0{1 + i % 9}-1{i % 10}T00:00:00"} for i in range(250)]
        rows.append({"name_value": "docs.lovable.app", "not_before": "2025-03-01T00:00:00"})
        rows.append({"name_value": "3fa85f64-5717-4562-b3fc-2c963f66afa6.lovable.app", "not_before": "2026-02-02T00:00:00"})
        subs = crt.parse_rows(rows, "lovable.app")
        names = {s.name: s for s in subs}
        self.assertIn("docs.lovable.app", names)
        self.assertIn("preview-*.lovable.app", names)
        self.assertIn("*.lovable.app", names, "a bare uuid label collapses to *")
        flood = names["preview-*.lovable.app"]
        self.assertEqual((flood.stem, flood.count), ("preview-*", 250))          # the count is a field, not text in the stem (review S15)
        self.assertEqual(flood.first_seen, "2026-01-10"); self.assertTrue(flood.last_seen >= flood.first_seen)
        self.assertEqual(len(subs), 3)

    def test_a_zone_flood_of_distinct_leaves_below_the_apex_collapses_once_over_200(self):
        words = ["happy", "tiger", "blue", "river", "soft", "cloud", "quick", "fox", "green", "leaf", "bold", "sun", "wild", "oak", "calm", "sea"]
        rows = [{"name_value": f"{words[i % 16]}-{words[(i // 16) % 16]}.preview.lovableproject.com", "not_before": f"2026-05-{1 + i % 28:02d}T00:00:00"} for i in range(201)]
        rows += [{"name_value": "docs.lovableproject.com", "not_before": "2026-05-01T00:00:00"},
                 {"name_value": "pr-1234.dwl.lovable.dev", "not_before": "2026-06-01T00:00:00"},
                 {"name_value": "pr-1235.dwl.lovable.dev", "not_before": "2026-06-02T00:00:00"}]
        subs = crt.parse_rows(rows, "lovableproject.com") + crt.parse_rows(rows, "lovable.dev")
        names = {s.name: s for s in subs}
        self.assertIn("*.preview.lovableproject.com", names)
        flood = names["*.preview.lovableproject.com"]
        self.assertEqual((flood.stem, flood.env, flood.first_seen, flood.count, flood.last_seen), ("*", "preview", "2026-05-01", 201, "2026-05-28"))
        self.assertIn("docs.lovableproject.com", names)
        self.assertIn("pr-*.dwl.lovable.dev", names)
        self.assertEqual(names["pr-*.dwl.lovable.dev"].first_seen, "2026-06-01")
        self.assertEqual(len(subs), 3)

    def test_many_real_names_directly_under_the_apex_are_not_collapsed(self):
        # gitlab has 504 distinct names and asana 1,036: real hosts, not a flood; the pipeline groups them by stem
        words = ["docs", "about", "forum", "handbook", "status", "registry", "design", "packages", "customers", "partners", "events", "learn", "gitlab", "store", "facade", "ops", "mail"]
        rows = [{"name_value": f"{words[i % 17]}-{words[(i // 17) % 17]}.gitlab.com", "not_before": "2024-01-01T00:00:00"} for i in range(289)]
        rows += [{"name_value": f"{w}.gitlab.com", "not_before": "2024-01-01T00:00:00"} for w in words[:11]]
        subs = crt.parse_rows(rows, "gitlab.com")
        self.assertEqual(len(subs), 300)


class FetchSeam(unittest.TestCase):
    def test_fetch_queries_every_apex_and_returns_records_and_outcomes(self):
        body = fixture("sources", "crt-linear.json")
        f = FakeFetcher({CRT.format("linear.app"): (200, body), CRT.format("linear.dev"): (200, "[]")})
        subs, outcomes = crt.fetch(linear_plan(apexes=["linear.app", "linear.dev"]), f)
        self.assertEqual([c[0] for c in f.calls], [CRT.format("linear.app"), CRT.format("linear.dev")])
        self.assertTrue(all(c[2] == "api" for c in f.calls))
        self.assertEqual(len(subs), 51)
        self.assertEqual([(o.source, o.state, o.items) for o in outcomes], [("crt", "ok", 51), ("crt", "no-results", 0)])
        self.assertIn("linear.app", outcomes[0].detail)
        self.assertIn("linear.dev", outcomes[1].detail)

    def test_http_error_is_retried_once_then_recorded(self):
        f = FakeFetcher({CRT.format("linear.app"): (503, "")})
        subs, outcomes = crt.fetch(linear_plan(), f)
        self.assertEqual(subs, [])
        self.assertEqual(len(f.calls), 3, "two polite retries with backoff on a 5xx (crt.sh answers 502 intermittently)")
        self.assertEqual(outcomes[0].state, "unreachable")

    def test_403_is_never_retried(self):
        f = FakeFetcher({CRT.format("linear.app"): (403, "")})
        subs, outcomes = crt.fetch(linear_plan(), f)
        self.assertEqual(len(f.calls), 1)
        self.assertEqual(outcomes[0].state, "blocked-403")

    def test_timeout_is_recorded(self):
        f = FakeFetcher({CRT.format("linear.app"): fetchmod.Fetched(CRT.format("linear.app"), CRT.format("linear.app"), "error", "timeout")})
        subs, outcomes = crt.fetch(linear_plan(), f)
        self.assertEqual(outcomes[0].state, "timeout")

    def test_truncated_response_is_capped(self):
        body = fixture("sources", "crt-linear.json")
        url = CRT.format("linear.app")
        f = FakeFetcher({url: fetchmod.Fetched(url, url, 200, "ok", body, "x", len(body), truncated=True)})
        subs, outcomes = crt.fetch(linear_plan(), f)
        self.assertEqual(outcomes[0].state, "capped")
        self.assertIn("truncated", outcomes[0].detail)

    def test_wildcard_dominated_result_is_capped_not_absence(self):
        rows = [{"name_value": f"*.z{i}.cloudflare.com", "not_before": "2020-01-01T00:00:00"} for i in range(80)]
        rows += [{"name_value": "www.cloudflare.com", "not_before": "2019-01-01T00:00:00"}]
        url = CRT.format("cloudflare.com")
        f = FakeFetcher({url: (200, json.dumps(rows))})
        subs, outcomes = crt.fetch(linear_plan(slug="cloudflare", domain="cloudflare.com", apexes=["cloudflare.com"]), f)
        self.assertEqual(len(subs), 1)
        self.assertEqual(outcomes[0].state, "capped")
        self.assertIn("wildcards", outcomes[0].detail)

    def test_cap_like_row_count_with_nothing_recent_is_capped(self):
        rows = [{"name_value": f"h{i}.asana.com", "not_before": "2020-01-01T00:00:00"} for i in range(5000)]
        url = CRT.format("asana.com")
        f = FakeFetcher({url: (200, json.dumps(rows))})
        subs, outcomes = crt.fetch(linear_plan(slug="asana", domain="asana.com", apexes=["asana.com"]), f, today=dt.date(2026, 10, 30))
        self.assertEqual(outcomes[0].state, "capped")
        self.assertIn("unverifiable", outcomes[0].detail)

    def test_non_json_body_is_an_error(self):
        f = FakeFetcher({CRT.format("linear.app"): (200, "<html>502 Bad Gateway</html>")})
        subs, outcomes = crt.fetch(linear_plan(), f)
        self.assertEqual(outcomes[0].state, "error")

    def test_health_does_one_small_query(self):
        url = CRT.format("example.com")
        f = FakeFetcher({url: (200, json.dumps([{"name_value": "www.example.com", "not_before": "2024-01-01T00:00:00"}]))})
        out = crt.health(f)
        self.assertEqual((out.source, out.state), ("crt", "ok"))
        self.assertEqual(len(f.calls), 1)


if __name__ == "__main__":
    unittest.main()
