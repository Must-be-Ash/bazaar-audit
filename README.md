# bazaar-audit

> **Not maintained.** x402 and the services this uses may have changed since it was built; check the latest x402 docs before relying on it.

A [Claude Code](https://docs.claude.com/en/docs/claude-code) **skill** that audits whether an
x402 API's endpoints are discoverable in [Coinbase's Bazaar](https://docs.cdp.coinbase.com/x402) —
and diagnoses/fixes the ones that aren't.

Run `/bazaar-audit`. It asks what to audit (local codebase, a domain/host, or a provider name),
builds the full payable-endpoint list, validates each against the CDP facilitator, checks Bazaar
search presence, buckets every endpoint, and reports the fix for each.

## Why

In x402/Bazaar there are three separate layers, and none implies the next:

**endpoint advertises x402** → **facilitator indexes it** (`index.active`) → **Bazaar search surfaces it**

So "indexed" does **not** mean "searchable." Search visibility tracks recent *successful paid
usage*, not crawl recency. This skill pinpoints which layer each endpoint is stuck at.

## Buckets it reports

| Bucket | Signal | Fix |
|---|---|---|
| **A — rejected** | validator rejects the discovery config (usually a schema/example type mismatch) | provider fixes the extension |
| **B — never indexed** | valid but `index: null` (never had a successful paid call) | one successful (200) paid call |
| **C — active, not searchable** | `index.active: true` but absent from search (paid usage lapsed ~30d) | a paid 200 / real traffic |
| **D — working** | indexed and in search | — |

## Install

Drop the folder into your Claude Code skills directory:

```bash
git clone https://github.com/<you>/bazaar-audit ~/.claude/skills/bazaar-audit
```

Then invoke it in Claude Code with `/bazaar-audit`.

## Layout

```
SKILL.md                    # workflow + trigger metadata
references/mechanics.md     # the model, validator contract, remediation behavior
scripts/
  extract_endpoints.py      # pull payable endpoints from an OpenAPI spec
  validate_endpoints.py     # CDP-validate sweep → buckets + parse errors + prices + crawl dates
```

The scripts use only the free, read-only CDP validator (`POST /platform/v2/x402/validate`) — no
payments. Optional remediation (paying to index/surface an endpoint) happens only with explicit
consent and requires an x402 wallet.
