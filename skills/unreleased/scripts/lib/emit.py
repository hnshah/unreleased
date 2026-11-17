"""Emit: the run folder (manifest, coverage, evidence.jsonl, checks.jsonl, diff.json, redactions.log,
evidence.md). `evidence.md` is addressed to the host model and follows evidence-format.md: coverage first,
findings grouped by cluster with their certainty phrase, check and receipt, then appendices. The host writes
the user-facing brief from it and never pastes it.
"""
from __future__ import annotations
from dataclasses import asdict
from collections import defaultdict
import json, os, re
import salience
from pipeline import RunResult
from schema import canonical_json, ROBOTS_NOT_CHECKED

SITE_KINDS = ("robots", "sitemap", "headline")
FINDINGS_CAP = 200       # lines in evidence.md; everything is still in evidence.jsonl
CLUSTER_CAP = 12         # lines per sibling cluster on the page; the rest of the cluster is counted

PHRASE = {"gate": "present in code", "config": "present in code", "catalog": "present in code", "registry": "present in code", "enum": "present in code",
          "proto": "present in code", "route": "present in code", "inline": "present in code", "call": "present in code", "string": "referenced in strings",
          "i18n": "referenced in strings", "manifest": "present in code", "hidden": "present in code", "subdomain": "new subdomain", "job": "job signal",
          "pricing": "on the pricing page", "redirect": "redirect", "unknown": "present in code",
          "robots": "disallowed from search", "sitemap": "in the sitemap", "headline": "headline on landing pages"}
CHECK_PHRASE = {"announced": "announced", "partial": "partially announced", "none": "no public mention found", "unchecked": "unchecked"}
BOILERPLATE = ("These are strings present in public code; a flag or route is evidence that something is being built, not that it "
               "will ship, and the reading of what a name refers to may be wrong. Every line links to the bytes it came from. Items "
               "marked announced are already public; the rest had no public mention found as of the run date in the sources listed.")


def _receipt(o) -> str:
    off = f"@{o.source.offset}" if o.source.offset is not None and o.source.offset >= 0 else ""
    return f"[{o.source.url} sha256:{o.source.sha256[:12]}{off}]"


from extractors import KIND_RANK as _KIND_RANK
_NAME_TOKEN = re.compile(r"[A-Za-z0-9]+")


def finding_count(r) -> int:
    """The one findings number: the ranked product findings evidence.md leads with (site kinds have their own
    section; evidence.jsonl rows are observations, several per key). The run summary and the footer use it."""
    return len(_dedupe([o for o in r.observations if o.tier == "finding" and o.kind not in SITE_KINDS]))


def _dedupe(findings: list) -> list:
    """One line per name: `MAKE_LOCAL_X` (enum) and `make_local_x` (registry) are the same observation to a reader;
    keep the kind that says most (a gate with a value over a bare route). Digits are part of the name
    (`checkout_step_1` and `_2` are two lines; review B3). Full detail stays in evidence.jsonl."""
    best: dict[str, object] = {}
    for o in findings:
        n = "_".join(t.lower() for t in _NAME_TOKEN.findall(o.key))
        cur = best.get(n)
        if cur is None or (_KIND_RANK.get(o.kind, 20), -o.salience) < (_KIND_RANK.get(cur.kind, 20), -cur.salience):
            best[n] = o
    return list(best.values())


def _why_low(o) -> str:
    """The reason travels with the mark (TRUST: 'medium confidence' alone is not useful)."""
    if o.extractor == "strings": return "a string, not a parsed structure"
    if o.extractor == "calls": return "a minified accessor read by frequency, not a named call"
    if o.extractor == "registry": return "a pattern match over accessors"
    if o.extractor == "proto": return "a proto field named like a gate"
    return "pattern match, not a parsed structure"


def _value(v) -> str:
    if v is None: return ""
    if isinstance(v, bool): return "on" if v else "off"
    s = str(v)
    return s if len(s) <= 60 else s[:57] + "..."


