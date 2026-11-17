#!/usr/bin/env python3
"""Fixture lever: cut an excerpt from a corpus body around a needle and record its provenance.

  python3 tools/make_fixture.py --corpus <corpus> --product figma \
      --needle assistant_monetization_config --before 1500 --after 4000 --shape gatemap --name figma-monetization

Writes tests/fixtures/<shape>/<name>.js (the excerpt) and <name>.js.json (product, source URL, sha256 of
the full body, start/end offsets, needle). Excerpts are small on purpose: a fixture is evidence for one
extractor, never a copy of a third-party bundle. Re-running with the same arguments reproduces the file.
"""
import argparse, glob, hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def latest_run(corpus, product):
    idx = os.path.join(corpus, "_latest.json")
    if os.path.exists(idx):
        rel = json.load(open(idx)).get(product)
        if rel:
            return rel if os.path.isabs(rel) else os.path.join(os.path.dirname(corpus.rstrip("/")), rel)
    runs = sorted(glob.glob(os.path.join(corpus, product, "*", "summary.json")))
    return os.path.dirname(runs[-1]) if runs else None


def url_for(run_dir, raw_name):
    """Map a raw file name (sha1(url)[:10] + ext) back to its URL via summary.json."""
    summ = json.load(open(os.path.join(run_dir, "summary.json")))
    stem = raw_name.split(".")[0]
    cands = [p["url"] for p in summ.get("pages", [])] + [u for u in summ.get("flag_keys", []) if u.startswith("http")]
    # scripts are not listed with urls in v0 summary; derive from flags.tsv sources and page urls
    seen = set(cands)
    try:
        for line in open(os.path.join(run_dir, "flags.tsv"), encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 4 and parts[3].startswith("http"):
                seen.add(parts[3].split("#")[0])
    except OSError:
        pass
    for u in seen:
        if hashlib.sha1(u.encode()).hexdigest()[:10] == stem:
            return u
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True); ap.add_argument("--product", required=True)
    ap.add_argument("--needle", required=True); ap.add_argument("--shape", required=True); ap.add_argument("--name", required=True)
    ap.add_argument("--before", type=int, default=1500); ap.add_argument("--after", type=int, default=4000)
    ap.add_argument("--occurrence", type=int, default=0, help="which occurrence of the needle (0 = first)")
    a = ap.parse_args()
    run = latest_run(a.corpus, a.product)
    if not run:
        print("no run for product", file=sys.stderr); return 2
    hits = []
    for p in sorted(glob.glob(os.path.join(run, "raw", "*"))):
        body = open(p, encoding="utf-8", errors="replace").read()
        i, n = body.find(a.needle), 0
        while i != -1:
            hits.append((p, body, i)); n += 1
            i = body.find(a.needle, i + 1)
    if not hits:
        print("needle not found in any raw body", file=sys.stderr); return 3
    if a.occurrence >= len(hits):
        print(f"only {len(hits)} occurrences", file=sys.stderr); return 3
    path, body, i = hits[a.occurrence]
    start, end = max(0, i - a.before), min(len(body), i + len(a.needle) + a.after)
    excerpt = body[start:end]
    outdir = os.path.join(ROOT, "tests", "fixtures", a.shape); os.makedirs(outdir, exist_ok=True)
    ext = ".html" if path.endswith(".html") else ".js"
    out = os.path.join(outdir, a.name + ext)
    open(out, "w", encoding="utf-8").write(excerpt)
    meta = {"product": a.product, "run": os.path.relpath(run, os.path.dirname(a.corpus.rstrip("/"))), "raw_file": os.path.basename(path),
            "url": url_for(run, os.path.basename(path)), "sha256_full": hashlib.sha256(body.encode("utf-8", "replace")).hexdigest(),
            "start": start, "end": end, "needle": a.needle, "occurrences_in_body": sum(1 for h in hits if h[0] == path), "bytes": len(excerpt)}
    json.dump(meta, open(out + ".json", "w"), indent=1)
    print(f"wrote {os.path.relpath(out, ROOT)} ({len(excerpt):,} bytes) from {meta['raw_file']} @ {start}-{end}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
