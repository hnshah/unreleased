# unreleased

**What is Linear building that it hasn't announced?** Ask, and get this back in about ninety seconds,
from nothing but public pages:

> **Agents on pull requests** · high
> `pull-request-agent-selector` "Choose an agent to resolve pull request checks, conflicts, and review comments",
> `pull-request-check-summaries` "Generate AI summaries for pull request check logs", `PullRequestAgentSuggestions`.
> Checked: pricing page, docs index (180 pages), changelog since 2026-07-23, one web query; nothing.
> Raises: Whether a pull request gets an assigned agent the way an issue gets an assignee.
>
> **Usage alerts and spend limits** · high
> `/:orgKey/inbox/usage-alert/:usageAlertId`, `UsageLimitLabels`, `usageLimitSpendQuery`. The `usageLimit` enum is
> announced in the docs; the alert route and the spend query are not. Checked: the same; nothing.
> Raises: Whether usage alerts reach the inbox before a spend cap is a setting a reader can find.

More like that in [`docs/examples/linear-brief.md`](docs/examples/linear-brief.md), each with a receipt into
the exact script and byte offset, written by a fresh host from nothing but the skill;
[`vercel-brief.md`](docs/examples/vercel-brief.md) is a second one (AI Gateway private inference, agent code
review with auto-merge, 130 unlinked compare pages), and [`vercel-report.html`](docs/examples/vercel-report.html)
is that brief rendered as a shareable file.

`/unreleased <product>` reads what is already public — feature flags and experiment names in the
product's JavaScript, strings for UI that doesn't exist yet, new subdomains in certificate logs, job posts,
the pricing page, the docs, robots.txt and the sitemap — and writes a dated brief in a fixed certainty vocabulary:
*present in code*, *flipped on since*, *announced <date>*, *no public mention found*, *could not see*.
Keyless. Python 3.11+, standard library only. MIT.

**What it is not.** It reads code; it does not log in, does not go around a 403 or a challenge page, does
not crawl what robots.txt disallows, and does not guess motives. About half of SaaS products are readable
this way (20 of the 39 in the design corpus); the rest get an honest *partial* or *could not see* that says
exactly what was in the way — a flag SDK whose values live at runtime, a blocked page — rather than a
thinner brief dressed up as a full one.

## How it works

The host model plans (which pages, apexes, job board, pricing and changelog URLs); the engine reads
those public pages, the product's own scripts under fixed caps, and the site's own published lists —
robots.txt (the paid landing pages a company keeps out of search), the sitemap (a compare or `-vs-` page
listed before any page links to it is next quarter's campaign) and the headline shared across its landing
pages — extracts eleven code shapes (gate
maps, inline bootstraps, call sites, catalogs, registries, protobuf descriptors, enums, routes, chunk
manifests, hidden surfaces, strings), drops vendor SDK noise, redacts keys, ids, customer-named gates and
company-named hosts, ranks what is left by salience and novelty, cross-checks it against the same-run
pricing text, changelog and docs index, diffs against the previous run, and writes a run folder:

```
manifest.json  coverage.json  evidence.jsonl  checks.jsonl  signals.json  diff.json  redactions.log  web_queries.json  evidence.md
```

`evidence.md` is addressed to the host, which writes the brief in a fixed certainty vocabulary
(*present in code*, *newly present since*, *flipped*, *announced <date> <url>*, *no public mention found*,
*could not see*). Every run also lands in a local SQLite library, so the second run on a product opens with
"since <date>". `docs/examples/` holds two worked briefs (Linear and Vercel, live) and their rendered reports.

## Install

In Claude Code, one line:

```
/plugin install unreleased --marketplace hnshah/unreleased
```

Anywhere else that supports Agent Skills (Codex, Cursor, Gemini CLI, Copilot and the rest):

```bash
npx skills add hnshah/unreleased
```

Then ask: "what is Linear building?" — or run the engine yourself:

```bash
python3 skills/unreleased/scripts/unreleased.py run figma --plan plan.json        # see skills/unreleased/references/plan.md for the plan
python3 skills/unreleased/scripts/unreleased.py diff figma
python3 skills/unreleased/scripts/unreleased.py library "ai gateway"
python3 skills/unreleased/scripts/unreleased.py report vercel --brief brief.md   # report.html + report.md, shareable
python3 skills/unreleased/scripts/unreleased.py doctor
```

Ask for "a file I can share" and the host writes the brief to a file and the engine renders it: one
self-contained HTML (no JavaScript, no external assets, light and dark, prints) with the brief verbatim
and the engine's appendix — since-last-run, campaign signals, the ranked findings with receipts, coverage —
plus the same as Markdown. Design tokens are CSS custom properties at the top of the file; `--theme
tokens.css` applies a design system. `docs/examples/linear-report.html` and `.md` are a rendered pair.

## Numbers (2026-11-06, offline replay of the 39-product corpus)

20 of 39 products rich (the rest honest partials: a 403, a challenge page, or a flag SDK whose values
live at runtime), golden recall 0.98 against the readers' hand findings, noise 0.0% of finding lines, zero
redaction leaks. Live: Linear 104 s (rich, 12.8 MB app shell), Vercel 78 s (rich).

The corpus is copies of other companies' bundles, so it is not published; the goldens (`tests/goldens/`) and
the scorer are. Record a corpus of your own and score it the same way:

```bash
python3 skills/unreleased/scripts/unreleased.py run figma --plan figma.json --record corpus   # once per product
python3 tools/run_corpus.py --corpus corpus                                                  # recall, noise, leaks, verdicts
```

## Layout

```
.claude-plugin/          plugin + marketplace manifests (install with one line in Claude Code)
skills/unreleased/       the skill — what any Agent Skills client loads
  SKILL.md               the host contract (6 KB, eight laws, a routing table)
  references/            runtime · plan · brief · could-not-see · diff · deep (18 KB of a 40 KB budget)
  scripts/unreleased.py  the CLI: run · diff · compare · report · library · doctor · setup
  scripts/lib/           schema · plan · fetch · scanner · discover · attribute · noise · salience · redact · crosscheck · store · diff · pipeline · emit · report
  scripts/lib/extractors/  one code shape per module
  scripts/lib/sources/   crt · ats (Greenhouse, Lever, Ashby, Workable) · pricing · changelog · site (robots, sitemap, landing pages)
  scripts/lib/vendors/   SDK fingerprints, one file each
tests/                   unit, source, end-to-end pipeline, record/replay and skill-contract tests; fixtures are excerpts of public bundles with provenance; goldens are the readers' findings
tools/                   validate_pack · package_release · golden · make_fixture · run_corpus (the benchmark) · budget · eval_brief
evals/                   host-contract cases
docs/adr, docs/solutions, docs/examples
```

## Policy, in one line

Public pages only, no logins, no circumvention, one polite request per second per host with an
identifying user agent, first-party attribution, every line linked to the bytes it came from, companies
can ask to be excluded. Full text: [POLICY.md](POLICY.md). Security reports: [SECURITY.md](SECURITY.md).

MIT. Test fixtures are short excerpts of other companies' public pages; see [NOTICE](NOTICE).