def _site_section(site: list, r: RunResult) -> list[str]:
    """Campaign signals: what robots.txt hides, which compare and landing pages the sitemap lists (and whether the
    pages read link to them), and the headline shared across the landing pages read. Findings here are marketing
    work, not code; the brief gives them their own block."""
    L = ["## Campaign signals (robots.txt, sitemap, landing pages)", ""]
    rob = [o for o in site if o.kind == "robots"]
    hid = [o for o in rob if o.tier == "finding"]
    if rob:
        L.append(f"- robots.txt disallows {len(rob)} prefix(es); campaign-shaped: " + (", ".join(f"`{o.key}` [{o.source.url} sha256:{o.source.sha256[:12]}@{o.source.offset}]" for o in hid[:20]) if hid else "none")
                 + (f"; other: " + ", ".join(f"`{o.key}`" for o in rob if o.tier != "finding")[:400] if len(rob) > len(hid) else "") + ". A disallowed prefix is a published list of pages kept out of search; the engine does not fetch under it.")
    sm = [o for o in site if o.kind == "sitemap"]
    comp = [o for o in sm if o.tier == "finding" and "compare page" in o.context]
    seo = [o for o in sm if "compare post (content)" in o.context]
    land = [o for o in sm if o.tier == "finding" and "landing page" in o.context]
    recent = [o for o in sm if o.tier != "finding"]
    def _line(o):
        linked = "linked from a public page" if "linked from a public page" in o.context else "not linked from the pages read"
        return f"- `{o.key}`" + (f" lastmod {o.value}" if o.value else "") + f". {linked[0].upper() + linked[1:]}" + ("; disallowed in robots.txt" if "disallowed" in o.context else "") + f" [{o.source.url} sha256:{o.source.sha256[:12]}@{o.source.offset}]"
    if comp:
        L += [f"- compare / alternative pages in the sitemap: {len(comp)} (newest first; one not linked from the pages read is a page built before its campaign)"] + [_line(o) for o in sorted(comp, key=lambda o: o.value or "", reverse=True)[:40]]
    if seo:
        L.append(f"- compare posts under content directories (SEO, not campaign pages; key list): {len(seo)}, newest " + ", ".join(f"`{o.key}`" for o in sorted(seo, key=lambda o: o.value or "", reverse=True)[:8]))
    if land:
        L += [f"- landing pages in the sitemap: {len(land)}"] + [_line(o) for o in sorted(land, key=lambda o: o.value or "", reverse=True)[:30]]
    if recent:
        L.append(f"- other pages modified in the last {45} days: {len(recent)} (key list in evidence.jsonl, kind=sitemap): " + ", ".join(f"`{o.key}`" for o in sorted(recent, key=lambda o: o.value or "", reverse=True)[:25]))
    heads = [o for o in site if o.kind == "headline"]
    for o in sorted(heads, key=lambda o: -(o.value or 0)):
        L.append(f"- headline {'on ' + str(o.value) + ' pages' if (o.value or 0) > 1 else 'read'}: \"{o.key}\". {o.context[0].upper() + o.context[1:]} [{o.source.url} sha256:{o.source.sha256[:12]}@{o.source.offset}]")
    if not (rob or sm or heads):
        L.append("- nothing read (see coverage: robots / sitemap)")
    return L + [""]


def _page_said(p) -> str:
    return "not checked (robots.txt asks crawlers to stay out)" if p.detail == ROBOTS_NOT_CHECKED else p.state


