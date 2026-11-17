"""The site source: robots.txt disallow prefixes are a published list, the sitemap says which compare page exists
before any page links to it, the headline shared by the landing pages read is the winner — and nothing under a
Disallow is ever fetched."""
import os, sys, tempfile, unittest
from helpers import FakeFetcher  # noqa: F401 (sets sys.path)
import pipeline, emit, plan as planmod, store as storemod
from sources import site

ROBOTS = """User-agent: *
Disallow: /lp/
Disallow: /go/
Disallow: /account/
Disallow:
Sitemap: https://acme.com/sitemap_index.xml

User-agent: GPTBot
Disallow: /lp/
"""
INDEX = """<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://acme.com/sitemap-blog.xml</loc></sitemap>
<sitemap><loc>https://acme.com/sitemap-pages.xml</loc><lastmod>2026-10-30</lastmod></sitemap>
</sitemapindex>"""
PAGES = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://acme.com/</loc><lastmod>2026-10-01</lastmod></url>
<url><loc>https://acme.com/pricing</loc><lastmod>2024-01-01</lastmod></url>
<url><loc>https://acme.com/compare/acme-vs-globex</loc><lastmod>2026-10-28</lastmod></url>
<url><loc>https://acme.com/compare/acme-vs-initech</loc><lastmod>2025-03-01</lastmod></url>
<url><loc>https://acme.com/webinars/agents-101</loc><lastmod>2026-10-20</lastmod></url>
<url><loc>https://acme.com/webinars/agents-102</loc><lastmod>2026-10-21</lastmod></url>
<url><loc>https://acme.com/webinars/agents-103</loc><lastmod>2026-10-22</lastmod></url>
<url><loc>https://acme.com/lp/black-friday</loc><lastmod>2026-10-29</lastmod></url>
<url><loc>https://other.example/evil</loc></url>
</urlset>"""
BLOG = """<urlset><url><loc>https://acme.com/blog/hello</loc><lastmod>2026-10-29</lastmod></url></urlset>"""
HOME = """<html><body><a href="/pricing">Pricing</a><a href="/compare/acme-vs-initech">vs Initech</a><script src="/app.js"></script></body></html>"""
APP = "window.__FLAGS__={ai_assistant_mcp_client:!1,ai_assistant_websearch:!1,ai_assistant_slides:!0,billing_lifecycle_v2:!1,checkout_step_1:!1,checkout_step_2:!1,sites_code_layers:!1,weave_shaders:!1};" + "x" * 3000


def lp(h):
    return f"<html><head><title>{h} | Acme</title></head><body><h1>{h}</h1><p>copy</p></body></html>"


def routes():
    return {"https://acme.com/login": (200, HOME), "https://acme.com/app.js": (200, APP), "https://acme.com/robots.txt": (200, ROBOTS),
            "https://acme.com/sitemap_index.xml": (200, INDEX), "https://acme.com/sitemap-pages.xml": (200, PAGES), "https://acme.com/sitemap-blog.xml": (200, BLOG),
            "https://acme.com/webinars/agents-101": (200, lp("Ship agents without the on-call")),
            "https://acme.com/webinars/agents-102": (200, lp("Ship agents without the on-call")),
            "https://acme.com/webinars/agents-103": (200, lp("Agents for ops teams")),
            "https://acme.com/lp/black-friday": (200, lp("SHOULD NEVER BE FETCHED"))}


