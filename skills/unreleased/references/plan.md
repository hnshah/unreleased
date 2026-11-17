# Plan: resolve a product into pages the engine may read

You are the planner. The engine never guesses which company a name means, and it never searches.

## Fields

```json
{
 "slug": "acme",                         // lowercase letters, digits, dashes; the library key
 "domain": "acme.com",                   // bare hostname
 "pages": ["https://app.acme.com/login", "https://www.acme.com/"],
 "apexes": ["acme.com"],                 // certificate logs are queried per apex (domain + CDN apexes)
 "cdn_hosts": ["acme.com", "static.acme.com"],   // scripts from these hosts are first-party
 "pricing": "https://www.acme.com/pricing/",
 "changelog": "https://www.acme.com/changelog/",   // index page or Atom/RSS feed; optional
 "ats": {"greenhouse": "acme"},          // greenhouse | lever | ashby | workable -> board slug; optional
 "careers": "https://www.acme.com/careers", // read when no board is found: title-looking lines, low confidence; optional
 "docs": "https://manual.acme.com/llms.txt", // docs index, manual home, docs sitemap or llms.txt: what exists today; optional, worth finding
 "notes": "login shell is the marketing bundle; app at app.acme.com"   // free text for the reader; optional
}
```

Only `slug`, `domain` and one https page are required. Everything else widens coverage; leave a field
out rather than invent it (an invented changelog URL costs a 404 line in coverage, nothing worse).

**Finding the URLs is in policy.** First, before any other request to a host you will probe, read its
robots.txt: `unreleased.py robots <url>...` fetches it with the project user agent and prints `allowed` or
`disallowed` for each URL, requesting nothing else. Never probe a disallowed URL; list it in the plan
anyway (the engine does not request it and records it as could-not-see). Then you may open public pages and
send `HEAD` or `GET` requests to candidate URLs (`/login`, `/pricing`, `/changelog`, `app.<domain>`; check
with `robots` first) with the project user agent (`unreleased.py ua`), one per second per host, and read the
home page's links; that is reading public pages, which is what the engine does. You may not log in or follow
a sign-in redirect. Note what you tried in the plan's `notes` field if a reader would wonder.

**Fixing a plan after a run.** When the first run shows the plan missed the app shell (the key list names a
sign-in page you did not plan, or coverage says only marketing chunks were read), fix the plan and run
again with `--no-store`: the engine then writes a run folder but no library row, so the first brief does
not become a "since" brief. Store the run once the plan is right.

## How to resolve

1. **Disambiguate first; retrieve before you ask.** A product name can mean two companies (an issue
   tracker and a bank; a note app and a tv brand). Check the conversation and any attached files first.
   If it is still open, ask one question and offer the inference you would otherwise have made ("Acme the
   issue tracker at acme.app? I'll run that unless you mean another"), then stop. Never run on a guess: a
   finished-looking brief on the wrong company is the worst outcome, because nobody checks the premise.
   When the conversation already makes one reading near-certain (the person's own work, an earlier run, a
   domain they typed), proceed and state the premise in the brief's coverage line ("read as Acme the issue
   tracker at acme.app") so it can be corrected in one word.
2. **Pages.** The app shell is the richest page (a login shell can carry thousands of gates in its
   bootstrap JSON); add the marketing home. Two or three pages is normal; more is rarely better. Check
   which bundle serves the login page: when `/login` is a page on the marketing site (its scripts are the
   same Next.js chunks as the home page), the app's gates are not there — look for the app's own host
   (`app.<domain>`, the host the login form posts to, or the host named in the `modulepreload` tags) and
   put its shell in `pages`. The coverage line will say so when the run read only marketing chunks. When
robots.txt disallows the app (`Disallow: /dashboard`), still list the app page: the engine does not request it,
and coverage then says the app could not be seen and why, so the brief reads "could not see", never "nothing found". A page
   that serves both (a `/login` that loads the marketing chunks and then the app shell) can land either way
   under the script cap from one run to the next; a run that reads the app shell is the better baseline, and
   `--since <that run>` keeps later diffs against it.
3. **Apexes.** The product domain plus any CDN apex you know (`acmestatic.com`-style hosts). The engine
   also promotes a host it sees in `modulepreload` and the majority script host, and reports the decision.
3b. **A domain that redirects** (acme.so to acme.com): plan the pages on the host the redirect lands on,
   list both apexes under `apexes` (certificates are issued to each), and say which one the brief names.
4. **Pricing, changelog, docs.** Use the real URLs when you know them (`/pricing`, `/changelog`,
   `/release-notes`, `/updates`, or a feed such as `/atom`). The changelog is what tells announced from
   not; without it, every finding is `unchecked`. The docs are the third source and the one most often
   missing: a feature the changelog never listed but the manual describes is public. Try
   `<docs host>/llms.txt` first, then the docs sitemap, then the manual's home page; any of the three works.
   An `llms.txt` of a few dozen lines is a table of contents, not the docs: when it lists fewer than about 80
   pages, prefer the docs sitemap (`/docs/sitemap.xml`, `sitemap-docs.xml`) or `llms-full.txt`, so a feature
   that has been public for years is not read as "no public mention found" (one host's lists 28 pages; its docs sitemap, thousands).
   Six of seven of one product's organization settings pages were on its manual and nowhere else.
5. **Job board.** Greenhouse `boards.greenhouse.io/<slug>`, Lever `jobs.lever.co/<slug>`, Ashby
   `jobs.ashbyhq.com/<slug>`, Workable `apply.workable.com/<slug>`. The engine verifies the board belongs
   to the product (own-domain job links, domain in descriptions, software titles) and reports
   `unverified` otherwise; an unverified board's jobs are shown as such. A board slug is the one field you
   may guess (the product's name, lowercased): the engine verifies ownership, so a wrong guess costs one
   `unverified` line, never a wrong claim.

## What the engine does with it

Reads the pages, discovers first-party scripts (webpack and Vite chunk maps included), reads them under
the caps, extracts gates, configs, catalogs, registries, routes, enums, manifests, hidden surfaces and
strings, drops vendor SDK noise, redacts, ranks by salience, cross-checks against the pricing text and
changelog index, diffs against the previous usable run, and writes the run folder.

## Conventional fallback

`run <slug> --domain <domain> --conventional` tries `/login`, `/`, `/pricing`, `/changelog` on the domain.
Use it only when you cannot resolve pages; say in the brief that the plan was conventional.
