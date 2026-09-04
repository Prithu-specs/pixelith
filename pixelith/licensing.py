# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Licence keys and the usage ledger.

Keys are Ed25519-signed tokens verified offline against a public key compiled
into the application. Nothing contacts a server: activation works on a machine
that has never been online, and PGA Tech Solutions issues keys with the
matching private key, which lives nowhere near this repository.

What this can and cannot do is worth stating plainly, because the source is
public. Signature verification stops someone typing in a made-up key. It does
not stop someone editing this file. The ledger is signed so that casual
editing is detected, not so that it is impossible. The aim is to make paying
the easy path, not to win an arms race against a determined user.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from .config import CACHE_DIR

PUBLIC_KEY_B64 = "h6c6tndgY6oFmVePWSMB87Ijls92xLiWmLeV9TkD5Po="

LICENCE_FILE = CACHE_DIR / "licence.json"
LEDGER_FILE = CACHE_DIR / "usage.json"

TIER_FREE = "free"
TIER_PERSONAL = "personal"
TIER_COMMERCIAL = "commercial"
PAID_TIERS = (TIER_PERSONAL, TIER_COMMERCIAL)


class LicenceError(RuntimeError):
    pass


# --------------------------------------------------------------- licence keys


def _public_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )

    return Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64))


def verify_key(token: str) -> dict:
    """Verify a licence token and return its claims. Raises on any problem."""
    from cryptography.exceptions import InvalidSignature

    token = "".join(token.split())
    if token.count(".") != 1:
        raise LicenceError("that does not look like a Pixelith licence key.")
    body_b64, sig_b64 = token.split(".")
    try:
        body = base64.urlsafe_b64decode(body_b64 + "=" * (-len(body_b64) % 4))
        sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
    except (ValueError, TypeError) as exc:
        raise LicenceError("the key is malformed.") from exc

    try:
        _public_key().verify(sig, body)
    except InvalidSignature as exc:
        raise LicenceError(
            "this key's signature is not valid. Keys are issued by PGA Tech "
            "Solutions; if you bought one, check it was copied in full."
        ) from exc

    try:
        claims = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LicenceError("the key's contents are unreadable.") from exc

    if claims.get("tier") not in PAID_TIERS:
        raise LicenceError(f"unknown licence tier {claims.get('tier')!r}.")
    return claims


def activate(token: str) -> dict:
    claims = verify_key(token)
    LICENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LICENCE_FILE.write_text(
        json.dumps({"token": token, "claims": claims, "activated": time.time()},
                   indent=2)
    )
    return claims


def deactivate() -> bool:
    if LICENCE_FILE.exists():
        LICENCE_FILE.unlink()
        return True
    return False


def active_licence() -> dict | None:
    """The stored licence, re-verified on every read."""
    if not LICENCE_FILE.exists():
        return None
    try:
        stored = json.loads(LICENCE_FILE.read_text())
        return verify_key(stored["token"])
    except (json.JSONDecodeError, KeyError, LicenceError, OSError):
        return None


def current_tier() -> str:
    claims = active_licence()
    return claims["tier"] if claims else TIER_FREE


# --------------------------------------------------------------- usage ledger


@dataclass
class Usage:
    install_id: str
    images: int = 0
    video_bytes: int = 0
    first_run: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


def _ledger_mac(data: dict) -> str:
    """Detects casual editing. Not a security boundary - the key is right here."""
    blob = json.dumps(
        {k: data[k] for k in ("install_id", "images", "video_bytes", "first_run")},
        sort_keys=True,
    ).encode()
    key = hashlib.sha256(b"pixelith-ledger:" + data["install_id"].encode()).digest()
    return hmac.new(key, blob, hashlib.sha256).hexdigest()


def load_usage() -> Usage:
    if LEDGER_FILE.exists():
        try:
            raw = json.loads(LEDGER_FILE.read_text())
            usage = Usage(
                install_id=raw["install_id"],
                images=int(raw.get("images", 0)),
                video_bytes=int(raw.get("video_bytes", 0)),
                first_run=float(raw.get("first_run", 0.0)),
            )
            if raw.get("mac") != _ledger_mac(usage.as_dict()):
                # Tampered or hand-edited. Do not silently trust a reset.
                usage.tampered = True  # type: ignore[attr-defined]
            return usage
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            pass
    usage = Usage(install_id=secrets.token_hex(8), first_run=time.time())
    save_usage(usage)
    return usage


