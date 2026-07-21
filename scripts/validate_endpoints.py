#!/usr/bin/env python3
"""Validate x402 endpoints against Coinbase's CDP facilitator and bucket them.

Reads endpoint URLs (one per line, optional "METHOD URL"; default POST; '#' comments
ignored) from a file argument or stdin. Runs the read-only CDP validate API on each and
classifies into:
  A. rejected      -> simulation.outcome == "rejected" (config bug; blocks indexing)
  B. never_indexed -> valid/accepted but index is null (never had a successful paid call)
  active           -> index.active == true (candidate C or D; search presence decided elsewhere)

Search presence (C vs D) is NOT determined here -- it requires the Bazaar search tool.
This script only covers the free, unauthenticated CDP validator.

Outputs a JSON report to --out (default /tmp/bazaar_audit.json) and prints a summary table.
"""
import argparse, concurrent.futures, json, sys, urllib.request, urllib.error

VALIDATE_URL = "https://api.cdp.coinbase.com/platform/v2/x402/validate"


def parse_lines(text):
    eps = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 1:
            eps.append(("POST", parts[0]))
        else:
            eps.append((parts[0].upper(), parts[1]))
    return eps


def validate(method, url, timeout=45):
    body = json.dumps({"resource": url, "method": method}).encode()
    req = urllib.request.Request(
        VALIDATE_URL, data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.load(r)
    except Exception as e:
        return {"method": method, "url": url, "error": str(e)}
    idx = j.get("index")
    sim = j.get("simulation") or {}
    parse_err = None
    for c in j.get("preflight", []):
        if c.get("check") == "parse" and not c.get("passed"):
            parse_err = c.get("detail")
    price = None
    try:
        acc = j["paymentRequirements"]["accepts"][0]
        price = int(acc["amount"]) / 1e6  # USDC-style base units -> USD (approx)
    except Exception:
        pass
    return {
        "method": method, "url": url,
        "valid": j.get("valid"),
        "outcome": sim.get("outcome"),
        "rejectionReason": sim.get("rejectionReason"),
        "index_null": idx is None,
        "active": (idx or {}).get("active") if idx else None,
        "lastCrawledAt": (idx or {}).get("lastCrawledAt") if idx else None,
        "parse_err": parse_err,
        "price_usd": price,
    }


def bucket(r):
    if r.get("error"):
        return "error"
    if r.get("outcome") == "rejected":
        return "A_rejected"
    if r.get("index_null"):
        return "B_never_indexed"
    if r.get("active"):
        return "active"  # C or D -- needs Bazaar search check
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("infile", nargs="?", help="file with endpoints (default: stdin)")
    ap.add_argument("--out", default="/tmp/bazaar_audit.json")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    text = open(args.infile).read() if args.infile else sys.stdin.read()
    eps = parse_lines(text)
    if not eps:
        print("No endpoints provided.", file=sys.stderr)
        sys.exit(1)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(validate, m, u): (m, u) for m, u in eps}
        for f in concurrent.futures.as_completed(futs):
            results.append(f.result())

    results.sort(key=lambda r: r["url"])
    for r in results:
        r["bucket"] = bucket(r)
    json.dump(results, open(args.out, "w"), indent=1)

    counts = {}
    for r in results:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    print(f"Checked {len(results)} endpoints -> {args.out}\n")
    for b in ["A_rejected", "B_never_indexed", "active", "other", "error"]:
        if counts.get(b):
            print(f"  {b:16} {counts[b]}")
    print()
    for r in results:
        if r["bucket"] == "A_rejected":
            print(f"  [A] {r['url']}\n      {r.get('parse_err') or r.get('rejectionReason')}")
    for r in results:
        if r["bucket"] == "B_never_indexed":
            print(f"  [B never-indexed] ${r.get('price_usd')}  {r['url']}")
    for r in results:
        if r["bucket"] == "active":
            print(f"  [active -> check search] {r['url']}  (crawled {r.get('lastCrawledAt')})")
    for r in results:
        if r["bucket"] in ("error", "other"):
            print(f"  [{r['bucket']}] {r['url']}  {r.get('error','')}")
    print("\nNext: for each 'active' endpoint, check Bazaar search presence to split C (absent) vs D (present).")


if __name__ == "__main__":
    main()
