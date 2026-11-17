# The could-not-see brief

The verdict is `could-not-see` when no first-party code was read (no bytes, or pages only with nothing in
them), and `partial` when a page answered 403 or a challenge, a flag SDK's values live at runtime with no
inline bootstrap, a source errored, a chunk map named code that was not served, or robots.txt keeps the
planned app page out (never requested: say "could not see; the site's robots.txt asks crawlers to stay out of
`/dashboard`", not a 403 and not "nothing found"). Both are results. Neither is a reason to retry, change user agents, use a proxy, a
mirror, a cache, or the person's own session. The policy forbids it and the engine does not do it.

## Write it like this

1. Badge line verbatim, then the blocker in one sentence ("app.acme.com/login answered 403 to a plain fetch;
   the app shell was not read"), then the coverage facts as in every brief. The blocker sentence is the one
   addition; LAW 2's order otherwise holds. If you are running inside an agent host whose own network policy
   may answer 403, say "to a plain fetch from this environment" — the engine cannot tell an origin 403 from an
   egress 403 — and suggest the person's own machine.
2. What was still read, with its findings: certificate logs and the pricing page usually survive; job
   boards almost always do. These are real signals; give them the full treatment. The engine's `no-results`
   on the job board means "no board resolved at the slugs tried", not "could not see" and not "not hiring";
   say which slugs were tried (the coverage line lists them).
3. What the person's own browser would see: "The flags live in the login page's bootstrap JSON; a
   browser session would show them. `/unreleased` does not log in."
4. Offer depth: the REA hand-off (`deep.md`) for a logged-in capture, and `last30days <product>` for how
   people are reacting to what is already public.
5. Footer as usual. For the `could-not-see` verdict only (nothing read), the boilerplate paragraph has its own
   form; a `partial` run keeps the standard paragraph and adds the blocker sentence:

   > Nothing here comes from the product's code, because none was read. A blocked page is a fact about this
   > run, not about the product. What was read above is public and dated; the rest is marked could not see.

Dates on the badge and footer are the engine's, in UTC; keep them as printed even when your local day differs.

## Runtime-only SDKs

"could not see: Statsig present; flags fetched at runtime, not read" means the gate names are not in
the static bundle. Do not call the vendor's endpoint. Say it plainly and move on to the other signals.
