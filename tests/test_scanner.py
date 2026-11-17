import unittest
from helpers import fixture  # sets sys.path
import scanner


class ScannerSeam(unittest.TestCase):
    """Internal seam: balanced object/array literals in minified JS and page JSON, with shallow keys/values."""

    def lits(self, text, **kw):
        return list(scanner.iter_literals(text, **kw))

    def test_finds_gate_map_with_values(self):
        js = 'var x={"ff_a":!0,"ff_b":!1,"ff_c":true,"ff_d":false,n:1};'
        objs = [l for l in self.lits(js) if l.kind == "object"]
        self.assertEqual(len(objs), 1)
        o = objs[0]
        self.assertEqual(o.keys, ["ff_a", "ff_b", "ff_c", "ff_d", "n"])
        self.assertEqual(o.values, [True, False, True, False, 1])

    def test_nested_literals_are_all_yielded_with_depth(self):
        js = 'a={outer:{inner:{deep:!0}},list:[{k:"v"},{k:"w"}]};'
        ls = self.lits(js)
        kinds = sorted((l.kind, l.depth) for l in ls)
        self.assertIn(("object", 0), kinds)
        self.assertIn(("object", 1), kinds)
        self.assertIn(("array", 1), kinds)
        self.assertIn(("object", 2), kinds)
        arr = next(l for l in ls if l.kind == "array")
        self.assertEqual(len([c for c in scanner.children(ls, arr)]), 2)

    def test_strings_with_braces_and_quotes_do_not_break_balance(self):
        js = 'o={a:"}{\\"",b:\'{\',c:`x${y}z}`,d:!0};'
        objs = [l for l in self.lits(js) if l.kind == "object"]
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].keys, ["a", "b", "c", "d"])
        self.assertEqual(objs[0].values[3], True)

    def test_function_values_are_marked_fn_and_do_not_break_balance(self):
        js = 'o={visible:()=>!1,cb:function(a){return{a:1}},k:"v"};'
        objs = [l for l in self.lits(js) if l.kind == "object" and "visible" in l.keys]
        self.assertEqual(len(objs), 1)
        o = objs[0]
        self.assertEqual(o.values[0], "fn")
        self.assertEqual(o.values[1], "fn")
        self.assertEqual(o.values[2], "v")

    def test_arrays_yield_scalar_items(self):
        js = 'x=["ff_one","ff_two","ff_three"];'
        arr = next(l for l in self.lits(js) if l.kind == "array")
        self.assertEqual(arr.items, ["ff_one", "ff_two", "ff_three"])

    def test_unbalanced_literal_is_skipped_not_fatal(self):
        js = 'bad={a:1,b:{c:2};good={x:!0};'
        ls = self.lits(js)
        self.assertTrue(any(l.keys == ["x"] for l in ls))

    def test_real_figma_bootstrap_two_thousand_gates_with_values(self):
        text = fixture("scanner", "figma-labmate.json")
        ls = self.lits(text)
        big = max((l for l in ls if l.kind == "object"), key=lambda l: len(l.keys))
        self.assertGreaterEqual(len(big.keys), 2100)
        self.assertEqual(sum(1 for v in big.values if v is True), 401)
        self.assertIn("make_local_native_ios_preview", big.keys)
        self.assertIn("figjam_code_layers", big.keys)

    def test_large_body_scans_in_reasonable_time(self):
        import time
        text = fixture("scanner", "figma-labmate.json") * 40   # ~3 MB
        t0 = time.time(); n = sum(1 for _ in scanner.iter_literals(text)); dt = time.time() - t0
        self.assertGreater(n, 40)
        self.assertLess(dt, 6.0, f"scan took {dt:.1f}s")


if __name__ == "__main__":
    unittest.main()


class Phase(unittest.TestCase):
    """Quotes inside regex literals, comments and cut strings must not flip the string phase (worker-notes-B §1,
    worker-notes-A §2): the literals after them stay visible, and an unterminated quote costs bounded time."""

    def test_regex_literal_with_quote_does_not_hide_the_next_object(self):
        js = "var R=/(?=([^']*'[^']*')*[^']*$)/g;x={a:\"1\",b:!0};"
        self.assertTrue(any(l.keys == ["a", "b"] for l in scanner.iter_literals(js)))

    def test_stray_quote_after_regex_is_bounded(self):
        js = "var R=/'/;" + ("x={ab:1};" * 2000) + "'"
        self.assertEqual(sum(1 for _ in scanner.iter_literals(js)), 2000)

    def test_comments_and_division(self):
        js = "/*! don't */ a={bb:1}; // it's\nc={dd:2}; e=(x+1)/2; f={gg:'/'}; h=[1,2]/4"
        ks = [l.keys for l in scanner.iter_literals(js) if l.kind == "object"]
        self.assertIn(["bb"], ks); self.assertIn(["dd"], ks); self.assertIn(["gg"], ks)

    def test_cut_json_parse_string_is_scanned_as_code(self):
        # a bundle cut by the byte cap inside JSON.parse('…'): the tail is data we want, not a 62 s rescan
        body = "var a={xx:1};JSON.parse('" + ("{\\'kk\\':1}," * 500) + "tail"
        self.assertGreaterEqual(sum(1 for _ in scanner.iter_literals(body)), 500)
