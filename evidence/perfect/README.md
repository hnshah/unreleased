# Perfecting-loop evidence

Logs written by a perfecting loop (the maintainers' own tool, not in this repo) from fresh-host trials (Claude Code, clean host, fresh
config) on a copy of this repo, together with the 22-point bar, a reader for each trial's stumbles, and a judge.
Each run has its own folder: `rounds.jsonl` is the machine record and `round-NN.md` the readable one. Local paths
are replaced with `<copy of unreleased>` and the pre-release commit ids are removed. The loop's fixes are never applied as they are. Each one is read first,
and the list below says which were folded back and which were declined.

## 2026-11-17 runs, $17.26 of a $20 cap

Trials: `notion-marketplace` and `cursor-blocked-page`, live sites, clean host with a fresh config; output evals
not run (`--no-evals`: this repo's cases are scored by `tools/eval_brief.py`, not `claude plugin eval`).

| Run | Rounds | Bar | Blocking (start → end) | Major | Judge serious | Stop | Cost |
|---|---|---|---|---|---|---|---|
| 1028 | 2, both reverted | 20 → 22 | 3 → 3 | 7 | 5 | stalled | $10.32 |
| 1116 | 1, kept | 22 | 2 → 1 | 7 → 5 | 4 | budget | $6.94 |

The 2026-11-16 baseline on the same tasks had 5 blocking stumbles, 8 major and 6 serious.

Folded back: run 1028's "absence under a cap" point (emit says "none seen in the N scripts read", and brief.md
forbids turning unread code into absence) and its llms.txt finding (bare-URL files parse); run 1116's kept fix
(`robots <url>...`, and plan.md reads robots.txt before any planning probe). Declined: run 1028's proposal to map
any `checkGate(` call to Statsig. That name is generic (Notion's own gate function), so the mapping would
mislabel the vendor.

Not cleared: one blocking stumble remains. The Notion trial reads 60 of 2,841 scripts by role and, on that run,
its brief did not name `checkGate`. The fixed engine's own live read of Notion lists 66 `checkGate` call sites and
the `marketplace_*` gates, so the evidence is reachable under the cap; which 60 scripts are read varies with the
build. Closing it means either ranking named chunks by what they name, or a cap counted in bytes rather than
scripts (8 MB of the 120 MB budget was used). The second changes ADR 0005's budget, so it is not done here.
