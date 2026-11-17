"""S2 seam: sources.ats.fetch(plan, fetcher) -> (jobs, outcomes) with identity verification (R13).

Expected values are read by hand from the fixtures (Greenhouse figma/lovable, Ashby linear, Lever palantir)
and from the readers' finding that Greenhouse `lovable` is an Italian lingerie retailer and Ashby `clarity`
a London startup. The Workable endpoints answered 429 keyless (tests/fixtures/sources/workable-*.attempt.json).
"""
import hashlib
import json
import unittest

from helpers import FakeFetcher, fixture, fixture_meta  # sets sys.path
import fetch as fetchmod
import plan as planmod
from sources import ats

GH = "https://boards-api.greenhouse.io/v1/boards/{}/jobs?content=false"
LEVER = "https://api.lever.co/v0/postings/{}?mode=json"
ASHBY = "https://api.ashbyhq.com/posting-api/job-board/{}"
WORKABLE = "https://apply.workable.com/api/v1/widget/accounts/{}?details=false"




def a_plan(slug, domain, **kw):
    raw = {"slug": slug, "domain": domain, "pages": [f"https://{domain}/"]}
    raw.update(kw)
    return planmod.validate(raw)


ASHBY_LOVABLE = json.dumps({"apiVersion": "1", "jobs": [
    {"id": "11111111-1111-4111-8111-111111111111", "title": "Growth Lead, Brazil", "department": "GTM", "team": "Growth", "location": "São Paulo",
     "publishedAt": "2026-09-29T10:00:00.000+00:00", "jobUrl": "https://jobs.ashbyhq.com/lovable/11111111-1111-4111-8111-111111111111",
     "descriptionPlain": "Lovable (lovable.dev) lets anyone build software by chatting. We are in Stockholm, London and NYC."},
    {"id": "22222222-2222-4222-8222-222222222222", "title": "Software Engineer, Agent Platform", "department": "EPD", "team": "Engineering", "location": "Stockholm",
     "publishedAt": "2026-10-02T10:00:00.000+00:00", "jobUrl": "https://jobs.ashbyhq.com/lovable/22222222-2222-4222-8222-222222222222",
     "descriptionPlain": "Build the agent that powers lovable.dev."},
]})


class Nouns(unittest.TestCase):
    def test_product_and_area_nouns_from_titles(self):
        cases = {
            "Staff PM, Accounting Products": ["Accounting Products"],
            "Senior Software Engineer, Grok Connectors": ["Grok Connectors"],
            "Product Manager, Coordinate": ["Coordinate"],
            "Software Engineer, Claude Marketplace": ["Claude Marketplace"],
            "Engineering Manager, Agentic Commerce": ["Agentic Commerce"],
            "Senior / Staff Fullstack Engineer": [],
            "Account Executive, Enterprise (Berlin, Germany)": ["Enterprise"],
            "Customer Success Manager - Figma Weave  (London, United Kingdom)": ["Figma Weave"],
            "Administrative Business Partner - ShipOS": ["ShipOS"],
            "Manager, Product Management - Figma Platform Experience": ["Figma Platform Experience"],
            "Senior Data Engineer": [],
            "Product Manager – Voice of the Customer": ["Voice of the Customer"],
            "Store Manager_Roma Est": [],
        }
        for title, want in cases.items():
            with self.subTest(title=title):
                self.assertEqual(ats.nouns(title), want)


