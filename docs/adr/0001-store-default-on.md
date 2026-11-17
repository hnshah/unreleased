# ADR 0001: the local store is on by default

Status: accepted, 2026-10-30.

Context. last30days keeps its SQLite research store opt-in (`--store`), because it serves watchlists.
The manual test of 39 products showed that the first run's output is a list of names, and the second
run's output ("since last week: 4 gates flipped on, 1 new subdomain") is the thing people post.

Decision. Every run writes to a local SQLite store and a content-addressed blob store under the XDG
data dir by default; `--no-store` skips it. Nothing leaves the machine.

Consequences. Disk use grows with runs (bounded by hashes; identical bodies are stored once). The diff
is available from the second run with no flags. An open commons, if ever added, is a separate opt-in.