class SiteSource(unittest.TestCase):
    def setUp(self):
        self.plan = planmod.validate({"slug": "acme", "domain": "acme.com", "pages": ["https://acme.com/login"], "cdn_hosts": ["acme.com"]})

    def test_robots_prefixes_are_listed_and_never_fetched(self):
        f = FakeFetcher(routes())
        obs, outcomes, bodies = site.fetch(self.plan, f)
        rob = {o.key: o.tier for o in obs if o.kind == "robots"}
        self.assertEqual(rob, {"/lp/": "finding", "/go/": "finding", "/account/": "key-list"})      # deduped across UA blocks; bare Disallow skipped
        self.assertFalse(any("/lp/" in u for u, _, _ in f.calls), f.calls)                            # the disallowed landing page stays unfetched
        self.assertTrue(site.disallowed("/lp/black-friday", ["/lp/"])); self.assertFalse(site.disallowed("/lpx", ["/lp/"]))

    def test_sitemap_keeps_compare_and_landing_pages_with_receipts_and_skips_foreign_hosts(self):
        obs, outcomes, bodies = site.fetch(self.plan, FakeFetcher(routes()))
        sm = {o.key: o for o in obs if o.kind == "sitemap"}
        self.assertIn("/compare/acme-vs-globex", sm); self.assertEqual(sm["/compare/acme-vs-globex"].value, "2026-10-28")
        self.assertEqual(sm["/compare/acme-vs-globex"].tier, "finding"); self.assertIn("compare page", sm["/compare/acme-vs-globex"].context)
        self.assertIn("disallowed in robots.txt", sm["/lp/black-friday"].context)
        self.assertNotIn("/evil", sm); self.assertNotIn("/pricing", sm)                    # foreign host; old ordinary page
        self.assertEqual(sm["/blog/hello"].tier, "key-list")                                   # recent ordinary page, kept for the next diff
        o = sm["/compare/acme-vs-globex"]
        self.assertIn(o.source.sha256, bodies); self.assertIn("acme-vs-globex", bodies[o.source.sha256][1][o.source.offset:o.source.offset + 60])
        st = {x.source: x for x in outcomes}
        self.assertEqual(st["sitemap"].state, "ok"); self.assertIn("3 sitemap file(s)", st["sitemap"].detail)

    def test_the_headline_shared_by_two_landing_pages_is_a_finding(self):
        obs, outcomes, _ = site.fetch(self.plan, FakeFetcher(routes()))
        heads = {o.key: o for o in obs if o.kind == "headline"}
        self.assertEqual(heads["Ship agents without the on-call"].tier, "finding"); self.assertEqual(heads["Ship agents without the on-call"].value, 2)
        self.assertEqual(heads["Agents for ops teams"].tier, "key-list")
        self.assertNotIn("SHOULD NEVER BE FETCHED", heads)

    def test_a_sitemap_served_only_to_search_engines_is_said_so(self):
        r = routes(); del r["https://acme.com/sitemap-pages.xml"]; del r["https://acme.com/sitemap-blog.xml"]
        from fetch import Fetched
        r["https://acme.com/sitemap-pages.xml"] = Fetched("https://acme.com/sitemap-pages.xml", "https://acme.com/?redirectTo=%2Fsitemap-pages.xml", 200, "ok", HOME, "ab" * 32, len(HOME))
        obs, outcomes, _ = site.fetch(self.plan, FakeFetcher(r))
        st = {x.source: x for x in outcomes}
        self.assertEqual(st["sitemap"].state, "no-results"); self.assertIn("redirected elsewhere", st["sitemap"].detail)

    def test_pipeline_puts_campaign_signals_in_their_own_section_and_diffs_pages(self):
        tmp = tempfile.TemporaryDirectory(); db = storemod.Store(os.path.join(tmp.name, "u.db"))
        try:
            r1 = pipeline.run(self.plan, FakeFetcher(routes()), db, engine_version="t", run_id="2026-10-29T000000Z")
            md = emit.evidence_md(r1)
            sec = md.split("## Campaign signals")[1].split("## New subdomains")[0] if "## New subdomains" in md else md.split("## Campaign signals")[1].split("## Announced")[0]
            self.assertIn("`/lp/`", sec); self.assertIn("/compare/acme-vs-globex", sec); self.assertIn("Not linked from the pages read", sec)
            self.assertIn("/compare/acme-vs-initech", sec); self.assertIn("Linked from a public page", sec)
            self.assertIn('headline on 2 pages: "Ship agents without the on-call"', sec)
            self.assertNotIn("/compare/acme-vs-globex", md.split("## Findings")[1].split("## Campaign signals")[0])   # not mixed into the code findings
            self.assertEqual(r1.coverage.verdict(), "rich")
            r2_routes = routes(); r2_routes["https://acme.com/sitemap-pages.xml"] = (200, PAGES.replace("</urlset>", '<url><loc>https://acme.com/compare/acme-vs-hooli</loc><lastmod>2026-10-30</lastmod></url></urlset>'))
            r2 = pipeline.run(self.plan, FakeFetcher(r2_routes), db, engine_version="t", run_id="2026-10-30T000000Z")
            self.assertEqual(r2.diff.pages_added, ["/compare/acme-vs-hooli"]); self.assertEqual(r2.diff.added, []); self.assertEqual(r2.diff.removed, [])
        finally:
            db.close(); tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
