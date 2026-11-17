"""S2 seam: sources.pricing — visible_text / chip_lines (pure) and fetch(plan, fetcher) -> (snapshots, outcomes).

Expected values: the readers' R15 line for GitLab ("Advanced Capacity — coming soon — $12,000 per top-level
group per year"), the corpus pricing.txt counts (HubSpot 36 chars, Lovable 7,509 chars with zero amounts) and
the Hotjar -> Contentsquare redirect recorded in results/hotjar/<run>/summary.json.
"""
import hashlib
import unittest

from helpers import FakeFetcher, fixture, fixture_meta  # sets sys.path
import fetch as fetchmod
import plan as planmod
from sources import pricing




def a_plan(domain="gitlab.com", pricing="https://about.gitlab.com/pricing/", **kw):
    raw = {"slug": domain.split(".")[0], "domain": domain, "pages": [f"https://{domain}/"], "pricing": pricing}
    raw.update(kw)
    return planmod.validate(raw)


SNIPPET = """<!doctype html><html><head><title>Plans</title><style>.x{color:red}</style>
<script>window.__DATA__={"price":"$999"}</script></head><body>
<!-- a comment with $5 -->
<nav><a href="/">Home</a><a href="/pricing">Pricing</a></nav>
<h2>Pro</h2><div class="amount"><span>$</span><span>12</span><span>per user</span> / mo</div>
<p>Everything in Free, plus:&nbsp;unlimited seats</p>
<ul><li>SSO</li><li>Audit log <span class="badge">Beta</span></li></ul>
<span class="icon"></span><span>★★★</span>
<div>New</div><div>Hand off and schedule tasks</div>
<noscript>Enable JavaScript</noscript>
<p>Coming soon: Advanced Capacity</p><p>Not yet available to buy</p>
<p>a</p><p>ok</p>
</body></html>"""


class VisibleText(unittest.TestCase):
    def test_strips_code_keeps_block_lines_joins_inline(self):
        text = pricing.visible_text(SNIPPET)
        lines = text.split("\n")
        self.assertNotIn("__DATA__", text); self.assertNotIn("$999", text); self.assertNotIn("color:red", text)
        self.assertNotIn("$5", text, "comments are not visible")
        self.assertNotIn("Enable JavaScript", text, "noscript is not visible to a browser with JS")
        self.assertIn("Pro", lines)
        self.assertIn("$ 12 per user / mo", lines, "inline spans join on one line")
        self.assertIn("Everything in Free, plus: unlimited seats", lines, "entities are unescaped")
        self.assertIn("Audit log Beta", lines)
        self.assertNotIn("", text, "private-use icon glyphs are dropped")
        self.assertNotIn("★", text, "decorative symbol runs are dropped")
        self.assertNotIn("a", lines, "lines shorter than 3 chars are dropped")
        self.assertNotIn("ok", lines)
        self.assertEqual(text, text.strip())
        self.assertFalse([l for l in lines if l != l.strip() or "  " in l], "whitespace is collapsed")

    def test_same_text_different_markup_hashes_the_same(self):
        a = "<div>Pro</div>\n\n<div>  $12   per user</div><span></span>"
        b = "<p>Pro</p><p>$12 per user</p>"
        self.assertEqual(pricing.visible_text(a), pricing.visible_text(b))


class ChipLines(unittest.TestCase):
    def test_chips_amounts_and_units_are_kept_and_bare_chips_attach_to_the_next_line(self):
        text = "\n".join(["Plans", "Pro", "$ 12 per user / mo", "Everything in Free", "Audit log Beta", "New",
                          "Hand off and schedule tasks", "Coming soon: Advanced Capacity", "Not yet available to buy",
                          "Starter €9/mo", "Team £ 20 per seat", "Claude Dashboards (beta)", "Join the waitlist", "Early access for teams",
                          "Preview", "Agent mode", "A new way to work", "100 credits", "$ 29", "per user/month,", "Free", "$ 0", "Compare plans"])
        lines = pricing.chip_lines(text)
        self.assertEqual(lines, ["$ 12 per user / mo", "Audit log Beta", "New: Hand off and schedule tasks", "Coming soon: Advanced Capacity",
                                 "Not yet available to buy", "Starter €9/mo", "Team £ 20 per seat", "Claude Dashboards (beta)",
                                 "Join the waitlist", "Early access for teams", "Preview: Agent mode", "$ 29 per user/month,", "$ 0"])

    def test_amount_count(self):
        self.assertEqual(pricing.amounts("Pro $12/mo, Team €20, Enterprise: contact us, 100 credits"), 2)


class GitLabFixture(unittest.TestCase):
    URL = "https://about.gitlab.com/pricing/"

    def test_fixture_provenance(self):
        meta = fixture_meta("sources", "pricing-gitlab.html")
        self.assertEqual(meta["url"], self.URL); self.assertTrue(meta["sha256_full"])

    def test_snapshot_carries_the_advanced_capacity_line(self):
        f = FakeFetcher({self.URL: (200, fixture("sources", "pricing-gitlab.html"))})
        snaps, outcomes = pricing.fetch(a_plan(), f)
        self.assertEqual(f.calls[0][2], "page")
        self.assertEqual(len(snaps), 1)
        s = snaps[0]
        self.assertEqual((s.url, s.status, s.final_url), (self.URL, "ok", self.URL))
        self.assertEqual(len(s.sha256_text), 64)
        self.assertGreater(s.chars, 3000)
        self.assertEqual((len(s.text), hashlib.sha256(s.text.encode()).hexdigest()), (s.chars, s.sha256_text), "text is the hashed visible text")
        self.assertIn("Advanced Capacity", s.text)
        coming = [l for l in s.lines if "Coming soon" in l and "Advanced Capacity" in l]
        amount = [l for l in s.lines if "12,000" in l and "per top-level group per year" in l]
        self.assertEqual(len(coming), 1, s.lines)
        self.assertEqual(len(amount), 1, s.lines)
        self.assertTrue(all("<" not in l for l in s.lines))
        self.assertEqual([(o.source, o.state, o.items) for o in outcomes], [("pricing", "ok", len(s.lines))])


