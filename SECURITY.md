# Security

`unreleased` reads public pages only and never logs in, so there is no account surface. What can go wrong is
ours to fix fast:

- **A redaction gap** — a key, org or customer id, customer-named gate or company-named host reaching a run
  folder, `evidence.md` or the SQLite library. Report it privately (see below) with the product and the run
  id; do not open a public issue with the literal in it.
- **A fetch that is not polite** — more than one request per second per host, a retry after a 403 or a
  challenge page, a request under a robots.txt `Disallow`, anything that reads a page the policy says we do
  not read. Same route.
- **A vulnerability in the engine** (a crafted bundle that crashes or hangs a run, a path escape in the run
  folder writer).

Report through GitHub's private vulnerability reporting on this repository:
<https://github.com/hnshah/unreleased/security/advisories/new>. We acknowledge within three days and fix
redaction gaps before anything else.

If the engine ever stumbles on a credential or a vulnerability in a product it reads, that is reported to
the product's company, not published (POLICY.md).
