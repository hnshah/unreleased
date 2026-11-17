"""S1 seam: hidden.extract(body, artifact) finds hidden-surface signals from corpus excerpts.

Expected values come from tests/goldens/<product>.json (the readers' hand findings), never from the code.
"""
import unittest
from helpers import fixture, fixture_meta, golden  # sets sys.path
from schema import Source
from extractors import hidden


def _artifact(shape, name):
    meta = fixture_meta(shape, name)
    return Source(url=meta["url"] or "https://example.invalid/" + name, sha256=meta["sha256_full"], offset=-1)


def _run(name):
    body = fixture("hidden", name)
    return body, hidden.extract(body, _artifact("hidden", name))


class RetoolReleaseSchedule(unittest.TestCase):
    """Sanity content releases `{id,name,status:"scheduled"|"active"|"published"}`: the title is the key, the
    status the value; only scheduled/active/draft entries are hidden surfaces."""

    @classmethod
    def setUpClass(cls):
        cls.body, cls.obs = _run("retool-1.js")
        cls.keys = {o.key: o for o in cls.obs}

    def test_golden_scheduled_release_is_found_with_its_status(self):
        want = golden("retool")["expect"]["hidden"]
        missing = [k for k in want if k not in self.keys]
        self.assertEqual(missing, [], f"missing {missing}")
        o = self.keys["Remove R2 Waitlist"]
        self.assertEqual(o.kind, "hidden")
        self.assertEqual(o.extractor, "hidden")
        self.assertEqual(o.value, "scheduled")
        self.assertEqual(o.group, "release")
        self.assertEqual(o.confidence, "high")
        self.assertIn("ruBV5nvAo", o.context)
        self.assertEqual(self.body[o.source.offset:o.source.offset + len(o.key)], o.key)

    def test_active_release_is_found_and_published_ones_are_not(self):
        self.assertEqual(self.keys["Marketing launch of R2"].value, "active")
        self.assertNotIn("October Launch", self.keys)
        self.assertNotIn("giles test release", self.keys)

    def test_reader_named_noise_is_absent(self):
        for n in golden("retool")["noise"]:
            self.assertNotIn(n, self.keys)


class HiddenSurfaces(unittest.TestCase):
    """The other hidden-surface shapes, one product each."""

    def test_vercel_internal_playgrounds_with_visible_false(self):
        body, obs = _run("vercel-1.js")
        keys = {o.key: o for o in obs}
        for p in ("/internal/vip-startups-onboarding-modal", "/internal/onboard-agent", "/internal/token-pass"):
            self.assertIn(p, keys, p)
            self.assertEqual(keys[p].value, "hidden")
            self.assertEqual(keys[p].group, "hidden-route")
            self.assertEqual(body[keys[p].source.offset:keys[p].source.offset + len(p)], p)
        self.assertEqual(keys["/internal/vip-startups-onboarding-modal"].context, "VIP Startup Onboarding Modal")
        # a hidden entry that is not under /internal/ is still a hidden surface
        self.assertEqual(keys["/ai-gateway-token-pass-empty-state"].value, "hidden")
        for n in golden("vercel")["noise"]:
            self.assertNotIn(n, keys)

    def test_linear_waitlist_event_enum(self):
        body, obs = _run("linear-1.js")
        keys = {o.key: o for o in obs}
        self.assertEqual(keys["MOBILE_DIFFS_WAITLIST"].value, "Mobile Diffs Waitlist")
        self.assertEqual(keys["MOBILE_DIFFS_WAITLIST"].group, "waitlist")
        self.assertIn("AGENTS_WAITLIST", keys)
        self.assertNotIn("ASKS_PLUS_TRIAL_CLICKED", keys)
        for n in golden("linear")["noise"]:
            self.assertNotIn(n, keys)

    def test_lovable_noindex_route(self):
        body, obs = _run("lovable-1.js")
        keys = {o.key: o for o in obs}
        self.assertIn("/lovtok", keys)
        self.assertEqual(keys["/lovtok"].value, "noindex")
        self.assertEqual(keys["/lovtok"].group, "noindex")
        self.assertEqual(body[keys["/lovtok"].source.offset:][:7], "/lovtok")

    def test_notion_waitlist_slug(self):
        body, obs = _run("notion-1.js")
        keys = {o.key: o for o in obs}
        self.assertIn("plus_lock_waitlist", keys)
        self.assertEqual(keys["plus_lock_waitlist"].group, "waitlist")
        self.assertEqual(keys["plus_lock_waitlist"].confidence, "low")
        for n in golden("notion")["noise"]:
            self.assertNotIn(n, keys)

    def test_retool_waitlist_route_in_html(self):
        body, obs = _run("retool-2.html")
        keys = {o.key: o for o in obs}
        self.assertIn("/agents-waitlist", keys)
        self.assertEqual(keys["/agents-waitlist"].group, "waitlist")
        self.assertEqual(keys["/agents-waitlist"].confidence, "medium")


if __name__ == "__main__":
    unittest.main()