def save_usage(usage: Usage) -> None:
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = usage.as_dict()
    data["mac"] = _ledger_mac(data)
    tmp = LEDGER_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, LEDGER_FILE)


def record(images: int = 0, video_bytes: int = 0) -> Usage:
    usage = load_usage()
    usage.images += max(0, int(images))
    usage.video_bytes += max(0, int(video_bytes))
    save_usage(usage)
    return usage


def install_id_bytes() -> bytes:
    return bytes.fromhex(load_usage().install_id)


# ----------------------------------------------------------------- allowances


class AllowanceExceeded(RuntimeError):
    """Raised when a job would go past the free tier."""

    def __init__(self, kind: str, usage: "Usage") -> None:
        from . import COMMERCIAL_CONTACT, FREE_IMAGE_COUNT, FREE_VIDEO_BYTES

        self.kind = kind
        self.usage = usage
        if kind == "images":
            used, limit = usage.images, FREE_IMAGE_COUNT
            detail = f"{used} of {limit} free images used"
        else:
            used, limit = usage.video_bytes, FREE_VIDEO_BYTES
            detail = (
                f"{used / 1024**3:.2f} GB of "
                f"{limit / 1024**3:.0f} GB free video used"
            )
        self.detail = detail
        super().__init__(
            f"You have reached the free limit ({detail}).\n"
            f"To carry on, a licence is a one-time payment: "
            f"$10 for personal use, $200 for commercial use, both for life.\n"
            f"Buy one at {COMMERCIAL_CONTACT}, then run: "
            f"pixelith activate <your-key>"
        )


def allowance_status() -> dict:
    """Where this install stands. Safe to show in any interface."""
    from . import FREE_IMAGE_COUNT, FREE_VIDEO_BYTES

    from . import beta_active, beta_days_left, BETA_ENDS

    tier = current_tier()
    usage = load_usage()
    in_beta = beta_active()
    unlimited = in_beta or tier in PAID_TIERS
    return {
        "beta": in_beta,
        "beta_ends": BETA_ENDS if in_beta else None,
        "beta_days_left": beta_days_left() if in_beta else None,
        "tier": tier,
        "licensed": unlimited,
        "holder": (active_licence() or {}).get("holder"),
        "install_id": usage.install_id,
        "images_used": usage.images,
        "images_limit": None if unlimited else FREE_IMAGE_COUNT,
        "images_remaining": None if unlimited
        else max(0, FREE_IMAGE_COUNT - usage.images),
        "video_bytes_used": usage.video_bytes,
        "video_bytes_limit": None if unlimited else FREE_VIDEO_BYTES,
        "video_bytes_remaining": None if unlimited
        else max(0, FREE_VIDEO_BYTES - usage.video_bytes),
        # Free-tier output is still marked during the beta: the mark is what
        # makes provenance work later, and it is disclosed either way.
        "watermarked": tier not in PAID_TIERS,
        "tampered": bool(getattr(usage, "tampered", False)),
    }


def check_allowance(kind: str, video_bytes: int = 0) -> None:
    """Raise AllowanceExceeded if this job is not permitted. Call before work.

    Nothing is refused during the public beta. Usage is still counted, so the
    meters stay meaningful and everyone can see where they would have stood,
    but no job is blocked and nothing is charged.
    """
    from . import FREE_IMAGE_COUNT, FREE_VIDEO_BYTES, beta_active

    if beta_active():
        return
    if current_tier() in PAID_TIERS:
        return
    usage = load_usage()
    if kind == "image":
        if usage.images >= FREE_IMAGE_COUNT:
            raise AllowanceExceeded("images", usage)
    else:
        if usage.video_bytes >= FREE_VIDEO_BYTES:
            raise AllowanceExceeded("video", usage)
        if usage.video_bytes + max(0, video_bytes) > FREE_VIDEO_BYTES:
            raise AllowanceExceeded("video", usage)
