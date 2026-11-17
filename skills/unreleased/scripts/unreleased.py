#!/usr/bin/env python3
"""unreleased: what a product is building and hasn't announced, from public pages.

The CLI is the shell: it validates the plan (the boundary), builds the fetcher and store, runs the pipeline,
writes the run folder and prints `evidence.md` for the host. Under an agent host it refuses to run without a
plan (the host is the planner), exactly as last30days does.

  unreleased run <product> --plan plan.json [--emit evidence|md|json] [--save-dir DIR] [--no-store] [--agent] [--since RUN_ID]
  unreleased report [<product>] [--run-dir DIR] [--brief brief.md] [--theme tokens.css]   # report.html + report.md
  unreleased diff <product>              last run vs the previous usable run
  unreleased compare <run_a> <run_b>     run ids or run folders
  unreleased library "<query>"
  unreleased doctor
  unreleased setup

Exit codes: 0 ok (including a could-not-see result) · 2 planner guard · 3 invalid plan · 4 Python too old · 1 unexpected error.
"""
import sys

if sys.version_info < (3, 11):   # before any import that would fail with a syntax error deep inside a module
    sys.stderr.write(f"unreleased: needs Python 3.11 or newer; this is {sys.version.split()[0]} ({sys.executable}). "
                     "Install a newer python3 or run with it explicitly: python3.12 scripts/unreleased.py ...\n")
    sys.exit(4)

import argparse, json, os, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))

VERSION = "0.1.0"
HOST_ENV = ("CLAUDECODE", "CURSOR_AGENT", "CODEX_SANDBOX", "GEMINI_CLI", "OPENCODE")


def home() -> str:
    base = os.environ.get("UNRELEASED_HOME") or os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "unreleased")
    os.makedirs(base, exist_ok=True)
    return base


