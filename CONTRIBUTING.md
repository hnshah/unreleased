# Contributing

The engine grows one adapter at a time, the way last30days grew by sources and REA by targets.

- **One PR = one adapter**: a `sources/<name>.py` (a public signal), an `extractors/<name>.py` (a code
  shape), or a `vendors/<name>.json` (an SDK fingerprint). Each ships a fixture under `tests/fixtures/`
  (a saved response or an excerpt of a public bundle, with its sha256 and URL) and a golden output.
- Adapters follow one signature: sources `fetch(plan, fetcher) -> (list[Record], list[SourceOutcome])` (an outcome per apex/board/page; a failed source is a recorded outcome, never a crash) and
  `health(fetcher) -> SourceOutcome`; extractors `extract(body, artifact) -> list[Observation]`.
- The policy layer (`fetch.py`, `POLICY.md`, redaction rules) changes only with a maintainer's review.
- No new network endpoints without a line in `POLICY.md` saying why it is public and polite.
- No keys, no telemetry, no update checks over the network.
- Instruction budgets are enforced in CI: `SKILL.md` ≤ 6 KB; `references/` ≤ 40 KB in total.
- Before changing a module, read its learnings under `docs/solutions/` (one file per non-obvious problem
  solved, with the failing input and the smallest fix); add one when you fix something whose reasoning the
  code alone would not show. Decisions with alternatives go to `docs/adr/`.
- Tests pin expected values from an independent source (the readers' hand findings, a golden verified
  against the corpus bytes), never from the implementation's own output. `tools/golden.py check` and
  `tools/run_corpus.py` are the levers; a change that moves the scorecard goes with its before/after.
