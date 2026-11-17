import unittest
from helpers import *  # noqa: F401,F403  (sets sys.path)
import plan


class PlanBoundary(unittest.TestCase):
    def test_conventional_plan_is_valid(self):
        p = plan.conventional("acme", "acme.com")
        self.assertEqual(p.pages[0], "https://acme.com/login")
        self.assertEqual(p.apexes, ["acme.com"])

    def test_rejects_bad_slug_domain_pages(self):
        for raw in ({"slug": "Bad", "domain": "acme.com", "pages": ["https://a.com"]},
                    {"slug": "ok", "domain": "nodots", "pages": ["https://a.com"]},
                    {"slug": "ok", "domain": "acme.com", "pages": []},
                    {"slug": "ok", "domain": "acme.com", "pages": ["http://insecure.com"]},
                    {"slug": "ok", "domain": "acme.com", "pages": ["https://a.com"], "ats": {"bamboo": "x"}}):
            with self.assertRaises(plan.PlanError):
                plan.validate(raw)

    def test_lowercases_hosts(self):
        p = plan.validate({"slug": "ok", "domain": "Acme.COM", "pages": ["https://acme.com/"], "cdn_hosts": ["CDN.Acme.com"]})
        self.assertEqual(p.domain, "acme.com"); self.assertEqual(p.cdn_hosts, ["cdn.acme.com"])


if __name__ == "__main__":
    unittest.main()


class ReviewS9(unittest.TestCase):
    def test_lists_are_type_checked_and_hosts_validated(self):
        import plan as planmod
        base = {"slug": "acme", "domain": "acme.com", "pages": ["https://acme.com/"]}
        for bad in ({"apexes": [1]}, {"apexes": "a.com"}, {"cdn_hosts": "cdn.a.com"}, {"apexes": ["not a host"]}, {"ats": {"greenhouse": "../x?y#z"}}):
            with self.assertRaises(planmod.PlanError, msg=bad):
                planmod.validate({**base, **bad})
        p = planmod.validate({**base, "apexes": ["Acme.com", "acme.io"], "ats": {"greenhouse": "acme-inc"}})
        self.assertEqual(p.apexes, ["acme.com", "acme.io"])
