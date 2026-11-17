# ADR 0007: a read cut short is partial; a cap is still a budget

Status: accepted, 2026-11-17. Extends ADR 0005; does not reverse it.

Context. The perfecting loop's live trial (2026-11-16) found a `rich: every source read` badge over a Notion run
that read 52 of 2,836 listed scripts. Two causes. The chunk URL builder assumed `name.hash.js` where Notion's
runtime writes `name-hash.js`, so every chunk answered 404; and the SM-8 guard then stopped *all* chunk reads
after eight 404s and recorded it as `capped`, which ADR 0005 says never changes the verdict. Separately, Cursor's
app paths sit under a robots.txt `Disallow`; the policy says they are never requested, and the run dropped them
without a word, so a gated app read as "nothing found".

Decision.
- The budget cap stays a budget (ADR 0005). `rich` under a cap says so: "rich: every source answered; under the
  budget cap: scripts read N of M enumerated". Only an uncapped run says "every source read".
- A chunk map whose chunks answer 404 eight times in a row stops only that map's chunks, and is recorded as
  `chunks: partial`, not `capped`. `partial` on first-party code (script, scripts, chunks) makes the run
  partial: the code was listed and could not be read, for a reason other than budget. `partial` on a
  second signal (an unverified job board) does not.
- robots.txt is honoured as POLICY.md says (decided again, 2026-11-17). A disallowed app
  route or planned page is listed as "could not see … not checked: the site's robots.txt asks crawlers to stay
  out", never counted as read or clean; a planned page it keeps out makes the run partial.
- One function, `schema.partial_sources`, holds the rule for both the engine and the report.

Consequences. Runs whose only gap is the cap stay `rich`, with honest words. A dead chunk map or a
robots-closed app shows up as `partial` with the reason named.