class Boards(unittest.TestCase):
    def test_greenhouse_figma_is_verified_with_first_published_dates(self):
        self.assertEqual(fixture_meta("sources", "greenhouse-figma.json")["url"], GH.format("figma"))
        f = FakeFetcher({GH.format("figma"): (200, fixture("sources", "greenhouse-figma.json"))})
        jobs, outcomes = ats.fetch(a_plan("figma", "figma.com", ats={"greenhouse": "figma"}), f)
        self.assertEqual(len(jobs), 140)
        j = jobs[0]
        self.assertEqual((j.ats, j.slug, j.external_id, j.title, j.dept, j.location, j.posted_at, j.url),
                         ("greenhouse", "figma", "5426468004", "Account Executive, Enterprise", "", "San Francisco, CA • New York, NY • United States",
                          "2025-01-28", "https://boards.greenhouse.io/figma/jobs/5426468004?gh_jid=5426468004"))
        weave = next(x for x in jobs if "Figma Weave" in x.title)
        self.assertEqual(weave.nouns, ["Figma Weave"])
        self.assertEqual(len(outcomes), 1)
        o = outcomes[0]
        self.assertEqual((o.source, o.state, o.items), ("ats", "ok", 140))
        self.assertIn("board found on greenhouse as `figma`", o.detail)
        self.assertIn("verified", o.detail)
        self.assertEqual([c[0] for c in f.calls], [GH.format("figma")], "a verified board stops the search")
        self.assertTrue(all(c[2] == "api" for c in f.calls))

    def test_greenhouse_lovable_is_the_lingerie_retailer_and_comes_back_unverified(self):
        f = FakeFetcher({GH.format("lovable"): (200, fixture("sources", "greenhouse-lovable.json"))})
        jobs, outcomes = ats.fetch(a_plan("lovable", "lovable.dev"), f)
        self.assertEqual(len(jobs), 61, "the jobs are still returned")
        self.assertEqual(jobs[0].ats, "greenhouse")
        self.assertFalse(ats.verify(a_plan("lovable", "lovable.dev"), "greenhouse", "lovable", json.loads(fixture("sources", "greenhouse-lovable.json")))[0])
        o = outcomes[0]
        self.assertEqual(o.state, "partial")
        self.assertIn("unverified board greenhouse/lovable", o.detail)
        # every slug variant on every ATS was tried before settling for the unverified board
        self.assertIn(LEVER.format("lovable"), [c[0] for c in f.calls])
        self.assertIn(ASHBY.format("lovable"), [c[0] for c in f.calls])

    def test_the_right_lovable_board_is_found_on_ashby_after_the_wrong_greenhouse_one(self):
        f = FakeFetcher({GH.format("lovable"): (200, fixture("sources", "greenhouse-lovable.json")), ASHBY.format("lovable"): (200, ASHBY_LOVABLE)})
        jobs, outcomes = ats.fetch(a_plan("lovable", "lovable.dev"), f)
        self.assertEqual([j.ats for j in jobs], ["ashby", "ashby"])
        self.assertEqual((jobs[0].title, jobs[0].posted_at, jobs[0].dept, jobs[0].location), ("Growth Lead, Brazil", "2026-09-29", "GTM", "São Paulo"))
        self.assertEqual(jobs[1].nouns, ["Agent Platform"])
        self.assertEqual(outcomes[0].state, "ok")
        self.assertIn("board found on ashby as `lovable`", outcomes[0].detail)

    def test_plan_named_board_is_tried_first(self):
        f = FakeFetcher({GH.format("lovable"): (200, fixture("sources", "greenhouse-lovable.json")), ASHBY.format("lovable"): (200, ASHBY_LOVABLE)})
        jobs, outcomes = ats.fetch(a_plan("lovable", "lovable.dev", ats={"ashby": "lovable"}), f)
        self.assertEqual([c[0] for c in f.calls], [ASHBY.format("lovable")])
        self.assertEqual(len(jobs), 2)

    def test_ashby_linear_verified_by_domain_in_descriptions(self):
        self.assertEqual(fixture_meta("sources", "ashby-linear.json")["url"], ASHBY.format("linear"))
        f = FakeFetcher({ASHBY.format("linear"): (200, fixture("sources", "ashby-linear.json"))})
        jobs, outcomes = ats.fetch(a_plan("linear", "linear.app", ats={"ashby": "linear"}), f)
        self.assertEqual(len(jobs), 6)
        j = jobs[0]
        self.assertEqual((j.ats, j.external_id, j.title, j.dept, j.location, j.posted_at, j.url),
                         ("ashby", "d3bc1ced-3ce4-4086-a050-555055dbb1ff", "Senior / Staff Fullstack Engineer", "Product", "Europe", "2021-04-27",
                          "https://jobs.ashbyhq.com/linear/d3bc1ced-3ce4-4086-a050-555055dbb1ff"))
        self.assertEqual(outcomes[0].state, "ok")
        self.assertIn("board found on ashby as `linear`", outcomes[0].detail)

    def test_ashby_clarity_is_a_london_startup_not_microsoft(self):
        body = json.dumps({"apiVersion": "1", "jobs": [
            {"id": "f6467175-bde7-4069-b896-c8282324f9ca", "title": "Web: Full Stack Tech Lead", "department": "Engineering", "location": "Ideally London-based (Hybrid)",
             "publishedAt": "2025-09-17T00:00:00.000+00:00", "jobUrl": "https://jobs.ashbyhq.com/clarity/f6467175-bde7-4069-b896-c8282324f9ca",
             "descriptionPlain": "At Clarity we are building the future of customer insight from our London office."},
            {"id": "6aaec88c-a73d-4c56-a7bc-47a2c9e81628", "title": "Senior Data Engineer", "department": "Engineering", "location": "London (Remote)",
             "publishedAt": "2025-12-11T00:00:00.000+00:00", "jobUrl": "https://jobs.ashbyhq.com/clarity/6aaec88c-a73d-4c56-a7bc-47a2c9e81628",
             "descriptionPlain": "Clarity is a London startup. Join us."}]})
        f = FakeFetcher({ASHBY.format("clarity"): (200, body)})
        jobs, outcomes = ats.fetch(a_plan("clarity", "clarity.microsoft.com", ats={"ashby": "clarity"}), f)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(outcomes[0].state, "partial")
        self.assertIn("unverified board ashby/clarity", outcomes[0].detail)

    def test_lever_palantir_dates_from_created_at(self):
        self.assertEqual(fixture_meta("sources", "lever-palantir.json")["url"], LEVER.format("palantir"))
        f = FakeFetcher({LEVER.format("palantir"): (200, fixture("sources", "lever-palantir.json"))})
        jobs, outcomes = ats.fetch(a_plan("palantir", "palantir.com", ats={"lever": "palantir"}), f)
        self.assertEqual(len(jobs), 5)
        j = jobs[0]
        self.assertEqual((j.ats, j.external_id, j.title, j.dept, j.location, j.posted_at, j.url),
                         ("lever", "6ed76ce8-4156-4b60-b120-403538bd66cd", "Administrative Business Partner", "Administrative", "Singapore, Singapore", "2026-08-11",
                          "https://jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd"))
        self.assertEqual(jobs[1].nouns, ["ShipOS"])
        self.assertEqual(outcomes[0].state, "ok")
        self.assertIn("board found on lever as `palantir`", outcomes[0].detail)

    def test_anthropic_board_verified_for_claude_by_the_domain_label_in_titles(self):
        body = json.dumps({"jobs": [
            {"id": 1, "title": "Software Engineer, Claude Code", "absolute_url": "https://job-boards.greenhouse.io/anthropic/jobs/1", "location": {"name": "San Francisco, CA"},
             "updated_at": "2026-10-19T00:00:00-04:00", "first_published": "2026-08-01T00:00:00-04:00", "company_name": "Anthropic"},
            {"id": 2, "title": "Account Executive, Nonprofit", "absolute_url": "https://job-boards.greenhouse.io/anthropic/jobs/2", "location": {"name": "New York City, NY"},
             "updated_at": "2026-10-26T00:00:00-04:00", "first_published": "2026-09-01T00:00:00-04:00", "company_name": "Anthropic"}], "meta": {"total": 2}})
        f = FakeFetcher({GH.format("anthropic"): (200, body)})
        jobs, outcomes = ats.fetch(a_plan("claude", "claude.com", ats={"greenhouse": "anthropic"}), f)
        self.assertEqual(outcomes[0].state, "ok")
        self.assertEqual(jobs[0].nouns, ["Claude Code"])
        self.assertIn("board found on greenhouse as `anthropic`", outcomes[0].detail)


