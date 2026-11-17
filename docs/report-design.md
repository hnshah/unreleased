# The report: design system

`report.html` is one file, no JavaScript, no external assets, from `scripts/lib/report.py`. This page is the
system behind it: every token, component and rule, with the reason each one is there. The system is codified
from a measured reference page (a campaign brief built on Tailwind defaults with Inter and JetBrains Mono);
the values below are its computed styles, not approximations, so a report reads like a document a team
already knows how to read. A system of your own is a `--theme tokens.css` that overrides the `:root` block;
nothing below the tokens hard-codes a colour or a size.

## Three readers, three layers

Tufte's sixth principle: analytical presentations stand or fall on the quality, relevance and integrity of
their content, so the first design question is what content-reasoning task the display serves (Beautiful
Evidence, "The Fundamental Principles of Analytical Design"). This report has three tasks, for three readers:

| Reader | Task | Layer that serves it |
|---|---|---|
| 30-second | Is there anything here? What is the shape of it? Can I trust the read? | the verdict strip, the shape callout, the source dots |
| 5-minute | What exactly is in the code, what was checked, what does it raise? | the findings as components |
| Verifier | Show me the bytes. What was not read? Who did the work, when, with what? | evidence on demand, coverage grid, receipts, the engine footer |

The layers are stacked in that order and each is complete on its own (Tidwell, Center Stage: the reader's
main task gets the page's centre). Coverage, receipts and the footer sit inside the last card with the same
typography as the findings, not greyed out below a rule, because documentation is content (Tufte's fifth
principle: "undocumented displays are inherently suspect").

## Tokens

All tokens are CSS custom properties on `:root`. Names say what a value is for, never what it looks like, so
a theme can re-value them without touching the layout.

### Canvas and ink

| Token | Value | Used for |
|---|---|---|
| `--canvas` | `#f9fafb` (gray-50) | the page |
| `--surface` | `#ffffff` | cards, the top bar |
| `--panel` | `#f9fafb` | code blocks, evidence lines, coverage cells, number chips |
| `--panel-2` | `#f3f4f6` (gray-100) | inline code |
| `--rule` | `#e5e7eb` (gray-200) | card borders, the top bar's bottom edge, table heads |
| `--rule-2` | `#f3f4f6` (gray-100) | rules between findings and table rows, fold borders |
| `--ink-900` … `--ink-300` | gray-900 `#111827`, 800 `#1f2937`, 700 `#374151`, 600 `#4b5563`, 500 `#6b7280`, 400 `#9ca3af`, 300 `#d1d5db` | headings (900), body (800), secondary (700/600), muted (500), labels (400), separators (300) |

### Status

Colour means status and nothing else (Tufte, The Visual Display: colour is a code, "the number of colours
should be kept small, and each should carry one meaning"). Each hue has a background, an ink, a dot, a text
and a border value, taken from the reference's 50/700/500/600/200 steps.

| Hue | Meaning | Background · ink · dot · text · border |
|---|---|---|
| info (blue) | the author's reading, an aside | `#eff6ff` · `#1e40af` · `#3b82f6` · `#1d4ed8` (badge) |
| ok (green) | ok, nothing in the way, rich | `#ecfdf5` · `#065f46` · `#10b981` · `#059669` · `#a7f3d0` |
| warn (yellow) | partial, capped, medium, rate limited | `#fefce8` · `#a16207` · `#facc15` · `#d97706` · `#fef08a` |
| bad (red) | blocked, challenged, error, could-not-see, low | `#fef2f2` · `#991b1b` · `#f87171` · `#b91c1c` · `#fecaca` |

The hues appear in five places only: the verdict pill, the "in the way" cell, confidence pills, source dots
and the shape callout. High confidence is a neutral outline pill, so the exceptions (medium, low) are what
the eye catches. Blue is reserved for the one block that is the author's reading rather than the engine's
record; it is never a link colour or an accent.

### Type

| Token | Value |
|---|---|
| `--font` | Inter, then the system sans stack |
| `--mono` | JetBrains Mono, then the system mono stack |
| `--size` / `--line` | 16 px / 24 px (the html root; body prose renders at `--sm`) |
| `--sm` / `--sm-line` | 14 px / 20 px: body text, findings, tables, rail links |
| `--xs` / `--xs-line` | 12 px / 16 px: labels, code, receipts, dates, pills |
| `--h1` … `--h3` | 24/32 px 700 gray-900 · 20/28 px 700 gray-900 · 16/24 px 600 gray-800 |
| `--label-tracking` | `.05em`, with uppercase and 600 weight, gray-400 |
| `--measure` | `66ch` for continuous prose (Bringhurst 2.1.2); tables, callouts and code run wider |

Fonts are the first entry in a system stack and never `@import`ed, so the file stays self-contained and
renders without them. Tabular numerals are on (`tnum`) so counts align.

### Space and shape

| Token | Value |
|---|---|
| `--page-max` | 1280 px (max-w-7xl) |
| `--gutter` | 24 px |
| `--rail` | 224 px (w-56), sticky at 64 px |
| `--card-pad` / `--card-gap` | 32 px / 32 px |
| `--radius-card` / `--radius` / `--radius-s` | 12 px / 8 px / 6 px (cards · callouts, folds, code blocks · chips, pills, evidence lines) |

Vertical space moves in multiples of 4 px, mostly 8 (Bringhurst 2.2.2: add and delete vertical space in
measured intervals).

## Components

| Component | Spec | Rule |
|---|---|---|
| Top bar | sticky, white, 1 px gray-200 bottom; inner `max-w-7xl` 12/24 px; product 600 gray-900 · "·" gray-300 · document name 14 px gray-500 · date 14 px 500 gray-700; right: engine and run id 12 px gray-400, verdict pill | the verdict is visible wherever the reader is; on phones only product, date and pill remain |
| Pill | 12 px 500, 4/8 px padding, full radius, 1 px border; neutral by default, tinted by status | one word; never a sentence |
| Rail | 224 px, sticky; "Contents" label; links 14 px gray-500, 4 px vertical padding, gray-900 on hover; sub-links 12 px gray-400 indented 12 px | hidden below 860 px and in print |
| Card | white, 1 px gray-200, 12 px radius, 32 px padding, 32 px gap, `scroll-margin-top` 24 px | one card per layer; never cards inside cards |
| Title | h1: the domain in gray-900, the question in gray-500 400 | names the domain and the question first |
| Verdict strip | key/value grid, `auto-fit minmax(180px)`, 16/24 px gaps, 1 px gray-100 top rule; keys are labels, values 14 px gray-800; the count is 24 px 700 | numbers before words; the "in the way" value takes the status text colour |
| Shape callout | `.callout.info`: blue-50, 8 px radius, 16 px padding, 14 px blue-800; label in blue-700 | the only tinted block on the page; labelled "the author's reading" |
| Read line | 14 px gray-500 after the callout | prose comes after the numbers and the reading |
| Group heading | h3, 16 px 600 gray-800, 1 px gray-100 rule beneath | only with more than six findings |
| Finding | 40 px number chip (mono 12 px, gray-50 on gray-200, 6 px radius) · noun 16 px 600 gray-900 · confidence pill; fact 14 px gray-800; "Checked" and "Raises" as label + text rows in gray-500 / gray-700; evidence fold | three beats, three rows; rules between items, not boxes |
| Fold (`details`) | 1 px gray-100, 8 px radius; summary 16 px padding, 14 px 500 gray-700, chevron ▾ on the right that turns when open; native marker hidden | the verifier's layer is one click away and never in the way |
| Evidence line | mono 12 px gray-700 on gray-50, 1 px gray-200, 6 px radius; key in gray-900 600, match highlighted in yellow-200, receipt as gray-400 meta | the engine's context line verbatim, never reworded |
| Coverage grid | `auto-fill minmax(200px)` cells on gray-50, 8 px radius; dot · source in 600 · state in gray-500 · detail | one cell per source; pages collapse into one |
| Table | 14 px; th 12 px 700 gray-400 with a gray-200 rule; td 8 px vertical padding, gray-100 rules; mono cells 12 px gray-600 | the ranked evidence table is folded by default |
| Since chips | 14 px on gray-50, 6 px radius, bold counts | all-zero is one line, not eight zeros |
| Receipts, boilerplate, footer | 12 px gray-500; the footer in a code block | text, never local links |

The brief is parsed, not styled by guesswork: `references/brief.md` defines the forms (`N. **Noun** · high`,
a `Raises:` line, bold-led blocks, a Receipts block, the fenced footer) and `report.parse_brief` turns them
into these components. A line the grammar does not recognise renders as plain Markdown; nothing is dropped.

## Copy

The renderer guarantees sentence case: `report.sentence_case` capitalises the first letter of every sentence
in prose nodes (paragraphs, list items, facts, Checked and Raises rows, the shape, the blocks), leaving code
spans, urls and paths, names with their own capitals (iOS, macOS, iCloud), known lowercase names (npm,
robots.txt, llms.txt) and the word after an abbreviation or a version number untouched. The badge line,
receipts, footnote lines, table cells and the engine footer are not prose and are not touched. The brief
contract carries the rest of the copy rules (`references/brief.md`, "Copy rules") and the eval enforces
them: no em or en dashes outside a verbatim string, one fixed form for Checked, names as their owners write
them. The product slug in the badge and footer is the engine's identifier and stays lowercase.

## Charts

None, by default. Berinato's two questions (conceptual or data-driven; declarative or exploratory) put this
report in the declarative, data-driven quadrant, but the data is counts of a handful of things, and a count
reads faster as a number than as a bar. A sparkline of findings per run belongs in a hosted history, not in a
one-run file (Tufte, Beautiful Evidence, "Sparklines": they need a series).

## Print and small screens

Print: the rail and top bar go, cards lose their borders, folds open, links lose their underline, 11 pt.
Phone (below 860 px): one column, the rail hidden, the top bar reduced to product, date and pill, 20 px card
padding. Both are checked by screenshot before a release (`tests/test_report.py` checks structure; the
screenshots are a release step).

## Theming

```css
/* tokens.css, passed with `report --theme tokens.css` */
:root { --font: "Söhne", ui-sans-serif, sans-serif; --info-bg: #f0fdfa; --info-ink: #115e59; --info-badge: #0f766e; --radius-card: 8px; }
```

A theme may change any token. It cannot change the layers, the components or the grammar: those are the
contract, and they are the same in `report.md`.
