import unittest
from helpers import fixture  # sets sys.path
import discover, attribute, plan


def P(slug, domain, cdn=()):
    return plan.validate({"slug": slug, "domain": domain, "pages": [f"https://{domain}/"], "cdn_hosts": list(cdn)})


class Discover(unittest.TestCase):
    def test_scripts_modulepreload_json_inline_importmap(self):
        html = ('<html><head><script src="/static/app.js"></script><script src="https://cdn.x.com/v.js"></script>'
                '<link rel="modulepreload" href="/assets/entry-abc123.js">'
                '<script type="application/json" id="__NEXT_DATA__">{"props":{"a":1}}</script>'
                '<script type="importmap">{"imports":{"feature-flags":"/mods/ff.js"}}</script>'
                '<script>window.__FLAGS__={"x":true}</script></head></html>')
        d = discover.page("https://app.example.com/login", html)
        self.assertEqual(d.scripts, ["https://app.example.com/static/app.js", "https://cdn.x.com/v.js"])
        self.assertEqual(d.modulepreload, ["https://app.example.com/assets/entry-abc123.js"])
        self.assertEqual(d.json_blocks, ['{"props":{"a":1}}'])
        self.assertEqual(d.importmap, {"feature-flags": "https://app.example.com/mods/ff.js"})
        self.assertIn('window.__FLAGS__={"x":true}', d.inline_scripts)

    def test_relative_scripts_resolve_against_final_url_not_requested_url(self):
        html = '<script src="page.CH08FGWY.js"></script>'
        d = discover.page("https://sentry.io/auth/login/", html)
        self.assertEqual(d.scripts, ["https://sentry.io/auth/login/page.CH08FGWY.js"])

    def test_webpack_chunk_map_is_resolved(self):
        js = fixture("discover", "sentry-webpack-runtime.js")
        urls = discover.chunks(js, "https://s1.sentry-cdn.com/_static/dist/sentry/entrypoints/app.js", lambda u: True)
        self.assertGreater(len(urls), 1500)
        self.assertTrue(any(u.endswith("/chunks/SetupWizard.") or "/chunks/SetupWizard." in u for u in urls), "named chunk resolved with its hash")
        self.assertTrue(all(u.endswith(".js") for u in urls))

    def test_webpack_chunk_separator_is_read_from_the_runtime_not_assumed(self):
        # Notion's runtime joins name and hash with "-": building "Name.hash.js" asked for 2,800 URLs that 404
        js = ('d.p="/_assets/",d.u=e=>""+(({16812:"icon-braintrust",17100:"MaybeMarketplaceReview"})[e]||e)+"-"'
              '+({16812:"2ee5a708afb6f5f3",17100:"a3c741ee355928d6",86267:"b21a1da81140e5c0"})[e]+".js",d.miniCssF=e=>"x"')
        urls = discover.chunks(js, "https://app.notion.com/_assets/app-1.js", lambda u: True)
        self.assertEqual(urls, {"https://app.notion.com/_assets/icon-braintrust-2ee5a708afb6f5f3.js",
                                "https://app.notion.com/_assets/MaybeMarketplaceReview-a3c741ee355928d6.js",
                                "https://app.notion.com/_assets/86267-b21a1da81140e5c0.js"})

    def test_separator_edge_cases(self):
        def one(expr):
            return discover.chunks('d.u=e=>' + expr + ',d.x=1', "https://a.com/s/app.js", lambda u: True)
        self.assertEqual(one('"s/"+e+"."+{12:"abcdef12"}[e]+".js"'), {"https://a.com/s/s/12.abcdef12.js"})
        self.assertEqual(one('"s/"+({12:"pay"}[e]||e)+".chunk."+{12:"abcdef12"}[e]+".js"'), {"https://a.com/s/s/pay.chunk.abcdef12.js"})
        self.assertEqual(one('"s/"+({12:"pay"}[e]||e)+"."+(e===5?"x":"")+{12:"abcdef12"}[e]+".js"'), {"https://a.com/s/s/pay.abcdef12.js"})

    def test_vite_mapdeps_is_resolved(self):
        js = fixture("discover", "lovable-vite-mapdeps.js")
        urls = discover.chunks(js, "https://lovable.dev/assets/index-abc.js", lambda u: True)
        self.assertIn("https://lovable.dev/assets/DebugPalette-WfFYjiTy.js", urls)
        self.assertFalse(any(u.endswith(".css") for u in urls))

    def test_absolute_and_relative_chunk_references(self):
        js = 'import("https://static.figma.com/webpack-artifacts/figma_app-abc.min.js");x="/_next/static/chunks/pages/foo-1a2b.js";y="https://cdn.other.com/t.js"'
        urls = discover.chunks(js, "https://www.figma.com/login", lambda u: "figma.com" in u)
        self.assertIn("https://static.figma.com/webpack-artifacts/figma_app-abc.min.js", urls)
        self.assertIn("https://www.figma.com/_next/static/chunks/pages/foo-1a2b.js", urls)
        self.assertNotIn("https://cdn.other.com/t.js", urls)

    def test_select_by_role_prefers_entry_named_then_rest_vendor_last(self):
        cands = ["https://a.com/vendor-react-F2x.js", "https://a.com/routes-Ab12.js", "https://a.com/9f8e7d6c5b4a3f2e.js", "https://a.com/entry.js", "https://a.com/polyfills-ZZ.js"]
        sel = discover.select_by_role(cands, entry=["https://a.com/entry.js"], cap=3)
        self.assertEqual(sel[0], "https://a.com/entry.js")
        self.assertEqual(sel[1], "https://a.com/routes-Ab12.js")
        self.assertNotIn("https://a.com/vendor-react-F2x.js", sel)
        self.assertEqual(len(sel), 3)


