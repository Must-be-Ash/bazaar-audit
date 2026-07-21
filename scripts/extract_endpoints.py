#!/usr/bin/env python3
"""Extract x402-payable endpoints from an OpenAPI spec.

Emits "METHOD https://host/path" lines (pipe into validate_endpoints.py).

By default, includes operations that carry a payment marker extension (default
'x-payment-info', configurable via --marker). If no operation has the marker, falls back
to ALL POST/PUT/PATCH operations and warns on stderr.

Base URL resolution: --base-url wins; else the spec's servers[0].url; else error.
Supports JSON specs natively; YAML only if PyYAML is installed.
"""
import argparse, json, sys


def load_spec(path):
    raw = open(path).read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml  # optional
        except ImportError:
            sys.exit("Spec is not JSON and PyYAML is not installed. Convert to JSON or `pip install pyyaml`.")
        return yaml.safe_load(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", help="path to openapi.json / .yaml")
    ap.add_argument("--base-url", help="override base URL (e.g. https://api.example.com)")
    ap.add_argument("--marker", default="x-payment-info",
                    help="operation-level extension marking payable endpoints")
    ap.add_argument("--all", action="store_true", help="include all POST/PUT/PATCH ops")
    args = ap.parse_args()

    spec = load_spec(args.spec)
    base = args.base_url
    if not base:
        servers = spec.get("servers") or []
        if servers and servers[0].get("url"):
            base = servers[0]["url"].rstrip("/")
    if not base:
        sys.exit("No base URL: pass --base-url or ensure the spec has servers[].url")

    methods = {"post", "put", "patch"}
    marked, all_ops = [], []
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for m, op in item.items():
            if m.lower() not in methods or not isinstance(op, dict):
                continue
            full = f"{m.upper()} {base}{path}"
            all_ops.append(full)
            if args.marker in op:
                marked.append(full)

    out = marked
    if args.all or not marked:
        if not marked:
            print(f"warning: no operation has '{args.marker}'; emitting all POST/PUT/PATCH ops",
                  file=sys.stderr)
        out = all_ops

    for line in out:
        print(line)
    print(f"\n# {len(out)} endpoints", file=sys.stderr)


if __name__ == "__main__":
    main()
