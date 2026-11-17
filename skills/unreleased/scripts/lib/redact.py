"""Redact (R10): never print keys/secrets, org or customer ids, customer-named gates and configs, or
dedicated-deployment hosts; demote A/B arm names and internal tooling to the key list. The log never
contains the redacted values, only kinds, keys and reasons.
"""
from __future__ import annotations
import re
from schema import Observation, Subdomain

_SECRET_KEY = re.compile(r"(?:api[_-]?key|client[_-]?key|secret|token|password|private[_-]?key|sdk[_-]?key|access[_-]?key)", re.I)
_SECRET_VALUE = re.compile(r"(?:^|[^A-Za-z0-9])(?:sk_live_|sk_test_|pk_live_|rk_live_|rk_test_|AKIA[0-9A-Z]{12,}|xox[abp]-|phc_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{60,}|AIza[0-9A-Za-z_\-]{30,}|sk-(?:ant|proj)-[A-Za-z0-9_\-]*[A-Za-z0-9_]{20}|glpat-(?=[A-Za-z0-9_\-]{0,19}\d)[A-Za-z0-9_\-]{20}|npm_[A-Za-z0-9]{30,}|client-[A-Za-z0-9]{32,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|[0-9a-f]{40,})")
# the whole token after a secret prefix, for scrubbing (the detector above only needs the prefix)
_SECRET_SPAN = re.compile(r"(^|[^A-Za-z0-9])(?:sk_live_|sk_test_|pk_live_|rk_live_|rk_test_|AKIA[0-9A-Z]{12,}|xox[abp]-|phc_|client-|eyJ|gh[pousr]_(?=[A-Za-z0-9]{30})|github_pat_(?=[A-Za-z0-9_]{60})|AIza(?=[0-9A-Za-z_\-]{30})|sk-(?:ant|proj)-(?=[A-Za-z0-9_\-]*[A-Za-z0-9_]{20})|glpat-(?=[A-Za-z0-9_\-]{0,19}\d)|npm_(?=[A-Za-z0-9]{30}))[A-Za-z0-9_\-.]*")
_IDS_KEY = re.compile(r"(?:org[_-]?ids?|orgs|tenant|single[_-]?tenant|dedicated|customer[_-]?ids?|account[_-]?ids?|workspace[_-]?ids?|allowlist|allow_list|whitelist)$|(?:_orgs?_|orgs$|Orgs$|_tenant|_tenants|OrgIds?$)", re.I)
_IDS_VALUE = re.compile(r"\b\d{7,}\b.*\b\d{7,}\b")       # two long ids; quotas and windows (100000, 86400) are not ids
_ID_ANY = re.compile(r"\b\d{5,}\b")
_TOKENISH = re.compile(r"^[A-Za-z0-9_\-./+=:]{16,}$")           # no spaces: a token, not a label
_CUSTOMER_GATE = re.compile(r"^[a-z]+s_specials$|_specials$|^for_[a-z]+_(?:org|team|workspace)$|_(?:org|workspace)_(?:override|exception)s?$", re.I)
_AB_ARM = re.compile(r"(?:^|[-_/])(?:control|treatment|variant|arm)(?:[-_][a-z0-9]{1,3})?$|[-_](?:a|b|c|d)$|^(?:half-price|first-month-(?:one|five|free)|[a-z-]*-price-test-[a-z])$|[-_](?:aa|ab)$|_v[1-9]$", re.I)
_INTERNAL = re.compile(r"(?:^|[-_])(?:admin|internal|staff|employee|dogfood|migration|debug|qa|canary|sandbox|impersonat)", re.I)
_PRICE_TEST = re.compile(r"price[-_]?test|pricing[-_]?(?:exp|test|variant)|[-_]discount[-_]?(?:v?\d|arm)", re.I)
COMPANY_LABELS = {"apple", "amazon", "google", "microsoft", "meta", "facebook", "openai", "nvidia", "tesla", "netflix", "salesforce", "adobe", "oracle", "ibm", "intel",
                  "cisco", "uber", "airbnb", "stripe", "shopify", "spotify", "disney", "walmart", "target", "nike", "samsung", "sony", "paypal", "visa", "mastercard",
                  "jpmorgan", "goldman", "citi", "boeing", "ford", "gm", "toyota", "bmw", "coca-cola", "pepsi", "anthropic", "deepmind", "xai", "bytedance", "tiktok"}


