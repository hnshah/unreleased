---
title: "Scanner: an unterminated quote in a capped bundle rescans to EOF from every later quote"
module: scanner
date: 2026-10-30
problem_type: performance_issue
component: service_layer
severity: high
symptoms:
  - "one PostHog bundle (8 MB, cut by the byte cap inside JSON.parse('…')) took 62 s to tokenize; the product's run took 391 s"
  - "time grew super-linearly with the length of the tail after the cut"
root_cause: logic_error
resolution_type: code_fix
tags: [scanner, regex, minified-js, caps]
---

# Scanner: an unterminated quote rescans to EOF from every later quote

## Problem

`iter_literals` tokenized with one `finditer` over `"…"|'…'|`…`|[{}[\]]`. When a bundle is cut by the
8 MB cap inside a string (PostHog's `JSON.parse('…')` skill catalog, 2,696 `\'` escapes in the tail), the
`'` at the cut has no closing quote. The engine scans to end-of-input, fails, advances one character, and
at the next `'` scans to end-of-input again: O(quotes × tail). Time grew with the
number of quotes in the tail.

## Solution

`scanner._tokens` is a manual loop: find the next interesting character, try the string pattern for that
quote kind; on failure, mark that quote kind dead up to the next newline (or EOF for backticks), so later
quotes of that kind are plain characters. One rescan per kind per line instead of one per quote.
Regex literals (`/'/`) and comments (`/*! don't */`) are consumed whole for the same reason: a quote inside
them must not open a string phase (Dropbox had 70 of 295 enum descriptors hidden that way).

Side effect worth knowing: the text after a dead quote is scanned as code, so a cut `JSON.parse('…')`
payload yields its objects — which is the data we wanted.

## Prevention

`tests/test_scanner.py::Phase` pins both behaviours with synthetic bodies; any tokenizer change must keep
them green. Time a scan of the corpus's largest bodies (`tools/run_corpus.py` prints seconds) before
merging scanner changes.
