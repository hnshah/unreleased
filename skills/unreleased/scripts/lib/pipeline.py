"""Pipeline: one run. plan -> fetch -> attribute -> discover -> extract -> noise -> signals -> cross-check ->
redact -> diff -> result. Pure given a Fetcher and a Store; the CLI is the shell around it.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import datetime as dt
import json, os, re, time
from importlib import import_module

import attribute, discover, noise, redact, crosscheck, salience, diff as diffmod
import extractors
from plan import Plan
from fetch import Fetcher
from schema import Observation, Check, Subdomain, Job, PricingSnapshot, Coverage, Manifest, Diff, Source, SourceOutcome, ROBOTS_NOT_CHECKED

DEFAULT_CAPS = {"max_scripts": 60, "max_script_bytes": 8_000_000, "max_total_bytes": 120_000_000, "max_page_bytes": 4_000_000, "crt_days": 120}


@dataclass
class RunResult:
    manifest: Manifest
    coverage: Coverage
    observations: list[Observation]
    checks: list[Check]
    subdomains: list[Subdomain]
    jobs: list[Job]
    pricing: PricingSnapshot | None
    diff: Diff | None
    redaction_log: list[str]
    web_queries: list[str] = field(default_factory=list)
    bodies: dict[str, str] = field(default_factory=dict)
    changelog_index: list[dict] = field(default_factory=list)
    third_party_hosts: list[str] = field(default_factory=list)
    flagged_subdomains: list[str] = field(default_factory=list)
    attribution_decisions: list[str] = field(default_factory=list)
    first_seen: dict = field(default_factory=dict)      # (kind,key) -> first run id, from the store


def _run_id() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def fresh_run_id(store, product: str, proposed: str | None = None) -> str:
    """A run id the library has not seen: the UTC second, moved forward while it collides (two runs in one second,
    a replayed corpus). Ids stay sortable timestamps, so `since` and baselines keep working (SM-3)."""
    rid = proposed or _run_id()
    while store is not None and store.has_run(rid):
        t = dt.datetime.strptime(rid, "%Y-%m-%dT%H%M%SZ") + dt.timedelta(seconds=1)
        rid = t.strftime("%Y-%m-%dT%H%M%SZ")
    return rid


ROUTE_PROBES = 25                     # anonymous GETs per run to tell live pages from gated routes; one per second per host


_OFFER_STEMS = {"go", "info", "pages", "try", "get", "offers", "offer", "learn", "resources", "hub", "lp", "promo", "events", "webinars", "discover", "start", "campaigns"}


def _call_source(name: str, plan: Plan, fetcher: Fetcher):
    """Sources return (records, outcomes) or records; missing modules are a recorded outcome, not a crash."""
    try:
        mod = import_module(f"sources.{name}")
        res = mod.fetch(plan, fetcher)
    except NotImplementedError:
        return [], [SourceOutcome(name, "skipped-unconfigured", 0, False, "source not implemented")]
    except Exception as e:  # a source must never kill a run
        return [], [SourceOutcome(name, "error", 0, True, f"{type(e).__name__}: {str(e)[:120]}")]
    if isinstance(res, tuple) and len(res) == 2:
        return list(res[0]), list(res[1])
    return list(res), [SourceOutcome(name, "ok", len(res), True, None)]


def _recorded_signals(path: str, plan: Plan):
    """Offline: subdomains, jobs and pricing as the probe saw them (corpus summary.json)."""
    with open(path, encoding="utf-8") as f:
        s = json.load(f)
    subs = [Subdomain(e["name"], e["first_seen"], e["name"].split(".")[0], "", plan.domain) for e in (s.get("crt") or {}).get("recent", [])]
    board = (s.get("jobs") or [{}])[0].get("board", "greenhouse")
    jobs = [Job(board, plan.ats.get(board, plan.slug), "", t, "", "", None, "", []) for t in s.get("job_titles", [])]
    pr = s.get("pricing")
    lines: list[str] = []
    ptxt = os.path.join(os.path.dirname(path), "pricing.txt")
    if pr and os.path.exists(ptxt):                      # the probe saved the page text; cross-checks need it
        with open(ptxt, encoding="utf-8", errors="replace") as f:
            lines = [l.strip() for l in f.read().replace(". ", ".\n").splitlines() if l.strip()]
    pricing = PricingSnapshot(pr["url"], pr["sha256_text"], pr["chars"], "ok", lines, pr.get("final_url", pr["url"]), text="\n".join(lines)) if pr else None
    rec = s.get("source_states") or {}                    # a run recorded with `run --record` keeps each source's own state
    outcomes = [SourceOutcome("crt", rec.get("crt") or ("ok" if s.get("crt") else "unreachable"), len(subs), True, "recorded"),
                SourceOutcome("ats", rec.get("ats") or ("ok" if jobs else "no-results"), len(jobs), True, "recorded"),
                SourceOutcome("pricing", rec.get("pricing") or ("ok" if pricing else "no-results"), 1 if pricing else 0, True, "recorded")]
    return subs, jobs, pricing, outcomes


def run(plan: Plan, fetcher: Fetcher, store, engine_version: str, run_id: str | None = None, caps: dict | None = None,
        recorded_signals: str | None = None, pricing_text_override: str | None = None, since: str | None = None,
        progress=None) -> RunResult:
    """`since`: diff against this earlier run id instead of the previous usable run ("since this morning").
    `progress(stage)`: called at each stage boundary, so a long run (Notion: 225 s) is not silent."""
    caps = {**DEFAULT_CAPS, **(caps or {})}
    run_id = run_id or (fresh_run_id(store, plan.slug) if store is not None else _run_id())
    if store is not None and store.has_run(run_id):
        raise ValueError(f"run id {run_id} already exists in the library; a run is never overwritten (SM-3)")
    if since is not None:
        if since >= run_id or store is None or not store.is_usable_run(plan.slug, since):
            raise ValueError(f"--since {since} is not a usable run of {plan.slug}: it must be an earlier stored run that read code with no blocked page (SM-2)")
    t0 = time.time()

    def stage(name: str) -> None:
        if progress:
            progress(f"{name} ({time.time() - t0:.0f}s)")
    manifest = Manifest(run_id=run_id, product=plan.slug, engine_version=engine_version)
    outcomes: list[SourceOutcome] = []
    bodies: dict[str, str] = {}
    artifacts: dict[str, Source] = {}          # sha -> Source
    attr = attribute.Attribution(domain=plan.domain, first_party_hosts=set(plan.cdn_hosts))
    candidates: list[str] = []; entry: list[str] = []; third_party: set[str] = set()
    page_bodies: list[tuple[str, str]] = []

    stage("pages")
    # 1. pages
    redirects: list[Observation] = []
    for url in plan.pages:
        f = fetcher.get(url, caps["max_page_bytes"], "page")
        manifest.pages.append({"url": url, "final_url": f.final_url, "status": f.status, "state": f.state, "sha256": f.sha256})
        final_host = f.final_url.split("/")[2] if f.final_url and "//" in f.final_url else ""
        if f.state == "ok" and final_host and attribute.registrable(final_host) not in {attribute.registrable(h) for h in [plan.domain] + plan.apexes + plan.cdn_hosts}:
            # another company's site answered (hotjar.com -> contentsquare.com): a signal, never first-party code
            outcomes.append(SourceOutcome(f"page:{url}", "partial", 0, True, f"redirected off-domain to {final_host}; not read as {plan.slug}'s code"))
            redirects.append(Observation(id="", kind="redirect", key=final_host, source=Source(url=url, sha256=f.sha256, offset=-1, first_party=False, attribution="redirect"),
                                         value=f.final_url, context=f"{url} -> {f.final_url}", extractor="pipeline", tier="finding", confidence="high"))
            continue
        outcomes.append(SourceOutcome(f"page:{url}", f.state, 1 if f.state == "ok" else 0, True, None if f.state == "ok" else _why(f)))
        if f.state != "ok" or not f.body:
            continue
        bodies[f.sha256] = f.body
        artifacts[f.sha256] = Source(url=f.final_url, sha256=f.sha256, offset=-1, first_party=True, attribution="domain")
        page_bodies.append((f.final_url, f.body))
        d = discover.page(f.final_url, f.body)
        a = attribute.decide(plan, f.final_url, f.body, d.scripts, d.modulepreload, d.icon_hosts)
        attr.first_party_hosts |= a.first_party_hosts; attr.decisions += [x for x in a.decisions if x not in attr.decisions]
        for u in d.scripts[:6]:
            if u not in entry: entry.append(u)
        for u in d.scripts + d.modulepreload + list(d.importmap.values()):
            if u not in candidates: candidates.append(u)

    stage("scripts")
    # 2. scripts, by role, with chunk discovery, under caps
    fetched: set[str] = set(); read = 0; requests = 0; total = 0; enumerated = 0; cap_hit = False
    prev_id = (since or store.previous_usable_run(plan.slug, before_run_id=run_id)) if store is not None else None
    preferred = store.run_urls(prev_id) if (store is not None and prev_id) else set()
    max_requests = caps.get("max_requests", 3 * caps["max_scripts"])     # misses cost a request, not script budget
    MISS_STREAK = 8          # consecutive 404s on chunk urls one script named: that manifest names chunks that are not served (SM-8)
    named_by: dict[str, str] = {}                    # chunk url -> the script whose chunk map named it
    miss_streak: dict[str, int] = {}; stale: dict[str, int] = {}     # per naming script: misses in a row; skipped once stale
    while True:
        fp = [u for u in candidates if u not in fetched and attr.is_first_party(u)]
        for u in candidates:
            if not attr.is_first_party(u):
                h = u.split("/")[2] if "//" in u else u
                third_party.add(h)
        enumerated = len(fp) + len(fetched)
        budget_left = read < caps["max_scripts"] and total < caps["max_total_bytes"] and requests < max_requests
        if not fp or not budget_left:
            cap_hit = bool(fp) and not budget_left
            break
        batch = discover.select_by_role(fp, entry=entry, cap=caps["max_scripts"] - read, preferred=preferred)
        new_candidates = []
        for u in batch:
            if read >= caps["max_scripts"] or total >= caps["max_total_bytes"] or requests >= max_requests:
                break
            origin = named_by.get(u)
            if origin in stale and u not in entry:
                fetched.add(u); stale[origin] += 1; continue     # a dead manifest: spend no more requests on its chunks,
                                                                 # but other scripts' chunks are still read
            fetched.add(u)
            f = fetcher.get(u, caps["max_script_bytes"], "script")
            if f.state == "skipped-unconfigured" or f.status == "stopped":
                if f.status in ("robots.txt", "stopped"):
                    outcomes.append(SourceOutcome(f"script:{u}", f.state, 0, False, _why(f)))
                continue           # no request was made (a replayed run has no recording for it): no budget spent
            requests += 1
            if f.state != "ok" or not f.body:
                outcomes.append(SourceOutcome(f"script:{u}", f.state, 0, True, _why(f) if f.state != "ok" else None))
                if f.status == 404 and u not in entry and origin is not None:
                    miss_streak[origin] = miss_streak.get(origin, 0) + 1
                    if miss_streak[origin] >= MISS_STREAK and origin not in stale:
                        stale[origin] = 0
                continue
            if origin is not None:
                miss_streak[origin] = 0
            if (f.content_type or "").startswith("text/html") or f.body.lstrip()[:1] == "<":
                outcomes.append(SourceOutcome(f"script:{u}", "schema-drift", 0, True, "HTML answered on a script URL; not read as code")); continue
            read += 1
            if f.sha256 in bodies:
                continue   # identical body already read (dedupe)
            total += f.bytes
            bodies[f.sha256] = f.body
            artifacts[f.sha256] = Source(url=u, sha256=f.sha256, offset=-1, first_party=True, attribution="domain" if attr.domain in u else "cdn-list")
            for c in discover.chunks(f.body, u, attr.is_first_party):
                if c not in candidates and c not in new_candidates:
                    new_candidates.append(c); named_by.setdefault(c, u)
        if not new_candidates:
            # nothing new discovered; loop once more only if unfetched first-party candidates remain
            if not [u for u in candidates if u not in fetched and attr.is_first_party(u)]:
                break
        candidates += new_candidates
    for origin, skipped in stale.items():
        # a read cut short, not a budget: the code was listed and could not be fetched (ADR 0007)
        outcomes.append(SourceOutcome("chunks", "partial", 0, True,
                                      f"{MISS_STREAK} chunk urls named by {origin.rsplit('/', 1)[-1]} answered 404 in a row: its chunk map names "
                                      f"chunks that are not served; its other {skipped} chunk urls were not requested"))

    stage("extraction")
    # 3. extraction over every first-party body (pages included: inline scripts and JSON blocks live there)
    observations: list[Observation] = list(redirects)
    vendors = noise.load_vendors()
    sdks: set[str] = set()
    for sha, body in bodies.items():
        src = artifacts[sha]
        errs: list[str] = []
        for ob in extractors.extract_all(body, src, errors=errs):
            observations.append(ob)
        for e in errs:
            outcomes.append(SourceOutcome(f"extractor:{e.split(':')[0]}", "error", 0, True, f"{e} on {src.url}"))
        sdks |= set(noise.detect_sdks(body, vendors))
    observations = extractors.collapse_same_span(observations)
    # ids
    for i, ob in enumerate(observations):
        ob.id = f"e{i + 1:05d}"
    observations = noise.assign_tiers(observations, bodies, vendors)
    salience.apply(observations)          # R7: plumbing keys leave the findings tier; nouns are ranked for the brief
    # an SDK whose flags live at runtime is "could not see" unless a gate map (not five server-prop booleans) was read
    valued_gates = sum(1 for o in observations if o.kind == "gate" and o.group and isinstance(o.value, bool))
    runtime_only = sorted(s for s in sdks if valued_gates < 5)

    stage("signals: crt, ats, pricing, changelog, docs")
    # 4. second signals
    if recorded_signals:
        subs, jobs, pricing, so = _recorded_signals(recorded_signals, plan); outcomes += so; changelog_index = []; docs_index = []
    else:
        subs, so = _call_source("crt", plan, fetcher); outcomes += so
        jobs, so = _call_source("ats", plan, fetcher); outcomes += so
        pr, so = _call_source("pricing", plan, fetcher); outcomes += so
        pricing = pr[0] if pr else None
        changelog_index, so = _call_source("changelog", plan, fetcher); outcomes += so
        docs_index, so = _call_source("docs", plan, fetcher); outcomes += so
    stage("site: robots, sitemap, landing pages")
    # 4b. the site itself: robots.txt, sitemaps, landing pages (campaign signals); after the signals on purpose (SM-5),
    #     so a stopped host costs the least valuable fetches. Its bodies become blobs; its HTML pages are public pages.
    site_obs: list[Observation] = []
    if not recorded_signals:
        try:
            from sources import site as sitemod
            site_obs, so, site_bodies = sitemod.fetch(plan, fetcher); outcomes += so
            for sha, (u, text) in site_bodies.items():
                bodies.setdefault(sha, text)
                artifacts.setdefault(sha, Source(url=u, sha256=sha, offset=-1, first_party=True, attribution="domain"))
                if text.lstrip()[:1] == "<" and "<html" in text[:2000].lower():
                    page_bodies.append((u, text))          # a landing page the engine read is a public page (SM-6)
        except Exception as e:  # a source must never kill a run
            outcomes.append(SourceOutcome("site", "error", 0, True, f"{type(e).__name__}: {str(e)[:120]}"))
    site_shas = {o.source.sha256 for o in site_obs}
    for i, ob in enumerate(site_obs):
        ob.id = f"s{i + 1:05d}"
    observations += site_obs

    stage("route probes")
    # 4c. live pages and route probes, last of all the fetching
    # a route that is linked from the public pages is a live page today, not unreleased work (Linear: /agents, /insights).
    # An href inside a script is only a candidate: one product's admin registry carries `href: "/admin/games"` for pages
    # that redirect every visitor to sign-in. A candidate is live when one anonymous GET answers 200 on the same
    # path; a redirect, 401/403 or 404 is itself the finding ("gated", "not routable"). Never under a robots Disallow.
    href_rx = re.compile(r'href[=:]\s*["\'](/[A-Za-z0-9_\-./]*)["\']')
    live = {m.group(1).split("?")[0].rstrip("/") or "/" for _, b in page_bodies for m in href_rx.finditer(b)}
    in_scripts = {m.group(1).split("?")[0].rstrip("/") or "/" for sha, b in bodies.items() if sha not in site_shas for m in href_rx.finditer(b)} - live
    disallow = [o.key for o in site_obs if o.kind == "robots"]
    probed: dict[str, str] = {}
    if not recorded_signals:
        from sources.site import disallowed as _disallowed
        in_code = [o for o in observations if o.kind == "route" and o.tier == "finding" and o.key.split("?")[0].rstrip("/") in in_scripts
                   and ":" not in o.key and "*" not in o.key]
        cands = [o for o in in_code if not _disallowed(o.key, disallow)]
        # a route robots.txt keeps us out of is never requested and never "nothing found": it is listed as not checked
        not_checked = sorted({o.key.split("?")[0].rstrip("/") or "/" for o in in_code if _disallowed(o.key, disallow)})
        for p in not_checked:
            probed[p] = "not checked"
        if not_checked:
            outcomes.append(SourceOutcome("routes:robots", "skipped-unconfigured", len(not_checked), False,
                                          f"{ROBOTS_NOT_CHECKED}: " + ", ".join(not_checked[:12]) + (" …" if len(not_checked) > 12 else "")))
        seen = set()
        for o in cands:
            path = o.key.split("?")[0].rstrip("/") or "/"
            if path in seen or len(seen) >= ROUTE_PROBES:
                continue
            seen.add(path)
            try:
                f = fetcher.get(f"https://{plan.domain}{path}", 200_000, "page")
            except Exception:
                continue
            fp = (f.final_url or "").split("//", 1)[-1].split("/", 1)
            same = len(fp) == 2 and ("/" + fp[1]).split("?")[0].rstrip("/") == path
            if f.state in ("blocked-403", "challenge"):
                break                                       # a host that refuses is not probed further
            if f.status == 200 and same and "<html" in (f.body or "")[:2000].lower():
                probed[path] = "live"; live.add(path)
            elif f.status == 404:
                probed[path] = "not routable"
            elif f.status in (401, 403) or (f.status == 200 and not same):
                probed[path] = "gated"
        if seen:
            outcomes.append(SourceOutcome("routes", "ok", len(seen), True,
                                          f"{len(seen)} routes from script hrefs probed anonymously: " + ", ".join(f"{k} {sum(1 for v in probed.values() if v == k)}" for k in ("live", "gated", "not routable"))))
    for o in observations:
        path = o.key.split("?")[0].rstrip("/") or "/"
        if o.kind == "sitemap" and o.tier == "finding":
            o.context += "; linked from a public page" if path in live else "; not linked from the pages read"
        if o.kind == "route" and o.tier == "finding":
            if path in live:
                o.tier = "key-list"; o.group = o.group or "live page"; o.context = (o.context + " " if o.context else "") + "[linked from a public page]"
            elif probed.get(path) == "gated":
                o.context = (o.context + " " if o.context else "") + "[gated: redirects or refuses an anonymous visitor]"; o.salience += 2
            elif probed.get(path) == "not checked":
                o.context = (o.context + " " if o.context else "") + "[could not see: robots.txt asks crawlers to stay out; not requested]"
            elif probed.get(path) == "not routable":
                o.context = (o.context + " " if o.context else "") + "[in code, 404 to a visitor today]"; o.salience += 1
    cutoff = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=caps["crt_days"])).isoformat()
    recent_subs = [s for s in subs if max(s.first_seen, s.last_seen or "") >= cutoff]   # a flood still minting counts
    recent_subs, flagged = redact.redact_subdomains(recent_subs)

    stage("redact, cross-check")
    # 5. redact, cross-check
    observations, rlog = redact.redact(observations, plan.domain, extra_scrub=flagged)
    pricing_text = pricing_text_override if pricing_text_override is not None else ""
    if pricing and not pricing_text:
        pricing_text = pricing.text or "\n".join(pricing.lines)
    findings = [o for o in observations if o.tier == "finding"]
    checks = crosscheck.check(findings, pricing_text, changelog_index, pricing_url=pricing.url if pricing else None, docs_index=docs_index)
    salience.novelty(findings, {c.observation_id: c.status for c in checks})   # the odd one out in an announced cluster rises
    queries = crosscheck.web_queries(findings, plan.slug)
    for sub in subs:                      # marketing-tool hosts (go./info./pages./try.) carry the gated offers; one site: query each
        if sub.stem in _OFFER_STEMS and sub.count == 1:
            queries.append(f"site:{sub.name}")

    stage("coverage")
    # 6. coverage
    page_bytes = sum(len(b) for (_, b) in page_bodies)
    coverage = Coverage(sources=outcomes, first_party_bytes=total + page_bytes, scripts_fetched=read,
                        scripts_enumerated=enumerated, cap_hit=cap_hit, runtime_flag_providers=runtime_only,
                        attribution_decisions=list(attr.decisions), redactions=len([l for l in rlog if l.startswith("redacted")]) + len(flagged),
                        observations=len(observations), page_bytes=page_bytes)
    if cap_hit:
        outcomes.append(SourceOutcome("scripts", "capped", read, True, f"read {read} of {enumerated} enumerated; cap {caps['max_scripts']} scripts / {caps['max_total_bytes']:,} bytes / {max_requests} requests"))
    for s in runtime_only:
        outcomes.append(SourceOutcome(f"sdk:{s}", "runtime-only", 0, True, "flags fetched at runtime; not read"))

    stage("store, diff")
    # 7. store + diff
    d = None; first_seen = {}
    if store is not None:
        store.begin()
        try:
            store.record_artifacts(run_id, [(sha, src.url, len(bodies[sha]), src.first_party) for sha, src in artifacts.items() if sha in bodies])
            counts: dict[str, int] = {}
            for line in rlog:
                reason = line.split(": ", 1)[1] if ": " in line else line
                counts[reason] = counts.get(reason, 0) + 1
            if counts:
                store.save_redactions(run_id, counts)
            if coverage.verdict() != "could-not-see":
                store.upsert_observations(plan.slug, run_id, observations)
                store.save_signals(plan.slug, run_id, recent_subs, jobs, pricing)
                store.save_checks(plan.slug, run_id, checks, observations)
            # the run row goes last: a run is visible only once everything that makes it a baseline is there (SM-1)
            store.record_run(manifest, verdict=coverage.verdict(), seconds=round(time.time() - t0, 1), first_party_bytes=coverage.first_party_bytes,
                             domain=plan.domain, plan_json=plan.to_json())
            store.commit()
        except Exception:
            store.rollback()
            raise
        if prev_id and coverage.verdict() != "could-not-see":          # an empty read diffs against nothing (review B2)
            prev_obs = store.observations(plan.slug, prev_id)
            ps, pj, pp = store.signals(plan.slug, prev_id)
            d = diffmod.compute(prev_obs, observations, ps, recent_subs, pj, jobs, pp, pricing, since_run=prev_id, prev_urls=preferred)
            dropped = redact.redact_diff(d)
            if dropped:
                rlog.append(f"redacted {dropped} key(s) from the diff lists (sensitive under today's rules; the baseline predates them)")
            prev_bytes = store.run_bytes(plan.slug, prev_id)
            prev_version = store.run_version(plan.slug, prev_id)
            if prev_version and prev_version != engine_version:
                d.note = f"baseline was read by engine {prev_version}, this run by {engine_version}: added/removed may reflect extractor changes, flips do not"
            blocked = any(s.state in ("blocked-403", "challenge") for s in outcomes if s.source.startswith("page:"))
            if d.removed and (blocked or (prev_bytes and coverage.first_party_bytes < 0.6 * prev_bytes)):
                d.note = (d.note + "; " if d.note else "") + (f"removed withheld: this run read {coverage.first_party_bytes:,} bytes against the baseline's {prev_bytes:,}"
                          + ("; a page was blocked" if blocked else "") + ". Absence here is not removal")
                d.removed = []
        first_seen = store.first_seen_map(plan.slug)
    manifest.seconds = round(time.time() - t0, 1)
    manifest.blobs = sorted(bodies)
    manifest.extractor_versions = {n: getattr(import_module(f"extractors.{n}"), "VERSION", "?") for n in extractors.SHAPES if _has(n)}
    return RunResult(manifest, coverage, observations, checks, recent_subs, jobs, pricing, d, rlog, queries, bodies, changelog_index,
                     sorted(third_party), flagged, list(attr.decisions), first_seen)


def _why(f) -> str:
    """The coverage note for a fetch that did not read: robots.txt and a stopped host are said in words."""
    if f.status == "robots.txt":
        return ROBOTS_NOT_CHECKED          # never requested; never read; never "nothing found"
    if f.status == "stopped":
        return f"host refused earlier this run ({f.state}); not requested"
    return f"HTTP {f.status}"


def _has(name: str) -> bool:
    try:
        import_module(f"extractors.{name}"); return True
    except ModuleNotFoundError:
        return False