_TOKEN_KEY = re.compile(r"^(?=[A-Za-z0-9_\-.:]{28,}$)(?=.*\d)(?=.*[A-Za-z])(?!.*[a-z]{4,}[_\-][a-z]{3,})")   # long, mixed, no words: a token, not a name
_PUBLIC_ID_KEY = re.compile(r"^\d{10,}-[a-z0-9]{20,}\.apps\.googleusercontent\.com$|^price_[A-Za-z0-9]{20,}$|^prod_[A-Za-z0-9]{12,}$|^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _is_secret(o: Observation) -> bool:
    # the key itself can be the secret: a Salesforce consumer key or an API token used as a map key (Linear's app bundle)
    if _TOKEN_KEY.match(o.key) or _SECRET_VALUE.search(o.key):
        return True
    val = "" if o.value is None else str(o.value)
    if _SECRET_VALUE.search(val) or (o.kind in ("config", "inline") and _SECRET_VALUE.search(o.context or "")):
        return True
    # a key that says key/secret/token is a secret only when it carries a string value that could be one
    return bool(_SECRET_KEY.search(o.key) and isinstance(o.value, str) and _TOKENISH.match(o.value) and not o.value.startswith(("http", "/")))


def _is_ids(o: Observation) -> bool:
    """Id lists live in values. Context is minified code full of webpack module ids (`i(218744)`), so it
    only counts when the key itself names orgs/tenants/customers."""
    val = "" if o.value is None else str(o.value)
    if _PUBLIC_ID_KEY.match(o.key):
        return True                                   # OAuth client ids, price/product ids, UUIDs: identifiers, not features
    if _IDS_VALUE.search(val):
        return True                                   # two long ids in the value, whatever the key says
    if _IDS_KEY.search(o.key) and (_ID_ANY.search(val) or _IDS_VALUE.search(o.context or "")):
        return True                                   # a key that names orgs/tenants/customers with any id in it
    # an org/customer list config with a structured value is ids even when the digits are not in the context window
    return bool(re.search(r"(?:^[a-z]+Orgs?$|_org_ids?$|_orgs$|OrgIds?$|_tenant_ids?$|_customer_ids?$|single_tenant)", o.key) and o.kind in ("config", "inline") and val in ("[]", "{}", "ref"))


def key_is_sensitive(key: str) -> bool:
    """The key-level part of the rules, for lists that carry only keys (a diff's added/removed from an older baseline)."""
    return bool(_TOKEN_KEY.match(key) or _SECRET_VALUE.search(key) or _PUBLIC_ID_KEY.match(key) or _CUSTOMER_GATE.search(key) or _company_named(key))


def redact_diff(d) -> int:
    """Drop sensitive keys from every list in a Diff (a baseline recorded by an older engine may still hold them)."""
    n = 0
    for name in ("added", "removed", "routes_added"):
        before = getattr(d, name); after = [k for k in before if not key_is_sensitive(k)]; n += len(before) - len(after); setattr(d, name, after)
    before = d.flipped; d.flipped = [x for x in before if not key_is_sensitive(x["key"])]; n += len(before) - len(d.flipped)
    return n


def redact(observations: list[Observation], product_domain: str, extra_scrub: list[str] | None = None) -> tuple[list[Observation], list[str]]:
    """Removal is driven by values (secrets, id lists, customer-specific gates), never by a word in a key:
    a gate named `password` with value false is a feature gate, not a secret. `extra_scrub` carries literals
    withheld elsewhere (company-named hosts from the certificate logs) that bundles also mention."""
    kept, log = [], []
    scrub: set[str] = set(extra_scrub or [])   # literals that must not survive in any context window either
    for o in observations:
        k = o.key
        if _is_secret(o):
            log.append(f"redacted {o.kind} {_blind(k) if (_TOKEN_KEY.match(k) or _PUBLIC_ID_KEY.match(k) or _SECRET_VALUE.search(k)) else k}: secret-like value")
            if isinstance(o.value, str) and len(o.value) >= 12: scrub.add(o.value)
            continue
        if _is_ids(o):
            log.append(f"redacted {o.kind} {_blind(k)}: org/customer identifiers")   # the key names the customer
            if isinstance(o.value, str) and len(o.value) >= 8: scrub.add(o.value)
            scrub.add(k); continue
        if _CUSTOMER_GATE.search(k) or _company_named(k):
            log.append(f"redacted {o.kind} {_blind(k)}: customer-specific gate"); scrub.add(k); continue
        if _AB_ARM.search(k) or _PRICE_TEST.search(k):
            if o.tier == "finding":
                o.tier = "key-list"; log.append(f"demoted {o.kind} {k}: A/B arm or price-test name")
        elif _INTERNAL.search(k):
            if o.tier == "finding":
                o.tier = "key-list"; log.append(f"demoted {o.kind} {k}: internal tooling")
        kept.append(o)
    # a removed gate's name is still quoted in the context window of the gate next to it (Notion:
    # `checkGate({gateName:"ai_image_generation"}),…checkGate({gateName:"alices_specials"})`)
    scrub = {x for x in scrub if len(x) >= 6}
    n = 0
    for o in kept:
        # a secret next to any key reaches the context window of calls, routes, hidden and strings too
        if o.context:
            new = _SECRET_SPAN.sub(lambda m: m.group(1) + "[redacted]", o.context) if _SECRET_VALUE.search(o.context) else o.context
            for lit in scrub:
                if lit in new:
                    new = new.replace(lit, "[redacted]")
            if new != o.context:
                o.context = new; n += 1
        if isinstance(o.value, str) and o.value and _SECRET_VALUE.search(o.value):
            o.value = "[redacted]"; n += 1
    if n:
        log.append(f"scrubbed {n} context window(s) or value(s) quoting a redacted literal")
    return kept, log


def _blind(key: str) -> str:
    """The log names a removed customer gate by a hash: the key is the customer's name."""
    import hashlib
    return f"<{hashlib.sha1(key.encode()).hexdigest()[:8]}>"


_DEDICATED = {"custom", "dedicated", "tenant", "cluster", "override", "exception", "exceptions", "special", "specials", "only", "contract", "deal", "pilot"}


def _company_named(key: str) -> bool:
    """`netflix_dedicated_cluster_enabled`, `apple_custom_fonts`: a company label leading a key about a dedicated or
    custom arrangement. Not `google_sso`, `anthropic-claude-5.5-opus`, `stripe_checkout`: those name integrations
    and models, which are the product's work (Figma has 37 google_* keys, all SSO and Drive)."""
    import salience
    ws = salience.words(key)
    return len(ws) >= 2 and ws[0] in COMPANY_LABELS and any(w in _DEDICATED for w in ws[1:3])


def redact_subdomains(subs: list[Subdomain]) -> tuple[list[Subdomain], list[str]]:
    """Hosts whose first label names a well-known company are a customer's dedicated deployment, not a product signal."""
    kept, flagged = [], []
    for s in subs:
        labels = s.name.lower().split(".")
        apex_labels = set((s.apex or "").lower().split(".")) if s.apex else set()
        own = [l for l in labels if l not in apex_labels][:-2] if not apex_labels else [l for l in labels if l not in apex_labels]
        # any label below the apex: errors.<company>.<product>.com is a customer's dedicated error host, not a product surface
        if any(l in COMPANY_LABELS for l in own):
            flagged.append(s.name)
        else:
            kept.append(s)
    return kept, flagged
