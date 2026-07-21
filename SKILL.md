---
name: bazaar-audit
description: Audit whether a provider's x402 endpoints are discoverable in Coinbase's Bazaar, and diagnose/fix the ones that aren't. Use when the user asks to check Bazaar/x402 discovery or indexing, why their endpoints don't show up in Bazaar search, whether their x402 API is indexed/searchable, or to audit an x402 provider by local codebase, domain/host, or provider name. Triggers include "/bazaar-audit", "are my endpoints in the bazaar", "why isn't my x402 endpoint showing up", "check bazaar indexing", "audit x402 discovery".
---

# Bazaar Audit

Audit x402 endpoints for Bazaar discoverability, bucket them by failure mode, and report the fix
for each. Read `references/mechanics.md` for the underlying model — the buckets (A/B/C/D), the
validator fields, and the remediation mechanics all come from there. Read it before interpreting
results or explaining fixes.

## Step 1 — Scope the audit (ask the user)

Use the **AskUserQuestion** tool to ask what to audit. Offer these options:

- **Local codebase** — find the OpenAPI spec or x402 middleware config in the current repo.
- **Domain / host** — audit a live host (e.g. `api.example.com`); pull its OpenAPI or probe.
- **Provider name** — a name/brand to look up in the Bazaar (e.g. "Nansen").

If the user already named a target in their message, skip the question and proceed. You may also ask
(only if unclear) whether they want a **read-only audit** (default) or to also **remediate** broken
endpoints with paid calls (costs money — see Step 5).

## Step 2 — Build the endpoint list

The audit needs the *full* payable endpoint list, not just what's already surfaced.

- **Local codebase:** locate the spec (`Glob` for `**/openapi.{json,yaml,yml}`, `**/swagger.json`;
  or x402 middleware config). Then:
  `scripts/extract_endpoints.py <spec> [--base-url https://host] [--marker x-payment-info]`
  It emits `METHOD URL` lines. If no operation carries the payment marker it falls back to all
  POST/PUT/PATCH and warns — pass `--marker` if the repo uses a different extension, or `--all`.
- **Domain / host:** try to fetch the spec (`https://<host>/openapi.json`, `/openapi.yaml`,
  `/swagger.json`, `/docs`, `/.well-known/`). Save it, then run `extract_endpoints.py`. If no spec
  is reachable, ask the user for the spec URL/path or an explicit endpoint list.
- **Provider name:** search the Bazaar (`mcp__bazaar__search_resources`, e.g. by `query` or by the
  provider's `payTo` address once known) to find what's *already* surfaced — but that only shows
  surfaced endpoints. For a complete audit still obtain the OpenAPI spec (ask the user where it is).
  If a spec truly isn't available, audit only the surfaced set and say so explicitly.

## Step 3 — Validate every endpoint (free)

Pipe the endpoint list through the validator sweep:

```bash
scripts/extract_endpoints.py <spec> --base-url https://<host> | scripts/validate_endpoints.py --out /tmp/bazaar_audit.json
```

(or feed a hand-made list; each line is `METHOD URL`, default POST). It classifies each endpoint as
**A_rejected**, **B_never_indexed**, or **active** (C/D candidate), and records the `parse` error,
price, and `lastCrawledAt`. It uses only the read-only CDP validator — no payment.

## Step 4 — Split active endpoints into C vs D (search presence)

The script cannot query Bazaar search. For **each** `active` endpoint, call
`mcp__bazaar__search_resources` with `urlSubstring` = the full path and `limit: 1`:

- Non-empty `tools` → **D (working)**. Capture the `Quality: N calls ... last called <date>` from
  the description.
- Empty with `partialResults:false` → **C (active but not searchable)**.

Do these per-endpoint (targeted), not via one broad sweep — broad sweeps cap at 20 results and
can't prove absence. Batch the calls in parallel where possible.

## Step 5 — Report (and optionally remediate)

Produce a summary table: counts for A/B/C/D and, per bucket, the specific endpoints + root cause +
fix (pull the exact wording/fixes from `references/mechanics.md`):

- **A rejected** → provider-side discovery-config bug. Show the `parse` error and offending field;
  give a reproduce curl and the concrete schema fix.
- **B never-indexed** → never had a successful paid call. Fix: one successful (200) paid call.
- **C active-not-searchable** → paid usage lapsed (~30-day window). Fix: a paid 200 / real traffic.
- **D working** → fine.

**Remediation (only with explicit user consent):** paying a successful call to a B or C endpoint
re-crawls it within ~1s (search surfaces after a lag). This requires an x402 wallet
(e.g. `mcp__sponge__paid_fetch` or another paid-fetch tool). Before spending:
1. Sum the prices (from the report) and show the total; flag any expensive endpoint.
2. Build **valid** request bodies from the OpenAPI required fields + enums (a 4xx/5xx still charges
   but does NOT index — see mechanics.md "Paying safely").
3. After paying, re-validate `index` immediately (should flip to active), and recheck Bazaar search
   after a delay to confirm surfacing.
Make clear this is a workaround, not a durable fix — visibility needs ongoing real traffic.

## Notes

- The audit is read-only by default and safe to run repeatedly.
- `references/mechanics.md` is the source of truth for definitions, the validator contract, and
  remediation behavior — cite it rather than re-deriving.
