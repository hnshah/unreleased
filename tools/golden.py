#!/usr/bin/env python3
"""Goldens lever: list, validate and check the readers' expected keys against the corpus.

The goldens (tests/goldens/<product>.json) are the independent source of truth for tests: keys and
strings a human reader found and judged nameable in the maintainers' corpus. The code never
produced them. This tool checks that every expected literal actually occurs in the product's first-party
bodies in the corpus, so a golden can't be wrong about what is in the bytes.

  python3 tools/golden.py list
  python3 tools/golden.py check --corpus <corpus>     # every expect/redact/noise literal occurs (a corpus recorded with `run --record`)
"""
import argparse, glob, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDENS = os.path.join(ROOT, "tests", "goldens")


def load_all():
    out = {}
    for p in sorted(glob.glob(os.path.join(GOLDENS, "*.json"))):
        name = os.path.basename(p)[:-5]
        if name.startswith("_"):
            continue
        out[name] = json.load(open(p, encoding="utf-8"))
    return out


def latest_run(corpus, product):
    idx = os.path.join(corpus, "_latest.json")
    if os.path.exists(idx):
        rel = json.load(open(idx)).get(product)
        if rel:
            return rel if os.path.isabs(rel) else os.path.join(os.path.dirname(corpus.rstrip("/")), rel)
    runs = sorted(glob.glob(os.path.join(corpus, product, "*", "summary.json")))
    return os.path.dirname(runs[-1]) if runs else None


def bodies(run_dir):
    for p in glob.glob(os.path.join(run_dir, "raw", "*")):
        try:
            yield os.path.basename(p), open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue


def check(corpus):
    bad = 0
    for product, g in load_all().items():
        run = latest_run(corpus, product)
        if not run:
            print(f"{product}: no run in corpus"); continue
        summ = json.load(open(os.path.join(run, "summary.json")))
        blob = "\n".join(b for _, b in bodies(run))
        signal_text = json.dumps(summ)  # subdomains, jobs, pricing hash live in the summary
        literals = []
        for kind, keys in g.get("expect", {}).items():
            for k in keys:
                literals.append((kind, k, k in blob or (kind == "subdomain" and k in signal_text)))
        for k in g.get("redact", []):
            literals.append(("redact", k, k in blob))
        for k in g.get("noise", []):
            literals.append(("noise", k, k in blob))
        missing = [(kind, k) for kind, k, ok in literals if not ok]
        print(f"{product:12} {len(literals)-len(missing):3}/{len(literals):3} literals present" + (f"  MISSING: {missing}" if missing else ""))
        bad += len(missing)
    return bad


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list")
    c = sub.add_parser("check"); c.add_argument("--corpus", required=True)
    a = ap.parse_args()
    if a.cmd == "list":
        for p, g in load_all().items():
            n = sum(len(v) for v in g.get("expect", {}).values())
            print(f"{p:12} expect {n:3}  redact {len(g.get('redact', []))}  noise {len(g.get('noise', []))}  ({g.get('reader')})")
        return 0
    if a.cmd == "check":
        return 1 if check(a.corpus) else 0
    ap.print_help(); return 0


if __name__ == "__main__":
    sys.exit(main())
