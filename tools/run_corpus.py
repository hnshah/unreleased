#!/usr/bin/env python3
"""Corpus benchmark lever: run the pipeline offline over a recorded corpus with the recorded fetcher and score
it against the goldens and the noise oracle. Deterministic, no network, rerunnable.

The corpus is copies of other companies' public bundles, so it is not redistributed. Record your own, then replay:

  python3 skills/unreleased/scripts/unreleased.py run figma --plan figma.json --record corpus    # once per product
  python3 tools/run_corpus.py --corpus corpus [--products figma,notion] [--out scorecard.json]

Each recorded run holds its plan.json; a corpus with a targets/targets.json beside it (the maintainers' 39-product
corpus) is read that way instead. Products without a golden in tests/goldens/ report recall as None.

Per product: golden recall (expected literals found as observations of any kind), finding-tier noise rate
(finding observations matching the noise oracle), redaction leaks (redact literals present in findings),
coverage verdict, seconds. Prints the V1/V5/V6 bars.
"""
import argparse, glob, json, os, re, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "unreleased", "scripts", "lib"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from golden import load_all, latest_run  # noqa: E402


def noise_match(key: str, oracle: dict) -> bool:
    if key in oracle["exact"]: return True
    if any(key.startswith(p) for p in oracle["prefix"]): return True
    if any(key.endswith(s) for s in oracle["suffix"]): return True
    return any(re.search(r, key) for r in oracle["regex"])


def score(product: str, result, g: dict, oracle: dict) -> dict:
    obs = result.observations
    found = {o.key for o in obs} | {o.context for o in obs if o.context} | {str(o.value) for o in obs if isinstance(o.value, str)}
    subs = {s.name for s in result.subdomains}
    expect = [(k, v) for k, vs in g.get("expect", {}).items() for v in vs]
    hit = 0
    missing = []
    for kind, lit in expect:
        ok = lit in subs if kind == "subdomain" else any(lit == k or lit in k for k in found)
        hit += ok
        if not ok: missing.append(lit)
    findings = [o for o in obs if o.tier == "finding"]
    noisy = [o.key for o in findings if noise_match(o.key, oracle) or o.key in g.get("noise", [])]
    leaks = [lit for lit in g.get("redact", []) if any(lit in o.key or lit in (o.context or "") or lit in str(o.value) for o in obs)]   # every tier (review S18)
    return {"product": product, "verdict": result.coverage.verdict(), "observations": len(obs), "findings": len(findings),
            "recall": round(hit / len(expect), 3) if expect else None, "expected": len(expect), "missing": missing,
            "noise_rate": round(len(noisy) / len(findings), 3) if findings else 0.0, "noisy": noisy[:20], "redaction_leaks": leaks}


def load_targets(corpus: str) -> list[dict]:
    """targets/targets.json beside the corpus when there is one; else every product whose latest run holds a plan.json
    (a corpus recorded with `run --record`)."""
    tj = os.path.join(os.path.dirname(corpus.rstrip("/")), "targets", "targets.json")
    if os.path.exists(tj):
        return json.load(open(tj))["targets"]
    out = []
    for slug in sorted(d for d in os.listdir(corpus) if os.path.isdir(os.path.join(corpus, d))):
        run_dir = latest_run(corpus, slug)
        pj = os.path.join(run_dir, "plan.json") if run_dir else ""
        if pj and os.path.exists(pj):
            with open(pj) as fh:
                plan = json.load(fh)
            out.append({"slug": slug, "plan": {k: v for k, v in plan.items() if v not in (None, [], {}, "")}})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True); ap.add_argument("--products"); ap.add_argument("--out", default="scorecard.json")
    a = ap.parse_args()
    import pipeline, fetch, plan as planmod
    goldens = load_all(); oracle = json.load(open(os.path.join(ROOT, "tests", "goldens", "_noise.json")))
    targets = load_targets(a.corpus)
    wanted = set(a.products.split(",")) if a.products else None
    rows = []
    for t in targets:
        if wanted and t["slug"] not in wanted: continue
        run_dir = latest_run(a.corpus, t["slug"])
        if not run_dir: continue
        p = planmod.validate(t["plan"] if "plan" in t else
                             {"slug": t["slug"], "domain": t["domain"], "pages": t["pages"], "pricing": t.get("pricing"),
                              "cdn_hosts": t.get("cdn_hosts", []), "ats": t.get("ats", {}), "apexes": [t["domain"]] + [h for h in t.get("cdn_hosts", []) if h.count(".") == 1]})
        f = fetch.RecordedFetcher(run_dir)
        t0 = time.time()
        try:
            r = pipeline.run(p, f, store=None, engine_version="bench", recorded_signals=os.path.join(run_dir, "summary.json"))
        except NotImplementedError as e:
            print(f"{t['slug']}: pipeline not implemented ({e})"); continue
        row = score(t["slug"], r, goldens.get(t["slug"], {}), oracle); row["seconds"] = round(time.time() - t0, 1)
        rows.append(row)
        print(f"{row['product']:12} {row['verdict']:13} obs={row['observations']:5} findings={row['findings']:4} recall={row['recall']} noise={row['noise_rate']} leaks={len(row['redaction_leaks'])} {row['seconds']}s")
    rich = sum(1 for r in rows if r["verdict"] == "rich")
    scored = [r for r in rows if r["recall"] is not None]
    mean_recall = round(sum(r["recall"] for r in scored) / len(scored), 3) if scored else None
    mean_noise = round(sum(r["noise_rate"] for r in rows) / len(rows), 3) if rows else None
    leaks = sum(len(r["redaction_leaks"]) for r in rows)
    summary = {"products": len(rows), "rich": rich, "mean_recall": mean_recall, "mean_noise_rate": mean_noise, "redaction_leaks": leaks,
               "V1_rich>=20": rich >= 20, "V1_recall>=0.8": (mean_recall or 0) >= 0.8, "V1_noise<=0.1": mean_noise is not None and mean_noise <= 0.1, "V5_leaks==0": leaks == 0}
    print(json.dumps(summary, indent=1))
    json.dump({"summary": summary, "rows": rows}, open(a.out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
