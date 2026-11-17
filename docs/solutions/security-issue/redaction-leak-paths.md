---
title: "Redaction: every field of every observation is an output path, not only the one you removed"
module: redact
date: 2026-10-30
problem_type: security_issue
component: service_layer
severity: critical
symptoms:
  - "a live key next to a checkGate() call reached evidence.md through the call's context window"
  - "the name of a removed customer gate was quoted in its neighbour's context and printed in redactions.log"
  - "an id list's value was gone, but its key (the customer's name) was in the log"
root_cause: missing_validation
resolution_type: code_fix
tags: [redaction, R10, contexts, logs, sqlite]
---

# Redaction: every field of every observation is an output path

## Problem

`redact.redact` removed the observation that *was* the secret (a config whose value matched `sk_live_…`)
and demoted A/B arms. Three other paths carried the same bytes out:

1. **Context windows.** Calls, routes, hidden and strings copy up to 200 bytes of raw code into
   `context`; a secret within 200 bytes of any key reached `evidence.md`, `evidence.jsonl`, SQLite
   (`observations.context`) and the FTS'd brief. The scrub applied only to `config`/`inline`.
2. **Neighbours quoting a removed name.** Notion: `checkGate({gateName:"ai_image_generation"}),…
   checkGate({gateName:"alices_specials"})` — `alices_specials` was removed, then printed inside
   `ai_image_generation`'s context.
3. **The log.** `redacted gate alices_specials: customer-specific gate` is the customer's name in a file the
   run folder ships; `redacted config acmeOrgs: org/customer identifiers` likewise.

## Solution

- Scrub is a pass over **every kept observation**: `_SECRET_SPAN` (prefix + the whole token) replaced in
  `context` and in string `value`s; every removed literal (secret values, id values, customer-gate names)
  replaced in every other context.
- The log names a removed customer or org key by `<sha1(key)[:8]>` and the reason, never the key.
- `tests/test_pipeline.py::test_first_run_is_rich_ranked_and_leak_free` reads back **every file** the run
  folder writes and asserts the token (and its suffix) and the customer name are in none of them;
  `tools/run_corpus.py` checks the goldens' `redact` list against every tier, context and value.

## Prevention

When you add a field that carries bytes from a body (a new `context`, a `snippet`, a `label`), add it to the
scrub pass and to the end-to-end leak assertion in the same commit. Treat `redactions.log`, `signals.json`
and `web_queries.json` as output too: the question for each is "could this line carry a customer's name or
a token?", not "is it the main brief?".
