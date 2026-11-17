"""S2 seam: sources.changelog — parse_feed / parse_html_index / parse_embedded_json (pure) and fetch.

Expected values: the entries as they read in the fixtures (vercel.com/atom, linear.app/changelog, the
cursor.com homepage excerpt the reader quoted in results/cursor.md: `2026-10-20 "Agent SDK"`,
`2026-10-16 "Cloud Agent Canvases and Environment Improvements"`).
"""
import hashlib
import unittest

from helpers import FakeFetcher, fixture, fixture_meta  # sets sys.path
import fetch as fetchmod
import plan as planmod
from sources import changelog




def a_plan(domain, changelog_url):
    return planmod.validate({"slug": domain.split(".")[0], "domain": domain, "pages": [f"https://{domain}/"], "changelog": changelog_url})


class Feed(unittest.TestCase):
    def test_vercel_atom(self):
        self.assertEqual(fixture_meta("sources", "feed-vercel.xml")["url"], "https://vercel.com/atom")
        entries = changelog.parse_feed(fixture("sources", "feed-vercel.xml"))
        self.assertEqual(len(entries), 6)
        first = entries[0]
        self.assertEqual((first["date"], first["title"], first["url"]),
                         ("2026-10-30", "Introducing Geist Serif", "https://vercel.com/blog/introducing-geist-serif"))
        self.assertTrue(first["text"].startswith("Geist started as a monospace typeface"), first["text"][:80])
        self.assertNotIn("<", first["text"])
        self.assertEqual([e["title"] for e in entries][2:4], ["Data Cache is moving to Runtime Cache", "Vercel Daemons can now call services with bindings"])
        self.assertEqual(sorted(entries, key=lambda e: e["date"], reverse=True), entries, "newest first")

    def test_feed_cut_by_the_byte_cap_keeps_its_whole_entries(self):
        # vercel.com/atom is 4 MB of xhtml; the cap cut it mid-entry and the parser returned [] — then the
        # HTML fallback read post bodies as a changelog and produced an entry dated 2026-12-31
        xml = fixture("sources", "feed-vercel.xml")
        cut = xml[: xml.rfind("</entry>") - 200]            # ends inside the last entry
        entries = changelog.parse_feed(cut)
        self.assertEqual(len(entries), 5)
        self.assertEqual(entries[0]["title"], "Introducing Geist Serif")

    def test_a_feed_is_never_read_as_an_html_index(self):
        import fetch as fetchmod, hashlib
        xml = fixture("sources", "feed-vercel.xml")
        cut = xml[:1500]                                     # no complete entry survives
        f = fetchmod.Fetched("https://vercel.com/atom", "https://vercel.com/atom", 200, "ok", cut, hashlib.sha256(cut.encode()).hexdigest(), len(cut), False)
        entries, how = changelog.parse_body(f, "https://vercel.com/atom")
        self.assertEqual(entries, []); self.assertIn("feed", how)

    def test_future_dated_entries_are_dropped(self):
        xml = """<?xml version="1.0"?><rss version="2.0"><channel><title>Acme</title>
        <item><title>Scheduled</title><link>https://acme.com/c/sched</link><pubDate>Tue, 31 Dec 2030 09:00:00 GMT</pubDate></item>
        <item><title>Real</title><link>https://acme.com/c/real</link><pubDate>Tue, 06 Oct 2026 09:00:00 GMT</pubDate></item>
        </channel></rss>"""
        self.assertEqual([e["title"] for e in changelog.parse_feed(xml)], ["Real"])

    def test_rss2(self):
        xml = """<?xml version="1.0"?><rss version="2.0"><channel><title>Acme</title>
        <item><title>Older</title><link>https://acme.com/changelog/older</link><pubDate>Tue, 06 Oct 2026 09:00:00 GMT</pubDate><description><![CDATA[<p>Old &amp; gold</p>]]></description></item>
        <item><title>Newer</title><link>https://acme.com/changelog/newer</link><pubDate>Tue, 20 Oct 2026 09:00:00 +0000</pubDate><description>New thing</description></item>
        </channel></rss>"""
        entries = changelog.parse_feed(xml)
        self.assertEqual([(e["date"], e["title"], e["url"], e["text"]) for e in entries],
                         [("2026-10-20", "Newer", "https://acme.com/changelog/newer", "New thing"),
                          ("2026-10-06", "Older", "https://acme.com/changelog/older", "Old & gold")])

    def test_not_a_feed(self):
        self.assertEqual(changelog.parse_feed("<html><body>hi</body></html>"), [])
        self.assertEqual(changelog.parse_feed("not xml at all <"), [])


