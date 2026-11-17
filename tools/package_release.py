#!/usr/bin/env python3
"""Build the release zip: exactly what a user needs, nothing else.

  python3 tools/package_release.py [--out dist/]

Ships: SKILL.md, references/, scripts/ (no __pycache__), POLICY.md, LICENSE, README.md, CHANGELOG.md,
SECURITY.md, SUPPORT.md, .claude-plugin/. Leaves out tests, tools, docs, evals, CI. The zip is named
unreleased-<version>.zip from scripts/lib/version.py; a dry run lists the files.
"""
import argparse, os, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "unreleased", "scripts", "lib"))
from version import VERSION  # noqa: E402

SHIP = ["POLICY.md", "LICENSE", "README.md", "CHANGELOG.md", "SECURITY.md", "SUPPORT.md", "skills", ".claude-plugin", "gemini-extension.json"]


def files():
    for base in SHIP:
        p = os.path.join(ROOT, base)
        if os.path.isfile(p):
            yield base
        else:
            for d, dirs, fs in os.walk(p):
                dirs[:] = [x for x in dirs if x != "__pycache__"]
                for f in sorted(fs):
                    if not f.endswith(".pyc"):
                        yield os.path.relpath(os.path.join(d, f), ROOT)


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="dist"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    names = list(files())
    if a.dry_run:
        print("\n".join(names)); print(f"{len(names)} files"); return 0
    os.makedirs(os.path.join(ROOT, a.out), exist_ok=True)
    out = os.path.join(ROOT, a.out, f"unreleased-{VERSION}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.write(os.path.join(ROOT, n), os.path.join(f"unreleased-{VERSION}", n))
    print(f"{out}: {len(names)} files, {os.path.getsize(out):,} bytes"); return 0


if __name__ == "__main__":
    sys.exit(main())
