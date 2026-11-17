---
title: "Vendor-marker windows wipe first-party keys next to a vendor name inside a data map"
module: noise
date: 2026-10-30
problem_type: logic_error
component: service_layer
severity: high
symptoms:
  - "Figma's ff_ai_credit_requests, enable_skills_in_ds_home and announce_agent_weave_ga_date vanished from every tier"
  - "golden recall for Figma stuck at 0.885 while the extractors found all three keys"
root_cause: logic_error
resolution_type: code_fix
tags: [noise, vendors, redaction, false-positive]
---

# Vendor-marker windows wipe first-party keys next to a vendor name inside a data map

## Problem

`noise.vendor_spans` marks ±600 bytes around every vendor marker as vendor code, and `assign_tiers` drops
any observation whose offset falls inside. Two first-party things triggered it on Figma's login page:

- Sentry's marker `_experiments` matched as a substring of the gate `ce_al_experiments_on`.
- The config value `"datadog_rum_site":"datadoghq.com"` matched the Datadog marker.

Either way the window covered 1.2 KB of Figma's own gate map, and the neighbours were dropped before
salience or redaction ever saw them. The same mechanism will fire on any product whose flags mention a
vendor (`sentry_sample_rate`, `launchdarkly_client_id`).

## Solution

Two rules in `scripts/lib/noise.py`:

1. Markers match at identifier boundaries: a marker that starts or ends with an identifier character
   cannot be preceded or followed by one.
2. An observation read out of a parsed map (`o.group` set) is judged by its own key and value, never by a
   vendor name nearby. Spans still apply to loose observations (routes, strings, call sites in code).

`tests/test_noise_redact_crosscheck.py::test_vendor_markers_inside_a_first_party_map_do_not_wipe_its_neighbours`
pins both.

## Prevention

Before adding a marker to `scripts/lib/vendors/*.json`, grep the corpus for it as a substring of
first-party keys; prefer markers that are vendor API names (`DD_RUM`, `Sentry.init(`) over generic words.
Any rule that removes an observation should be driven by the observation's own key or value, not its
neighbourhood (the redaction module follows the same principle: `_is_secret`, `_is_ids` are value-driven).
