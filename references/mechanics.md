# x402 / Coinbase Bazaar — indexing & search mechanics (reference)

The "why" behind the audit. Read this when interpreting results or explaining fixes.

## Three layers, none implies the next

**(a) endpoint advertises x402** → **(b) facilitator indexes it** (`index.active:true`) →
**(c) Bazaar search surfaces it**.

- **Indexed ≠ searchable.** An endpoint can be `index.active:true` and still return nothing from
  Bazaar search.
- **Search visibility tracks recent *successful paid usage*, not crawl recency.** No paid calls in
  the trailing ~30 days → it drops from search even while still "indexed."

## The CDP validator (free, unauthenticated, read-only)

```bash
curl -s -X POST https://api.cdp.coinbase.com/platform/v2/x402/validate \
  -H "Content-Type: application/json" \
  -d '{"resource":"https://<host>/<path>","method":"POST"}'
```

Ref: `https://docs.cdp.coinbase.com/api-reference/v2/rest-api/x402-facilitator/validate-x402-endpoint`
Same logic as the live indexing pipeline; no payment, no side effects. Key fields:

- `valid` (bool); `simulation: { outcome: accepted|rejected, rejectionReason }`
- `preflight: [...]` — each `{check, passed, severity}`; `required` blocks indexing, `advisory` only
  affects ranking. The `parse` check validates the discovery extension's schema vs its example.
- `index` — present only if indexed: `{active, lastCrawledAt}`. `index: null` ⇒ never indexed.
- `paymentRequirements.accepts[].amount` — price in token base units (USDC → `/1e6` for USD).
- `bazaarExtension` / `extensions.bazaar` — the discovery `info` example + JSON `schema`.

## Bucket definitions (what the audit reports)

| Bucket | Signal | Meaning | Fix |
|---|---|---|---|
| **A rejected** | `simulation.outcome=rejected` (a required preflight, usually `parse`, failed) | Discovery-config bug | Provider fixes the extension |
| **B never-indexed** | `valid`+`accepted` but `index:null` | Never had a successful paid call | One successful (200) paid call |
| **C active-not-searchable** | `index.active:true` but absent from Bazaar search | Paid usage lapsed (~30d) | A paid 200 / real traffic |
| **D working** | `index.active:true` and in search | Fine | — |

## Checking search presence reliably

Use the Bazaar search tool with a **per-endpoint** query: `urlSubstring` = the full path, and read
`partialResults`. Non-empty `tools` ⇒ surfaced; empty with `partialResults:false` ⇒ genuinely not
surfaced. Do **not** infer absence from a broad `payTo`/`query` sweep — those cap at 20 with
`partialResults:true`, so a missing item may just be on a later page. Search result descriptions
carry `Quality: N calls from M unique payers over the last 30 days, last called <date>`; a
freshly-surfaced endpoint has **no `Quality:` line yet** (a useful "just added" tell).

## The common rejection (bucket A) — schema/example type mismatch

`parse` error like `Invalid type. Expected: object, given: string`: the discovery extension's schema
declares a field one type while its example sends another. Frequent root cause: a schema generator
that doesn't resolve `anyOf: [ $ref → string enum ]` and emits `"object"`, while the example
correctly sends the enum string. Fix = make the declared `type` match what the endpoint actually
accepts (verify against the OpenAPI source and/or a live call). Provider-side generator bug, not a
validator quirk. Report the exact field + a reproduce curl.

## Remediation mechanics (buckets B and C) — verified empirically

- **A successful (HTTP 200) paid call re-crawls the endpoint immediately** — `index.lastCrawledAt`
  updates to the call second; `index:null` flips to `active`.
- **Payment ≠ success.** x402 **settles before the endpoint executes**, so a 4xx/5xx still costs
  money but does **not** trigger a crawl/index. (Verified: a 422 bad-body and a 500 timeout both
  paid but did not index; the corrected 200 retry did.)
- **Search-surfacing lags indexing** by a variable amount (~1–40 min observed). Confirm indexing
  immediately via the validator; recheck *search* later.
- This is a **workaround, not a durable fix** — visibility decays again once paid usage falls
  outside the ~30-day window. Durable answer = real user traffic.

## Paying safely (if remediating)

- Build valid request bodies from the OpenAPI spec's required fields + enums **before** paying; a
  wrong body → 422 → wasted fee → no benefit.
- `additionalProperties:false` is common — send **only** declared fields (an extra field can 422).
- Use realistic inputs (real tx hashes / addresses / token mints); heavy history endpoints can
  time out (500) on high-activity inputs — prefer a low-activity input for a clean 200.
- Confirm the response was **200**, not merely that payment settled.
- Always get explicit user consent + show a summed cost estimate before spending; flag any
  unusually expensive endpoint (agent/LLM endpoints can be dollars, not cents).

## Open questions (state honestly if they come up)

- Exact search-surfacing lag / determinism (observed 1–40 min).
- Exact `Quality` threshold & window for surfacing (≥1 paid 200 within ~30d appeared sufficient).
- Whether errored paid calls count toward the `Quality` counter.
- Bazaar's internal registry↔search replication is a black box; "indexed but not searchable" was
  reproducible but its internal cause is not observable.
