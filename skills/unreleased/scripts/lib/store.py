"""Store: SQLite (schema in ARCHITECTURE.md section 2.4) with sightings and a briefs full-text table. Default on.

The store answers three questions the brief needs: what did the previous usable run see (for the diff),
since when has each key been seen (sightings), and what did earlier briefs say (library).
"""
from __future__ import annotations
import json, sqlite3
from schema import Observation, Source, Manifest, Subdomain, Job, PricingSnapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS products(slug TEXT PRIMARY KEY, domain TEXT, plan_json TEXT, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, product TEXT, started_at TEXT, engine_version TEXT, verdict TEXT, seconds REAL, first_party_bytes INTEGER, manifest_json TEXT);
CREATE TABLE IF NOT EXISTS artifacts(sha256 TEXT PRIMARY KEY, url TEXT, first_seen_run TEXT, last_seen_run TEXT, bytes INTEGER, first_party INTEGER);
CREATE TABLE IF NOT EXISTS run_artifacts(run_id TEXT, url TEXT, sha256 TEXT, PRIMARY KEY(run_id, url));
CREATE TABLE IF NOT EXISTS observations(product TEXT, kind TEXT, key TEXT, value_json TEXT, group_key TEXT, tier TEXT, confidence TEXT,
  source_sha256 TEXT, source_url TEXT, offset INTEGER, context TEXT, extractor TEXT, first_seen_run TEXT, last_seen_run TEXT, sighting_count INTEGER DEFAULT 1, dismissed INTEGER DEFAULT 0,
  PRIMARY KEY(product, kind, key));
