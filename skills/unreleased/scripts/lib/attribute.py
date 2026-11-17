"""Attribute (R4): which hosts are first-party, decided by evidence, with the plan's cdn_hosts as a fallback.

Rules, in order, each logged as a decision:
1. the plan's domain and any subdomain of it; the plan's cdn_hosts
2. the host of modulepreload/preload scripts (the app's own chunk loader points at its CDN: retool-edge.com,
   frontend-assets.supabase.com)
3. the host serving the majority of script tags after known third parties are removed (Duolingo and Asana
   on CloudFront, Clarity on azureedge)
4. the host of the favicon/manifest when it also serves at least one script
Known third-party hosts (consent managers, site builders, analytics, CDNs of libraries) are never promoted,
even as a majority, unless they are the plan's own domain.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from urllib.parse import urlparse
from plan import Plan

KNOWN_THIRD_PARTY = (
    "cookielaw.org", "onetrust.com", "framerusercontent.com", "framer.com", "website-files.com", "webflow.com",
    "plausible.io", "googletagmanager.com", "google-analytics.com", "googleapis.com", "gstatic.com", "google.com",
    "hs-scripts.com", "hsforms.net", "hubspot.com", "hsappstatic.net", "intercomcdn.com", "intercom.io",
    "cdn.jsdelivr.net", "cdnjs.cloudflare.com", "unpkg.com", "js.stripe.com", "stripe.com", "segment.com", "segment.io",
    "heapanalytics.com", "hotjar.com", "contentsquare.net", "clarity.ms", "mxpnl.com", "mixpanel.com", "amplitude.com",
    "sentry-cdn.com", "sentry.io", "launchdarkly.com", "statsig.com", "posthog.com", "posthog.net", "optimizely.com",
    "cloudflareinsights.com", "clearbit.com", "intellimize.co", "typekit.net", "fonts.net", "recaptcha.net",
    "doubleclick.net", "facebook.net", "twitter.com", "linkedin.com", "licdn.com", "tiktok.com", "bing.com",
    "yext.com", "sanity.io", "contentful.com", "algolia.net", "algolianet.com", "cloudinary.com", "imgix.net",
)


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().split("@")[-1].split(":")[0]


def _under(host: str, apex: str) -> bool:
    return host == apex or host.endswith("." + apex)


@dataclass
class Attribution:
    domain: str
    first_party_hosts: set[str] = field(default_factory=set)
    decisions: list[str] = field(default_factory=list)

    def is_first_party(self, url: str) -> bool:
        h = _host(url)
        if not h:
            return False
        if _under(h, self.domain):
            return True
        return any(_under(h, fp) for fp in self.first_party_hosts)


def _known_third_party(host: str, domain: str) -> bool:
    if _under(host, domain):
        return False
    return any(_under(host, k) for k in KNOWN_THIRD_PARTY)


def decide(plan: Plan, page_url: str, html: str, script_urls: list[str], modulepreload: list[str], icon_hosts: list[str] | None = None) -> Attribution:
    a = Attribution(domain=plan.domain)
    for c in plan.cdn_hosts:
        a.first_party_hosts.add(c)
    if plan.cdn_hosts:
        a.decisions.append(f"plan cdn_hosts: {', '.join(plan.cdn_hosts)}")
    page_host = _host(page_url)
    if page_host and not _under(page_host, plan.domain) and not _known_third_party(page_host, plan.domain):
        a.first_party_hosts.add(page_host); a.decisions.append(f"page served from {page_host} (redirect): treated as first-party")

    for u in modulepreload:
        h = _host(u)
        if h and not _under(h, plan.domain) and not _known_third_party(h, plan.domain) and h not in a.first_party_hosts:
            a.first_party_hosts.add(h); a.decisions.append(f"{h}: promoted (modulepreload target)")

    hosts = [_host(u) for u in script_urls]
    hosts = [h for h in hosts if h]
    candidates = [h for h in hosts if not _under(h, plan.domain) and not _known_third_party(h, plan.domain) and h not in a.first_party_hosts]
    if candidates:
        counts = {}
        for h in candidates: counts[h] = counts.get(h, 0) + 1
        top, n = max(counts.items(), key=lambda kv: kv[1])
        considered = len([h for h in hosts if not _known_third_party(h, plan.domain)])   # the domain's own tags count too
        own = len([h for h in hosts if _under(h, plan.domain)])
        # a strict majority of at least two tags; or the only place the app's code can come from when the
        # domain serves no script itself (Asana: one cookielaw tag, one cloudfront tag). A widget host that
        # serves one of two tags beside the domain's own is neither (review S11).
        if (n >= 2 and n * 2 > considered) or (own == 0 and n == len(candidates)):
            a.first_party_hosts.add(top); a.decisions.append(f"{top}: promoted (serves {n} of {considered} non-third-party script tags; domain serves {own})")

    for h in icon_hosts or []:
        if h and not _under(h, plan.domain) and not _known_third_party(h, plan.domain) and h in hosts and h not in a.first_party_hosts:
            a.first_party_hosts.add(h); a.decisions.append(f"{h}: promoted (favicon/manifest host that also serves scripts)")
    return a


_TWO_LEVEL = {"co.uk", "com.au", "com.br", "co.jp", "co.in", "co.nz", "com.mx", "co.za", "org.uk", "ac.uk", "com.sg"}


def registrable(host: str) -> str:
    """The registrable domain of a host (figma.com for static.figma.com; bbc.co.uk for www.bbc.co.uk)."""
    host = (host or "").lower().split(":")[0]
    labels = host.split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in _TWO_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host