def evidence_md(r: RunResult) -> str:
    c, m = r.coverage, r.manifest
    verdict = c.verdict()
    checks = {k.observation_id: k for k in r.checks}
    note = f"since {r.diff.since_run[:10]}" if r.diff and r.diff.since_run else "first run"
    L = [f"🔎 unreleased {m.engine_version} · {m.product} · {m.started_at[:10]} · {verdict} · {note}", "",
         "<!-- EVIDENCE FOR THE HOST: read, don't emit. Write the brief from this in the certainty vocabulary. -->", "",
         "## Coverage", "", f"- verdict: {c.verdict_reason()}"]
    pages = [s for s in c.sources if s.source.startswith("page:")]
    L.append(f"- pages read {sum(1 for p in pages if p.state == 'ok')} of {len(pages)}" + (": " + "; ".join(f"{p.source[5:]} {_page_said(p)}" for p in pages if p.state != "ok") if any(p.state != "ok" for p in pages) else ""))
    shut = [p.source[5:] for p in pages if p.detail == ROBOTS_NOT_CHECKED] + \
           [d[len(ROBOTS_NOT_CHECKED) + 2:] for d in (s.detail or "" for s in c.sources if s.source == "routes:robots") if d.startswith(ROBOTS_NOT_CHECKED + ": ")]
    if shut: L.append(f"- could not see: {', '.join(shut)} ({ROBOTS_NOT_CHECKED}; not requested, so not read and not clean)")
    L.append(f"- first-party code {c.first_party_bytes:,} bytes in {c.scripts_fetched} scripts (enumerated {c.scripts_enumerated}; cap hit: {'yes' if c.cap_hit else 'no'})")
    if r.attribution_decisions: L.append("- attribution: " + "; ".join(r.attribution_decisions))
    if r.third_party_hosts: L.append(f"- third-party hosts seen, not read: {', '.join(r.third_party_hosts[:12])}" + (" …" if len(r.third_party_hosts) > 12 else ""))
    if c.runtime_flag_providers: L.append(f"- could not see: {', '.join(c.runtime_flag_providers)} present; flags fetched at runtime, not read")
    elif c.cap_hit:   # absence under a cap is not absence: never let "no provider" read as a fact (a fresh-host trial, 2026-11-17)
        L.append(f"- flag SDKs: none seen in the {c.scripts_fetched} scripts read; the other {max(c.scripts_enumerated - c.scripts_fetched, 0):,} enumerated were not read and may load one")
    for s in c.sources:
        if not s.source.startswith("page:"):                      # every source the run touched, in the engine's order
            L.append(f"- {s.source}: {s.state}" + (f" ({s.detail})" if s.detail else "") + (f", {s.items} items" if s.items else ""))
    if r.flagged_subdomains: L.append(f"- hosts named for a company, withheld: {len(r.flagged_subdomains)}")
    demoted = sum(1 for ln in r.redaction_log if ln.startswith("demoted"))
    L.append(f"- redactions: {c.redactions}; demoted to the key list: {demoted} (both in redactions.log)")
    if not any(k.status != "unchecked" for k in r.checks) and any(o.tier == "finding" for o in r.observations):
        L.append("- cross-check: unchecked (no changelog index or pricing text was readable; run the web queries below before calling anything unannounced)")
    L.append("")
    if r.diff:
        d = r.diff
        quiet = not (d.flipped or d.added or d.removed or d.routes_added or d.pages_added or d.subdomains_added or d.jobs_added or d.jobs_removed or d.pricing_changed)
        L += [f"## Since {d.since_run}", ""] + ([f"Nothing material moved since {d.since_run[:10]}: no flips, no new keys or routes, no new hosts, jobs and pricing unchanged. Quiet is a valid answer; say so first.", ""] if quiet else []) + [
              f"- flipped: {len(d.flipped)}" + (": " + ", ".join(f"{x['key']} {_value(x['from'])}→{_value(x['to'])}" for x in d.flipped[:20]) if d.flipped else ""),
              f"- added: {len(d.added)}" + (": " + ", ".join(d.added[:30]) if d.added else ""),
              f"- removed: {len(d.removed)}" + (": " + ", ".join(d.removed[:30]) if d.removed else ""),
              f"- routes added: {len(d.routes_added)}" + (": " + ", ".join(d.routes_added[:20]) if d.routes_added else ""),
              f"- sitemap pages added: {len(d.pages_added)}" + (": " + ", ".join(d.pages_added[:20]) if d.pages_added else "") + (f"; removed {len(d.pages_removed)}" if d.pages_removed else ""),
              f"- new subdomains: {', '.join(d.subdomains_added) or 'none'}",
              f"- jobs: +{len(d.jobs_added)} −{len(d.jobs_removed)}",
              f"- pricing changed: {'yes' if d.pricing_changed else 'no'}" + (": " + "; ".join(d.pricing_lines_changed[:10]) if d.pricing_lines_changed else "")]
        if d.new_scripts_read:
            L.append(f"- newly read, not newly present: {d.added_in_new_scripts} keys in {d.new_scripts_read} scripts the baseline never read (the sample moved; these are not changes in the product)")
        if d.note:
            L.append(f"- note: {d.note}")
        L.append("")
    site = [o for o in r.observations if o.kind in SITE_KINDS]
    findings = _dedupe([o for o in r.observations if o.tier == "finding" and o.kind not in SITE_KINDS])
    # the vocabulary for second runs: a flip or a new key is the line's certainty phrase, and it ranks first
    flipped = {x["key"]: x for x in (r.diff.flipped if r.diff else [])}
    added = set(r.diff.added) | set(r.diff.routes_added) if r.diff else set()
    since_date = r.diff.since_run[:10] if r.diff else ""
    for o in findings:
        if o.key in flipped: o.salience += 10
        elif o.key in added: o.salience += 6
    baseline = min(r.first_seen.values()) if r.first_seen else ""     # "first seen" is news only after the product's first run
    checked_any = any(k.status != "unchecked" for k in r.checks)
    # clusters ordered by their best member, members by salience; the cap keeps the file readable — the rest is in evidence.jsonl
    clusters: dict[str, list] = defaultdict(list)
    for o in findings:
        clusters[salience.cluster(o.key)].append(o)
    ordered = sorted(clusters.items(), key=lambda kv: (-max(x.salience for x in kv[1]), -len(kv[1]), kv[0]))
    shown = 0
    # where the findings came from (gate maps, catalogs, route tables), once — not repeated on every line
    origins: dict[str, tuple[int, str]] = {}
    for o in findings:
        if o.group and o.group.lower() not in ("http", "https", "www"):
            n, ctx = origins.get(o.group, (0, o.context or ""))
            origins[o.group] = (n + 1, ctx)
    L += [f"## Findings ({len(findings)}; ranked by salience, clustered by prefix; showing up to {FINDINGS_CAP})", ""]
    if origins:
        def _origin(g: str) -> str:   # a minified table name (`l`, `Rn`, `A`) says nothing; say what it is
            return f"identifier table `{g}`" if len(g) <= 2 else f"`{g}`"
        L += ["origins: " + "; ".join(f"{_origin(g)} ×{n}" + (f' ("{c[:80]}")' if c and c.startswith(g) else "") for g, (n, c) in sorted(origins.items(), key=lambda kv: -kv[1][0])[:12]), ""]
    for g, items in ordered:
        if shown >= FINDINGS_CAP:
            break
        if len(items) > 1:
            L.append(f"**{g}** ({len(items)})")
        in_cluster = 0
        for o in sorted(items, key=lambda x: (-x.salience, x.key)):
            if shown >= FINDINGS_CAP:
                break
            if in_cluster >= CLUSTER_CAP:          # one cluster of 300 routes must not spend the whole page (Linear's /:orgKey/…)
                L.append(f"  … {len(items) - in_cluster} more `{g}` lines in evidence.jsonl"); break
            in_cluster += 1
            k = checks.get(o.id)
            cp = (" " + CHECK_PHRASE.get(k.status, "unchecked") + (" (docs)" if k.note == "docs" else "")) if k and k.status != "unchecked" else ""
            cp_detail = (f" {k.date}" if k and k.date else "") + (f" {k.url}" if k and k.url else "") + (f" (searched: {', '.join(k.searched)})" if k and k.status == "none" and k.searched else "")
            first = r.first_seen.get((o.kind, o.key))
            since = f"; first seen {first[:10]}" if first and first != m.run_id and first != baseline else ""
            val = f" = {_value(o.value)}" if o.value is not None and o.kind in ("gate", "inline", "call", "config") else ""
            ctx = f': "{o.context[:140]}"' if o.context and not (o.group and o.context.startswith(o.group)) else ""
            if o.key in flipped:
                phrase = f"flipped {_value(flipped[o.key]['from'])}→{_value(flipped[o.key]['to'])} since {since_date}"
            elif o.key in added:
                phrase = f"newly present since {since_date}"
            else:
                phrase = PHRASE.get(o.kind, "present in code")
            conf = f" · {o.confidence}" + (f" ({_why_low(o)})" if o.confidence == "low" else "")
            L.append(f"- `{o.key}`{val}: {phrase} ({o.kind}{since}){ctx}.{cp}{cp_detail}{conf} {_receipt(o)}")
            shown += 1
    if len(findings) > shown:
        L.append(f"- … {len(findings) - shown} more findings in evidence.jsonl (tier=finding), ordered by salience")
    L.append("")
    if site:
        L += _site_section(site, r)
    if r.subdomains:
        L += ["## New subdomains (certificate logs, last 120 days)", ""] + [f"- {s.first_seen} `{s.name}`" + (f" ({s.env})" if s.env else "") + (f" ({s.count:,} hosts, latest {s.last_seen})" if s.count > 1 else "") for s in sorted(r.subdomains, key=lambda s: s.first_seen)[:60]] + [""]
    if r.jobs:
        nouns = defaultdict(int)
        for j in r.jobs:
            for n in (j.nouns or []): nouns[n] += 1
        ats_line = next((s.detail for s in c.sources if s.source == "ats" and s.detail), "")
        unverified = "unverified" in (ats_line or "")
        L += [f"## Jobs ({len(r.jobs)} on {r.jobs[0].ats}" + ("; board NOT verified as this product's: titles may belong to another company" if unverified else "") + ")", ""]
        L += [f"- nouns: " + ", ".join(f"{n} ×{c}" for n, c in sorted(nouns.items(), key=lambda kv: -kv[1])[:20])] if nouns else []
        L += [f"- {j.posted_at or 'undated'} {j.title}" + (f" [{j.url}]" if j.url else "") for j in sorted(r.jobs, key=lambda j: j.posted_at or "", reverse=True)[:40]] + [""]
    if r.pricing:
        rc = f"[{r.pricing.final_url or r.pricing.url} sha256(text):{r.pricing.sha256_text[:12]}]"
        L += [f"## Pricing page ({r.pricing.status}; {r.pricing.chars:,} chars; receipt for every line below: {rc})", ""] + [f"- {l}" for l in r.pricing.lines[:30]] + [""]
    announced = [o for o in findings if checks.get(o.id) and checks[o.id].status == "announced"]
    if announced:
        L += ["## Announced, for calibration", ""] + [f"- `{o.key}`: {checks[o.id].date or ''} {checks[o.id].url or ''}" for o in announced[:40]] + [""]
    keylist = _dedupe([o for o in r.observations if o.tier == "key-list" and o.kind not in SITE_KINDS]); codenames = _dedupe([o for o in r.observations if o.tier == "codename"])
    L += [f"## Appendix: key list ({len(keylist)})", "", ", ".join(f"`{o.key}`" for o in keylist[:400]) or "none", "",
          f"## Appendix: codenames seen ({len(codenames)})", "", ", ".join(f"`{o.key}`" for o in codenames[:300]) or "none", "",
          "## Web queries for the host (bounded)", ""] + [f"- {q}" for q in r.web_queries] + ["", "## Boilerplate", "", BOILERPLATE, "",
          "```text", f"unreleased {m.engine_version} · {m.product} · run {m.run_id} · {verdict} · findings {len(findings)} · key-list {len(keylist)} · codenames {len(codenames)} · redactions {c.redactions} · {m.seconds}s", "```", ""]
    return "\n".join(L)


