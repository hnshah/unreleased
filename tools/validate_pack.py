#!/usr/bin/env python3
"""Pack validator: the rules a change must keep, enforced in CI and never weakened to let a change through.

  python3 tools/validate_pack.py

Rules (each exists because a client, a reviewer or a reader would reject the pack without it):
- SKILL.md frontmatter uses only the Agent Skills spec's six fields (name, description, license,
  compatibility, metadata, allowed-tools); any other key makes other clients reject the skill.
- name matches the directory and the name rules; description is 1-1024 chars and front-loads the request
  vocabulary; metadata maps strings to strings; metadata.version equals version.py and plugin.json.
- SKILL.md <= 6 KB (our budget) and <= 500 lines; references/ <= 40 KB in total (tools/budget.py).
- every references/*.md is routed from SKILL.md and every routed file exists (orphans fail).
- "Do not use this skill when" exists and names at least one neighbour.
- no credential-shaped string anywhere shipped; no real-company example in method text
  (SKILL.md, references/): method, not facts — real names live in docs/examples and the corpus.
- CHANGELOG.md has a section for the current version; LF line endings everywhere shipped.
- .claude-plugin/plugin.json version equals version.py.
Exit 1 with every error listed; exit 0 clean.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SECRET_RE = re.compile(r"(?:sk_live_|sk_test_|AKIA[0-9A-Z]{12,}|xox[abp]-|ghp_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY)")
# real products the corpus studied; method text names none of them (docs/examples and tests may)
REAL_NAMES = re.compile(r"\b(figma|notion|linear\.app|vercel|sentry|dropbox|loom|stripe|posthog|supabase|netlify|lovable|replit|cursor|amplitude|hubspot|intercom|mixpanel|shopify|webflow|zoom|slack|discord|spotify|duolingo|asana|miro|airtable|gitlab|cloudflare|postman|retool|perplexity|canva|clarity|hotjar|chatgpt)\b", re.I)
ALLOWED_REAL = {"last30days", "lmty", "rea"}     # neighbours named in hand-offs are not examples
SKILL_DIR = os.path.join("skills", "unreleased")       # the plugin layout: a root SKILL.md is not a plugin skill
SHIPPED = [SKILL_DIR, "POLICY.md", "LICENSE", "README.md", ".claude-plugin"]

errors: list[str] = []


def read(*parts) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        errors.append("SKILL.md: missing YAML frontmatter"); return {}
    fm: dict = {}; cur = None
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        if line.startswith("  ") and cur:
            k, _, v = line.strip().partition(":")
            fm.setdefault(cur, {})[k.strip()] = v.strip().strip('"')
        else:
            k, _, v = line.partition(":")
            k = k.strip(); v = v.strip()
            if v == "":
                cur = k; fm[k] = {}
            else:
                cur = None; fm[k] = v.strip('"')
    return fm


def main() -> int:
    sys.path.insert(0, os.path.join(ROOT, SKILL_DIR, "scripts", "lib"))
    from version import VERSION
    skill = read(SKILL_DIR, "SKILL.md")
    fm = frontmatter(skill)
    extra = set(fm) - SPEC_FIELDS
    if extra:
        errors.append(f"SKILL.md: frontmatter keys outside the Agent Skills spec: {sorted(extra)} (other clients reject them)")
    name = fm.get("name", "")
    if name != "unreleased" or not NAME_RE.match(name):
        errors.append(f"SKILL.md: name {name!r} must be `unreleased` and match the name rules")
    desc = fm.get("description", "")
    if not (1 <= len(desc) <= 1024):
        errors.append(f"SKILL.md: description length {len(desc)} outside 1-1024")
    if not re.search(r"\b(building|working on|launch|testing)\b", desc[:160], re.I):
        errors.append("SKILL.md: description does not front-load the request vocabulary (Codex truncates long descriptions)")
    meta = fm.get("metadata", {})
    if not isinstance(meta, dict) or any(not isinstance(v, str) for v in meta.values()):
        errors.append("SKILL.md: metadata must map string keys to string values (Agent Skills spec)")
    if meta.get("version") != VERSION:
        errors.append(f"SKILL.md: metadata.version {meta.get('version')!r} != version.py {VERSION!r}")
    if len(skill.encode("utf-8")) > 6 * 1024:
        errors.append(f"SKILL.md: {len(skill.encode('utf-8'))} bytes > 6 KB budget")
    if skill.count("\n") > 500:
        errors.append("SKILL.md: over 500 lines")
    routed = set(re.findall(r"`references/([a-z-]+\.md)`", skill))
    on_disk = {f for f in os.listdir(os.path.join(ROOT, SKILL_DIR, "references")) if f.endswith(".md")}
    for f in sorted(on_disk - routed):
        errors.append(f"references/{f}: ships but SKILL.md never routes to it")
    for f in sorted(routed - on_disk):
        errors.append(f"SKILL.md: routes to references/{f}, which does not exist")
    if "## Do not use this skill when" not in skill:
        errors.append("SKILL.md: no 'Do not use this skill when' section naming the neighbours that own excluded work")
    for rel in [os.path.join(SKILL_DIR, "SKILL.md")] + [os.path.join(SKILL_DIR, "references", f) for f in sorted(on_disk)]:
        text = read(rel)
        hits = sorted({m.lower() for m in REAL_NAMES.findall(text)} - ALLOWED_REAL)
        if hits:
            errors.append(f"{rel}: names real products in method text {hits}; use placeholders (Acme), keep real names in docs/examples")
    for base in SHIPPED:
        path = os.path.join(ROOT, base)
        files = [path] if os.path.isfile(path) else [os.path.join(d, f) for d, _, fs in os.walk(path) for f in fs if "__pycache__" not in d]
        for p in files:
            if p.endswith((".png", ".jpg", ".db")):
                continue
            with open(p, "rb") as fh:
                b = fh.read()
            if b"\r\n" in b:
                errors.append(f"{os.path.relpath(p, ROOT)}: CRLF line endings")
            if SECRET_RE.search(b.decode("utf-8", "replace")) and "/tests/" not in p and "redact.py" not in p:
                errors.append(f"{os.path.relpath(p, ROOT)}: looks like a credential")
    plug = json.loads(read(".claude-plugin", "plugin.json"))
    if plug.get("version") != VERSION:
        errors.append(f".claude-plugin/plugin.json: version {plug.get('version')!r} != version.py {VERSION!r}")
    gem = json.loads(read("gemini-extension.json"))
    if gem.get("version") != VERSION:
        errors.append(f"gemini-extension.json: version {gem.get('version')!r} != version.py {VERSION!r}")
    changelog = read("CHANGELOG.md")
    if f"## [{VERSION}]" not in changelog:
        errors.append(f"CHANGELOG.md: no '## [{VERSION}]' section for the current version")
    readme = read("README.md")
    m = re.search(r"\b(\d{2,})\s+(?:tests|fingerprints|extractors|sources)\b", readme)
    if m:
        errors.append(f"README.md: copy counts something that goes stale ({m.group(0)!r}); describe it instead, or date it")
    if errors:
        print("ERRORS:")
        for e in errors:
            print("-", e)
        return 1
    print(f"pack ok: skill {len(skill.encode())} B, {len(on_disk)} references routed, version {VERSION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