class HtmlIndex(unittest.TestCase):
    BASE = "https://linear.app/changelog"

    def test_linear_changelog_index(self):
        self.assertEqual(fixture_meta("sources", "changelog-linear.html")["url"], self.BASE)
        entries = changelog.parse_html_index(fixture("sources", "changelog-linear.html"), self.BASE)
        got = [(e["date"], e["title"], e["url"]) for e in entries]
        self.assertEqual(got[:3], [
            ("2026-10-22", "More ways to run and share Loops", "https://linear.app/changelog/2026-10-22-slack-and-github-loops"),
            ("2026-10-08", "Stacked pull requests", "https://linear.app/changelog/2026-10-08-stacked-pull-requests"),
            ("2026-09-24", "New controls for Linear coding agent", "https://linear.app/changelog/2026-09-24-new-controls-for-linear-coding-agent"),
        ])
        self.assertEqual(len(entries), 3)
        self.assertTrue(all(e["text"] for e in entries))

    def test_time_element_and_other_date_formats(self):
        html = """<html><body>
        <article><time datetime="2026-10-20T00:00:00Z">Oct 20, 2026</time><h3><a href="/changelog/a">Agent SDK</a></h3><p>Define an agent as a folder of code.</p></article>
        <article><h2><a href="/changelog/b">Stacked PRs</a></h2><span>8 October 2026</span><p>Stack them.</p></article>
        <article><div>2026-09-24</div><h2>Coding agent controls</h2><p>More controls.</p></article>
        <article><h2>Undated note</h2><p>No date here.</p></article>
        <footer>© 2026 Acme · Last updated September 1, 2026</footer>
        </body></html>"""
        entries = changelog.parse_html_index(html, "https://acme.com/changelog")
        got = [(e["date"], e["title"], e["url"], e["text"]) for e in entries]
        self.assertEqual(got, [
            ("2026-10-20", "Agent SDK", "https://acme.com/changelog/a", "Define an agent as a folder of code."),
            ("2026-10-08", "Stacked PRs", "https://acme.com/changelog/b", "Stack them."),
            ("2026-09-24", "Coding agent controls", "", "More controls."),
        ])

    def test_cap_and_sort(self):
        html = "".join(f"<div><span>2025-01-{(i % 28) + 1:02d}</span><h2>Entry {i}</h2></div>" for i in range(260))
        entries = changelog.parse_html_index(html, "https://acme.com/changelog")
        self.assertEqual(len(entries), 200)
        self.assertEqual(entries[0]["date"], "2025-01-28")