def write_run_folder(r: RunResult, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    def w(name, text):
        p = os.path.join(out_dir, name)
        with open(p, "w", encoding="utf-8", errors="replace") as f: f.write(text)
        paths[name] = p
    w("manifest.json", json.dumps(json.loads(canonical_json(r.manifest)), sort_keys=True, indent=1, ensure_ascii=False))
    cov = asdict(r.coverage); cov["verdict"] = r.coverage.verdict(); cov["verdict_reason"] = r.coverage.verdict_reason(); cov["third_party_hosts"] = r.third_party_hosts; cov["flagged_subdomains"] = len(r.flagged_subdomains)
    w("coverage.json", json.dumps(cov, indent=1, sort_keys=True))
    tier_rank = {"finding": 0, "key-list": 1, "codename": 2, "redacted": 3}
    ordered = sorted(r.observations, key=lambda o: (tier_rank.get(o.tier, 9), -o.salience, o.kind, o.key))
    w("evidence.jsonl", "".join(json.dumps(asdict(o), sort_keys=True, default=str) + "\n" for o in ordered))
    w("checks.jsonl", "".join(json.dumps(asdict(c), sort_keys=True) + "\n" for c in r.checks))
    w("signals.json", json.dumps({"subdomains": [asdict(s) for s in r.subdomains], "jobs": [asdict(j) for j in r.jobs], "pricing": asdict(r.pricing) if r.pricing else None,
                                  "changelog_index": r.changelog_index[:200]}, indent=1, sort_keys=True))
    if r.diff: w("diff.json", json.dumps(asdict(r.diff), indent=1, sort_keys=True))
    w("redactions.log", "\n".join(r.redaction_log + [f"withheld subdomain named for a company ({i + 1} of {len(r.flagged_subdomains)})" for i in range(len(r.flagged_subdomains))]) + ("\n" if r.redaction_log or r.flagged_subdomains else ""))
    w("web_queries.json", json.dumps(r.web_queries, indent=1))
    w("evidence.md", evidence_md(r))
    return paths
