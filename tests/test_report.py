"""The report: the host's brief verbatim inside a self-contained HTML (and the same as Markdown), the engine's
appendix after it, receipts kept as receipts, nothing synthesised when no brief is given."""
import html.parser, json, os, tempfile, unittest
from helpers import FakeFetcher  # noqa: F401 (sets sys.path)
import report

BRIEF = """🔎 unreleased 0.1.0 · acme · 2026-10-30 · rich · first run
Read 3 KB in 1 script. Full coverage at the end.

**The shape of it** (my reading): Acme is wiring an assistant into every surface.

**Unannounced** (2)

*Members*

1. **Assistant with web search** · high
   `ai_assistant_websearch` = off (gate). Checked: pricing-text; nothing. ¹
   Raises: Whether search is a paid add-on.
2. **Slides from the assistant** · high
   `ai_assistant_slides` = on. ²
   Raises: A <b>tag</b> that must not render & an ampersand.

**Announced, for calibration**: Nothing.

**Receipts**: host https://acme.com/
¹ app.js sha256:0123456789ab@12
² app.js sha256:0123456789ab@40

```text
unreleased 0.1.0 · acme · run 2026-10-30T000000Z · rich · findings 2
```
"""


class Balanced(html.parser.HTMLParser):
    VOID = {"meta", "br", "hr", "img", "link", "input"}

    def __init__(self):
        super().__init__(); self.stack = []; self.bad = []

    def handle_starttag(self, t, a):
        if t not in self.VOID: self.stack.append(t)

    def handle_endtag(self, t):
        if self.stack and self.stack[-1] == t: self.stack.pop()
        else: self.bad.append(t)


def run_folder(tmp):
    d = os.path.join(tmp, "acme", "2026-10-30T000000Z"); os.makedirs(d)
    json.dump({"run_id": "2026-10-30T000000Z", "product": "acme", "engine_version": "0.1.0"}, open(os.path.join(d, "manifest.json"), "w"))
    json.dump({"first_party_bytes": 3000, "sources": [{"source": "crt", "state": "ok"}]}, open(os.path.join(d, "coverage.json"), "w"))
    with open(os.path.join(d, "evidence.jsonl"), "w") as f:
        f.write(json.dumps({"id": "o1", "kind": "gate", "key": "ai_assistant_websearch", "value": False, "tier": "finding", "salience": 5, "context": "ai_assistant_websearch:!1,ai_assistant_slides:!0",
                            "source": {"url": "https://acme.com/app.js", "sha256": "0123456789abcdef" * 4, "offset": 12}}) + "\n")
        f.write(json.dumps({"id": "o2", "kind": "sitemap", "key": "/compare/acme-vs-globex", "value": "2026-10-28", "tier": "finding", "salience": 0,
                            "source": {"url": "https://acme.com/sitemap.xml", "sha256": "ab" * 32, "offset": 5}}) + "\n")
    with open(os.path.join(d, "evidence.md"), "w") as f:
        f.write("🔎 unreleased 0.1.0 · acme · 2026-10-30 · rich\n\n## Coverage\n\n- crt: ok\n\n## Findings\n\n- x\n\n## Campaign signals (robots.txt, sitemap, landing pages)\n\n- `/compare/acme-vs-globex` lastmod 2026-10-28. Not linked [https://acme.com/sitemap.xml sha256:abababababab@5]\n\n"
                "These are strings present in public code; a flag or route is evidence that something is being built, not that it will ship.\n\n```text\nunreleased 0.1.0 · acme · run 2026-10-30T000000Z · rich · findings 2\n```\n")
    return d


