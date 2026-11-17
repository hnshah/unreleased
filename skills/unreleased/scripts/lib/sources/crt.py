"""crt source: certificate-transparency subdomains from crt.sh, one query per apex (R12).

Contract (shared by every module in `sources/`): `fetch(plan, fetcher) -> (records, outcomes)` where
`records` is a list of `Subdomain` and `outcomes` a list of `SourceOutcome`, one per apex queried; and
`health(fetcher) -> SourceOutcome`. The tuple is the final contract: the worker brief said records only,
but a source has to say what happened to each endpoint (crt.sh failed on 5 of 39 targets; wildcard-heavy
orgs print "0 of N") and the caller must not infer that from an empty list.

What this module does with a crt.sh response:
- every apex in `plan.apexes` is queried (`chatgpt.com`, `hf.co`, `claude.com` were missed by apex-only runs);
- `first_seen` = the earliest `not_before` per name (YYYY-MM-DD); wildcards (`*.x`) are skipped, malformed
  rows (names containing `http`, `/`, spaces) and the apex itself are dropped;
- environment conventions are parsed into `env` and removed from `stem`: `-test`, `-staging`, `-prod-N`,
  `-dev`, `-sandbox`, `-canary`, `-experimental`, `preprod-` and whole labels `test`, `staging`, `prod`,
  `preview`, `sandbox`, `internal`, `p` (prod), `i` (internal); several markers join with `/`
  (`aster.preview.i.perplexity.ai` -> stem `aster`, env `preview/internal`). Cloud region labels
  (`europe-west1`, `ap-southeast-1`) are removed from the stem so regional copies group under one stem;
- machine-generated labels (long hex, uuids, `<word>-<hash>` / `pr-<n>`) collapse to one record per pattern
  (`preview-*.lovable.app`) whose `stem` carries the count and first-seen range (`preview-* (4289, a..b)`);
  more than 200 distinct leaves under one parent collapse the same way (`*.lovableproject.com`);
- ALL names are returned with `first_seen`; the pipeline applies the recent window.

Outcome states: HTTP 5xx / unreachable / timeout are retried twice with backoff (never a 403), then recorded as
`unreachable` / `timeout`; a truncated body, a wildcard-dominated result ("0 of N (wildcards)") and a
cap-like row count with nothing recent are `capped` (unverifiable, not absence); a non-JSON body is `error`.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections import defaultdict
from typing import Optional

from schema import SourceOutcome, Subdomain

SOURCE = "crt"
CRT_URL = "https://crt.sh/?q=%25.{apex}&output=json"
LIMIT = 50_000_000            # crt.sh answers for large orgs run to tens of MB
HEALTH_APEX = "example.com"
RECENT_DAYS = 120
CAP_LIKE_ROWS = 4500          # the readers saw 4,978 / 4,909 row counts with nothing recent: a cap, not absence
FLOOD = 200                   # more than this many distinct leaves under one parent is a preview flood
MIN_WILDCARDS = 20

_ENV = {"test": "test", "testing": "test", "tst": "test", "staging": "staging", "stg": "staging", "stage": "staging",
        "prod": "prod", "production": "prod", "p": "prod", "preprod": "preprod", "preview": "preview",
        "dev": "dev", "development": "dev", "sandbox": "sandbox", "sbx": "sandbox", "canary": "canary",
        "internal": "internal", "i": "internal", "qa": "qa", "uat": "uat", "experimental": "experimental"}
_ENV_SUFFIX = re.compile(r"^(?P<stem>[a-z0-9][a-z0-9-]*?)-(?P<env>test|testing|staging|stg|stage|prod|production|preprod|preview|dev|development|sandbox|sbx|canary|qa|uat|experimental)(?P<n>-?\d+)?$")
_ENV_PREFIX = re.compile(r"^(?P<env>preprod|staging|stg|test|sandbox|canary|prod)-(?P<stem>[a-z0-9][a-z0-9-]*)$")
_ENV_WHOLE_N = re.compile(r"^(?P<env>test|staging|prod|dev|preview|sandbox|canary|experimental)-?(?P<n>\d+)$")
_REGION = re.compile(r"^(?:(?:us|eu|europe|asia|ap|sa|ca|me|af|australia|northamerica|southamerica|uk|jp)-(?:east|west|north|south|central|southeast|northeast|southwest|northwest)\d*(?:-\d+)?[a-z]?|(?:east|west|north|south|central)(?:us|europe|asia|india|japan)\d*)$")
_REGION_SUFFIX = re.compile(r"^(?P<stem>[a-z0-9][a-z0-9-]*?)-(?P<region>(?:us|eu|europe|asia|ap|sa|ca|me|af|australia|uk|jp)-(?:east|west|north|south|central|southeast|northeast|southwest|northwest)\d*(?:-\d+)?[a-z]?)$")
_HEX = re.compile(r"^(?=(?:.*\d){2})[0-9a-f]{12,}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_ALNUM = re.compile(r"^(?=(?:.*\d){4})[a-z0-9]{16,}$")
_NUMERIC = re.compile(r"^\d{3,}$")
_HASH_SUFFIX = re.compile(r"^(?P<word>[a-z][a-z0-9-]*?)-+(?P<hash>(?=[a-f]*\d)[0-9a-f]{6,}|\d{3,})$")
_NAME_OK = re.compile(r"^[a-z0-9.-]+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


# --- pure parsing ------------------------------------------------------------------------------------

def parse_name(name: str, apex: str) -> tuple[str, str]:
    """(stem, env) for a host under `apex`: env markers are removed from the stem and joined with `/`."""
    if not name.endswith("." + apex):
        return name, ""
    rest = name[: -len(apex) - 1]
    labels, kept, envs = rest.split("."), [], []

    def add(env: str):
        if env not in envs:
            envs.append(env)

    for label in labels:
        if label in _ENV:
            add(_ENV[label]); continue
        m = _ENV_WHOLE_N.match(label)
        if m:
            add(_ENV[m.group("env")] + "-" + m.group("n")); continue
        if _REGION.match(label):
            continue
        m = _ENV_SUFFIX.match(label)
        if m:
            add(_ENV[m.group("env")] + (("-" + m.group("n").lstrip("-")) if m.group("n") else ""))
            label = m.group("stem")
        else:
            m = _ENV_PREFIX.match(label)
            if m:
                add(_ENV[m.group("env")]); label = m.group("stem")
        m = _REGION_SUFFIX.match(label)
        if m:
            label = m.group("stem")
        if label:
            kept.append(label)
    stem = ".".join(kept) if kept else labels[0]
    return stem, "/".join(envs)


def _machine(label: str) -> Optional[str]:
    """The pattern a machine-generated label collapses to (`*`, `preview-*`), or None for a human name."""
    if _HEX.match(label) or _UUID.match(label) or _ALNUM.match(label) or _NUMERIC.match(label):
        return "*"
    m = _HASH_SUFFIX.match(label)
    if m:
        return m.group("word") + "-*"
    return None


def _clean_names(rows: list[dict], apex: str) -> dict[str, str]:
    """name -> earliest not_before (YYYY-MM-DD); wildcards, malformed rows and the apex are dropped."""
    first: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        nb = str(row.get("not_before") or "")[:10]
        if not _DATE.match(nb):
            continue
        for raw in str(row.get("name_value") or "").split("\n"):
            n = raw.strip().lower()
            if not n or n.startswith("*.") or "http" in n or not _NAME_OK.match(n):
                continue
            if n == apex or not n.endswith("." + apex):
                continue
            if n not in first or nb < first[n]:
                first[n] = nb
    return first


def parse_rows(rows: list[dict], apex: str) -> list[Subdomain]:
    """Subdomains for one apex from crt.sh JSON rows: one record per name, floods collapsed to a pattern."""
    first = _clean_names(rows, apex)
    # 1. collapse machine-generated labels to a pattern
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)        # pattern name -> [(name, first_seen)]
    for name, seen in first.items():
        labels = name[: -len(apex) - 1].split(".")
        pat = [(_machine(l) or l) for l in labels]
        groups[".".join(pat) + "." + apex].append((name, seen))
    # 2. collapse a flood of distinct leaves under one parent below the apex (a preview zone); never the apex
    #    itself: gitlab (504) and asana (1,036) have that many real hosts and the pipeline groups them by stem
    leaves: dict[str, int] = defaultdict(int)
    for name in first:
        parent = name.split(".", 1)[1]
        if parent != apex:
            leaves[parent] += 1
    merged: dict[str, list[tuple[str, str]]] = {}
    for pat, members in groups.items():
        parent = pat.split(".", 1)[1]
        if parent != apex and leaves[parent] > FLOOD:
            merged.setdefault("*." + parent, []).extend(members)
        else:
            merged.setdefault(pat, []).extend(members)
    out = []
    for pat, members in merged.items():
        seen_dates = sorted(s for _, s in members)
        stem, env = parse_name(pat, apex)
        if "*" in pat:
            count = len(members)
            out.append(Subdomain(name=pat, first_seen=seen_dates[0], stem=stem, env=env, apex=apex, count=count, last_seen=seen_dates[-1]))
        else:
            name, seen = members[0]
            out.append(Subdomain(name=name, first_seen=seen, stem=stem, env=env, apex=apex))
    out.sort(key=lambda s: (s.first_seen, s.name))
    return out


def _wildcards(rows: list[dict]) -> int:
    names = set()
    for row in rows:
        if isinstance(row, dict):
            for raw in str(row.get("name_value") or "").split("\n"):
                if raw.strip().startswith("*."):
                    names.add(raw.strip().lower())
    return len(names)


def _outcome(apex: str, fetched, today: dt.date) -> tuple[list[Subdomain], SourceOutcome]:
    if fetched.state != "ok" or not isinstance(fetched.status, int) or fetched.status != 200:
        tries = getattr(fetched, "tries", 1)
        what = f"HTTP {fetched.status}" if isinstance(fetched.status, int) else f"{fetched.state} (no HTTP status: connection or read failure)"
        return [], SourceOutcome(SOURCE, fetched.state, 0, True, f"{apex}: {what} after {tries} {'try' if tries == 1 else 'tries'} with backoff")
    try:
        rows = json.loads(fetched.body)
        if not isinstance(rows, list):
            raise ValueError("not a list")
    except Exception:
        if fetched.truncated:
            return [], SourceOutcome(SOURCE, "capped", 0, True, f"{apex}: response truncated at {fetched.bytes} bytes; nothing parsed")
        return [], SourceOutcome(SOURCE, "error", 0, True, f"{apex}: non-JSON body ({fetched.bytes} bytes)")
    subs = parse_rows(rows, apex)
    n, w = len(subs), _wildcards(rows)
    if fetched.truncated:
        return subs, SourceOutcome(SOURCE, "capped", n, True, f"{apex}: response truncated at {fetched.bytes} bytes; {n} names parsed")
    if w >= MIN_WILDCARDS and n <= w:
        return subs, SourceOutcome(SOURCE, "capped", n, True, f"{apex}: {n} names, {w} wildcards: wildcard-covered hosts are unverifiable")
    cutoff = (today - dt.timedelta(days=RECENT_DAYS)).isoformat()
    if len(rows) >= CAP_LIKE_ROWS and not any(s.first_seen >= cutoff for s in subs):
        return subs, SourceOutcome(SOURCE, "capped", n, True, f"{apex}: {len(rows)} rows (cap-like) with nothing first seen in {RECENT_DAYS} days: unverifiable")
    if n == 0:
        return subs, SourceOutcome(SOURCE, "no-results", 0, True, f"{apex}: 0 names from {len(rows)} certificates")
    return subs, SourceOutcome(SOURCE, "ok", n, True, f"{apex}: {n} names from {len(rows)} certificates")


# --- the seam ----------------------------------------------------------------------------------------

RETRIES = 3          # crt.sh answers 502 intermittently (3 of 4 tries on 2026-10-31); a public query service, so three polite tries
BACKOFF = (3.0, 8.0)


def _get(fetcher, url: str):
    """One crt.sh request with up to two polite retries, backing off, on a server error or a timeout; never on a 403 or 429."""
    import time
    f = fetcher.get(url, LIMIT, kind="api"); tries = 1
    for wait in BACKOFF[:RETRIES - 1]:
        server_error = isinstance(f.status, int) and f.status >= 500
        if not (server_error or f.state in ("unreachable", "timeout", "error")):
            break
        sleep = getattr(fetcher, "_sleep", time.sleep)
        sleep(wait)
        f = fetcher.get(url, LIMIT, kind="api"); tries += 1
    f.tries = tries
    return f


def fetch(plan, fetcher, today: Optional[dt.date] = None) -> tuple[list[Subdomain], list[SourceOutcome]]:
    today = today or dt.date.today()
    records, outcomes = [], []
    for apex in plan.apexes:
        subs, out = _outcome(apex, _get(fetcher, CRT_URL.format(apex=apex)), today)
        records.extend(subs); outcomes.append(out)
    return records, outcomes


def health(fetcher) -> SourceOutcome:
    """One small query (`%.example.com`): says whether crt.sh answers JSON right now."""
    subs, out = _outcome(HEALTH_APEX, fetcher.get(CRT_URL.format(apex=HEALTH_APEX), 5_000_000, kind="api"), dt.date.today())
    return out
