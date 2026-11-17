"""The CLI shell: commands that take run references."""
import json, os, subprocess, sys, tempfile, unittest

CLI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "unreleased", "scripts", "unreleased.py")


def _run_folder(home: str, slug: str, run_id: str, rows: list[dict]) -> str:
    d = os.path.join(home, "runs", slug, run_id); os.makedirs(d)
    with open(os.path.join(d, "evidence.jsonl"), "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)
    return d


class Compare(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.a = _run_folder(self.home, "acme", "2026-11-01T000000Z", [{"kind": "gate", "key": "beta", "value": False}, {"kind": "gate", "key": "old", "value": True}])
        self.b = _run_folder(self.home, "acme", "2026-11-08T000000Z", [{"kind": "gate", "key": "beta", "value": True}, {"kind": "route", "key": "/new", "value": None}])

    def cli(self, *args):
        env = dict(os.environ, UNRELEASED_HOME=self.home)
        return subprocess.run([sys.executable, "-I", CLI, *args], capture_output=True, text=True, env=env)

    def test_compare_takes_run_ids(self):
        p = self.cli("compare", "2026-11-01T000000Z", "2026-11-08T000000Z")
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)
        self.assertEqual(out["only_in_a"], ["gate:old"]); self.assertEqual(out["only_in_b"], ["route:/new"])
        self.assertEqual(out["value_changed"], ["beta: False -> True"])

    def test_compare_still_takes_run_folders(self):
        p = self.cli("compare", self.a, self.b)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_a_run_id_two_products_share_is_refused_not_guessed(self):
        _run_folder(self.home, "beta", "2026-11-01T000000Z", [])
        p = self.cli("compare", "2026-11-01T000000Z", "2026-11-08T000000Z")
        self.assertEqual(p.returncode, 3); self.assertIn("pass the run folder", p.stderr)

    def test_an_unknown_run_is_a_message_not_a_traceback(self):
        p = self.cli("compare", "2026-11-01T000000Z", "no-such-run")
        self.assertEqual(p.returncode, 3)
        self.assertIn("no-such-run", p.stderr); self.assertNotIn("Traceback", p.stderr)


if __name__ == "__main__":
    unittest.main()
