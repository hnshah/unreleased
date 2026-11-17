# ADR 0003: the first run is static and keyless; SDK endpoints are never called directly

Status: accepted for v1, 2026-10-30; `--browser` is an open question.

Context. Several products (Notion, Loom, Netlify, HubSpot, Intercom) fetch their flags at runtime from
LaunchDarkly/Statsig/PostHog with public client keys that sit in the bundle. Calling those endpoints
would roughly double coverage.

Decision. v1 reads only the bytes a browser would download and evaluates nothing. Runtime-only SDKs are
recorded as `runtime-only` coverage, printed as "could not see". Direct calls to flag-vendor endpoints
are not made in any mode. A later `--browser` mode may observe what the page itself fetches.

Consequences. Honest but blind for runtime-SDK products; the brief says so. Nothing a company could
describe as the tool "pulling our flags".
