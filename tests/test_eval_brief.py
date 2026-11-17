"""The eval grader (tools/eval_brief.py) fails wrong answers. Review blocker 4 (2026-11-17): bare substring checks passed a brief
whose badge said rich because `ats: partial` sat in its coverage block, and passed 'sha256:' and code-only mentions."""
import os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "eval_brief.py")
BOILER = ("These are strings present in public code; a flag or route is evidence that something is being built, not that it "
          "will ship, and the reading of what a name refers to may be wrong.")
FOOTER = "```text\nunreleased 0.1.0 · cursor · run 2026-11-17T000000Z · {v} · findings 3\n```\n"


def brief(verdict: str, line: str, coverage: str, receipt="¹ App.js sha256:0123456789ab@42") -> str:
    return (f"🔎 unreleased 0.1.0 · cursor · 2026-11-17 · {verdict} · first run\n{line}\n\n"
            f"**The shape of it** (my reading): Agents and an editor.\n\n{receipt}\n\n**Coverage**: {coverage}\n\n{BOILER}\n\n"
            + FOOTER.format(v=verdict))


class Grader(unittest.TestCase):
    def grade(self, case: str, text: str) -> tuple[int, str]:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(text)
        p = subprocess.run([sys.executable, "-I", TOOL, case, f.name], capture_output=True, text=True)
        os.unlink(f.name)
        return p.returncode, p.stdout

    def test_the_trials_wrong_answer_fails(self):
        # the brief the trial produced: badge rich, "partial" only inside the ats line, app unread and unsaid
        rc, out = self.grade("cursor-blocked-page", brief("rich", "Read 7.6 MB in 38 scripts.", "verdict: rich; ats: partial (unverified board); robots.txt read; /dashboard listed"))
        self.assertEqual(rc, 1, out)
        self.assertIn("badge says rich", out)
        self.assertIn("missing: could not see", out)

    def test_the_right_answer_passes(self):
        rc, out = self.grade("cursor-blocked-page", brief(
            "partial", "Read 7.6 MB in 38 scripts. Could not see the app: the site's robots.txt asks crawlers to stay out of /dashboard.",
            "Verdict partial; pages 1 of 2 (/dashboard not checked)"))
        self.assertEqual(rc, 0, out)

    def test_a_phrase_only_in_the_boilerplate_or_footer_does_not_count(self):
        rc, out = self.grade("notion-marketplace", brief("rich", "Read 8 MB.", "verdict: rich", receipt="¹ app.js sha256:0123456789ab@42")
                             .replace("cursor", "notion") + "\n")
        self.assertIn("missing: present in code", out)      # "present in public code" in the boilerplate is not the brief's claim

    def test_a_key_in_code_is_not_the_phrase(self):
        rc, out = self.grade("notion-marketplace", brief("rich", "Set aside: `MARKETPLACE_CHECKGATE_X`, present in code.", "verdict: rich").replace("cursor", "notion"))
        self.assertIn("missing: marketplace", out); self.assertIn("missing: checkGate", out)

    def test_a_bare_sha256_is_not_a_receipt(self):
        rc, out = self.grade("cursor-blocked-page", brief("partial", "Could not see /dashboard: robots.txt.", "verdict: partial", receipt="¹ sha256: see the run"))
        self.assertIn("no receipt", out)

    def test_whole_words_still_allow_plurals_and_urls(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("eval_brief", TOOL); g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
        for phrase, text in (("job", "12 jobs posted"), ("certificate", "certificates show"), ("403", "got 403s"), ("/dashboard", "cursor.com/dashboard")):
            self.assertTrue(g.has_phrase(phrase, g.norm(text)), phrase)
        for phrase, text in (("partial", "partially announced"), ("waitlist", "agents_waitlist"), ("partial", "ats-partial")):
            self.assertFalse(g.has_phrase(phrase, g.norm(text)), phrase)

    def test_a_capitalised_contradicting_verdict_line_fails(self):
        rc, out = self.grade("cursor-blocked-page", brief(
            "partial", "Could not see the app: robots.txt asks crawlers to stay out of /dashboard.", "Verdict: rich"))
        self.assertIn("a coverage line says rich", out)

    def test_every_case_names_its_verdict(self):
        import json
        with open(os.path.join(ROOT, "evals", "evals.json"), encoding="utf-8") as f:
            self.assertEqual([c["id"] for c in json.load(f)["cases"] if not c.get("verdict")], [])

    def test_the_shipped_examples_still_pass(self):
        for case, path in (("linear-fresh-host", "docs/examples/linear-brief.md"), ("vercel-footnoted", "docs/examples/vercel-brief.md")):
            with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                rc, out = self.grade(case, f.read())
            self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
