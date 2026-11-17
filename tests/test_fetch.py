import gzip, json, os, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from helpers import *  # noqa: F401,F403
import fetch


class Stub(BaseHTTPRequestHandler):
    log = []
    routes = {}

    def do_GET(self):
        Stub.log.append({"path": self.path, "ua": self.headers.get("User-Agent", "")})
        status, body, headers = Stub.routes.get(self.path, (404, b"nope", {}))
        self.send_response(status)
        for k, v in headers.items(): self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def log_message(self, *a): pass


GZ_PAYLOAD = os.urandom(5000)        # incompressible: the compressed stream is longer than the cap


class FetchSeam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Stub); cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.port}"
        big = b"x" * 10_000
        Stub.routes = {
            "/ok": (200, b"<html>hello</html>", {"Content-Type": "text/html"}),
            "/forbidden": (403, b"denied", {}),
            "/challenge": (200, b"<html><title>Just a moment...</title><script>window._cf_chl_opt={}</script></html>", {}),
            "/big": (200, big, {}),
            "/gz": (200, gzip.compress(b"<html>zipped</html>"), {"Content-Encoding": "gzip"}),
            "/gzbig": (200, gzip.compress(GZ_PAYLOAD), {"Content-Encoding": "gzip"}),
            "/notgz": (200, b"plain bytes, not gzip", {"Content-Encoding": "gzip"}),
            "/a.js": (200, b"var a=1;", {"Content-Type": "application/javascript"}),
            "/b.js": (200, b"var a=1;", {"Content-Type": "application/javascript"}),
            "/go": (302, b"", {"Location": "/private/x"}),
            "/hop": (302, b"", {"Location": "/ok"}),
            "/private/x": (200, b"<html>private</html>", {}),
        }

    def setUp(self):
        Stub.log.clear(); Stub.routes.pop("/robots.txt", None)
        self.sleeps = []
        self.clock = [1000.0]
        self.blobdir = tempfile.mkdtemp()
        self.f = fetch.LiveFetcher(blobs=fetch.BlobStore(self.blobdir), min_interval=1.0,
                                   sleep=lambda s: (self.sleeps.append(s), self.clock.__setitem__(0, self.clock[0] + s)),
                                   now=lambda: self.clock[0])

    def test_ok_fetch_has_project_ua_and_blob(self):
        r = self.f.get(self.base + "/ok", 1_000_000)
        self.assertEqual((r.status, r.state), (200, "ok"))
        self.assertIn("unreleased/", Stub.log[0]["ua"])
        self.assertIn("public pages only", Stub.log[0]["ua"])
        self.assertTrue(os.path.exists(os.path.join(self.blobdir, r.sha256)))

    def test_same_host_requests_are_spaced(self):
        self.f.get(self.base + "/ok", 1000); self.f.get(self.base + "/ok", 1000)
        self.assertTrue(any(s > 0.9 for s in self.sleeps), f"expected a ~1 s wait, got {self.sleeps}")

    def pages(self):
        return [e["path"] for e in Stub.log if e["path"] != "/robots.txt"]

    def test_robots_is_read_first_and_once_per_host(self):
        self.f.get(self.base + "/ok", 1000); self.f.get(self.base + "/a.js", 1000, kind="script")
        self.assertEqual([e["path"] for e in Stub.log], ["/robots.txt", "/ok", "/a.js"])

    def test_the_robots_command_reads_only_robots_txt(self):
        """Fresh-host trial (2026-11-17): a planning agent sent a GET to Cursor's /dashboard before reading robots.txt. `robots <url>...`
        answers allowed/disallowed from robots.txt alone, so a planner checks before it probes."""
        import argparse, contextlib, importlib.util, io
        spec = importlib.util.spec_from_file_location("unreleased_cli", os.path.join(os.path.dirname(fetch.__file__), "..", "unreleased.py"))
        cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
        Stub.routes["/robots.txt"] = (200, b"User-agent: *\nDisallow: /dashboard\n", {})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli.cmd_robots(argparse.Namespace(urls=[self.base + "/dashboard", self.base + "/pricing", "ftp://x"]))
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().splitlines(), [f"disallowed\t{self.base}/dashboard", f"allowed\t{self.base}/pricing", "invalid\tftp://x"])
        self.assertEqual([e["path"] for e in Stub.log], ["/robots.txt"])          # nothing but robots.txt, once

    def test_robots_disallow_is_never_requested(self):
        Stub.routes["/robots.txt"] = (200, b"User-agent: *\nDisallow: /ok\n", {})
        r = self.f.get(self.base + "/ok", 1000)
        self.assertEqual((r.status, r.state), ("robots.txt", "skipped-unconfigured"))
        self.assertEqual(self.pages(), [])
        self.assertEqual(self.f.get(self.base + "/a.js", 1000, kind="script").state, "ok")

    def test_robots_disallow_all_closes_the_host(self):
        """`Disallow: /` was skipped as "nothing to report" and so never honoured."""
        Stub.routes["/robots.txt"] = (200, b"User-agent: unreleased\nDisallow: /\n", {})
        for path in ("/ok", "/a.js", "/forbidden"):
            self.assertEqual(self.f.get(self.base + path, 1000).state, "skipped-unconfigured")
        self.assertEqual(self.pages(), [])

    def test_robots_for_other_agents_does_not_bind(self):
        Stub.routes["/robots.txt"] = (200, b"User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nDisallow:\n", {})
        self.assertEqual(self.f.get(self.base + "/ok", 1000).state, "ok")

    def test_robots_txt_itself_is_served_from_the_first_read(self):
        Stub.routes["/robots.txt"] = (200, b"User-agent: *\nDisallow: /lp/\n", {})
        a = self.f.get(self.base + "/robots.txt", 1000); b = self.f.get(self.base + "/robots.txt", 1000)
        self.assertEqual((a.state, b.body), ("ok", "User-agent: *\nDisallow: /lp/\n"))
        self.assertEqual(len(Stub.log), 1)

    def test_apis_are_not_gated_on_robots(self):
        Stub.routes["/robots.txt"] = (200, b"User-agent: *\nDisallow: /\n", {})
        self.assertEqual(self.f.get(self.base + "/a.js", 1000, kind="api").state, "ok")

    def test_a_redirect_into_a_disallowed_path_is_not_followed(self):
        """Review: urllib followed redirects itself, so `/go` -> `/private/x` read a page robots.txt disallows."""
        Stub.routes["/robots.txt"] = (200, b"User-agent: *\nDisallow: /private\n", {})
        r = self.f.get(self.base + "/go", 1000)
        self.assertEqual(r.state, "skipped-unconfigured"); self.assertNotIn("/private/x", self.pages())

    def test_an_allowed_redirect_is_followed_hop_by_hop(self):
        r = self.f.get(self.base + "/hop", 1000)
        self.assertEqual((r.state, r.body, r.url, r.final_url), ("ok", "<html>hello</html>", self.base + "/hop", self.base + "/ok"))
        self.assertEqual(self.pages(), ["/hop", "/ok"])

    def test_a_robots_txt_that_cannot_be_read_disallows_everything(self):
        """RFC 9309: 5xx or unreachable robots.txt means full disallow; 4xx means allow (the default 404 above)."""
        Stub.routes["/robots.txt"] = (503, b"down", {})
        self.assertEqual(self.f.get(self.base + "/ok", 1000).state, "skipped-unconfigured")
        self.assertEqual(self.pages(), [])

    def test_a_byte_order_mark_does_not_hide_the_first_group(self):
        Stub.routes["/robots.txt"] = (200, "\ufeffUser-agent: *\nDisallow: /ok\n".encode("utf-8"), {})
        self.assertEqual(self.f.get(self.base + "/ok", 1000).state, "skipped-unconfigured")

    def test_a_challenge_marker_inside_robots_txt_is_a_rule_not_a_challenge(self):
        Stub.routes["/robots.txt"] = (200, b"User-agent: *\nDisallow: /_Incapsula_Resource\n", {})
        self.assertEqual(self.f.get(self.base + "/ok", 1000).state, "ok")

    def test_one_host_however_it_is_spelled(self):
        self.f.get(self.base + "/forbidden", 1000)
        r = self.f.get(self.base.replace("127.0.0.1", "127.0.0.1".upper()) + "/ok", 1000)
        self.assertEqual(r.state, "blocked-403")
        self.assertEqual(fetch.host_key(fetch.urllib.parse.urlsplit("https://A.com:443/x")), "a.com")

    def test_a_recorded_robots_skip_replays_without_crashing(self):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "raw"))
        with open(os.path.join(d, "summary.json"), "w") as fh:
            json.dump({"pages": [{"url": "https://x.com/r", "status": "robots.txt", "state": "skipped-unconfigured"},
                                 {"url": "https://x.com/s", "status": "stopped", "state": "blocked-403"}]}, fh)
        rf = fetch.RecordedFetcher(d)
        self.assertEqual(rf.get("https://x.com/r", 10).state, "skipped-unconfigured")
        self.assertEqual(rf.get("https://x.com/s", 10).state, "blocked-403")

    def test_a_redirected_robots_txt_is_read_where_it_lands(self):
        Stub.routes["/robots.txt"] = (301, b"", {"Location": "/real-robots.txt"})
        Stub.routes["/real-robots.txt"] = (200, b"User-agent: *\nDisallow: /ok\n", {})
        try:
            self.assertEqual(self.f.get(self.base + "/ok", 1000).state, "skipped-unconfigured")
            self.assertNotIn("/ok", self.pages())
        finally:
            Stub.routes.pop("/real-robots.txt")

    def test_a_redirect_to_a_local_file_or_a_bad_port_is_not_followed(self):
        for target in ("file:///etc/passwd", "https://host:bad/"):
            Stub.routes["/evil"] = (302, b"", {"Location": target})
            r = self.f.get(self.base + "/evil", 1000)
            self.assertEqual((r.status, r.state), ("bad-redirect", "error"), target)
        Stub.routes.pop("/evil")

    def test_403_stops_the_host_and_is_never_retried(self):
        r = self.f.get(self.base + "/forbidden", 1000)
        self.assertEqual(r.state, "blocked-403")
        self.assertEqual(self.pages(), ["/forbidden"])
        again = self.f.get(self.base + "/ok", 1000)
        self.assertEqual((again.status, again.state), ("stopped", "blocked-403"))
        self.assertEqual(self.pages(), ["/forbidden"], "no request after a 403")

    def test_challenge_is_not_retried_and_stops_the_host(self):
        r = self.f.get(self.base + "/challenge", 1_000_000, kind="page")
        self.assertEqual(r.state, "challenge")
        self.assertEqual(self.f.get(self.base + "/ok", 1000).state, "challenge")
        self.assertEqual(self.pages(), ["/challenge"])
        self.assertFalse(any(s > 1.5 for s in self.sleeps), f"no challenge wait: {self.sleeps}")

    def test_cap_truncates_and_flags(self):
        r = self.f.get(self.base + "/big", 4000)
        self.assertTrue(r.truncated); self.assertEqual(r.bytes, 4000)

    def test_gzip_is_decoded(self):
        r = self.f.get(self.base + "/gz", 1000)
        self.assertEqual(r.body, "<html>zipped</html>")

    def test_an_oversized_gzip_body_is_inflated_up_to_the_cap_not_scanned_raw(self):
        r = self.f.get(self.base + "/gzbig", 2000)         # the compressed stream is over the cap: it is cut mid-way
        self.assertTrue(r.truncated); self.assertGreater(r.bytes, 1500); self.assertLessEqual(r.bytes, 2000)
        self.assertEqual(r.body, GZ_PAYLOAD[:r.bytes].decode("utf-8", "replace"))   # inflated bytes, never the compressed ones

    def test_concatenated_gzip_members_are_all_inflated(self):
        self.assertEqual(fetch._gunzip(gzip.compress(b"var a=1;") + gzip.compress(b"var b=2;"), 1000), b"var a=1;var b=2;")
        self.assertEqual(fetch._gunzip(gzip.compress(b"x" * 50) + gzip.compress(b"y" * 50), 60), b"x" * 50 + b"y" * 10)

    def test_a_body_that_claims_gzip_but_is_not_is_an_error_not_code(self):
        r = self.f.get(self.base + "/notgz", 1000)
        self.assertEqual(r.state, "error"); self.assertEqual(r.body, "")

    def test_identical_bodies_share_one_blob(self):
        a = self.f.get(self.base + "/a.js", 1000, kind="script"); b = self.f.get(self.base + "/b.js", 1000, kind="script")
        self.assertEqual(a.sha256, b.sha256)
        self.assertEqual(len(os.listdir(self.blobdir)), 1)

    def test_recorded_fetcher_replays_corpus_and_reports_unrecorded(self):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "raw"))
        import hashlib
        url = "https://x.com/login"
        with open(os.path.join(d, "raw", hashlib.sha1(url.encode()).hexdigest()[:10] + ".html"), "w") as fh: fh.write("<html>rec</html>")
        with open(os.path.join(d, "summary.json"), "w") as fh:
            json.dump({"pages": [{"url": url, "status": 200, "final_url": url}, {"url": "https://x.com/blocked", "status": 403}]}, fh)
        rf = fetch.RecordedFetcher(d)
        self.assertEqual(rf.get(url, 1000).body, "<html>rec</html>")
        self.assertEqual(rf.get("https://x.com/blocked", 1000).state, "blocked-403")
        self.assertEqual(rf.get("https://x.com/never", 1000).state, "skipped-unconfigured")


if __name__ == "__main__":
    unittest.main()
