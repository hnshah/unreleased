# ADR 0004: coverage states are last30days' RunOutcomeState plus four

Status: accepted, 2026-10-30.

Context. Every research skill invents its own coverage words; a survey of
research skills named a shared run-outcome vocabulary as a missing precursor and recommended lifting
last30days' rather than inventing another.

Decision. `schema.RunOutcomeState` is last30days' eleven states verbatim (`ok`, `no-results`, `partial`,
`rate-limited`, `auth-failed`, `payment-required`, `unreachable`, `timeout`, `schema-drift`,
`skipped-unconfigured`, `error`) plus `blocked-403`, `challenge`, `runtime-only`, `capped`.

Consequences. A host that already reads last30days' coverage reads ours; the four additions are the only
new words.
