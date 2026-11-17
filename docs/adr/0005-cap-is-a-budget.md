# ADR 0005: a hit cap is a budget note, not a partial verdict

Status: accepted, 2026-10-30.

Context. The script cap (60 scripts, 120 MB) exists so a run ends in a minute. Sentry enumerates 1,888
lazy chunks and Linear 440; reading them all is neither possible under the cap nor the design (chunks are
read by role: entry, named, rest). With `capped` counted as a failure, 31 of 39 corpus products were
"partial" and the verdict stopped meaning anything.

Decision. `Coverage.verdict()` is `could-not-see` when no first-party code was read, `partial` when
something that should have been readable was not (`blocked-403`, `challenge`, `runtime-only`, `error`,
`unreachable`, `timeout`, `rate-limited`), else `rich`. `capped` is reported in coverage as "read N of M
enumerated" and never changes the verdict. Replayed misses (`skipped-unconfigured`) spend no request budget.

Consequences. 20 of 39 corpus products are rich; the 16 partials each name a blocker a reader can act on.
A host must still print the cap line (LAW 2), so a reader knows 60 of 440 were read.
