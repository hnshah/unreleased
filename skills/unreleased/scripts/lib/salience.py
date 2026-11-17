"""Salience (R7): which observations are nameable nouns worth a finding line, and how they cluster.

The readers judged ~140 of Figma's 615 keys nameable; the rest were plumbing (logging, perf, cache, rollout
mechanics) or unreadable codenames. A brief leads with product nouns (plans, prices, credits, agents,
integrations, surfaces); plumbing goes to the key list. Scores are small integers so they are easy to argue
about and test. Everything here is a pure function of the observation.
"""
from __future__ import annotations
import re
from schema import Observation

PRODUCT = set("""ai agent agents assistant assistants copilot cofounder mcp model models llm gpt claude gemini sonnet opus credit credits plan plans pricing price
prices tier tiers seat seats billing subscription subscribe trial trials upgrade upgrades upsell checkout invoice payment payments discount coupon coupons
promo free pro premium enterprise business starter education edu student nonprofit marketplace store shop app apps plugin plugins extension extensions
integration integrations connector connectors slack github gitlab jira linear notion figma google microsoft salesforce hubspot zapier webhook webhooks sdk cli
desktop mobile ios android mac windows browser voice audio video transcript transcription transcribe meeting meetings calendar mail email inbox chat messages
comment comments canvas whiteboard slides slide docs doc sheets forms templates template library publish publishing share sharing collaboration workspace
project projects agentic autonomous workflow workflows automation automations skills skill tools tool local cloud byoc vault sso saml scim residency region
eu compliance soc hipaa gdpr export import search analytics insights dashboard dashboards reports report notebook notebooks code developer git preview
beta alpha early access waitlist launch ga marketplace payout payouts refund refunds coupon seat bundle bundles credits metering usage quota limits limit
storage versioning lifecycle webhooks repositories repository perimeters perimeter private inference gateway models providers provider accounting wrapped
agent cofounder omni missions memory wallet browser computers computer imessage whatsapp telegram pix regional passkey passkeys passwordless login signup
onboarding admin console api keys key tokens token marketplace container kernel kernels buckets bucket spaces space jobs environments evaluations inbox
observatory make local weave figjam sites buzz slides storyboard charts chart trim trimming chapters ratio print approvals table layers layer shaders motion
riffs generative plugins skills assistant credits starter design designer""".split())
PLUMBING = set("""log logs logging logger cache caching cached perf performance metrics metric debug debugging migration migrate migrated cleanup fix refactor
internal test tests testing tracking track telemetry sample sampling rollout pct percent killswitch kill timeout retry retries batch batching sync flush
serverside backend worker workers queue hydrate hydration prefetch preload lazy cdn dns ssl tls cert http https ws websocket poll polling cron gc memory
mem cpu thread threads render rendering virtualization virtualized shim polyfill legacy deprecated deprecate fallback fallbacks guard guards check checks
validate validation verify verification parse parser serialize encode decode compress compression gzip chunk chunks bundle bundling webpack vite build
builds ci deploy deployment env envs staging prod production dev canary dogfood sentry datadog otel trace tracing span spans error errors exception
exceptions crash crashes repair patch hotfix bugfix bug bugs issue workaround hack temp tmp old holdout ramp gate gated gating flag flags enable enabled
disable disabled use uses allow allows skip force forced hide hidden show shows mode modes fe be impl implementation optimization optimize optimized
optimisation lookup lookups fetch fetching load loading loader reload throttle debounce noop dummy placeholder stub mock mocks fixture fixtures spec
specs lint format formatter minify sourcemap sourcemaps eager strict loose compat compatibility shimmed interop esm cjs tree shake treeshake""".split())
_WORD = re.compile(r"[A-Za-z]{2,}")
_HUMAN = re.compile(r"[A-Z][a-z]{2,} [A-Za-z]{2,}|[a-z]{3,} [a-z]{3,} [a-z]{3,}")


def words(key: str) -> list[str]:
    parts = re.split(r"[_\-./:\s]+|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", key)
    return [p.lower() for p in parts if _WORD.fullmatch(p)]


