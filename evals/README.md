# Evals

`evals.json` holds host-level questions drawn from the manual test's demo briefs,
each with the run folder to answer from and the facts a correct brief must state in the certainty vocabulary.
`tools/run_corpus.py` is the engine-level benchmark (recall, noise, leaks, verdicts over the 39-product corpus);
this folder is for the host contract: given `evidence.md`, does the brief come out right?

How to score: run the engine offline on the named corpus run, give the host `SKILL.md` + the run folder, save
the brief, and run `python3 tools/eval_brief.py <case-id> <brief.md>` (the badge verdict against the case's
`verdict`; phrases as whole words in the host's own prose, never in the footer, the boilerplate or
inside an identifier (`AGENTS_WAITLIST` is not "waitlist"); plurals count;
forbidden words; a real `sha256:<12 hex>@<offset>` receipt; badge first, footer last). `docs/examples/linear-brief.md` and `vercel-brief.md` pass their cases in CI. A brief fails on any
forbidden word (`confirmed`, `launching`, `will ship` outside the boilerplate), a missing receipt, or a finding
whose check status was `announced`.
