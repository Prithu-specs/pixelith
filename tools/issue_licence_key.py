#!/usr/bin/env python3
"""Issue a Pixelith licence key.  FOR PGA TECH SOLUTIONS ONLY.

Requires the Ed25519 private key, which must never be committed or shared.
The matching public key is compiled into pixelith/licensing.py.

    python tools/issue_licence_key.py --tier personal --holder "Jane Doe"
    python tools/issue_licence_key.py --tier commercial --holder "Acme Ltd"
"""
from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path

DEFAULT_KEY = Path.home() / ".pixelith-licensing-private-key.pem"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", required=True, choices=("personal", "commercial"))
    ap.add_argument("--holder", required=True,
                    help="person for a personal key, company for a commercial one")
    ap.add_argument("--order", default="", help="your order or invoice reference")
    ap.add_argument("--private-key", type=Path, default=DEFAULT_KEY)
    args = ap.parse_args()

    if not args.private_key.exists():
        print(f"private key not found at {args.private_key}")
        return 2

    from cryptography.hazmat.primitives import serialization

    priv = serialization.load_pem_private_key(
        args.private_key.read_bytes(), password=None
    )
    claims = {
        "tier": args.tier,
        "holder": args.holder,
        "issued": int(time.time()),
        "licensor": "PGA Tech Solutions",
    }
    if args.order:
        claims["order"] = args.order

    body = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
    sig = priv.sign(body)
    b = lambda x: base64.urlsafe_b64encode(x).decode().rstrip("=")  # noqa: E731
    token = f"{b(body)}.{b(sig)}"

    price = {"personal": "$10", "commercial": "$200"}[args.tier]
    print(f"\nPixelith {args.tier} licence for {args.holder}  ({price}, one-time)\n")
    print(token)
    print("\nThe customer activates it with:\n")
    print(f"    pixelith activate {token[:28]}...\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
