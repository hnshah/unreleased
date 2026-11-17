"""S1 seam: manifest.extract(body, artifact) finds the readers' chunk/module names from corpus excerpts.

Expected values come from tests/goldens/<product>.json (the readers' hand findings), never from the code.
"""
import unittest
from helpers import fixture, fixture_meta, golden  # sets sys.path
from schema import Source
from extractors import manifest


def _artifact(shape, name):
    meta = fixture_meta(shape, name)
    return Source(url=meta["url"] or "https://example.invalid/" + name, sha256=meta["sha256_full"], offset=-1)


def _run(name):
    body = fixture("manifest", name)
    return body, manifest.extract(body, _artifact("manifest", name))


class HuggingFaceViteMapDeps(unittest.TestCase):
    """`__vite__mapDeps` array of `Name-hash.js` chunk files: the human name is the key, hashes and
    extensions stripped, `Icon*` names dropped."""

    @classmethod
    def setUpClass(cls):
        cls.body, cls.obs = _run("huggingface-1.js")
        cls.keys = {o.key: o for o in cls.obs}

    def test_golden_component_names_are_found(self):
        want = golden("huggingface")["expect"]["manifest"]
        missing = [k for k in want if k not in self.keys]
        self.assertEqual(missing, [], f"missing {missing}")
        for k in want:
            o = self.keys[k]
            self.assertEqual(o.kind, "manifest")
            self.assertEqual(o.extractor, "manifest")
            self.assertEqual(o.confidence, "high")

    def test_context_is_the_chunk_file_and_receipt_points_at_it(self):
        o = self.keys["NewContainerImageForm"]
        self.assertEqual(o.context, "NewContainerImageForm-Tz8MZHAJ.js")
        self.assertEqual(self.body[o.source.offset:o.source.offset + len(o.key)], o.key)

    def test_group_is_the_name_noun(self):
        self.assertEqual(self.keys["NewContainerImageForm"].group, "container")
        self.assertEqual(self.keys["ContainerTagDelete"].group, "container")
        self.assertEqual(self.keys["PreReleaseCountdown"].group, "prerelease")
        self.assertEqual(self.keys["PreReleaseNotifyButton"].group, "prerelease")

    def test_icon_chunks_and_reader_noise_are_absent(self):
        for n in golden("huggingface")["noise"]:
            self.assertNotIn(n, self.keys)
        self.assertFalse([k for k in self.keys if k.startswith("Icon")], "Icon* chunk names")

    def test_hashes_and_extensions_are_stripped(self):
        for k in self.keys:
            self.assertFalse(k.endswith((".js", ".css")), k)
        self.assertIn("ActivityFeed", self.keys)

    def test_cap_and_context_bound(self):
        self.assertLessEqual(len(self.obs), 800)
        for o in self.obs:
            self.assertLessEqual(len(o.context), 200)


class ChunkNameExcerpts(unittest.TestCase):
    """Excerpts of manifests too large to commit whole, read as text runs."""

    def test_lovable_cofounder_chunks_share_the_cofounder_group(self):
        body, obs = _run("lovable-1.js")
        keys = {o.key: o for o in obs}
        for k in ("cofounder", "useCofounderOnboardingKickoff", "cofounderOnboarding"):
            self.assertIn(k, keys, k)
            self.assertEqual(keys[k].group, "cofounder", k)
        self.assertEqual(keys["cofounder"].context, "assets/cofounder-BopHSQDa.js")
        self.assertEqual(body[keys["cofounder"].source.offset:][:9], "cofounder")

    def test_notion_webpack_id_name_map(self):
        # `{…,31369:"agent-chat-transcribe-audio-to-text",…}`: bare numeric keys, read as `id:"name"` runs
        body, obs = _run("notion-1.js")
        keys = {o.key: o for o in obs}
        self.assertIn("agent-chat-transcribe-audio-to-text", keys)
        o = keys["agent-chat-transcribe-audio-to-text"]
        self.assertEqual(o.context, "31369:agent-chat-transcribe-audio-to-text")
        self.assertEqual(o.group, "agent")
        self.assertEqual(body[o.source.offset:o.source.offset + len(o.key)], o.key)
        self.assertFalse([k for k in keys if k.startswith("icon-")], "icon-* module names")
        for n in golden("notion")["noise"]:
            self.assertNotIn(n, keys)

    def test_zoom_vite_chunks_with_dot_hash(self):
        # the reader filed `app-new-experience-portal` under strings; the bytes are a chunk name
        body, obs = _run("zoom-1.js")
        keys = {o.key: o for o in obs}
        self.assertIn("app-new-experience-portal", keys)
        self.assertEqual(keys["app-new-experience-portal"].context, "./chunks/app-new-experience-portal.DcfEdPUI.js")
        self.assertEqual(keys["app-new-experience-portal"].confidence, "high")
        for n in golden("zoom")["noise"]:
            self.assertNotIn(n, keys)


if __name__ == "__main__":
    unittest.main()
