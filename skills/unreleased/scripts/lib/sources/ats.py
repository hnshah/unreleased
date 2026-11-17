"""ats source: public job boards with identity verification (R13), plus a first-party careers page.

Contract (shared across `sources/`): `fetch(plan, fetcher) -> (jobs, outcomes)`: a list of `Job` and one
`SourceOutcome` for the board search (`source="ats"`), plus one for the careers-page fallback when it ran
(`source="careers-page"`); `health(fetcher) -> SourceOutcome`.

Search order: the boards the plan names (`plan.ats`), then every slug variant (the slug, the domain's first
label, the slug without dashes) on Greenhouse, Lever, Ashby and Workable. The first *verified* board wins
and stops the search; a board that answers but fails verification is kept as a fallback and its jobs are
still returned, with the outcome `partial` and the detail "unverified board <ats>/<slug>". The readers hit
Greenhouse `lovable` (an Italian lingerie retailer; the real board is Ashby `lovable`) and Ashby `clarity`
(a London startup, not Microsoft Clarity), so the slug alone is never trusted.

Verification scores four signals and needs 2 points. Weak evidence is anything the board slug itself
implies (its name, the slug in ATS-hosted URLs: a board named `lovable` says "Lovable" whoever owns it):
- +2 a job URL on the product's own domain (not an ATS host);
- +2 a strong token in any job or board text: the plan domain or an apex (`linear.app`, `lovable.dev`), or
  the registrable label / plan slug when it differs from the board slug (`claude` on the `anthropic`
  board, `microsoft` for `clarity.microsoft.com`);
- +1 the board or company name contains the slug or label (Greenhouse `company_name`, Workable `name`);
- +1 at least 20% of titles carry software-industry vocabulary (Engineer, Product Manager, Data, ML, ...).

Dates: Ashby `publishedAt`, Greenhouse `first_published` (its `updated_at` is not a posting date), Lever
`createdAt` (epoch ms), Workable `published_on`. `nouns` are the product/area noun phrases of a title
("Staff PM, Accounting Products" -> ["Accounting Products"]) for clustering; role words are not nouns.

Workable: `https://apply.workable.com/api/v1/widget/accounts/<slug>?details=false` and the public
`https://www.workable.com/api/accounts/<slug>?details=true` both answered 429 keyless on 2026-10-30
(tests/fixtures/sources/workable-*.attempt.json), so the widget shape is parsed from its documented
fields (`name`, `jobs[].title/shortcode/department/city/country/published_on/url`), one request, never
retried on 429, and the outcome records `rate-limited` when that is what happens.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import urllib.parse

from schema import Job, SourceOutcome

SOURCE = "ats"
LIMIT = 20_000_000              # Lever boards with full descriptions run to several MB (Palantir: 5.9 MB)
CAREERS_LIMIT = 4_000_000
ORDER = ("greenhouse", "lever", "ashby", "workable")
URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=false",
}
ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com")
HEALTH_URL = "https://boards-api.greenhouse.io/v1/boards/greenhouse"
_TWO_LEVEL = {"co.uk", "com.au", "com.br", "co.jp", "co.in", "co.nz", "com.mx", "co.za", "org.uk", "ac.uk", "com.sg"}

SOFTWARE = re.compile(r"\b(?:engineer(?:ing)?|software|developer|programmer|product (?:manager|designer|lead|marketing|management)|designer|data|research(?:er)?|scientist|security|infrastructure|platform|machine learning|\bml\b|\bai\b|solutions? (?:engineer|architect)|devrel|developer advocate|technical|sre|backend|frontend|front-end|back-end|full ?stack|mobile|ios|android|\bqa\b|cloud|analytics|devops|kernel|compiler)\b", re.I)
_LEVEL = {"senior", "sr", "sr.", "staff", "lead", "principal", "junior", "jr", "jr.", "associate", "head", "director", "vp", "vice", "president", "chief",
          "intern", "internship", "ii", "iii", "iv", "i", "new", "grad", "graduate", "entry", "level", "global", "regional", "emea", "apac", "americas",
          "north", "america", "europe", "remote", "hybrid", "contract", "temporary", "part-time", "full-time", "fellow", "fellowship"}
_ROLE = {"engineer", "engineers", "engineering", "manager", "managers", "management", "designer", "design", "developer", "developers", "development",
         "scientist", "analyst", "specialist", "executive", "executives", "architect", "intern", "recruiter", "counsel", "partner", "partnerships",
         "associate", "representative", "coordinator", "marketer", "writer", "researcher", "advocate", "consultant", "officer", "president", "vp", "pm",
         "sdr", "bdr", "cto", "ceo", "cfo", "coo", "lead", "leads", "head", "director", "operations", "ops", "success", "support", "sales", "marketing",
         "accountant", "administrator", "assistant", "strategist", "evangelist", "technician", "generalist", "controller", "buyer", "planner", "trainer"}
_GENERIC = _LEVEL | _ROLE | {"pacific", "mountain", "eastern", "central", "time", "remote", "hybrid", "onsite", "us", "usa", "uk", "emea", "apac", "amer", "software", "product", "products", "program", "project", "technical", "customer", "customers", "account", "accounts", "business",
                             "team", "of", "and", "the", "for", "in", "on", "to", "&", "with", "a", "an", "or", "at", "data", "machine", "learning", "ml", "ai",
                             "full", "stack", "fullstack", "frontend", "backend", "front-end", "back-end", "mobile", "web", "ios", "android", "cloud", "infrastructure",
                             "security", "solutions", "solution", "strategic", "enterprise", "growth", "people", "talent", "finance", "legal", "revenue", "gtm",
                             "field", "inside", "outbound", "inbound", "staff", "member", "technical", "tech", "general", "senior"}
_AREA_ONLY_OK = {"enterprise", "growth", "security", "infrastructure", "cloud", "mobile", "web", "data", "ai", "finance", "legal", "revenue", "solutions"}
_SEG_SPLIT = re.compile(r"\s*[,:|/;]\s*|\s+[-–—]\s+|\s*[–—]\s*")
_TITLE_LINE = re.compile(r"\b(?:engineer|manager|designer|lead|director|head of|scientist|analyst|specialist|executive|developer|architect|intern|recruiter|counsel|partner|associate|representative|coordinator|marketer|writer|researcher|advocate|consultant|officer|vp|president|accountant|administrator|strategist|technician)\b", re.I)


# --- pure helpers ---------------------------------------------------------------------------------------

def registrable(host: str) -> str:
    labels = host.lower().split(":")[0].split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in _TWO_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def slug_variants(plan) -> list[str]:
    cands = [plan.slug, plan.domain.split(".")[0], plan.slug.replace("-", "")]
    out = []
    for c in cands:
        c = c.lower()
        if c and c not in out:
            out.append(c)
    return out


def nouns(title: str) -> list[str]:
    """Product / area noun phrases of a job title, for clustering. Role and level words are not nouns."""
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", title or "")
    out = []
    for seg in _SEG_SPLIT.split(t):
        seg = " ".join(seg.split())
        if not seg or "_" in seg:
            continue
        words = seg.split()
        if len(words) > 6:
            continue
        lower = [w.lower().strip(".,") for w in words]
        if lower[-1] in _ROLE or lower[-1] in _LEVEL:
            continue
        content = [w for w, l in zip(words, lower) if l not in _GENERIC or (len(words) == 1 and l in _AREA_ONLY_OK)]
        if not content or not any(w[:1].isupper() for w in content):
            continue
        if seg not in out:
            out.append(seg)
    return out


def _date(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = float(value)
        if v > 1e11:
            v /= 1000.0
        try:
            return dt.datetime.fromtimestamp(v, dt.timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value)
    return s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else None


def parse_board(ats: str, slug: str, data) -> tuple[list[Job], dict]:
    """(jobs, evidence) for one parsed board response. evidence = {"name": str, "texts": [str], "urls": [str]}."""
    jobs, texts, urls, name = [], [], [], ""
    if ats == "greenhouse" and isinstance(data, dict) and isinstance(data.get("jobs"), list):
        for j in data["jobs"]:
            if not isinstance(j, dict):
                continue
            name = name or str(j.get("company_name") or "")
            title = str(j.get("title") or "").strip()
            dept = ", ".join(str(d.get("name", "")) for d in (j.get("departments") or []) if isinstance(d, dict) and d.get("name"))
            loc = str((j.get("location") or {}).get("name") or "") if isinstance(j.get("location"), dict) else ""
            url = str(j.get("absolute_url") or "")
            jobs.append(Job("greenhouse", slug, str(j.get("id") or ""), title, dept, loc, _date(j.get("first_published")), url, nouns(title)))
            texts += [title, dept, loc, str(j.get("content") or "")]; urls.append(url)
    elif ats == "lever" and isinstance(data, list):
        for j in data:
            if not isinstance(j, dict):
                continue
            cats = j.get("categories") if isinstance(j.get("categories"), dict) else {}
            title = str(j.get("text") or "").strip()
            url = str(j.get("hostedUrl") or j.get("applyUrl") or "")
            jobs.append(Job("lever", slug, str(j.get("id") or ""), title, str(cats.get("team") or cats.get("department") or ""), str(cats.get("location") or ""),
                            _date(j.get("createdAt")), url, nouns(title)))
            texts += [title, str(cats.get("team") or ""), str(cats.get("location") or ""), str(j.get("descriptionPlain") or ""), str(j.get("additionalPlain") or ""),
                      str(j.get("openingPlain") or ""), str(j.get("description") or ""), str(j.get("additional") or "")]   # the HTML carries the links
            urls.append(url)
    elif ats == "ashby" and isinstance(data, dict) and isinstance(data.get("jobs"), list):
        for j in data["jobs"]:
            if not isinstance(j, dict):
                continue
            title = str(j.get("title") or "").strip()
            url = str(j.get("jobUrl") or j.get("applyUrl") or "")
            jobs.append(Job("ashby", slug, str(j.get("id") or ""), title, str(j.get("department") or j.get("team") or ""), str(j.get("location") or ""),
                            _date(j.get("publishedAt")), url, nouns(title)))
            texts += [title, str(j.get("department") or ""), str(j.get("team") or ""), str(j.get("location") or ""), str(j.get("descriptionPlain") or ""), str(j.get("descriptionHtml") or "")]
            urls.append(url)
    elif ats == "workable" and isinstance(data, dict) and isinstance(data.get("jobs"), list):
        name = str(data.get("name") or "")
        texts.append(str(data.get("description") or ""))
        for j in data["jobs"]:
            if not isinstance(j, dict):
                continue
            title = str(j.get("title") or "").strip()
            loc = ", ".join(str(j[k]) for k in ("city", "state", "country") if j.get(k))
            url = str(j.get("url") or j.get("shortlink") or j.get("application_url") or "")
            jobs.append(Job("workable", slug, str(j.get("shortcode") or j.get("code") or ""), title, str(j.get("department") or ""), loc, _date(j.get("published_on")), url, nouns(title)))
            texts += [title, str(j.get("department") or ""), loc]; urls.append(url)
    return jobs, {"name": name, "texts": [t for t in texts if t], "urls": [u for u in urls if u]}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def verify(plan, ats: str, slug: str, data) -> tuple[bool, str]:
    """(verified, reason) for a board response against the plan. Pure."""
    jobs, ev = parse_board(ats, slug, data)
    if not jobs:
        return False, "no jobs"
    board = slug.lower()
    domains = [plan.domain.lower()] + [a.lower() for a in plan.apexes]
    strong = {d for d in domains}
    for d in domains:
        label = registrable(d).split(".")[0]
        if label and label != board and label != board.replace("-", ""):
            strong.add(label)
    if plan.slug.lower() not in (board, board.replace("-", "")):
        strong.add(plan.slug.lower())
    weak = {board, plan.slug.lower()} | {registrable(d).split(".")[0] for d in domains}
    score, reasons = 0, []
    # +2 a job URL on the product's own domain
    for u in ev["urls"]:
        host = urllib.parse.urlparse(u).netloc.lower()
        if host and not any(host == h or host.endswith("." + h) for h in ATS_HOSTS):
            r = registrable(host)
            if any(r == registrable(d) for d in domains) or any(l in host for l in strong if "." not in l):
                score += 2; reasons.append("url"); break
    # +2 a strong token in the text
    blob = "\n".join(ev["texts"]).lower()
    for tok in sorted(strong, key=len, reverse=True):
        hit = tok in blob if "." in tok else re.search(r"(?<![a-z0-9])" + re.escape(tok) + r"(?![a-z0-9])", blob)
        if hit:
            score += 2; reasons.append(f"text:{tok}"); break
    # +1 the board / company name
    nm = _norm(ev["name"])
    if nm and any((len(t) >= 4 and (_norm(t) in nm or nm in _norm(t))) for t in weak | strong if "." not in t):
        score += 1; reasons.append(f"name:{ev['name']}")
    # +1 software vocabulary in titles
    titles = [j.title for j in jobs if j.title]
    if titles and sum(1 for t in titles if SOFTWARE.search(t)) >= 0.2 * len(titles):
        score += 1; reasons.append("titles")
    return score >= 2, ", ".join(reasons) or "no signal"


def careers_page_jobs(html: str, url: str, slug: str) -> list[Job]:
    """Low-confidence jobs from a first-party careers page: job-title-looking lines, linked when they are links."""
    from sources import changelog as _cl
    nodes = _cl.linearise(html)
    out, seen = [], set()
    for n in nodes:
        text = n.get("text", "").strip()
        if not text or len(text) > 80 or text.endswith((".", "!", "?")):
            continue
        words = text.split()
        if not 2 <= len(words) <= 10 or not _TITLE_LINE.search(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        href = n.get("href", "")
        out.append(Job("careers-page", slug, hashlib.sha1(key.encode()).hexdigest()[:12], text, "", "", None,
                       urllib.parse.urljoin(url, href) if href else url, nouns(text)))
    return out


# --- the seam ---------------------------------------------------------------------------------------------

def candidates(plan) -> list[tuple[str, str]]:
    out = []
    for ats, slug in (plan.ats or {}).items():
        if ats in URLS and isinstance(slug, str) and slug and (ats, slug.lower()) not in out:
            out.append((ats, slug.lower()))
    for ats in ORDER:
        for slug in slug_variants(plan):
            if (ats, slug) not in out:
                out.append((ats, slug))
    return out


def fetch(plan, fetcher) -> tuple[list[Job], list[SourceOutcome]]:
    tried, fallback = [], None
    for ats, slug in candidates(plan):
        f = fetcher.get(URLS[ats].format(slug=slug), LIMIT, kind="api")
        if f.state != "ok" or f.status != 200:
            tried.append(f"{ats}/{slug} ({'404' if f.status == 404 else f.state})")
            continue
        try:
            data = json.loads(f.body)
        except ValueError:
            tried.append(f"{ats}/{slug} (non-JSON)"); continue
        jobs, _ = parse_board(ats, slug, data)
        if not jobs:
            tried.append(f"{ats}/{slug} (0 jobs)"); continue
        ok, why = verify(plan, ats, slug, data)
        if ok:
            detail = f"board found on {ats} as `{slug}` (verified: {why}); {len(jobs)} jobs"
            return jobs, [SourceOutcome(SOURCE, "ok", len(jobs), True, detail)]
        tried.append(f"{ats}/{slug} (unverified)")
        if fallback is None:
            fallback = (ats, slug, jobs, why)
    if fallback:
        ats, slug, jobs, why = fallback
        detail = f"unverified board {ats}/{slug}: {len(jobs)} jobs returned but the company could not be matched to {plan.domain} ({why}); tried {', '.join(tried)}"
        return jobs, [SourceOutcome(SOURCE, "partial", len(jobs), True, detail)]
    limited = [t for t in tried if "rate-limited" in t]
    outcomes = [SourceOutcome(SOURCE, "rate-limited" if limited else "no-results", 0, True,
                              f"no board found for {plan.domain}; tried {', '.join(tried)}" + ("; a rate-limited board is unread, not empty" if limited else ""))]
    if plan.careers:
        f = fetcher.get(plan.careers, CAREERS_LIMIT, kind="page")
        if f.state == "ok" and f.status == 200:
            jobs = careers_page_jobs(f.body, f.final_url or plan.careers, plan.slug)
            state = "partial" if jobs else "no-results"
            outcomes.append(SourceOutcome("careers-page", state, len(jobs), True, f"{plan.careers}: {len(jobs)} title-looking lines (low confidence, no dates)"))
            return jobs, outcomes
        outcomes.append(SourceOutcome("careers-page", f.state, 0, True, f"{plan.careers}: HTTP {f.status}"))
    return [], outcomes


def health(fetcher) -> SourceOutcome:
    """One small request to Greenhouse's own board root: says whether the job-board API answers right now."""
    f = fetcher.get(HEALTH_URL, 200_000, kind="api")
    if f.state != "ok" or f.status != 200:
        return SourceOutcome(SOURCE, f.state, 0, True, f"{HEALTH_URL}: HTTP {f.status}")
    try:
        name = json.loads(f.body).get("name")
    except (ValueError, AttributeError):
        return SourceOutcome(SOURCE, "error", 0, True, f"{HEALTH_URL}: non-JSON body")
    return SourceOutcome(SOURCE, "ok" if name else "schema-drift", 0, True, f"{HEALTH_URL}: board name {name!r}")
