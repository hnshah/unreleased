"""S1 seam: extractors.proto.extract(body, artifact) finds the readers' enum values and message names from
protobuf-JS descriptors in corpus excerpts. Expected values come from tests/goldens/dropbox.json."""
import unittest
from helpers import fixture, fixture_meta, golden  # sets sys.path
from schema import Source
from extractors import proto


def _run(name):
    meta = fixture_meta("proto", name)
    body = fixture("proto", name)
    return proto.extract(body, Source(meta["url"] or "", meta["sha256_full"])), body


class ProtoDropbox(unittest.TestCase):
    """Dropbox's login bundle: TS-enum objects `((y={})[y.CODEX=1]="CODEX",…)` registered with
    `setEnumType(ey,"coding_agent.AgentRuntime",[{no,name:"AGENT_RUNTIME_CODEX"}])`, and messages
    `X.typeName="pkg.Msg",X.fields=newFieldList(function(){return[{no,name,kind,T}]})`."""
    FIXTURES = ["dropbox-1.js", "dropbox-2.js", "dropbox-3.js", "dropbox-4.js", "dropbox-5.js"]

    def test_every_golden_enum_value_is_found(self):
        expected = golden("dropbox")["expect"]["enum"]
        found, all_bodies = set(), ""
        for name in self.FIXTURES:
            obs, body = _run(name)
            all_bodies += body
            found |= {o.key for o in obs if o.kind == "enum"}
        for g in expected:
            self.assertIn('="' + g + '"', all_bodies, f"golden {g} is in no fixture: cut one")
        self.assertTrue(set(expected) <= found, sorted(set(expected) - found))

    def test_enum_observation_shape(self):
        obs, body = _run("dropbox-2.js")
        enums = {(o.group, o.key): o for o in obs if o.kind == "enum"}
        o = enums[("AgentRuntime", "UNIFIED_HARNESS")]
        self.assertEqual(o.value, 3)
        self.assertEqual(o.context, "coding_agent.AgentRuntime AGENT_RUNTIME_UNIFIED_HARNESS")
        self.assertEqual(o.extractor, "proto"); self.assertEqual(o.confidence, "high")
        self.assertEqual(body[o.source.offset:o.source.offset + len(o.key)], o.key)
        self.assertNotIn(("AgentRuntime", "UNSPECIFIED"), enums)    # the proto3 zero value is boilerplate

    def test_message_observation_shape(self):
        obs, body = _run("dropbox-2.js")
        msgs = {o.key: o for o in obs if o.kind == "proto"}
        self.assertIn("bolt.OpResult", msgs)
        o = msgs["bolt.OpResult"]
        self.assertEqual(o.params, ["channel_id", "success"])
        self.assertEqual(o.context, "channel_id success")
        self.assertEqual(o.group, "bolt")
        self.assertEqual(body[o.source.offset:o.source.offset + len(o.key)], o.key)

    def test_enum_values_carry_their_enum_as_group_and_package_as_context(self):
        obs, _ = _run("dropbox-4.js")
        o = next(o for o in obs if o.kind == "enum" and o.key == "COMMITS_AND_CREDITS")
        self.assertEqual(o.group, "BillingDashboard")
        self.assertTrue(o.context.startswith("metering_apiv2.BillingDashboard"))

    def test_no_reader_named_noise(self):
        for name in self.FIXTURES:
            obs, _ = _run(name)
            for n in golden("dropbox")["noise"]:
                self.assertNotIn(n, {o.key for o in obs})


class ProtoShapes(unittest.TestCase):
    def test_protobuf_es_make_enum_and_message(self):
        js = ('const E=proto3.makeEnum("pkg.Mode",[{no:0,name:"MODE_UNSPECIFIED"},{no:1,name:"MODE_FAST",localName:"FAST"},'
              '{no:2,name:"MODE_SLOW"}]);const M=proto3.makeMessageType("pkg.Thing",()=>[{no:1,name:"id",kind:"scalar",T:9},'
              '{no:2,name:"mode",kind:"enum",T:E}]);')
        obs = proto.extract(js, Source("u", "s"))
        enums = sorted((o.group, o.key, o.value) for o in obs if o.kind == "enum")
        self.assertEqual(enums, [("Mode", "FAST", 1), ("Mode", "SLOW", 2)])   # prefix stripped like localName
        m = next(o for o in obs if o.kind == "proto")
        self.assertEqual((m.key, m.params), ("pkg.Thing", ["id", "mode"]))

    def test_plain_arrays_of_objects_are_not_descriptors(self):
        js = 'x=[{no:1,name:"a"},{no:2,name:"b"}];y=[{name:"c",kind:"scalar"}];'
        self.assertEqual(proto.extract(js, Source("u", "s")), [])


if __name__ == "__main__":
    unittest.main()
