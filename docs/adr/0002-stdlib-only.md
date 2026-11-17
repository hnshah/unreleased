# ADR 0002: Python standard library only

Status: accepted, 2026-10-30.

Context. last30days ships `dependencies = []` and vendors the one client it needs; REA's ~160 npm
dependencies include an update checker that contacts the registry. A skill installs into many hosts on
machines we do not control.

Decision. The engine depends on Python 3.11+ and the standard library only (`urllib`, `sqlite3`, `json`,
`re`, `hashlib`, `html`). No network update checks, no telemetry.

Consequences. No HTML parser beyond regex and `html.parser`; no JS parser (we write a tolerant scanner).
Slower to write, trivial to install, nothing to audit.
