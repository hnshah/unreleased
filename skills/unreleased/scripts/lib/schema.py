"""Typed records for an `unreleased` run.

Every stage of the engine reads and writes these. States are `Literal` types so a typo is a type error.
The coverage vocabulary adopts last30days' RunOutcomeState verbatim and adds four states this domain needs.
See docs/adr/0004-coverage-vocabulary.md for the rationale.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Literal, Optional
import json

SCHEMA_VERSION = "0.1"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- coverage -----------------------------------------------------------------------------------

# last30days' RunOutcomeState (adopted verbatim) ...
RunOutcomeState = Literal[
    "ok", "no-results", "partial", "rate-limited", "auth-failed", "payment-required",
    "unreachable", "timeout", "schema-drift", "skipped-unconfigured", "error",
    # ... plus four states this domain needs:
    "blocked-403",   # the host refused a plain fetch; never retried, never routed around
    "challenge",     # an interstitial (WAF/Cloudflare); never retried, the host is stopped for the run
    "runtime-only",  # a flag SDK is present but its flags are fetched at runtime; not read
    "capped",        # a cap, truncated window or partial enumeration limited what was read
]


@dataclass
class SourceOutcome:
    """What happened to one source during this run (page, script set, crt, ats, pricing, changelog)."""
    source: str
    state: RunOutcomeState
    items: int = 0
    attempted: bool = True
    detail: Optional[str] = None
    at: str = field(default_factory=utc_now)


# --- observations --------------------------------------------------------------------------------

ObservationKind = Literal[
    "gate", "config", "catalog", "registry", "enum", "proto", "route", "inline", "call",
    "string", "i18n", "manifest", "hidden", "subdomain", "job", "pricing", "redirect", "unknown",
    "robots", "sitemap", "headline",       # the site source: campaign signals from robots.txt, sitemaps, landing pages
]
Tier = Literal["finding", "key-list", "codename", "redacted"]
Confidence = Literal["high", "medium", "low"]
Attribution = Literal["domain", "cdn-list", "entry-script-host", "script-majority", "favicon-host", "modulepreload", "third-party"]


@dataclass
class Source:
    url: str
    sha256: str
    offset: int = -1
    first_party: bool = True
    attribution: Attribution = "domain"


@dataclass
class Observation:
    id: str
    kind: ObservationKind
    key: str
    source: Source
    value: object = None
    default: object = None
    params: list[str] = field(default_factory=list)
    group: str = ""
    context: str = ""
    extractor: str = ""
    tier: Tier = "key-list"
    confidence: Confidence = "low"
    name_date: Optional[str] = None   # a date parsed from the key itself (q3fy27, 2026_10_20)
    salience: int = 0                 # salience.score(): nameable product nouns up, plumbing down; orders evidence.md


# --- cross-check ---------------------------------------------------------------------------------

CheckStatus = Literal["announced", "partial", "none", "unchecked"]


@dataclass
class Check:
    observation_id: str
    status: CheckStatus
    date: Optional[str] = None
    url: Optional[str] = None
    searched: list[str] = field(default_factory=list)
    note: str = ""


# --- second signals ------------------------------------------------------------------------------

@dataclass
class Subdomain:
    name: str
    first_seen: str            # YYYY-MM-DD from certificate not_before
    stem: str = ""
    env: str = ""              # test / staging / prod-N / preview / ""
    apex: str = ""
    count: int = 1             # >1 for a collapsed flood (preview-*.lovable.app: 4,289 hosts)
    last_seen: str = ""        # latest not_before in a collapsed flood; "" for a single host


@dataclass
class Job:
    ats: Literal["greenhouse", "lever", "ashby", "workable", "careers-page"]
    slug: str
    external_id: str
    title: str
    dept: str = ""
    location: str = ""
    posted_at: Optional[str] = None   # Ashby gives one; Greenhouse `updated_at` is not a posting date
    url: str = ""
    nouns: list[str] = field(default_factory=list)


@dataclass
class PricingSnapshot:
    url: str
    sha256_text: str
    chars: int
    status: Literal["ok", "client-rendered", "404", "redirect", "blocked-403", "challenge"]
    lines: list[str] = field(default_factory=list)   # chips: New / Beta / Coming soon / not yet available / $ amounts
    final_url: str = ""
    text: str = ""                                   # full visible text, for cross-checks within the run; not stored in SQLite


# --- run-level -----------------------------------------------------------------------------------

@dataclass
class Diff:
    since_run: str
    flipped: list[dict] = field(default_factory=list)      # {key, from, to}
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    routes_added: list[str] = field(default_factory=list)
    pages_added: list[str] = field(default_factory=list)          # sitemap pages (compare / landing / recent) absent before
    pages_removed: list[str] = field(default_factory=list)
    subdomains_added: list[str] = field(default_factory=list)
    jobs_added: list[str] = field(default_factory=list)
    jobs_removed: list[str] = field(default_factory=list)
    pricing_changed: bool = False
    pricing_lines_changed: list[str] = field(default_factory=list)
    new_scripts_read: int = 0                               # scripts read this run that the baseline never read
    added_in_new_scripts: int = 0                           # keys that are "added" only because their script is newly read
    note: str = ""                                          # why a section is withheld ("removed withheld: this run read 12% of the baseline's bytes")


@dataclass
class Coverage:
    sources: list[SourceOutcome]
    first_party_bytes: int = 0
    scripts_fetched: int = 0
    scripts_enumerated: int = 0
    cap_hit: bool = False
    runtime_flag_providers: list[str] = field(default_factory=list)
    attribution_decisions: list[str] = field(default_factory=list)
    redactions: int = 0
    observations: int = 0
    page_bytes: int = 0                      # pages are not scripts: a marketing shell with zero first-party scripts is not "rich"

    def verdict(self) -> Literal["rich", "partial", "could-not-see"]:
        """Printed on the badge. 'could-not-see' when no first-party code was read; 'partial' when something
        that should have been readable was not (ADR 0005, widened by ADR 0007: a read cut short by a dead chunk
        map, a planned page robots.txt keeps us out of). A hit cap is a budget, reported in coverage, not a failure."""
        if self.first_party_bytes == 0 or (self.scripts_fetched == 0 and self.observations == 0):
            return "could-not-see"
        return "partial" if partial_sources(self.sources) else "rich"

    def verdict_reason(self) -> str:
        """Why the verdict is what it is, in the sources' own words. 'rich' never claims every source was read when
        a budget cut the read: `rich: every source answered; under the budget cap: scripts read 60 of 440 enumerated`."""
        v = self.verdict()
        if v == "could-not-see":
            return "could-not-see: no first-party code was read"
        if v == "partial":
            return "partial: " + ", ".join(f"{s.source} {_said(s)}" for s in partial_sources(self.sources)[:6])
        capped = [s for s in self.sources if s.state == "capped"]
        if not capped:
            return "rich: every source read"
        scripts = next((s for s in capped if s.source == "scripts"), None)
        parts = ([f"scripts {scripts.detail.split(';')[0]}" if scripts.detail else "scripts"] if scripts else []) \
            + sorted({s.source for s in capped if s is not scripts})
        return "rich: every source answered; under the budget cap: " + ", ".join(parts)


# ADR 0005: the states that make a run partial. ADR 0007 adds two cases that are not states of their own.
PARTIAL_STATES = frozenset({"blocked-403", "challenge", "runtime-only", "error", "unreachable", "timeout", "rate-limited"})
CODE_SOURCES = ("script:", "scripts", "chunks")   # not page: a page `partial` is an off-domain redirect, a signal
ROBOTS_NOT_CHECKED = "not checked: the site's robots.txt asks crawlers to stay out"


def partial_sources(sources: list) -> list:
    """The sources that make a run partial; SourceOutcome objects or their coverage.json dicts. One rule for the engine
    and the report: a failing state (ADR 0005); first-party code whose read was cut short (`partial` on a script
    or chunk map: listed, never served); a planned page robots.txt keeps us out of (never requested, never read)."""
    out = []
    for s in sources:
        src, state, detail = (s.get("source") or "", s.get("state"), s.get("detail")) if isinstance(s, dict) else (s.source, s.state, s.detail)
        if state in PARTIAL_STATES or (state == "partial" and src.startswith(CODE_SOURCES)) \
                or (src.startswith("page:") and detail == ROBOTS_NOT_CHECKED):
            out.append(s)
    return out


def _said(s) -> str:
    if s.detail == ROBOTS_NOT_CHECKED:
        return "could not see (robots.txt asks crawlers to stay out)"
    if s.state == "partial" and s.detail:
        return f"partial ({s.detail.split(':')[0]})"          # chunks: "8 chunk urls named by app.js answered 404 in a row"
    return s.state


@dataclass
class Manifest:
    run_id: str
    product: str
    engine_version: str
    schema_version: str = SCHEMA_VERSION
    started_at: str = field(default_factory=utc_now)
    seconds: float = 0.0
    pages: list[dict] = field(default_factory=list)
    blobs: list[str] = field(default_factory=list)       # sha256 of every body read, sorted
    extractor_versions: dict = field(default_factory=dict)
    policy: str = "public pages only; no login; no circumvention; first-party attribution; project UA; >=1 s per host"


def canonical_json(obj) -> str:
    """Canonical serialisation (sorted keys, no whitespace games) so two manifests compare byte for byte."""
    data = asdict(obj) if hasattr(obj, "__dataclass_fields__") else obj
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