def cmd_run(a) -> int:
    import plan as planmod, fetch, store as storemod, pipeline, emit
    under_agent = any(os.environ.get(k) for k in HOST_ENV)
    if not a.plan:
        if under_agent and not a.conventional:
            print("unreleased: you are the planner. Resolve the product into pages/apexes/ATS/pricing/changelog and pass --plan <file> "
                  "(see references/plan.md), or pass --conventional to use /login, /, /pricing, /changelog on the domain. Exiting before any network request.", file=sys.stderr)
            return 2
        if not a.domain:
            print("unreleased: --plan <file> or --domain <domain> is required", file=sys.stderr); return 3
        p = planmod.conventional(a.product, a.domain)
    else:
        try:
            p = planmod.load_plan(a.plan)
        except (planmod.PlanError, OSError, ValueError) as e:
            print(f"unreleased: invalid plan: {e}", file=sys.stderr); return 3
    h = home()
    blobs = fetch.BlobStore(os.path.join(h, "blobs"))
    fetcher = fetch.RecordedFetcher(a.recorded) if a.recorded else fetch.LiveFetcher(blobs=blobs)
    recorder = None
    if a.record and not a.recorded:
        import datetime as _dt
        rec_dir = os.path.join(a.record, p.slug, _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ"))
        fetcher = recorder = fetch.RecordingFetcher(fetcher, rec_dir)
    st = None if a.no_store else storemod.Store(os.path.join(h, "unreleased.db"))
    if a.since and st is None:
        print("unreleased: --since needs the library; drop --no-store", file=sys.stderr); return 3
    try:
        try:
            r = pipeline.run(p, fetcher, st, engine_version=VERSION, recorded_signals=os.path.join(a.recorded, "summary.json") if a.recorded else None, since=a.since,
                             progress=lambda m: print(f"unreleased: {m}", file=sys.stderr, flush=True))
        except ValueError as e:                                   # SM-2 / SM-3: a bad --since or a reused run id, before any fetch
            print(f"unreleased: {e}", file=sys.stderr); return 3
        out_dir = os.path.join(a.save_dir or os.path.join(h, "runs"), p.slug, r.manifest.run_id)
        if os.path.exists(os.path.join(out_dir, "manifest.json")):
            print(f"unreleased: run folder {out_dir} already exists; a run is never overwritten", file=sys.stderr); return 3
        paths = emit.write_run_folder(r, out_dir)
        if recorder is not None:
            import dataclasses
            print(f"unreleased: recorded for replay in {recorder.finish(r, dataclasses.asdict(p))}", file=sys.stderr)
        if st is not None and r.coverage.verdict() != "could-not-see":
            with open(paths["evidence.md"], encoding="utf-8") as f:
                st.save_brief(p.slug, r.manifest.run_id, paths["evidence.md"], f.read())   # `library` searches these
    finally:
        if st: st.close()
    print(f"run folder: {out_dir}", file=sys.stderr)
    cfg = h; os.makedirs(cfg, exist_ok=True)
    with open(os.path.join(cfg, "last-run.json"), "w", encoding="utf-8") as f:
        json.dump({"product": p.slug, "run_id": r.manifest.run_id, "run_dir": out_dir, "verdict": r.coverage.verdict(), "findings": emit.finding_count(r)}, f, indent=1)
    if a.emit == "json" or a.agent:
        print(json.dumps({"product": p.slug, "run_id": r.manifest.run_id, "run_dir": out_dir, "verdict": r.coverage.verdict(), "paths": paths,
                          "findings": emit.finding_count(r), "observations": len(r.observations), "seconds": r.manifest.seconds}, indent=1))
    else:
        with open(paths["evidence.md"], encoding="utf-8") as f:
            sys.stdout.write(f.read())
        print(f"\nrun folder: {out_dir}", file=sys.stderr)
    return 0


def cmd_diff(a) -> int:
    import store as storemod
    st = storemod.Store(os.path.join(home(), "unreleased.db"))
    try:
        rows = st.db.execute("SELECT run_id, verdict FROM runs WHERE product=? ORDER BY run_id DESC LIMIT 2", (a.product,)).fetchall()
        if len(rows) < 2:
            print("need two runs", file=sys.stderr); return 1
        cur, prev = rows[0]["run_id"], st.previous_usable_run(a.product, rows[0]["run_id"])
        import diff as diffmod, redact
        if a.since: prev = a.since
        sp, sc = st.signals(a.product, prev), st.signals(a.product, cur)
        # the same call the run makes, so `diff` and the run folder's diff.json cannot disagree
        d = diffmod.compute(st.observations(a.product, prev), st.observations(a.product, cur), sp[0], sc[0], sp[1], sc[1], sp[2], sc[2],
                            since_run=prev, prev_urls=st.run_urls(prev))
        redact.redact_diff(d)
        from dataclasses import asdict
        print(json.dumps(asdict(d), indent=1)); return 0
    finally:
        st.close()


def run_dir_for(ref: str) -> str | None:
    """A run folder from a path or a run id (the footer's `run <id>`): ids are looked up under <home>/runs/<slug>/<id>."""
    if os.path.isfile(os.path.join(ref, "evidence.jsonl")):
        return ref
    runs = os.path.join(home(), "runs")
    if os.sep not in ref and os.path.isdir(runs):
        found = [os.path.join(runs, slug, ref) for slug in sorted(os.listdir(runs)) if os.path.isfile(os.path.join(runs, slug, ref, "evidence.jsonl"))]
        if len(found) > 1:          # ids are timestamps: two products can share one; never pick silently
            raise LookupError(f"run id {ref!r} names {len(found)} runs ({', '.join(found)}); pass the run folder")
        return found[0] if found else None
    return None


def cmd_compare(a) -> int:
    def load(d):
        with open(os.path.join(d, "evidence.jsonl"), encoding="utf-8") as f:
            return {(r["kind"], r["key"]): r for r in map(json.loads, filter(str.strip, f))}
    try:
        dirs = [run_dir_for(r) for r in (a.run_a, a.run_b)]
    except LookupError as e:
        print(f"unreleased: {e}", file=sys.stderr); return 3
    for ref, d in zip((a.run_a, a.run_b), dirs):
        if d is None:
            print(f"unreleased: no run folder or run id {ref!r} (looked under {os.path.join(home(), 'runs')})", file=sys.stderr); return 3
    x, y = load(dirs[0]), load(dirs[1])
    print(json.dumps({"only_in_a": sorted(f"{k[0]}:{k[1]}" for k in x.keys() - y.keys())[:200], "only_in_b": sorted(f"{k[0]}:{k[1]}" for k in y.keys() - x.keys())[:200],
                      "value_changed": sorted(f"{k[1]}: {x[k]['value']} -> {y[k]['value']}" for k in x.keys() & y.keys() if x[k]["value"] != y[k]["value"])[:200]}, indent=1))
    return 0


def cmd_report(a) -> int:
    """A shareable file from a run folder and (usually) the host's brief: report.html and report.md beside the run."""
    import report
    run_dir = a.run_dir
    if not run_dir and a.brief:                      # the brief's footer names its run; render against that one
        with open(a.brief, encoding="utf-8") as f:
            rid = report.brief_run_id(f.read())
        if rid:
            for slug in ([a.product] if a.product else os.listdir(os.path.join(home(), "runs")) if os.path.isdir(os.path.join(home(), "runs")) else []):
                cand = os.path.join(home(), "runs", slug, rid)
                if os.path.exists(os.path.join(cand, "evidence.jsonl")):
                    run_dir = cand; break
    if not run_dir:
        try:
            with open(os.path.join(home(), "last-run.json"), encoding="utf-8") as f:
                last = json.load(f)
        except FileNotFoundError:
            print("no run folder given and no last run recorded; pass --run-dir", file=sys.stderr); return 3
        if a.product and last.get("product") != a.product:
            print(f"last run is for {last.get('product')!r}, not {a.product!r}; pass --run-dir", file=sys.stderr); return 3
        run_dir = last["run_dir"]
    if not os.path.exists(os.path.join(run_dir, "evidence.jsonl")):
        print(f"not a run folder: {run_dir}", file=sys.stderr); return 3
    out_html, out_md = report.write(run_dir, a.brief, a.out, a.md, a.theme, None, top=a.top)
    print(json.dumps({"html": out_html, "md": out_md, "brief": bool(a.brief)}, indent=1))
    return 0


def cmd_library(a) -> int:
    import store as storemod
    st = storemod.Store(os.path.join(home(), "unreleased.db"))
    try:
        for h in st.search_briefs(a.query): print(json.dumps(h))
        return 0
    finally:
        st.close()


def cmd_doctor(a) -> int:
    import sqlite3
    info = {"version": VERSION, "python": sys.version.split()[0], "home": home(), "fts5": False, "sources": {}}
    try:
        c = sqlite3.connect(":memory:"); c.execute("CREATE VIRTUAL TABLE t USING fts5(x)"); info["fts5"] = True
    except Exception:
        pass
    if not a.offline:
        import fetch
        from importlib import import_module
        f = fetch.LiveFetcher(robots=False)          # health endpoints exist to be queried; doctor stays at four requests
        for name in ("crt", "ats", "pricing", "changelog", "site", "docs"):
            try:
                o = import_module(f"sources.{name}").health(f); info["sources"][name] = o.state if hasattr(o, "state") else str(o)
            except NotImplementedError:
                info["sources"][name] = "not implemented"
            except Exception as e:
                info["sources"][name] = f"error: {type(e).__name__}"
    print(json.dumps(info, indent=1)); return 0


def cmd_robots(a) -> int:
    """For each URL: read its host's robots.txt (once, with the project user agent) and say whether the engine may
    request it. Only robots.txt is requested, never the URL itself; probe a URL only when this says allowed."""
    import urllib.parse, fetch
    f = fetch.LiveFetcher()
    for url in a.urls:
        sp = urllib.parse.urlsplit(url)
        if sp.scheme not in ("http", "https") or not sp.hostname:
            print(f"invalid\t{url}"); continue
        _, rules = f._robots_for(sp.scheme, sp.netloc, fetch.host_key(sp))
        path = (sp.path or "/") + (("?" + sp.query) if sp.query else "")
        print(f"{'disallowed' if fetch.robots_disallows(path, rules) else 'allowed'}\t{url}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="unreleased", description=__doc__.split("\n")[0])
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="read a product's public pages and code; writes a run folder and evidence.md"); r.add_argument("product"); r.add_argument("--plan"); r.add_argument("--domain"); r.add_argument("--conventional", action="store_true")
    r.add_argument("--emit", choices=["evidence", "md", "json"], default="evidence"); r.add_argument("--save-dir"); r.add_argument("--no-store", action="store_true")
    r.add_argument("--agent", action="store_true"); r.add_argument("--recorded", help="replay a probe run folder instead of the network (tests, benchmarks)"); r.add_argument("--record", metavar="DIR", help="also keep what was read under DIR/<product>/<run-id>/ for offline replay (tools/run_corpus.py)")
    r.add_argument("--since", help="diff against this earlier run id (the one the person last read) instead of the previous usable run")
    d = sub.add_parser("diff", help="what moved since the previous usable run of a product"); d.add_argument("product"); d.add_argument("--since", help="diff against this earlier run id")
    c = sub.add_parser("compare", help="diff two specific runs, by run id or run folder"); c.add_argument("run_a"); c.add_argument("run_b")
    rp = sub.add_parser("report", help="report.html + report.md from a run folder and the host's brief")
    rp.add_argument("product", nargs="?"); rp.add_argument("--run-dir", help="a run folder (default: the last run)")
    rp.add_argument("--brief", help="the brief as written (markdown); without it the report is an evidence report")
    rp.add_argument("--out", help="html path (default: <run>/report.html)"); rp.add_argument("--md", help="markdown path (default: <run>/report.md)")
    rp.add_argument("--theme", help="a CSS file of :root custom properties overriding the design tokens"); rp.add_argument("--top", type=int, default=40)
    l = sub.add_parser("library", help="search earlier briefs and evidence offline"); l.add_argument("query")
    dc = sub.add_parser("doctor", help="health checks: python, sqlite, network, each source"); dc.add_argument("--offline", action="store_true")
    sub.add_parser("setup", help="create the local library and config folder")
    sub.add_parser("ua", help="print the project user agent, for probes made while planning")
    rb = sub.add_parser("robots", help="read robots.txt and print allowed or disallowed for each URL, before probing it while planning"); rb.add_argument("urls", nargs="+")
    a = ap.parse_args()
    try:
        if a.cmd == "run": return cmd_run(a)
        if a.cmd == "diff": return cmd_diff(a)
        if a.cmd == "compare": return cmd_compare(a)
        if a.cmd == "report": return cmd_report(a)
        if a.cmd == "library": return cmd_library(a)
        if a.cmd == "doctor": return cmd_doctor(a)
        if a.cmd == "robots": return cmd_robots(a)
        if a.cmd == "ua":
            from fetch import UA; print(UA); return 0
        if a.cmd == "setup":
            print(json.dumps({"home": home(), "note": "no keys needed; run `unreleased doctor` to check sources"})); return 0
        ap.print_help(); return 0
    except Exception:
        traceback.print_exc(); return 1


if __name__ == "__main__":
    sys.exit(main())