CREATE TABLE IF NOT EXISTS run_observations(run_id TEXT, product TEXT, kind TEXT, key TEXT, value_json TEXT, tier TEXT, PRIMARY KEY(run_id, kind, key));
CREATE TABLE IF NOT EXISTS checks(run_id TEXT, product TEXT, kind TEXT, key TEXT, status TEXT, date TEXT, url TEXT, searched_json TEXT);
CREATE TABLE IF NOT EXISTS subdomains(product TEXT, run_id TEXT, name TEXT, first_seen TEXT, stem TEXT, env TEXT, apex TEXT);
CREATE TABLE IF NOT EXISTS jobs(product TEXT, run_id TEXT, ats TEXT, slug TEXT, external_id TEXT, title TEXT, dept TEXT, location TEXT, posted_at TEXT, url TEXT, nouns_json TEXT);
CREATE TABLE IF NOT EXISTS pricing(product TEXT, run_id TEXT, url TEXT, sha256_text TEXT, chars INTEGER, status TEXT, lines_json TEXT, final_url TEXT);
CREATE TABLE IF NOT EXISTS redactions(run_id TEXT, kind TEXT, reason TEXT, count INTEGER);
CREATE TABLE IF NOT EXISTS briefs(product TEXT, run_id TEXT, saved_at TEXT DEFAULT (datetime('now')), path TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS watch(product TEXT PRIMARY KEY, schedule TEXT, enabled INTEGER DEFAULT 1, last_run_id TEXT);
"""


class Store:
    def __init__(self, path: str):
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.fts = False
        self._init()

    def _init(self) -> None:
        self.db.executescript(SCHEMA)
        try:
            self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS briefs_fts USING fts5(product, run_id, body)")
            self.fts = True
        except sqlite3.OperationalError:
            self.fts = False
        self.db.commit()

    def close(self):
        self.db.close()

    # --- runs ---------------------------------------------------------------------------------
    def begin(self) -> None:
        """One transaction per run: observations, signals, checks, artifacts and the run row commit together or not
        at all (SM-1). sqlite3 opens a transaction on the first write; this makes the intent explicit."""
        self.db.execute("BEGIN")

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    def has_run(self, run_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone() is not None

    def is_usable_run(self, product: str, run_id: str) -> bool:
        """A baseline: this product's, read code, no blocked or challenged page, and has observations (SM-2, SM-4)."""
        row = self.db.execute("SELECT manifest_json, verdict FROM runs WHERE run_id=? AND product=?", (run_id, product)).fetchone()
        if row is None or row["verdict"] == "could-not-see":
            return False
        try:
            pages = json.loads(row["manifest_json"] or "{}").get("pages", [])
        except ValueError:
            pages = []
        if any(p.get("state") in ("blocked-403", "challenge") for p in pages):
            return False
        return self.db.execute("SELECT 1 FROM run_observations WHERE run_id=? LIMIT 1", (run_id,)).fetchone() is not None

    def record_run(self, m: Manifest, verdict: str, seconds: float, first_party_bytes: int, domain: str = "", plan_json: str = "") -> None:
        from dataclasses import asdict
        self.db.execute("INSERT INTO products(slug, domain, plan_json) VALUES(?,?,?) ON CONFLICT(slug) DO UPDATE SET domain=excluded.domain, plan_json=excluded.plan_json",
                        (m.product, domain, plan_json))
        self.db.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?,?,?,?)",
                        (m.run_id, m.product, m.started_at, m.engine_version, verdict, seconds, first_party_bytes, json.dumps(asdict(m), sort_keys=True)))

    def previous_usable_run(self, product: str, before_run_id: str) -> str | None:
        """The baseline for a diff: the latest earlier run that read code and had no blocked or challenged page
        (R11: challenged and empty runs are never baselines)."""
        for row in self.db.execute("SELECT run_id FROM runs WHERE product=? AND run_id<? AND verdict!='could-not-see' ORDER BY run_id DESC LIMIT 20",
                                   (product, before_run_id)):
            if self.is_usable_run(product, row["run_id"]):
                return row["run_id"]
        return None

    def run_version(self, product: str, run_id: str) -> str:
        row = self.db.execute("SELECT engine_version FROM runs WHERE product=? AND run_id=?", (product, run_id)).fetchone()
        return str(row["engine_version"] or "") if row else ""

    def run_bytes(self, product: str, run_id: str) -> int:
        row = self.db.execute("SELECT first_party_bytes FROM runs WHERE product=? AND run_id=?", (product, run_id)).fetchone()
        return int(row["first_party_bytes"] or 0) if row else 0

    # --- observations -------------------------------------------------------------------------
    def upsert_observations(self, product: str, run_id: str, obs: list[Observation]) -> None:
        for o in obs:
            vj = json.dumps(o.value, sort_keys=True, default=str)
            self.db.execute("""INSERT INTO observations(product,kind,key,value_json,group_key,tier,confidence,source_sha256,source_url,offset,context,extractor,first_seen_run,last_seen_run,sighting_count)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                               ON CONFLICT(product,kind,key) DO UPDATE SET value_json=excluded.value_json, tier=excluded.tier, confidence=excluded.confidence,
                               source_sha256=excluded.source_sha256, source_url=excluded.source_url, offset=excluded.offset, context=excluded.context,
                               last_seen_run=excluded.last_seen_run, sighting_count=observations.sighting_count+1""",
                            (product, o.kind, o.key, vj, o.group, o.tier, o.confidence, o.source.sha256, o.source.url, o.source.offset, o.context, o.extractor, run_id, run_id))
            self.db.execute("INSERT OR REPLACE INTO run_observations VALUES(?,?,?,?,?,?)", (run_id, product, o.kind, o.key, vj, o.tier))

    def observations(self, product: str, run_id: str) -> list[Observation]:
        rows = self.db.execute("""SELECT ro.kind, ro.key, ro.value_json, ro.tier, o.group_key, o.confidence, o.source_sha256, o.source_url, o.offset, o.context, o.extractor
                                  FROM run_observations ro JOIN observations o ON o.product=ro.product AND o.kind=ro.kind AND o.key=ro.key
                                  WHERE ro.run_id=? AND ro.product=?""", (run_id, product)).fetchall()
        out = []
        for r in rows:
            out.append(Observation(id=f"{run_id}-{r['kind']}-{r['key']}", kind=r["kind"], key=r["key"], value=json.loads(r["value_json"]) if r["value_json"] else None,
                                   tier=r["tier"], group=r["group_key"] or "", confidence=r["confidence"] or "low", context=r["context"] or "", extractor=r["extractor"] or "",
                                   source=Source(url=r["source_url"] or "", sha256=r["source_sha256"] or "", offset=r["offset"] if r["offset"] is not None else -1)))
        return out

    def sightings(self, product: str, key: str, kind: str | None = None) -> dict | None:
        q = "SELECT first_seen_run, last_seen_run, sighting_count FROM observations WHERE product=? AND key=?" + (" AND kind=?" if kind else "")
        row = self.db.execute(q, (product, key, kind) if kind else (product, key)).fetchone()
        return dict(row) if row else None

    def first_seen_map(self, product: str) -> dict[tuple[str, str], str]:
        return {(r["kind"], r["key"]): r["first_seen_run"] for r in self.db.execute("SELECT kind, key, first_seen_run FROM observations WHERE product=?", (product,))}

    # --- signals ------------------------------------------------------------------------------
    def save_signals(self, product: str, run_id: str, subs: list[Subdomain], jobs: list[Job], pricing: PricingSnapshot | None) -> None:
        for t in ("subdomains", "jobs", "pricing"):
            self.db.execute(f"DELETE FROM {t} WHERE run_id=?", (run_id,))
        self.db.executemany("INSERT INTO subdomains VALUES(?,?,?,?,?,?,?)", [(product, run_id, s.name, s.first_seen, s.stem, s.env, s.apex) for s in subs])
        self.db.executemany("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)", [(product, run_id, j.ats, j.slug, j.external_id, j.title, j.dept, j.location, j.posted_at, j.url, json.dumps(j.nouns)) for j in jobs])
        if pricing:
            self.db.execute("INSERT INTO pricing VALUES(?,?,?,?,?,?,?,?)", (product, run_id, pricing.url, pricing.sha256_text, pricing.chars, pricing.status, json.dumps(pricing.lines), pricing.final_url))

    def signals(self, product: str, run_id: str):
        subs = [Subdomain(r["name"], r["first_seen"], r["stem"] or "", r["env"] or "", r["apex"] or "") for r in self.db.execute("SELECT * FROM subdomains WHERE product=? AND run_id=?", (product, run_id))]
        jobs = [Job(r["ats"], r["slug"], r["external_id"], r["title"], r["dept"] or "", r["location"] or "", r["posted_at"], r["url"] or "", json.loads(r["nouns_json"] or "[]")) for r in self.db.execute("SELECT * FROM jobs WHERE product=? AND run_id=?", (product, run_id))]
        pr = self.db.execute("SELECT * FROM pricing WHERE product=? AND run_id=?", (product, run_id)).fetchone()
        pricing = PricingSnapshot(pr["url"], pr["sha256_text"], pr["chars"], pr["status"], json.loads(pr["lines_json"] or "[]"), pr["final_url"] or "") if pr else None
        return subs, jobs, pricing

    def save_checks(self, product: str, run_id: str, checks, observations: list[Observation] | None = None) -> None:
        """Checks are stored by the observation's (kind, key) so they join across runs; the per-run id alone does not."""
        by_id = {o.id: o for o in (observations or [])}
        rows = []
        for c in checks:
            o = by_id.get(c.observation_id)
            rows.append((run_id, product, o.kind if o else "", o.key if o else c.observation_id, c.status, c.date, c.url, json.dumps(c.searched)))
        self.db.execute("DELETE FROM checks WHERE run_id=?", (run_id,))
        self.db.executemany("INSERT INTO checks VALUES(?,?,?,?,?,?,?,?)", rows)

    def save_redactions(self, run_id: str, counts: dict[str, int]) -> None:
        """Counts by reason only ("secret-like value": 2); never a key or a value."""
        self.db.execute("DELETE FROM redactions WHERE run_id=?", (run_id,))
        self.db.executemany("INSERT INTO redactions VALUES(?,?,?,?)", [(run_id, "", reason, n) for reason, n in counts.items()])

    def record_artifacts(self, run_id: str, artifacts: list[tuple[str, str, int, bool]]) -> None:
        """(sha256, url, bytes, first_party) per body read; first/last seen run per sha so a receipt can be dated."""
        self.db.executemany("""INSERT INTO artifacts(sha256, url, first_seen_run, last_seen_run, bytes, first_party) VALUES(?,?,?,?,?,?)
                               ON CONFLICT(sha256) DO UPDATE SET last_seen_run=excluded.last_seen_run""",
                            [(sha, url, run_id, run_id, n, int(fp)) for sha, url, n, fp in artifacts])
        self.db.executemany("INSERT OR REPLACE INTO run_artifacts VALUES(?,?,?)", [(run_id, url, sha) for sha, url, n, fp in artifacts])

    def run_urls(self, run_id: str) -> set[str]:
        """The script and page URLs a run read: continuity for the next run's selection and the diff's honesty."""
        return {r["url"] for r in self.db.execute("SELECT url FROM run_artifacts WHERE run_id=?", (run_id,))}

    # --- library ------------------------------------------------------------------------------
    def save_brief(self, product: str, run_id: str, path: str, body: str) -> None:
        self.db.execute("INSERT INTO briefs(product, run_id, path, body) VALUES(?,?,?,?)", (product, run_id, path, body))
        if self.fts:
            self.db.execute("INSERT INTO briefs_fts(product, run_id, body) VALUES(?,?,?)", (product, run_id, body))
        self.db.commit()

    def search_briefs(self, query: str, limit: int = 10) -> list[dict]:
        if self.fts:
            rows = self.db.execute("SELECT product, run_id, snippet(briefs_fts, 2, '[', ']', '…', 12) AS snippet FROM briefs_fts WHERE briefs_fts MATCH ? LIMIT ?", (query, limit)).fetchall()
        else:
            rows = self.db.execute("SELECT product, run_id, substr(body, 1, 160) AS snippet FROM briefs WHERE body LIKE ? LIMIT ?", (f"%{query}%", limit)).fetchall()
        return [dict(r) for r in rows]
