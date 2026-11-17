"""Diff (R11): this run against the previous usable run of the same product, by value.

Flips are value changes on the same (kind, key); added/removed are keys that appeared or disappeared among
non-route observations; routes are reported separately because route tables accumulate and are undated.
"""
from __future__ import annotations
from schema import Observation, Diff, Subdomain, Job, PricingSnapshot


_DIFFABLE_TIERS = ("finding", "key-list")      # strings and codenames vary with the 60-script sample; a diff over them is noise


def _index(obs: list[Observation]) -> dict[tuple[str, str], Observation]:
    import salience
    return {(o.kind, o.key): o for o in obs if o.tier in _DIFFABLE_TIERS and o.kind not in ("string", "i18n") and o.group != "live page"
            and not (o.kind == "route" and salience._NAV_ROUTE.match(o.key))}     # the site's own nav flaps with page rendering


def compute(prev: list[Observation], cur: list[Observation], prev_sub: list[Subdomain], cur_sub: list[Subdomain],
            prev_jobs: list[Job], cur_jobs: list[Job], prev_pricing: PricingSnapshot | None, cur_pricing: PricingSnapshot | None,
            since_run: str, prev_urls: set[str] | None = None) -> Diff:
    """`prev_urls` (the baseline's read scripts) keeps "added" honest: a key from a script the baseline never read
    is newly *read*, not newly *present* (Linear: a different 60 of 440 chunks produced 3,541 "added" keys)."""
    p, c = _index(prev), _index(cur)
    d = Diff(since_run=since_run)
    new_scripts: set[str] = set()
    for k, o in c.items():
        if k in p:
            if o.value is not None and p[k].value is not None and o.value != p[k].value:
                d.flipped.append({"key": o.key, "from": p[k].value, "to": o.value})
        elif prev_urls is not None and o.source.url and o.source.url not in prev_urls:
            d.added_in_new_scripts += 1; new_scripts.add(o.source.url)
        elif o.kind == "route":
            d.routes_added.append(o.key)
        elif o.kind == "sitemap":
            d.pages_added.append(o.key)
        elif o.kind in ("robots", "headline"):
            d.added.append(f"{o.kind}:{o.key}")
        else:
            d.added.append(o.key)
    d.new_scripts_read = len(new_scripts)
    for k, o in p.items():
        if k in c or o.kind == "route":
            continue
        if o.kind == "sitemap":
            d.pages_removed.append(o.key)
        elif o.kind == "headline":
            continue                      # three pages read per run; a headline not seen again is not gone
        else:
            d.removed.append(o.key)
    ps, cs = {s.name for s in prev_sub}, {s.name for s in cur_sub}
    d.subdomains_added = sorted(cs - ps)
    pj, cj = {j.title for j in prev_jobs}, {j.title for j in cur_jobs}
    d.jobs_added, d.jobs_removed = sorted(cj - pj), sorted(pj - cj)
    if prev_pricing and cur_pricing and prev_pricing.sha256_text != cur_pricing.sha256_text:
        d.pricing_changed = True
        added = sorted(set(cur_pricing.lines) - set(prev_pricing.lines)); removed = sorted(set(prev_pricing.lines) - set(cur_pricing.lines))
        d.pricing_lines_changed = [f"+{l}" for l in added] + [f"-{l}" for l in removed]
    d.flipped.sort(key=lambda x: x["key"]); d.added.sort(); d.removed.sort(); d.routes_added.sort(); d.pages_added.sort(); d.pages_removed.sort()
    return d