class Attribute(unittest.TestCase):
    def decide(self, slug, domain, name, cdn=()):
        html = fixture("attribute", f"{name}-tags.html")
        d = discover.page(f"https://{domain}/", html)
        return attribute.decide(P(slug, domain, cdn), f"https://{domain}/", html, d.scripts, d.modulepreload)

    def test_plan_domain_and_cdn_list_are_first_party(self):
        a = attribute.decide(P("acme", "acme.com", ["acmecdn.net"]), "https://acme.com/", "", [], [])
        self.assertTrue(a.is_first_party("https://app.acme.com/a.js"))
        self.assertTrue(a.is_first_party("https://static.acmecdn.net/a.js"))
        self.assertFalse(a.is_first_party("https://cdn.cookielaw.org/x.js"))

    def test_majority_script_host_is_promoted_duolingo_cloudfront(self):
        a = self.decide("duolingo", "duolingo.com", "duolingo")
        self.assertTrue(a.is_first_party("https://d35aaqx5ub95lt.cloudfront.net/js/app.js"))
        self.assertTrue(any("cloudfront" in x for x in a.decisions))

    def test_majority_after_known_third_parties_asana_cloudfront(self):
        a = self.decide("asana", "asana.com", "asana")
        self.assertTrue(a.is_first_party("https://d3ki9tyy5l5ruj.cloudfront.net/x.js"))
        self.assertFalse(a.is_first_party("https://cdn.cookielaw.org/x.js"))

    def test_modulepreload_host_is_promoted_retool_edge(self):
        a = self.decide("retool", "retool.com", "retool")
        self.assertTrue(a.is_first_party("https://retool-edge.com/assets_vjs/src-index-CMdn4Rp9.js"))

    def test_supabase_frontend_assets_promoted(self):
        a = self.decide("supabase", "supabase.com", "supabase")
        self.assertTrue(a.is_first_party("https://frontend-assets.supabase.com/x.js"))

    def test_clarity_azureedge_promoted(self):
        a = self.decide("clarity", "clarity.microsoft.com", "clarity")
        self.assertTrue(a.is_first_party("https://claritystatic.azureedge.net/x.js"))

    def test_miro_mirostatic_promoted_framer_stays_third_party(self):
        a = self.decide("miro", "miro.com", "miro")
        self.assertTrue(a.is_first_party("https://mirostatic.com/app/x.js"))
        self.assertFalse(a.is_first_party("https://framerusercontent.com/sites/x.js"))

    def test_known_third_party_never_promoted_even_as_majority(self):
        html = '<script src="https://cdn.cookielaw.org/a.js"></script><script src="https://cdn.cookielaw.org/b.js"></script>'
        d = discover.page("https://acme.com/", html)
        a = attribute.decide(P("acme", "acme.com"), "https://acme.com/", html, d.scripts, d.modulepreload)
        self.assertFalse(a.is_first_party("https://cdn.cookielaw.org/a.js"))


if __name__ == "__main__":
    unittest.main()
