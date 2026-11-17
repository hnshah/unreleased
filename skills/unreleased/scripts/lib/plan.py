"""Plan: the host's resolution of a product. Validated here (the boundary); trusted everywhere else."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import json, re

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_HOST = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$")
_BOARD = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$", re.I)


@dataclass
class Plan:
    slug: str
    domain: str
    pages: list[str]                       # public pages to read: login/app shell, marketing
    apexes: list[str] = field(default_factory=list)       # apex domains for certificate logs (domain + CDN apexes)
    cdn_hosts: list[str] = field(default_factory=list)    # hosts whose scripts count as first-party (fallback list)
    ats: dict = field(default_factory=dict)               # {"greenhouse": slug} | {"ashby": slug} | {"lever": slug} | {"workable": slug}
    pricing: str | None = None
    changelog: str | None = None                          # index page or feed
    careers: str | None = None
    docs: str | None = None                               # docs index, manual home, docs sitemap or llms.txt: a third cross-check source
    notes: str = ""                                       # free text from the planner, carried in the run folder for the reader

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1)


class PlanError(ValueError):
    pass


def load_plan(path: str) -> Plan:
    """Parse and validate a plan file. Raises PlanError with a message the host can act on."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return validate(raw)


def _hosts(v, field: str) -> list[str]:
    """A list of bare hostnames, or a PlanError that names the field (a string is not a list of one; review S9)."""
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(h, str) for h in v):
        raise PlanError(f"{field} must be a list of hostnames")
    out = [h.lower().strip() for h in v]
    bad = [h for h in out if not _HOST.match(h)]
    if bad:
        raise PlanError(f"{field} has an invalid hostname: {bad[0]!r}")
    return out


def validate(raw: dict) -> Plan:
    if not isinstance(raw, dict):
        raise PlanError("plan must be a JSON object")
    slug, domain = str(raw.get("slug", "")), str(raw.get("domain", "")).lower()
    if not _SLUG.match(slug):
        raise PlanError("slug must be lowercase letters, digits and dashes")
    if not _HOST.match(domain):
        raise PlanError("domain must be a bare hostname such as example.com")
    pages = raw.get("pages") or []
    if not pages or not all(isinstance(p, str) and p.startswith("https://") for p in pages):
        raise PlanError("pages must be one or more https URLs")
    for k in ("pricing", "changelog", "careers", "docs"):
        v = raw.get(k)
        if v is not None and not (isinstance(v, str) and v.startswith("https://")):
            raise PlanError(f"{k} must be an https URL or omitted")
    ats = raw.get("ats") or {}
    if not isinstance(ats, dict) or any(k not in ("greenhouse", "lever", "ashby", "workable") for k in ats):
        raise PlanError("ats must map greenhouse|lever|ashby|workable to a board slug")
    for k, v in ats.items():
        if not (isinstance(v, str) and _BOARD.match(v)):
            raise PlanError(f"ats.{k} must be a board slug (letters, digits, dots, dashes, underscores)")
    apexes = _hosts(raw.get("apexes"), "apexes") or [domain]
    cdn = _hosts(raw.get("cdn_hosts"), "cdn_hosts")
    return Plan(slug=slug, domain=domain.lower(), pages=pages, apexes=apexes, cdn_hosts=cdn, ats=ats,
                pricing=raw.get("pricing"), changelog=raw.get("changelog"), careers=raw.get("careers"), docs=raw.get("docs"), notes=str(raw.get("notes") or "")[:500])


def conventional(slug: str, domain: str) -> Plan:
    """A plan from conventions when the host knows only the domain. The host should still check the pages exist."""
    base = f"https://{domain}"
    return validate({"slug": slug, "domain": domain, "pages": [f"{base}/login", f"{base}/"], "pricing": f"{base}/pricing",
                     "changelog": f"{base}/changelog", "apexes": [domain]})
