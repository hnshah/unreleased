#!/usr/bin/env python3
"""Score a host-written brief against an evals.json case (the host contract, not the engine).

  python3 tools/eval_brief.py <case-id> <brief.md> [--run <run folder>]

With --run, every `sha256:<prefix>@<offset>` in the brief must name a blob and offset that exist in that run's
evidence.jsonl: a host that retypes a receipt gets caught here, not by a reader.

Checks: the badge's verdict equals the case's `verdict`, and no coverage line claims another; every must_state
phrase present as whole words in the host's own prose (case-insensitive, whitespace-normalised; fenced blocks and the
fixed boilerplate paragraph do not count, so "partial" is not satisfied by `ats: partial` or a footer); no
must_not_state phrase; no forbidden word outside the boilerplate's "not that it will ship"; at least one real
receipt `sha256:<12 hex>@<offset>`; the badge line first; the fenced footer last. Exit 0 pass, 1 fail, with the reasons.
"""
from __future__ import annotations
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN = re.compile(r"\b(confirmed|launching|will ship)\b", re.I)
RECEIPT = re.compile(r"sha256:[0-9a-f]{12}@\d+")
VERDICTS = ("rich", "partial", "could-not-see")
BOILERPLATE = ("These are strings present in public code", "Nothing here comes from the product's code")   # brief.md, could-not-see.md


def prose_of(body: str) -> str:
    """What the host wrote in its own words: no fenced blocks (the engine's footer) and no fixed boilerplate paragraph."""
    paras = re.split(r"\n\s*\n", re.sub(r"```.*?```", " ", body, flags=re.S))
    return "\n\n".join(p for p in paras if not p.lstrip("> ").startswith(BOILERPLATE))


def has_phrase(phrase: str, text: str) -> bool:
    """Whole words: `partial` is not `partially` or `ats_partial`; a plural counts (`jobs`, `403s`), and a phrase that
    starts or ends with punctuation (`/dashboard`) needs no boundary on that side (`cursor.com/dashboard`)."""
    p = norm(phrase)
    left = r"(?<![\w-])" if re.match(r"\w", p) else ""
    right = r"(?:e?s)?(?![\w-])" if re.search(r"\w$", p) else ""
    return re.search(left + re.escape(p) + right, text) is not None


def badge_verdict(first_line: str) -> str | None:
    fields = [f.strip() for f in first_line.split("·")]
    return next((f for f in fields if f in VERDICTS), None)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


def main() -> int:
    case_id, path = sys.argv[1], sys.argv[2]
    run = sys.argv[sys.argv.index("--run") + 1] if "--run" in sys.argv else None
    cases = {c["id"]: c for c in json.load(open(os.path.join(ROOT, "evals", "evals.json"), encoding="utf-8"))["cases"]}
    c = cases[case_id]
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    body = raw.split("---", 2)[-1] if raw.startswith("#") and "\n---\n" in raw else raw   # skip a doc preamble
    b = norm(body)
    fails = []
    lines = [l for l in body.strip().splitlines() if l.strip()]
    want = c.get("verdict")
    if want:
        got = badge_verdict(lines[0]) if lines else None
        if got != want: fails.append(f"verdict: badge says {got}, the case expects {want}")
        for m in re.finditer(r"verdict:\s*`?(rich|partial|could-not-see)\b", body, re.I):
            if m.group(1).lower() != want: fails.append(f"verdict: a coverage line says {m.group(1)}, the case expects {want}")
    p = norm(prose_of(body))
    for m in c["must_state"]:
        if not has_phrase(m, p): fails.append(f"missing: {m}")
    # quoted code (`MODIFY_INVOICE_FORM_CONFIRMED`) is evidence, not the host's claim: forbidden words count in prose only
    scrubbed = re.sub(r"`[^`\n]*`", " ", b).replace("not that it will ship", "")
    for m in c.get("must_not_state", []):
        if m.startswith("re:"):      # a pattern: motive attribution is "<company|they|it> ... because", not the word alone
            if re.search(m[3:], scrubbed, re.I): fails.append(f"present: {m}")
        elif norm(m) in scrubbed: fails.append(f"present: {m}")
    for w in FORBIDDEN.findall(scrubbed): fails.append(f"forbidden word: {w}")
    # copy rules (references/brief.md): no em or en dashes outside code spans and quoted strings; sentence case after labels
    raw_body = "" if c.get("legacy_layout") else re.sub(r"```.*?```", "", body, flags=re.S)   # the engine's footer is not the host's copy; legacy examples predate the copy rules
    prose = re.sub(r"`[^`\n]*`", "``", re.sub(r'"[^"\n]*"', '""', raw_body))    # verbatim strings and code spans are not prose
    if re.search(r"[—–]", prose): fails.append(f"em/en dash in prose: {len(re.findall(r'[—–]', prose))}")
    for m in re.finditer(r"^\s*(Raises|Checked):\s*([a-z])", raw_body, re.M): fails.append(f"lower-case after {m.group(1)}: {m.group(2)}…")
    for m in re.finditer(r"^\*\*([^*]+)\*\*(?: \([^)]*\))?:\s*([a-z])", raw_body, re.M):
        if m.group(1) != "Receipts": fails.append(f"lower-case after the block label {m.group(1)!r}: {m.group(2)}…")   # Receipts is a fragment by contract
    if "**Unannounced**" not in raw_body and re.search(r"^\d+\. \*\*", raw_body, re.M): fails.append("numbered findings without the **Unannounced** (N) header")
    for m in re.finditer(r"(?<=[.!?])\s+(?:[¹²³⁴⁵⁶⁷⁸⁹⁰]+\s*)?([a-z][a-z]+)\b", prose):
        if m.group(1) not in ("vs", "e", "i", "etc", "sha", "lastmod", "llms", "agent", "robots", "sitemap", "openapi", "js", "txt"):
            fails.append(f"sentence starts lower-case: {m.group(1)}"); break
    if not RECEIPT.search(body) and badge_verdict(lines[0] if lines else "") != "could-not-see": fails.append("no receipt")   # nothing read, nothing to receipt
    if run:
        known = set()
        with open(os.path.join(run, "evidence.jsonl"), encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    src = json.loads(line)["source"]; known.add((src["sha256"][:12], src["offset"]))
        hashes = {h for h, _ in known}; last = None
        for m in re.finditer(r"(?:sha256:([0-9a-f]{12}))?@(\d+)", body):
            h = m.group(1) or last; last = h
            if h is None: continue
            if h not in hashes: fails.append(f"receipt names no blob of this run: sha256:{h}")
            elif (h, int(m.group(2))) not in known: fails.append(f"receipt offset not in evidence.jsonl: sha256:{h}@{m.group(2)}")
    if not lines or not lines[0].startswith("🔎 unreleased"): fails.append("badge line is not first")
    if not body.rstrip().endswith("```"): fails.append("fenced footer is not last")
    print(f"{case_id}: {'PASS' if not fails else 'FAIL'}" + ("" if not fails else "\n  " + "\n  ".join(fails)))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
