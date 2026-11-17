"""The skill's instructions and the engine's output agree: routing rows point at files that exist, the
vocabulary the brief may use is the vocabulary emit prints, the budgets hold, and no forbidden word leaks."""
import os, re, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(os.path.dirname(HERE), "skills", "unreleased")
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import emit

def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


SKILL = _read(ROOT, "SKILL.md")
REFS = os.path.join(ROOT, "references")
PHRASES = ["present in code", "newly present since", "flipped on/off since", "removed since", "referenced in strings", "new subdomain",
           "job signal", "on the pricing page", "disallowed from search", "in the sitemap", "headline on landing pages",
           "announced", "partially announced", "no public mention found", "could not see"]
FORBIDDEN = re.compile(r"\b(confirmed|launching|will ship)\b", re.I)


class SkillContract(unittest.TestCase):
    def test_root_budget(self):
        self.assertLessEqual(len(SKILL.encode("utf-8")), 6 * 1024)

    def test_routing_rows_name_existing_references_and_every_reference_is_routed(self):
        routed = set(re.findall(r"`references/([a-z-]+)\.md`", SKILL))
        on_disk = {f[:-3] for f in os.listdir(REFS) if f.endswith(".md")}
        self.assertEqual(routed, on_disk)
        self.assertGreaterEqual(len(routed), 6)

    def test_routing_row_and_reference_agree_on_when_it_is_read(self):
        """Review blocker 5 (2026-11-17): SKILL.md routed report.md "after the brief, every run" while report.md opened "read when the
        person asks for a file": a host had to guess. Each reference's opening "Read ..." line must carry its row's trigger."""
        for situation, ref in re.findall(r"^\| ([^|]+?) \| `references/([a-z-]+)\.md` \|", SKILL, re.M):
            if "every run" in situation:
                opening = _read(REFS, f"{ref}.md").split("\n\n")[1]
                self.assertIn("every run", opening, f"{ref}.md opening disagrees with SKILL.md's row {situation!r}")
                self.assertFalse(re.match(r"Read (only )?when the person asks", opening), ref)

    def test_laws_cover_planner_coverage_vocabulary_receipts_footer_check_redaction(self):
        for n, word in [(1, "PLANNER"), (2, "COVERAGE"), (3, "VOCABULARY"), (4, "RECEIPT"), (5, "evidence.md"), (6, "UNANNOUNCED"), (7, "REDACTIONS")]:
            self.assertRegex(SKILL, rf"\*\*LAW {n} - [^*]*{re.escape(word)}", f"LAW {n}")

    def test_vocabulary_matches_the_engine(self):
        brief = _read(REFS, "brief.md")
        for p in PHRASES:
            self.assertIn(p, brief, p); self.assertIn(p.split(" <")[0], SKILL.replace("*", ""), p)
        for v in emit.PHRASE.values():
            self.assertTrue(any(v.startswith(p) for p in PHRASES) or v == "redirect", v)
        for v in emit.CHECK_PHRASE.values():
            self.assertTrue(v == "unchecked" or any(v.startswith(p) for p in PHRASES), v)

    def test_engine_output_carries_no_forbidden_word(self):
        # the disclaimer itself says "not that it will ship": the negated use is the one allowed form
        self.assertIsNone(FORBIDDEN.search(emit.BOILERPLATE.replace("not that it will ship", "")))
        for v in list(emit.PHRASE.values()) + list(emit.CHECK_PHRASE.values()):
            self.assertIsNone(FORBIDDEN.search(v), v)

    def test_cli_commands_in_skill_exist(self):
        cli = _read(ROOT, "scripts", "unreleased.py")
        for cmd in re.findall(r'unreleased\.py"? (run|diff|library|doctor|compare|setup)\b', SKILL):
            self.assertIn(f'sub.add_parser("{cmd}"', cli, cmd)


if __name__ == "__main__":
    unittest.main()
