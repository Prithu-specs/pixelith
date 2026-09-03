# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Licence keys, the usage ledger, and the allowance gate."""
import base64
import json

import pytest

import pixelith
from pixelith import licensing as L


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Never touch the real user's ledger or licence."""
    monkeypatch.setattr(L, "LEDGER_FILE", tmp_path / "usage.json")
    monkeypatch.setattr(L, "LICENCE_FILE", tmp_path / "licence.json")
    yield


def signed_key(tier="personal", holder="Test"):
    """Sign a key the way the issuing tool does, if the private key is present."""
    from pathlib import Path

    from cryptography.hazmat.primitives import serialization

    path = Path.home() / ".pixelith-licensing-private-key.pem"
    if not path.exists():
        pytest.skip("issuing key not on this machine")
    priv = serialization.load_pem_private_key(path.read_bytes(), password=None)
    body = json.dumps(
        {"tier": tier, "holder": holder, "issued": 1, "licensor": "PGA Tech Solutions"},
        separators=(",", ":"), sort_keys=True,
    ).encode()
    b = lambda x: base64.urlsafe_b64encode(x).decode().rstrip("=")  # noqa: E731
    return f"{b(body)}.{b(priv.sign(body))}"


# ------------------------------------------------------------------ the keys


def test_a_made_up_key_is_rejected():
    for junk in ("", "nonsense", "a.b", "not.arealkey"):
        with pytest.raises(L.LicenceError):
            L.verify_key(junk)


def test_a_key_with_a_tampered_body_is_rejected():
    """The whole point of signing: editing the claims must invalidate it."""
    token = signed_key(tier="personal")
    body, sig = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    claims["tier"] = "commercial"          # try to upgrade yourself
    forged = base64.urlsafe_b64encode(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
    ).decode().rstrip("=")
    with pytest.raises(L.LicenceError):
        L.verify_key(f"{forged}.{sig}")


def test_a_valid_key_activates_and_sets_the_tier():
    assert L.current_tier() == L.TIER_FREE
    L.activate(signed_key("commercial", "Acme Ltd"))
    assert L.current_tier() == "commercial"
    assert L.active_licence()["holder"] == "Acme Ltd"
    assert L.deactivate() is True
    assert L.current_tier() == L.TIER_FREE


def test_a_corrupted_stored_licence_falls_back_to_free():
    L.activate(signed_key())
    L.LICENCE_FILE.write_text("{ not json")
    assert L.current_tier() == L.TIER_FREE


# ---------------------------------------------------------------- the ledger


def test_usage_accumulates_and_persists():
    L.record(images=3)
    L.record(images=2, video_bytes=1000)
    usage = L.load_usage()
    assert usage.images == 5
    assert usage.video_bytes == 1000


def test_hand_editing_the_ledger_is_detected():
    L.record(images=50)
    raw = json.loads(L.LEDGER_FILE.read_text())
    raw["images"] = 0                       # "I have used nothing, honest"
    L.LEDGER_FILE.write_text(json.dumps(raw))
    assert L.allowance_status()["tampered"] is True


def test_install_id_is_stable_across_reads():
    first = L.load_usage().install_id
    L.record(images=1)
    assert L.load_usage().install_id == first
    assert len(L.install_id_bytes()) == 8


# ------------------------------------------------------------- the allowance


def test_free_tier_permits_work_below_the_limit():
    L.record(images=pixelith.FREE_IMAGE_COUNT - 1)
    L.check_allowance("image")              # must not raise


def test_free_tier_blocks_the_image_limit():
    L.record(images=pixelith.FREE_IMAGE_COUNT)
    with pytest.raises(L.AllowanceExceeded) as exc:
        L.check_allowance("image")
    assert "$10" in str(exc.value) and "$200" in str(exc.value)


def test_free_tier_blocks_the_video_limit():
    L.record(video_bytes=pixelith.FREE_VIDEO_BYTES)
    with pytest.raises(L.AllowanceExceeded):
        L.check_allowance("video", video_bytes=1)


def test_a_video_that_would_overshoot_is_refused_before_it_starts():
    """Refuse up front rather than half-processing a file and then stopping."""
    L.record(video_bytes=pixelith.FREE_VIDEO_BYTES - 1000)
    with pytest.raises(L.AllowanceExceeded):
        L.check_allowance("video", video_bytes=5000)


def test_the_two_allowances_are_independent():
    L.record(images=pixelith.FREE_IMAGE_COUNT)      # images exhausted
    L.check_allowance("video", video_bytes=1000)    # video still fine
    with pytest.raises(L.AllowanceExceeded):
        L.check_allowance("image")


def test_a_paid_licence_removes_both_limits():
    L.record(images=10_000, video_bytes=pixelith.FREE_VIDEO_BYTES * 5)
    L.activate(signed_key("personal"))
    L.check_allowance("image")
    L.check_allowance("video", video_bytes=10**12)


def test_allowance_status_reports_the_watermark_state():
    assert L.allowance_status()["watermarked"] is True
    L.activate(signed_key("commercial"))
    assert L.allowance_status()["watermarked"] is False