class Search(unittest.TestCase):
    def test_slug_variants_in_order(self):
        p = a_plan("hugging-face", "huggingface.co")
        self.assertEqual(ats.slug_variants(p), ["hugging-face", "huggingface"])
        self.assertEqual(ats.slug_variants(a_plan("clarity", "clarity.microsoft.com")), ["clarity"])

    def test_nothing_found_lists_what_was_tried_and_falls_back_to_the_careers_page(self):
        careers = "https://acme.com/careers"
        html = """<html><body><nav><a href="/">Home</a></nav><h1>Join Acme</h1><p>We are hiring across the company. Read on for our open roles and apply today.</p>
        <ul><li><a href="/careers/1">Senior Software Engineer, Billing Platform</a></li><li><a href="/careers/2">Product Manager, Coordinate</a></li>
        <li><a href="/careers/3">Head of Design</a></li></ul><p>Apply now</p><footer>© Acme</footer></body></html>"""
        f = FakeFetcher({careers: (200, html)})
        jobs, outcomes = ats.fetch(a_plan("acme", "acme.com", careers=careers), f)
        self.assertEqual([j.title for j in jobs], ["Senior Software Engineer, Billing Platform", "Product Manager, Coordinate", "Head of Design"])
        self.assertEqual({j.ats for j in jobs}, {"careers-page"})
        self.assertEqual(jobs[1].nouns, ["Coordinate"])
        self.assertEqual(jobs[0].url, "https://acme.com/careers/1")
        self.assertEqual([o.source for o in outcomes], ["ats", "careers-page"])
        self.assertEqual(outcomes[0].state, "no-results")
        self.assertIn("greenhouse/acme", outcomes[0].detail)
        self.assertIn("ashby/acme", outcomes[0].detail)
        self.assertEqual((outcomes[1].state, outcomes[1].items), ("partial", 3))
        self.assertIn("low confidence", outcomes[1].detail)
        self.assertEqual(f.calls[-1][0], careers)
        self.assertEqual(f.calls[-1][2], "page")

    def test_no_board_and_no_careers_page(self):
        jobs, outcomes = ats.fetch(a_plan("acme", "acme.com"), FakeFetcher({}))
        self.assertEqual(jobs, [])
        self.assertEqual([(o.source, o.state) for o in outcomes], [("ats", "no-results")])

    def test_workable_rate_limit_is_recorded_not_retried(self):
        url = WORKABLE.format("huggingface")
        f = FakeFetcher({url: (429, "")})
        jobs, outcomes = ats.fetch(a_plan("huggingface", "huggingface.co", ats={"workable": "huggingface"}), f)
        self.assertEqual(jobs, [])
        self.assertEqual([c[0] for c in f.calls].count(url), 1)
        self.assertEqual(outcomes[0].state, "rate-limited")          # unread is not empty (Raycast round: "no results" hid a 429)
        self.assertIn("workable/huggingface (rate-limited)", outcomes[0].detail)

    def test_workable_widget_shape_parses_when_it_answers(self):
        body = json.dumps({"name": "Hugging Face", "description": "The AI community building the future.", "jobs": [
            {"title": "Machine Learning Engineer, Kernels", "shortcode": "AB12CD", "department": "Engineering", "city": "Paris", "country": "France",
             "published_on": "2026-10-01", "url": "https://apply.workable.com/huggingface/j/AB12CD/"}]})
        f = FakeFetcher({WORKABLE.format("huggingface"): (200, body)})
        jobs, outcomes = ats.fetch(a_plan("huggingface", "huggingface.co", ats={"workable": "huggingface"}), f)
        j = jobs[0]
        self.assertEqual((j.ats, j.external_id, j.title, j.dept, j.location, j.posted_at, j.nouns), ("workable", "AB12CD", "Machine Learning Engineer, Kernels", "Engineering", "Paris, France", "2026-10-01", ["Kernels"]))
        self.assertEqual(outcomes[0].state, "ok")

    def test_403_on_a_board_is_recorded_and_never_retried(self):
        f = FakeFetcher({GH.format("figma"): (403, "")})
        jobs, outcomes = ats.fetch(a_plan("figma", "figma.com", ats={"greenhouse": "figma"}), f)
        self.assertEqual([c[0] for c in f.calls].count(GH.format("figma")), 1)
        self.assertIn("greenhouse/figma (blocked-403)", outcomes[0].detail)

    def test_health(self):
        url = "https://boards-api.greenhouse.io/v1/boards/greenhouse"
        f = FakeFetcher({url: (200, json.dumps({"name": "Greenhouse", "content": ""}))})
        out = ats.health(f)
        self.assertEqual((out.source, out.state), ("ats", "ok"))


if __name__ == "__main__":
    unittest.main()
