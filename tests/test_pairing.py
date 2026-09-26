"""Temporary pairing codes and in-memory LAN sessions."""
import pytest

from pixelith.pairing import PairingError, PairingManager


def test_pairing_creates_random_authenticated_session_and_rotates_code():
    manager = PairingManager()
    code = manager.enable()
    token, ttl = manager.pair(code, "192.168.1.9")
    assert ttl == manager.SESSION_TTL
    assert len(token) >= 40
    assert manager.authenticate(token)
    assert manager.current_code()[0] != code
    with pytest.raises(PairingError, match="invalid or expired"):
        manager.pair(code, "192.168.1.10")


def test_session_is_revoked_without_storing_plain_token():
    manager = PairingManager()
    token, _ = manager.pair(manager.enable(), "phone")
    assert token not in manager._sessions
    manager.revoke(token)
    assert not manager.authenticate(token)


def test_pairing_is_disabled_by_default():
    manager = PairingManager()
    assert manager.authenticate(None)
    with pytest.raises(PairingError, match="not enabled"):
        manager.pair("123456", "phone")


def test_pairing_rate_limits_guesses():
    manager = PairingManager()
    manager.enable()
    for _ in range(manager.MAX_ATTEMPTS):
        with pytest.raises(PairingError, match="invalid or expired"):
            manager.pair("000000", "phone")
    with pytest.raises(PairingError, match="too many attempts"):
        manager.pair("000000", "phone")
