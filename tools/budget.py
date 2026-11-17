#!/usr/bin/env python3
"""Instruction-budget lever: SKILL.md <= 6 KB, references/ <= 40 KB in total. Non-zero exit over budget.

Both breakouts bloated after breaking out (last30days' root is 31.7 KB and a run loads ~144 KB; REA's
skill went 15 KB -> 154 KB in three weeks). CI runs this so the budget is a build failure, not a review note.
Tokens are approximated at 4 bytes per token, which is close enough for English and keys.
"""
import glob, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_LIMIT, REFS_LIMIT = 6 * 1024, 40 * 1024


def main():
    root = os.path.join(ROOT, "skills", "unreleased")
    skill = os.path.getsize(os.path.join(root, "SKILL.md"))
    refs = {os.path.basename(p): os.path.getsize(p) for p in glob.glob(os.path.join(root, "references", "*.md"))}
    refs_total = sum(refs.values())
    print(f"SKILL.md: {skill:,} B (~{skill // 4:,} tokens) / {ROOT_LIMIT:,}")
    for n, s in sorted(refs.items()):
        print(f"  references/{n}: {s:,} B")
    print(f"references total: {refs_total:,} B (~{refs_total // 4:,} tokens) / {REFS_LIMIT:,}")
    over = []
    if skill > ROOT_LIMIT: over.append("SKILL.md")
    if refs_total > REFS_LIMIT: over.append("references/")
    if over:
        print("OVER BUDGET: " + ", ".join(over)); return 1
    print("within budget"); return 0


if __name__ == "__main__":
    sys.exit(main())
