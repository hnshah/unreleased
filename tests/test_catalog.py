"""S1 seam: extractors.catalog.extract(body, artifact) finds the readers' catalog keys from corpus excerpts.

Expected values come from tests/goldens/<product>.json (the readers' hand findings), never from running the
extractor. A golden key counts as found when an emitted key equals it, or ends with it where the reader
abbreviated a prefixed name (loom's `hyperframes-overlays-agent-version` is `loom-hyperframes-…` in the bytes).
"""
import unittest
from helpers import fixture, fixture_meta, golden  # sets sys.path
from schema import Source, Observation
from extractors import catalog


def _src(meta: dict) -> Source:
    return Source(url=meta["url"] or "", sha256=meta["sha256_full"])


def _run(shape: str, name: str) -> tuple[list[Observation], str]:
    body = fixture(shape, name)
    return catalog.extract(body, _src(fixture_meta(shape, name))), body


def _missing(obs: list[Observation], expected: list[str], body_text: str) -> list[str]:
    """Golden keys present in this fixture's bytes that no observation names."""
    keys = {o.key for o in obs}
    out = []
    for g in expected:
        if g not in body_text:
            continue   # a golden that lives in another fixture of the same product
        if g in keys or any(k.endswith(g) for k in keys):
            continue
        out.append(g)
    return out


class CatalogLovable(unittest.TestCase):
    """Lovable's flag-catalog chunk: sibling objects `{key, team, scope, fallback, variants?}` at the top level."""
    FIXTURES = ["lovable-1.js", "lovable-2.js", "lovable-3.js"]

    def test_every_golden_key_is_found_across_the_fixtures(self):
        expected = golden("lovable")["expect"]["catalog"]
        all_bodies, found = "", set()
        for name in self.FIXTURES:
            obs, body = _run("catalog", name)
            self.assertFalse(_missing(obs, expected, body), f"{name}: missing")
            all_bodies += body; found |= {o.key for o in obs}
        for g in expected:
            self.assertIn(g, all_bodies, f"golden {g} is in no fixture: cut one")
        self.assertTrue(set(expected) <= found, sorted(set(expected) - found))

    def test_observation_shape(self):
        obs, body = _run("catalog", "lovable-1.js")
        meta = fixture_meta("catalog", "lovable-1.js")
        by_key = {o.key: o for o in obs}
        o = by_key["brl-pix-pricing"]
        self.assertEqual(o.kind, "catalog")
        self.assertEqual(o.extractor, "catalog")
        self.assertEqual(o.confidence, "high")
        self.assertEqual(o.value, {"enabled": False})          # the fallback literal, read not guessed
        self.assertEqual(o.group, "billing")                    # team is the sibling cluster
        self.assertIn("team=billing", o.context); self.assertIn("scope=server_geo", o.context)
        self.assertLessEqual(len(o.context), 200)
        self.assertEqual(o.source.url, meta["url"]); self.assertEqual(o.source.sha256, meta["sha256_full"])
        self.assertEqual(body[o.source.offset:o.source.offset + len(o.key)], o.key)   # receipt: offset of the key
        self.assertEqual(o.tier, "key-list")                    # tiers are assigned later, not here
        # an experiment entry keeps its arms as params and its fallback variant as the value
        self.assertEqual(by_key["active-workspace-resurrection-offer-v2"].params,
                         ["disabled", "first-month-five", "first-month-one", "half-price", "holdout"])
        self.assertEqual(by_key["active-workspace-resurrection-offer-v2"].value, {"variant": "disabled"})

    def test_ids_are_unique_and_stable(self):
        a, _ = _run("catalog", "lovable-1.js"); b, _ = _run("catalog", "lovable-1.js")
        self.assertEqual([o.id for o in a], [o.id for o in b])
        self.assertEqual(len({o.id for o in a}), len(a))

    def test_no_reader_named_noise(self):
        for name in self.FIXTURES:
            obs, _ = _run("catalog", name)
            keys = {o.key for o in obs}
            for n in golden("lovable")["noise"]:
                self.assertNotIn(n, keys)


class CatalogLoom(unittest.TestCase):
    """Loom's LD→Statsig migration map: `{"name":{team:i.u.X,statsigLink:"…"}, [v]:{…}}` keyed by the parent's
    keys, some of them `[v]` variables declared just above. The rest of loom's golden "catalog" keys live in
    its `UPPER:"kebab"` constant tables, which are the registry shape (see tests/test_registry.py)."""

    def test_keyed_map_entries_are_found_by_parent_key(self):
        obs, body = _run("catalog", "loom-1.js")
        by_key = {o.key: o for o in obs}
        expected_here = [g for g in golden("loom")["expect"]["catalog"] if '"' + g + '"' in body]
        self.assertEqual(expected_here, ["rollout-post-to-community"])
        o = by_key["rollout-post-to-community"]
        self.assertEqual(o.group, "Activation")                   # team=i.u.Activation, read as a ref
        self.assertIn("console.statsig.com/gates/rollout-post-to-community", o.context)
        self.assertEqual(body[o.source.offset:o.source.offset + len(o.key)], o.key)
        # `[g]:{…}` keys resolve through `g="rollout-community-looms"` declared above the map; the receipt is there
        self.assertIn("rollout-community-looms", by_key); self.assertIn("dark-mode-toggle", by_key)
        for o in obs:
            self.assertEqual(body[o.source.offset:o.source.offset + len(o.key)], o.key, f"receipt for {o.key}")
        self.assertGreaterEqual(len(obs), 36)                     # the reader counted 36 entries with team names

    def test_no_reader_named_noise(self):
        obs, _ = _run("catalog", "loom-1.js")
        for n in golden("loom")["noise"]:
            self.assertNotIn(n, {o.key for o in obs})


class CatalogShapes(unittest.TestCase):
    """Hand-written minimal shapes the classifier must and must not claim."""

    def test_array_of_entries_with_name_and_default(self):
        js = 'const F=[{name:"alpha-one",defaultValue:!1,description:"first"},{name:"beta-two",defaultValue:!0,description:"second"},{name:"gamma",defaultValue:"x",description:"third"}];'
        obs = catalog.extract(js, Source("u", "s"))
        self.assertEqual(sorted(o.key for o in obs), ["alpha-one", "beta-two", "gamma"])
        o = next(o for o in obs if o.key == "alpha-one")
        self.assertEqual(o.value, False); self.assertIn("first", o.context)

    def test_two_entries_are_not_a_catalog(self):
        js = 'x=[{key:"a",team:"t",scope:"s"},{key:"b",team:"t",scope:"s"}];'
        self.assertEqual(catalog.extract(js, Source("u", "s")), [])

    def test_entries_without_metadata_are_not_a_catalog(self):
        js = 'x=[{key:"a",v:1},{key:"b",v:2},{key:"c",v:3},{key:"d",v:4}];'
        self.assertEqual(catalog.extract(js, Source("u", "s")), [])


if __name__ == "__main__":
    unittest.main()
