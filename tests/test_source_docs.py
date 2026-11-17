"""The docs source: a product's own documentation index as a third cross-check, so a feature the changelog never
listed but the manual describes is `announced (docs)`, not `no public mention found` (the Raycast round)."""
import unittest
from helpers import FakeFetcher  # noqa: F401
import crosscheck, plan as planmod
from sources import docs
from schema import Observation, Source

LLMS = """# Acme docs
- [MCP servers](https://manual.acme.com/teams/mcp-servers): connect MCP servers for an organization
- [Custom API keys (BYOK)](https://manual.acme.com/enterprise/api-keys): bring your own model keys
- [Billing](https://manual.acme.com/billing)
"""
HTML = '<html><body><nav><a href="/teams/mcp-servers">MCP servers</a><a href="/enterprise/api-keys">Custom API Keys</a><a href="https://other.example/x">Off host</a><a href="#top">top</a></nav></body></html>'
SM = '<?xml version="1.0"?><urlset><url><loc>https://manual.acme.com/teams/mcp-servers</loc></url><url><loc>https://manual.acme.com/enterprise/api-keys</loc></url></urlset>'


def a_plan(docs=None):
    raw = {"slug": "acme", "domain": "acme.com", "pages": ["https://acme.com/"], "cdn_hosts": ["acme.com"]}
    if docs: raw["docs"] = docs
    return planmod.validate(raw)


class Docs(unittest.TestCase):
    def test_three_index_shapes_parse_to_the_same_entries(self):
        for body, how in ((LLMS, "llms.txt"), (HTML, "html-index"), (SM, "sitemap")):
            entries, children, h = docs.parse(body, "https://manual.acme.com/")
            self.assertEqual(h, how); urls = {e["url"] for e in entries}
            self.assertIn("https://manual.acme.com/teams/mcp-servers", urls); self.assertNotIn("https://other.example/x", urls)
            e = next(x for x in entries if x["url"].endswith("mcp-servers")); self.assertIn("mcp servers", e["text"])

    def test_an_llms_txt_of_bare_urls_is_pages_not_no_links(self):
        body = "# Cursor docs\nhttps://cursor.com/docs/cloud-agent/automations\nhttps://cursor.com/docs/models\n- https://cursor.com/docs/cli\n"
        entries, children, how = docs.parse(body, "https://cursor.com/llms.txt")
        self.assertEqual([e["url"] for e in entries], ["https://cursor.com/docs/cloud-agent/automations", "https://cursor.com/docs/models", "https://cursor.com/docs/cli"])
        self.assertEqual(how, "llms.txt (bare urls)")
        self.assertIn("automations", entries[0]["text"])

    def test_a_mixed_llms_txt_keeps_its_bare_urls(self):
        body = "- [Models](https://cursor.com/docs/models): the list\nhttps://cursor.com/docs/cli\n"
        entries, _, how = docs.parse(body, "https://cursor.com/llms.txt")
        self.assertEqual([e["url"] for e in entries], ["https://cursor.com/docs/models", "https://cursor.com/docs/cli"])
        self.assertEqual(how, "llms.txt (links and bare urls)")

    def test_fetch_reports_and_caps(self):
        entries, out = docs.fetch(a_plan("https://manual.acme.com/llms.txt"), FakeFetcher({"https://manual.acme.com/llms.txt": (200, LLMS)}))
        self.assertEqual(len(entries), 3); self.assertEqual(out[0].state, "ok"); self.assertIn("llms.txt", out[0].detail)
        _, out = docs.fetch(a_plan(), FakeFetcher({})); self.assertEqual(out[0].state, "skipped-unconfigured")
        _, out = docs.fetch(a_plan("https://manual.acme.com/"), FakeFetcher({})); self.assertEqual(out[0].state, "no-results")

    def test_a_route_the_manual_describes_is_announced_docs_and_its_odd_sibling_is_not(self):
        entries, _ = docs.fetch(a_plan("https://manual.acme.com/llms.txt"), FakeFetcher({"https://manual.acme.com/llms.txt": (200, LLMS)}))
        S = Source("https://acme.com/app.js", "a" * 64, 1)
        obs = [Observation("o1", "route", "/settings/organizations/:handle/mcp-servers", S, tier="finding"),
               Observation("o2", "route", "/settings/organizations/:handle/external-agents", S, tier="finding"),
               Observation("o3", "route", "/settings/organizations/:handle/api-keys", S, tier="finding")]
        ch = {c.observation_id: c for c in crosscheck.check(obs, "", [{"title": "Shipped dark mode", "date": "2026-10-01", "url": "https://acme.com/changelog/dark"}], docs_index=entries)}
        self.assertEqual((ch["o1"].status, ch["o1"].note, ch["o1"].url), ("announced", "docs", "https://manual.acme.com/teams/mcp-servers"))
        self.assertEqual(ch["o3"].status, "announced")
        self.assertEqual(ch["o2"].status, "none"); self.assertTrue(any(s.startswith("docs-index") for s in ch["o2"].searched))
        self.assertEqual(crosscheck.route_words("/settings/organizations/:handle/mcp-servers"), ["mcp", "servers"])


if __name__ == "__main__":
    unittest.main()
