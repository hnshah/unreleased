# Depth and reaction: the hand-offs

`/unreleased` reads public pages without logging in. Three things it does not do, and who does:

- **Logged-in surfaces, runtime flag endpoints, gated UI screenshots.** Hand off to REA (the
  reverse-engineering assistant) with the run folder path: it starts from `evidence.jsonl`, the blob
  store and the plan, and the person's own session. `/unreleased` never uses a session.
- **How people are reacting** to what is already public: `last30days <product>` on the announced items.
- **Mobile and desktop binaries.** Not in v1. Say so.

When the person asks for "more", offer these by name and say what each would add; do not widen the caps
or re-run with different headers.

## The "and" rule

Requests routinely arrive as two questions joined by "and". Answer the one this skill owns, in full. For
the rest, one line the reader can act on, naming who owns it; never a disclaimer at the bottom, and never
a quiet attempt at the other half built on this skill's evidence alone.

| The request also wants | Say to run |
| --- | --- |
| how people are reacting to what is already public | `last30days <product>` |
| the company as a business: positioning, pricing strategy, strengths, customers | LMTY's `competitive-deep-dive` |
| a rep-facing card or objection handling built on these findings | LMTY's `competitive-battlecard` / `competitive-objection-response` |
| a logged-in capture, runtime flags, screenshots of gated UI | REA, with this run folder as the starting point |
| a recurring watch with a digest across products | not yet a skill: run `unreleased` on a cadence and lead with the `## Since` block |
