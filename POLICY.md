# Policy: what the probe and the product may and may not do

Written before the test, so the test is bound by it.

## Sources

- **Public only.** A page or file that any person could open in a browser without an account. Login pages
  and marketing sites are public; the application behind a login is not. We do not log in, do not reuse
  cookies, and do not use someone's session.
- **No circumvention.** A 403, 429, a Cloudflare or similar challenge page, a robots-style "no automated
  access" response: the probe records `blocked`, asks that host nothing more that run, and moves on. No proxies, no mirrors, no header games beyond
  a normal browser user agent that also identifies the research project.
- **robots.txt is honoured, and read first.** Before any other request to a host, its robots.txt is read; a
  page or script under a `Disallow` for `*` or `unreleased` is never requested, and `Disallow: /` closes the
  host. A `Disallow` prefix is reported as what it is — a published list of pages a company keeps out of
  search. APIs that exist to be queried (certificate logs, public job board APIs) are not crawled pages. Landing pages are opened only when
  the sitemap lists them and robots.txt allows them, three at most, one request each.
- **Hostile platforms are out of scope.** Reddit, X, and anything that has made its position on automated
  access clear are not sources for this product. The sources are the product's own bundles, pages,
  certificate transparency logs, public job boards, public release notes and changelogs.
- **Identity.** Every fetch, including a reader's hand check, uses the project user agent only; no personal
  identifiers (names, emails) go into headers or query strings.
- **Health checks.** `unreleased doctor` makes at most four small requests, one per source, to public
  endpoints that exist to be queried: crt.sh (`%.example.com`), Greenhouse's own public board root, and
  `https://example.com/` for the page fetcher. Nothing else runs without a plan.
- **Politeness.** At most one request per second per host; hard caps on bytes per bundle and bundles per
  product; exponential backoff on 429 and stop; cache everything so repeated runs do not refetch unchanged
  files (ETag / content hash).

## Attribution

- Flags, experiment names and strings count as the product's only when they come from **first-party
  bundles** (served from the product's own hosts or its CDN paths). Third-party SDK code (Google sign-in,
  Intercom, analytics vendors) is recorded separately and never reported as the product's unreleased work.
- Every line in a brief carries the URL of the bundle or page and the byte offset or the exact string, so a
  reader can open it and see it.

## Interpretation

- The engine extracts; the host model interprets; the brief says which is which. A flag name is evidence
  that a flag exists, not that a feature ships. The brief's vocabulary: *present in code*, *newly present
  since <date>*, *removed since <date>*, *referenced in strings*, *announced* (if a public changelog or
  post matches). "Confirmed" is reserved for things a public, dated source states.
- "Could not see" is printed: blocked hosts, bundles over the cap, SDKs whose flags are fetched at runtime
  and so are invisible to a static read.

## Disclosure and use

- This is journalism's method applied by a tool: reading public code. Companies may dislike it. The
  product will credit and link, will not present guesses as announcements, and will honour a request from
  a company to stop including it (recorded publicly).
- Not for: credentials, personal data, private repos, anything behind authentication, or security
  vulnerabilities (if the probe stumbles on one, it is reported to the company, not published).
