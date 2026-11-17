# Runtime

Read before any engine command. `SKILL_DIR` is the directory holding the loaded `SKILL.md`.

## Interpreter

Python 3.11 or newer, standard library only. No `pip install`, no keys, no environment variables are
required. Check once:

```bash
python3 -c 'import sys; assert sys.version_info >= (3, 11), sys.version' && echo ok
```

If that fails, say so and stop; do not try other interpreters on the person's behalf.

## Where things go

- Home: `$UNRELEASED_HOME`, else `$XDG_DATA_HOME/unreleased`, else `~/.local/share/unreleased`. Holds
  `unreleased.db` (SQLite: products, runs, observations with first/last seen, checks, signals, briefs)
  and `blobs/` (content-addressed copies of every page and script read, so a receipt can be opened later).
- Runs: `<home>/runs/<slug>/<run-id>/` with `manifest.json`, `coverage.json`, `evidence.jsonl`,
  `checks.jsonl`, `signals.json`, `diff.json` (second run on), `redactions.log`, `web_queries.json`,
  `evidence.md`. `--save-dir DIR` puts the run folder under DIR instead. `evidence.jsonl` is one row per
  observation (several per key; `tier` is finding, key-list, codename or redacted); `checks.jsonl` joins to
  it on `observation_id` = `id`. The findings count on the badge, the footer and the run summary is the
  ranked product findings `evidence.md` lists (capped at 200 lines there; every row is in the jsonl).
  `--emit evidence` is for you; `--emit json` is for scripts.
- The run prints `run folder: <path>` on stderr when it finishes, whatever `--emit` is; `last-run.json`
  in the engine home (`UNRELEASED_HOME`, else `$XDG_DATA_HOME/unreleased`, else `~/.local/share/unreleased`) names it too. Read either.

## Commands and exit codes

```
run <slug> --plan plan.json [--emit evidence|json] [--save-dir DIR] [--no-store] [--since RUN_ID]
run <slug> --domain example.com --conventional      # /login, /, /pricing, /changelog; fallback only
diff <slug> · compare <run_a> <run_b> (ids or folders) · library "<query>" · doctor [--offline] · setup
robots <url>...      # allowed or disallowed per URL; read robots.txt only, before any probe while planning
```

0: a result (including could-not-see) · 2: planner guard, pass `--plan` · 3: invalid plan (message
names the field) · 4: Python older than 3.11 (the message names the interpreter) · 1: unexpected error with
a traceback; report it, do not retry blindly.

`--emit evidence` prints `evidence.md` to stdout (the default; `md` is an alias). `--emit json` prints the run summary and
paths only (agent mode; the brief is then written from the files).

## `doctor`

Four small requests, one per source, with no plan. A source `doctor` reports unreachable is a note for the
coverage line, not a reason to stop: crt.sh answers 502 intermittently and the run retries it. Run `doctor`
when a run's fetches all fail, to tell the environment from the target.

## Caps and politeness (fixed; not flags)

60 scripts, 8 MB per script, 120 MB per run, 4 MB per page, 25 route probes, one request per second per
host. The user agent is a browser string with the project token appended, `… unreleased/<version>
(research; public pages only; <repo url>)`, so CDNs serve the same bundles a browser gets and the token
identifies the run; use the same string for any URL you probe while planning: `unreleased.py ua` prints it. A hit cap is reported in
coverage as `capped` with "read N of M enumerated"; it does not make the run partial (ADR 0005), and a capped
`rich` run never says "every source read": its reason is "rich: every source answered; under the budget cap:
scripts read N of M enumerated". Say the N of M in the brief's one line. A chunk map whose chunks answer 404
(eight in a row from one script) is different: its other chunks are not requested, coverage says `chunks:
partial`, and the run is `partial` (ADR 0007), because listed code went unread for a reason other than budget. robots.txt is read
before anything else on a host and a page or script under a `Disallow` for `*` or `unreleased` is never
requested (`Disallow: /` closes the host). A disallowed page or app route is never "nothing found": coverage lists it as
"could not see: … (not checked: the site's robots.txt asks crawlers to stay out)", and a planned page it keeps
out makes the run `partial`. A 403 or a challenge
page stops that host for the run, never retried; a host that fails three times in a
row (timeouts, connection errors) is not asked again that run. `coverage.json` carries `verdict_reason`
("partial: crt error"), and `evidence.md`'s first coverage line repeats it.

## Time

First run on a product: one to four minutes live (network-bound; 78 s for a site with 110 chunks, 225 s for one with 2,800
enumerated). Each stage prints a line on stderr (`unreleased: scripts (12s)`), so a silent minute is a stall,
a line a minute is the run. Re-runs reuse blobs for unchanged scripts.
Products with thousands of lazy chunks are read by role (entry, named, rest) under the cap.
