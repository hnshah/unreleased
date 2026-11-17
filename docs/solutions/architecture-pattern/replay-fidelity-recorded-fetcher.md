---
title: "Offline replay must not be starved by budgets that only exist for the network"
module: pipeline
date: 2026-10-30
problem_type: architecture_pattern
component: testing_framework
severity: medium
tags: [benchmark, recorded-fetcher, caps, corpus]
---

# Offline replay must not be starved by budgets that only exist for the network

## Context

`tools/run_corpus.py` replays the 39-product corpus through the real pipeline with `RecordedFetcher`. Two
things made the replay disagree with the extractors' own recall on the same bodies:

- The probe that built the corpus resolved relative script URLs against the page URL it asked for;
  the pipeline resolves against the final (redirected) URL. `www.notion.so/login` became
  `app.notion.com/login`, so every chunk URL hashed to a file that did not exist. Notion read 1.4 of 7.3 MB.
- The pipeline enumerates every chunk a bundle names (Supabase 1,047; Notion 2,728), and the request
  budget (3 × the script cap) ran out on URLs the recording never had before reaching the 40 it did.

## Guidance

- A replayed miss is not a request: `RecordedFetcher` answers `skipped-unconfigured`, and the pipeline
  spends no request budget on that state. Live 404s still cost a request.
- `RecordedFetcher` maps a redirect host back to the probe's original host (`host_alias`) when resolving
  a URL, so the pipeline's correct resolution still finds the probe's file.
- When the benchmark and a unit test disagree about the same body, suspect the fetch layer before the
  extractor: run the extractor directly on the raw file (`extractors.extract_all(body, src)`), then trace
  through `noise.assign_tiers` and `redact.redact` one stage at a time. That order found all four
  recall bugs on 2026-10-30 in minutes each.

## Applicability

Any lever that replays recorded fixtures through code written for the network. Budgets, retries and
redirects are the three places the two worlds differ.