def score(o: Observation) -> int:
    ws = words(o.key)
    prod = sum(1 for w in ws if w in PRODUCT)
    plumb = sum(1 for w in ws if w in PLUMBING)
    s = 2 * prod - 2 * plumb
    if o.context and _HUMAN.search(o.context):
        s += 3
    if o.kind in ("config", "catalog", "enum", "hidden", "manifest"):
        s += 1
    if o.kind == "gate" and o.value is False:
        s += 1            # off gates are where unannounced work lives
    if o.kind == "route":
        s += 1 if prod else 0
    if len(ws) >= 5 and prod == 0:
        s -= 1            # long mechanical names
    if _SCOPE.search(o.key) and o.kind in ("gate", "registry", "enum", "catalog", "config"):
        s -= 3            # a permission scope, not a feature
    if _EVENT.search(o.key) and o.kind in ("enum", "registry", "catalog", "string", "hidden"):
        s -= 3            # an analytics event name (SIGN_UP_CLICKED, QUALITY_VIDEO_HEARTBEAT), not a feature
    if o.kind == "route" and _NAV_ROUTE.match(o.key):
        s -= 5            # the public site's own navigation and published posts
    if o.kind == "route" and _PLUMBING_ROUTE.search(o.key):
        s -= 4            # OAuth callbacks, auth flows, API key pages: the plumbing of integrations that already ship (Linear: /connect/jira/callback)
    if not re.search(r"[A-Za-z]{3,}", o.key):
        s -= 6            # a key with no word in it (`1`, `2`: a demo task list's ids) names nothing
    if _SLUG.match(o.key) and o.kind in ("enum", "catalog", "registry", "string", "hidden"):
        s -= 6            # `owner/repo`: a store or GitHub slug in a featured list (Raycast's `florisdobber/claude`), not a feature
    return s


def cluster(key: str) -> str:
    """Sibling cluster: the first two readable segments (`make_local_*`, `loom-agentic-*`)."""
    ws = words(key)
    return "_".join(ws[:2]) if len(ws) >= 2 else (ws[0] if ws else key)


FINDING_MIN = 2          # a key needs one product noun and no plumbing word (or a human phrase in context) to be a finding
KEEP_KINDS = ("subdomain", "job", "pricing", "redirect", "hidden", "robots", "sitemap", "headline")   # already human-facing; never demoted
# permission scopes and CRUD grants read like gates but describe an API surface, not a feature: Stripe's dashboard
# registry alone has 3,600 `*_read` / `*_write` keys
_EVENT = re.compile(r"(?:^|[_-])(?:clicked|viewed|opened|closed|submitted|heartbeat|played|completed|toggled|selected|downloaded|started|scrolled|hovered|dismissed|shown|rendered|loaded|impression|tracked|sent|verified|skipped|failed|succeeded)$", re.I)
_NAV_ROUTE = re.compile(r"^/(?:login|signup|sign-up|signin|logout|register|pricing|docs|blog|changelog|customers|about|careers|jobs|contact|terms|privacy|security|legal|press|help|support|faq|status|enterprise|download|integrations|method|features|product)(?:/[A-Za-z0-9_.\-]+)*/?$", re.I)
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_.-]*/[a-z0-9][a-z0-9_.-]*$", re.I)
_PLUMBING_ROUTE = re.compile(r"/(?:connect|oauth|auth|callback|login|logout|signup|sign-?in|sign-?up|sso|saml|verify|reset-password|magic-link|api-keys?|tokens?|webhooks?)(?:/|$)|/callback$", re.I)
_SCOPE = re.compile(r"(?:^|[_.:-])(?:read|write|create|update|delete|view|edit|manage|admin)$|^(?:can|has|is)_?[a-z]+_?(?:read|write|access|permission)s?$", re.I)


def apply(observations: list[Observation]) -> None:
    """Score every observation; demote low-salience findings to the key list. In place; order untouched."""
    for o in observations:
        o.salience = score(o)
        if o.tier == "finding" and o.kind not in KEEP_KINDS and o.salience < FINDING_MIN:
            o.tier = "key-list"
        elif o.tier == "finding" and o.kind in ("hidden", "subdomain", "job", "pricing") and not re.search(r"[A-Za-z]{3,}", o.key):
            o.tier = "key-list"       # a template fragment (`${e.error?.statusCode||`) is not a hidden surface


def is_finding(o: Observation) -> bool:
    return score(o) >= FINDING_MIN


def novelty(findings: list[Observation], status: dict) -> None:
    """Rank by what is new, not only by what is nameable: inside a sibling cluster where at least one key is
    announced or partially announced, a key with no public mention is the odd one out (Raycast's
    `external-agents` beside six announced organization settings pages) and gains NOVELTY_BOOST; an announced
    key loses the same, so the brief's order and the engine's agree. Keys the engine could not check are
    left alone. In place."""
    by_cluster: dict[str, list[Observation]] = {}
    for o in findings:
        by_cluster.setdefault(cluster(o.key), []).append(o)
    for members in by_cluster.values():
        if len(members) < 2:
            continue
        st = [status.get(o.id, "unchecked") for o in members]
        if not any(x in ("announced", "partial") for x in st):
            continue
        for o, x in zip(members, st):
            if x == "none":
                o.salience += NOVELTY_BOOST
            elif x == "announced":
                o.salience -= NOVELTY_BOOST


NOVELTY_BOOST = 3