class Statuses(unittest.TestCase):
    def test_unconfigured(self):
        f = FakeFetcher({})
        snaps, outcomes = pricing.fetch(a_plan(pricing=None), f)
        self.assertEqual((snaps, f.calls), ([], []))
        self.assertEqual((outcomes[0].state, outcomes[0].attempted), ("skipped-unconfigured", False))

    def test_404_403_challenge(self):
        url = "https://www.zoom.com/en/products/pricing/"
        for status, body, want, state in ((404, "", "404", "no-results"), (403, "", "blocked-403", "blocked-403"),
                                          (200, "<html><head><title>Just a moment...</title></head><body>cf-chl-x</body></html>", "challenge", "challenge")):
            with self.subTest(status=status):
                f = FakeFetcher({url: (status, body)})
                snaps, outcomes = pricing.fetch(a_plan("zoom.com", url), f)
                self.assertEqual((snaps[0].status, snaps[0].text), (want, ""))
                self.assertEqual(outcomes[0].state, state)

    def test_network_error_has_no_snapshot(self):
        url = "https://x.com/pricing"
        f = FakeFetcher({url: fetchmod.Fetched(url, url, "error", "timeout")})
        snaps, outcomes = pricing.fetch(a_plan("x.com", url), f)
        self.assertEqual(snaps, []); self.assertEqual(outcomes[0].state, "timeout")

    def test_redirect_to_another_host_is_recorded(self):
        url, final = "https://www.hotjar.com/pricing/", "https://contentsquare.com/pricing/?utm_source=hotjar-pricing"
        body = "<h1>Pricing</h1><p>Starter $39/mo</p><p>Growth $99/mo</p>" + "".join(f"<p>Feature row number {i} of the comparison table</p>" for i in range(60))
        f = FakeFetcher({url: fetchmod.Fetched(url, final, 200, "ok", body, "s", len(body), False)})
        snaps, outcomes = pricing.fetch(a_plan("hotjar.com", url), f)
        self.assertEqual((snaps[0].status, snaps[0].final_url), ("redirect", final))
        self.assertIn("Starter $39/mo", snaps[0].text)
        self.assertEqual(outcomes[0].state, "partial")
        self.assertIn("contentsquare.com", outcomes[0].detail)

    def test_redirect_inside_the_domain_is_not_a_redirect(self):
        url, final = "https://figma.com/pricing", "https://www.figma.com/pricing/"
        body = "<h1>Pricing</h1><p>Professional $16 per editor / mo</p><p>Organization $55 per editor / mo</p>" + "<p>%s</p>" % ("Compare plans " * 300)
        f = FakeFetcher({url: fetchmod.Fetched(url, final, 200, "ok", body, "s", len(body), False)})
        snaps, outcomes = pricing.fetch(a_plan("figma.com", url), f)
        self.assertEqual((snaps[0].status, outcomes[0].state), ("ok", "ok"))

    def test_client_rendered_shell(self):
        url = "https://www.hubspot.com/pricing/marketing"
        body = "<html><head><title>Marketing Software Pricing | HubSpot</title></head><body><div id=app></div><script src=a.js></script></body></html>"
        f = FakeFetcher({url: (200, body)})
        snaps, outcomes = pricing.fetch(a_plan("hubspot.com", url), f)
        self.assertEqual(snaps[0].status, "client-rendered")
        self.assertEqual(outcomes[0].state, "partial")
        self.assertIn("client-rendered", outcomes[0].detail)

    def test_placeholder_dominated_page_is_client_rendered(self):
        url = "https://x.com/pricing"
        body = "<h1>Pricing</h1>" + "".join(f"<div>{{{{ plan.price{i} }}}}</div><div>Loading…</div>" for i in range(60)) + "<p>Compare plans and features in detail below</p>"
        f = FakeFetcher({url: (200, body)})
        snaps, outcomes = pricing.fetch(a_plan("x.com", url), f)
        self.assertEqual(snaps[0].status, "client-rendered")

    def test_long_text_with_zero_amounts_is_ok_but_partial(self):
        url = "https://lovable.dev/pricing"
        body = "<h1>Lovable Pricing</h1>" + "".join(f"<p>Plan feature line {i} describes capacity and limits for teams.</p>" for i in range(120))
        f = FakeFetcher({url: (200, body)})
        snaps, outcomes = pricing.fetch(a_plan("lovable.dev", url), f)
        self.assertEqual(snaps[0].status, "ok")
        self.assertEqual(outcomes[0].state, "partial")
        self.assertIn("cards not visible without a browser", outcomes[0].detail)

    def test_health_fetches_one_small_page(self):
        f = FakeFetcher({"https://example.com/": (200, "<html><body><h1>Example Domain</h1><p>This domain is for use in illustrative examples in documents.</p></body></html>")})
        out = pricing.health(f)
        self.assertEqual((out.source, out.state), ("pricing", "ok"))
        self.assertEqual(len(f.calls), 1)


if __name__ == "__main__":
    unittest.main()