class EmbeddedJson(unittest.TestCase):
    def test_cursor_homepage_rsc_payload(self):
        meta = fixture_meta("sources", "cursor-home-embedded.html")
        self.assertEqual(meta["url"], "https://cursor.com/")
        entries = changelog.parse_embedded_json(fixture("sources", "cursor-home-embedded.html"), "https://cursor.com/")
        got = [(e["date"], e["title"], e["url"]) for e in entries]
        self.assertEqual(got, [
            ("2026-10-20", "Agent SDK", "https://cursor.com/changelog/agent-sdk"),
            ("2026-10-16", "Cloud Agent Canvases and Environment Improvements", "https://cursor.com/changelog/cloud-agent-canvases-and-environments"),
            ("2026-10-13", "Origin App Marketplace", "https://cursor.com/changelog/origin-app-marketplace"),
            ("2026-10-06", "Remote control for local agents", "https://cursor.com/changelog/remote-control-local-agents"),
        ])
        self.assertTrue(entries[1]["text"].startswith("Cloud agents can now build and share interactive canvases."))

    def test_plain_json_script(self):
        html = """<script type="application/json">{"props":{"releases":[{"title":"v2.1","date":"2026-10-01","href":"/releases/2-1","summary":"Bits"},
        {"title":"v2.2","publishedAt":"2026-10-15T10:00:00Z","url":"https://acme.com/releases/2-2"}]}}</script>"""
        entries = changelog.parse_embedded_json(html, "https://acme.com/")
        self.assertEqual([(e["date"], e["title"], e["url"], e["text"]) for e in entries],
                         [("2026-10-15", "v2.2", "https://acme.com/releases/2-2", ""), ("2026-10-01", "v2.1", "https://acme.com/releases/2-1", "Bits")])

    def test_nothing_embedded(self):
        self.assertEqual(changelog.parse_embedded_json("<html><body><p>changelog</p></body></html>", "https://x.com/"), [])


class FetchSeam(unittest.TestCase):
    def test_feed_url(self):
        url = "https://vercel.com/atom"
        f = FakeFetcher({url: (200, fixture("sources", "feed-vercel.xml"))})
        entries, outcomes = changelog.fetch(a_plan("vercel.com", url), f)
        self.assertEqual(len(entries), 6)
        self.assertEqual([(o.source, o.state, o.items) for o in outcomes], [("changelog", "ok", 6)])
        self.assertIn("feed", outcomes[0].detail)

    def test_html_index_url(self):
        url = "https://linear.app/changelog"
        f = FakeFetcher({url: (200, fixture("sources", "changelog-linear.html"))})
        entries, outcomes = changelog.fetch(a_plan("linear.app", url), f)
        self.assertEqual(len(entries), 3)
        self.assertEqual(outcomes[0].state, "ok")
        self.assertIn("index", outcomes[0].detail)

    def test_embedded_json_on_a_page(self):
        url = "https://cursor.com/"
        f = FakeFetcher({url: (200, fixture("sources", "cursor-home-embedded.html"))})
        entries, outcomes = changelog.fetch(a_plan("cursor.com", url), f)
        self.assertEqual([e["title"] for e in entries][:1], ["Agent SDK"])
        self.assertEqual(len(entries), 4)
        self.assertIn("embedded", outcomes[0].detail)

    def test_page_without_dated_entries_is_no_results(self):
        url = "https://x.com/changelog"
        f = FakeFetcher({url: (200, "<html><body><div id=app></div><script src=a.js></script></body></html>")})
        entries, outcomes = changelog.fetch(a_plan("x.com", url), f)
        self.assertEqual((entries, outcomes[0].state), ([], "no-results"))
        self.assertIn("no dated entries", outcomes[0].detail)

    def test_unconfigured_404_403_challenge_timeout(self):
        url = "https://x.com/changelog"
        entries, outcomes = changelog.fetch(a_plan("x.com", None), FakeFetcher({}))
        self.assertEqual((entries, outcomes[0].state, outcomes[0].attempted), ([], "skipped-unconfigured", False))
        for route, state in (((404, ""), "no-results"), ((403, ""), "blocked-403"),
                             ((200, "<html><head><title>Just a moment...</title></head><body>cf-chl-x</body></html>"), "challenge"),
                             (fetchmod.Fetched(url, url, "error", "timeout"), "timeout")):
            with self.subTest(state=state):
                entries, outcomes = changelog.fetch(a_plan("x.com", url), FakeFetcher({url: route}))
                self.assertEqual((entries, outcomes[0].state), ([], state))

    def test_health(self):
        f = FakeFetcher({"https://example.com/": (200, "<html><body><h1>Example Domain</h1><p>This domain is for use in illustrative examples.</p></body></html>")})
        out = changelog.health(f)
        self.assertEqual((out.source, out.state), ("changelog", "ok"))


if __name__ == "__main__":
    unittest.main()
