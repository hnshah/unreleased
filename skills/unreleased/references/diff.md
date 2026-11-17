# Second runs: lead with since

When `diff.json` exists, the brief opens, after coverage, with:

```
Since <previous run date> (<n> days): 4 flags flipped on, 2 routes added, 1 new subdomain, pricing
unchanged, jobs +3 −1.
```

"Since this morning" means the run the person last read, which may not be the previous usable run: pass
`--since <run id>` (the id is in that brief's footer) and the diff is against that run. Run ids are UTC
timestamps; "<n> days" may be 0.

On a quiet run, after the one-line lead, give the standing top findings (5–12) as what is still present,
not as news; say that is what they are.

**Quiet is allowed.** When the diff is empty, lead with that one line — "Nothing material moved since
<date>: no flips, no new keys, no new hosts, pricing unchanged" — and keep the findings list short. A run
that finds nothing new is a valid answer, not a failure to be padded.

Then, before the findings list:

- **Flipped off → on** are the strongest launch signals the engine produces; name each with its receipt
  and check the changelog since the previous run for an announcement (LAW 6).
- **Newly present** keys and routes: "newly present since <date>".
- **Removed since** keys: a feature shipped and its gate was deleted, or the experiment ended. Say which
  you cannot tell.
- **New subdomains** by stem and environment (`*-staging`, `preview-*`).
- **Pricing lines** `+`/`-`: quote them.

`previous usable run` skips could-not-see runs and runs with a blocked or challenged page, and an empty
read never produces a diff of its own; when this run read far fewer bytes than the baseline, `removed` is
withheld and the diff carries a `note` saying so (absence under a smaller read is not removal). The
engine records `first_seen` per key across all runs; "first seen <date>" on a line comes from that.

`compare <run_a> <run_b>` diffs any two run folders offline when the person asks about a specific pair.
