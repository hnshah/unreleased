# Shareable report (HTML and Markdown)

Read after every brief: render it once, every run, and give the paths in one line (SKILL.md's routing row and
self-check item 7). Read it again when the person asks for a file they can share ("give me this as HTML", "a doc
for the team", "something I can paste into a wiki or print") or for an export of a brief already written. The
engine renders; you supply the prose. Never re-run the engine to render; never hand-write HTML.

## How

1. Write the brief exactly as you delivered it (badge line through the fenced footer) to a file. Same text,
   same order, nothing added. Overwrite the file on a rerun; do not keep versions.
2. Render from the run folder the brief came from (the footer names its run id):

```bash
python3 "$SKILL_DIR/scripts/unreleased.py" report <slug> --brief brief.md            # last run of <slug>
python3 "$SKILL_DIR/scripts/unreleased.py" report --run-dir <run folder> --brief brief.md
```

   Output is JSON with the absolute paths of `report.html` and `report.md`, written beside the brief by
   default (`--out`, `--md` to choose), where a person will look for them. `--theme tokens.css` applies a design system: a file of `:root { --bg: …; --font: …; }`
   overrides, nothing else.
3. Hand over the absolute path(s) in one line and say what the file holds: the brief as written, then an
   appendix the engine adds (since-last-run, campaign signals, the ranked findings table with receipts,
   coverage, the footer). Do not paste the HTML, and do not paste the
   brief again if it is already in the reply.

## What the file is

One self-contained HTML file: no JavaScript, no web fonts, no external assets; light and dark follow the
reader's system; prints cleanly. Three layers: a verdict strip and the shape paragraph for a thirty-second
read; the findings as components (number · noun · confidence · fact · raises); and, for whoever checks,
the engine's own context line folded under every key a finding names, the coverage grid, the receipts and
the footer. The brief is parsed by the forms in `brief.md` (`N. **Noun** · high`, a `Raises:` line, bold-led
blocks, the Receipts block, the fenced footer) — keep them exact and the file renders as components; a line
off the grammar renders as plain text, never dropped. Every design decision is a CSS custom property at the
top of the file (`docs/report-design.md` is the system). `report.md` is the same content as Markdown.

`report` without `--run-dir` renders against the run the brief's footer names; a brief rendered against a
different run carries a note saying so.

Without `--brief` the engine writes an *evidence report* — its ranked evidence with a line saying no brief
was written — never a synthesis. A report is only as good as the brief; write the brief first (`brief.md`).

## The grammar the renderer reads

`N. **Noun** · high` opens an item; its indented lines are the fact, a `Checked:` line and a `Raises:` line.
A one-line label in italics (`*Members*`) or bold (`**Members**`) directly above numbered items is a group
header; use groups only with more than six items. A bold-led line that is not followed by items
(`**Partially announced** (1): …`) is a block and renders under its label without item components, so a
partially announced item that deserves fact / checked / raises belongs in the numbered list instead, with
its public part in the fact.

## Never

- Upload or publish anywhere unless asked; a file on disk is the deliverable.
- Add warnings, debug notes or engine health to the shareable file; those belong in the reply.
- Rephrase the brief for the file. The eval checks the file against the run's receipts the same way.
