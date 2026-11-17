# Glossary

Terms used in code, tests, docs and briefs. Use these words exactly.

- **Product**: the thing a run is about, identified by a slug (`figma`) and a domain (`figma.com`).
- **Plan**: the host's resolution of a product into pages, apexes, a job-board slug, a pricing URL and a changelog URL. The engine validates a plan; it never invents one.
- **Run**: one execution of the pipeline on one product, identified by a run id (UTC timestamp). A run leaves a run folder and store rows behind.
- **Artifact**: one fetched body (page or script), stored once by its sha256 in the blob store, with its URL, status and attribution.
- **First-party**: an artifact served by the product's own domain, a listed CDN host, or a host the attribution rules promote by evidence (entry-script host, script-tag majority, favicon host, modulepreload target). Only first-party bodies are read for observations.
- **Observation**: one thing found in a body or a signal: a gate, a config, a catalog entry, a registry entry, an enum value, a route, an inline value, a flag call, a string, a chunk name, a hidden surface, a subdomain, a job, a pricing line, a redirect. Every observation carries a receipt.
- **Receipt**: the URL, sha256 and byte offset of the body an observation came from, plus the exact string.
- **Gate map**: an object literal whose values are mostly booleans (or 0/1): a set of feature gates with values.
- **Catalog**: an array of objects that share a key field and metadata (team, scope, fallback, variants).
- **Registry**: a dense table of constants, `UPPER: "kebab"` pairs or `{name, jira}` entries.
- **Route table**: an object or array mapping paths to labels, groups, flags or page sources.
- **Tier**: how an observation may appear in a brief: `finding` (nameable, with context), `key-list` (real but not headline material), `codename` (a bare name), `redacted` (never printed, counted).
- **Check**: the result of cross-checking an observation against the product's own announcements: `announced`, `partial`, `none`, `unchecked`.
- **Coverage**: per-source outcomes for a run, in the fixed vocabulary (`ok`, `partial`, `blocked-403`, `challenge`, `runtime-only`, `capped`, …), plus caps and attribution decisions. Printed before any finding.
- **Verdict**: the run's one-word summary on the badge: `rich`, `partial`, `could-not-see`.
- **Diff**: what changed between this run and the previous run of the same product: flips (value changes), added, removed, new subdomains, jobs, pricing lines.
- **Brief**: the host's user-facing output, written from `evidence.md` in the certainty vocabulary.
- **Vendor**: a third-party SDK or library whose vocabulary must not be attributed to the product (Sentry, Optimizely, PostHog's own docs, Google sign-in).
- **Salience**: a small integer per observation (`salience.score`): product nouns in the key up, plumbing words, permission scopes, analytics event names and the site's own navigation down, a human phrase in context up. ≥ 2 is a finding; it orders `evidence.md` and `evidence.jsonl`.
- **Cluster**: sibling keys grouped by their first two readable segments (`make_local_*`, `ai_assistant_*`); the brief writes one line per cluster, the engine one web query per cluster.
- **Origin**: the map or table an observation was read out of (`INITIAL_OPTIONS.labmate_data.statsig`, `dynamic_configs`, an identifier table); printed once above the findings, never repeated per line.
- **Scrub**: after a literal is redacted, its text is removed from every other observation's context window too, so a neighbour cannot quote it.
- **Replay**: an offline run over a probe recording (`--recorded <run dir>`, `RecordedFetcher`); a replayed miss is `skipped-unconfigured` and spends no request budget.