class Report(unittest.TestCase):
    def test_markdown_subset(self):
        h = report.markdown("## Title\n\nA **bold** `code` [link](https://x.y/z) and https://a.b/c.\n\n1. one\n   more\n2. two\n\n- bullet\n\n```text\nfoot\n```\n")
        self.assertIn("<h2>Title</h2>", h); self.assertIn("<strong>bold</strong>", h); self.assertIn("<code>code</code>", h)
        self.assertIn('<a href="https://x.y/z">link</a>', h); self.assertIn('<a href="https://a.b/c">https://a.b/c</a>', h)
        self.assertIn("<ol><li>One<br>More</li><li>Two</li></ol>", h); self.assertIn("<ul><li>Bullet</li></ul>", h); self.assertIn("<pre><code>foot</code></pre>", h)

    def test_brief_is_verbatim_escaped_and_html_is_balanced(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = run_folder(tmp)
            h, m = report.build(d, BRIEF)
            self.assertIn("&lt;b&gt;tag&lt;/b&gt;", h); self.assertIn("&amp; an ampersand", h)             # a brief is text, never markup
            self.assertIn('class="callout info" id="shape"', h); self.assertIn('class="pill rich"', h)
            self.assertIn('id="f1"', h); self.assertIn('class="pill high"', h); self.assertIn('class="raises"', h)           # items are components
            self.assertIn("Evidence: 1 line from the run", h); self.assertIn("<mark>ai_assistant_websearch</mark>", h)         # evidence on demand
            self.assertIn("<sup>¹</sup>", h); self.assertIn('>sha256:0123456789ab@12</span>', h)       # receipts stay receipts
            self.assertNotIn("<script", h); self.assertNotIn("http://", h.split("<main>")[0])                  # self-contained, no external assets
            self.assertNotIn("file://", h); self.assertNotIn(tmp, h)                                             # and no local paths
            p = Balanced(); p.feed(h); self.assertEqual((p.bad, p.stack), ([], []))
            self.assertIn("Campaign signals", h); self.assertIn("top 1 of 1", h)                                # site kinds are not in the findings table
            self.assertTrue(m.startswith("🔎 unreleased 0.1.0 · acme"))                                          # markdown: the brief first, verbatim
            self.assertIn("## Appendix (engine)", m); self.assertIn("| 1 | gate | `ai_assistant_websearch` | off |  | app.js sha256:0123456789ab@12 |", m)
            self.assertEqual(m.count("```text"), 2)                                                               # the brief's footer and the appendix's

    def test_without_a_brief_it_is_an_evidence_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = run_folder(tmp)
            h, m = report.build(d, None)
            self.assertIn("Evidence report", h); self.assertIn("No brief was written", m); self.assertNotIn('id="shape"', h)

    def test_theme_tokens_override_without_touching_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = run_folder(tmp)
            h, _ = report.build(d, BRIEF, theme_css=":root { --ok-dot: #ff00aa; --font: Inter, sans-serif; }")
            self.assertIn("--ok-dot: #ff00aa", h); self.assertLess(h.index("--ok-dot: #10b981"), h.index("--ok-dot: #ff00aa"))   # theme after tokens wins
            self.assertIn(".rail { width: var(--rail)", h)

    def test_the_brief_is_parsed_into_its_grammar(self):
        b = report.parse_brief(BRIEF)
        self.assertTrue(b["badge"].startswith("🔎")); self.assertEqual(b["lead"], "Read 3 KB in 1 script. Full coverage at the end.")
        self.assertEqual([g["name"] for g in b["groups"]], ["Members"]); items = b["groups"][0]["items"]
        self.assertEqual((items[0]["n"], items[0]["noun"], items[0]["conf"]), (1, "Assistant with web search", "high"))
        self.assertEqual(items[0]["raises"], "Whether search is a paid add-on."); self.assertIn("`ai_assistant_websearch` = off (gate)", items[0]["fact"][0])
        self.assertEqual([x["title"] for x in b["blocks"]], ["Announced, for calibration", "Receipts"]); self.assertTrue(b["footer"].startswith("unreleased 0.1.0"))
        self.assertEqual(report.brief_run_id(BRIEF), "2026-10-30T000000Z")

    def test_a_brief_from_another_run_is_rendered_with_a_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = run_folder(tmp)
            h, _ = report.build(d, BRIEF.replace("run 2026-10-30T000000Z", "run 2026-10-29T000000Z"))
            self.assertIn("the brief names run 2026-10-29T000000Z", h)

    def test_checked_is_its_own_beat_and_colour_means_status_only(self):
        self.assertEqual(report.split_checked("`a` = off. My reading: x. Checked: pricing-text; nothing. ¹"), ("`a` = off. My reading: x.", "Checked: pricing-text; nothing. ¹"))
        self.assertEqual(report.split_checked("`a` = off"), ("`a` = off", ""))
        with tempfile.TemporaryDirectory() as tmp:
            h, _ = report.build(run_folder(tmp), BRIEF)
            self.assertIn('class="checked"', h); self.assertNotIn("--accent", h)                  # no accent token: links are ink, panels are paper

    def test_write_lands_beside_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = run_folder(tmp); b = os.path.join(tmp, "brief.md"); open(b, "w").write(BRIEF)
            oh, om = report.write(d, b, None, None, None, None)
            self.assertEqual((os.path.basename(oh), os.path.basename(om)), ("report.html", "report.md")); self.assertTrue(os.path.getsize(oh) < 60_000)


if __name__ == "__main__":
    unittest.main()


class SentenceCase(unittest.TestCase):
    def test_capitalises_every_sentence_start(self):
        sc = report.sentence_case
        self.assertEqual(sc("the key is present. it flips on. ends here? yes."), "The key is present. It flips on. Ends here? Yes.")
        self.assertEqual(sc("checked: the same; nothing."), "Checked: the same; nothing.")
        self.assertEqual(sc("**the shape** of it: *my reading*."), "**The shape** of it: *my reading*.")

    def test_leaves_names_paths_code_and_abbreviations(self):
        sc = report.sentence_case
        for keep in ("iOS and macOS stay.", "e.g. this stays.", "robots.txt lists it.", "`admin_v2` is a key.", "npm installs it.",
                     "See v0.1.0. x", "https://x.y/z is first.", "Linear said so. iCloud too."):
            self.assertEqual(sc(keep), keep, keep)
        self.assertEqual(sc("`x` continues here. after the span."), "`x` continues here. After the span.")

    def test_receipts_badge_and_footnotes_are_not_prose(self):
        h = report.markdown("🔎 unreleased 0.1.0 · acme · 2026-11-07 · rich · first run\n\n**Receipts**: host https://acme.com · run folder /r\n¹ app.js sha256:fc27b1b9cfa6@26222")
        self.assertIn("🔎 unreleased 0.1.0", h); self.assertIn("<sup>¹</sup> app.js", h); self.assertNotIn("Unreleased 0.1.0", h)
