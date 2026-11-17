# ADR 0006: salience ranks the brief; the engine does not pick the story

Status: accepted, 2026-10-30.

Context. Figma's first run produced 2,849 "findings" in map order. The readers had judged ~140 of 615
keys nameable. A brief needs product nouns first and plumbing out of the way, but the engine must not
decide what a feature *is* (that is the host's reading, marked as such).

Decision. `salience.score(observation)` is a small integer from word lists (product nouns +2 each,
plumbing −2 each, a human phrase in context +3, an off gate +1, permission scopes / analytics event names
/ the site's own navigation −3 to −5). Score ≥ 2 is a finding; lower goes to the key list, still in
`evidence.jsonl`. `evidence.md` shows at most 150 lines, clustered by the key's first two segments,
deduped by name, best cluster first; flipped and newly present keys get +10/+6 so a second run leads
with change. Word lists are data (`salience.PRODUCT`, `salience.PLUMBING`) and the readers' hand findings
are the test (`tests/test_salience.py`).

Consequences. The engine orders; the host reads. A missing noun in the list costs rank, not presence —
everything is still in `evidence.jsonl` ordered by salience, and the host is told so.
