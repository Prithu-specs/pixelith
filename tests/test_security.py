"""Security boundaries for the local HTTP application."""
import pytest
from starlette.requests import Request

from pixelith.pipeline import plan
from pixelith.pairing import PAIRING
from pixelith.server import (MOBILE_UPLOAD_BYTES, PREVIEW_UPLOAD_BYTES,
                             SECURITY_HEADERS, _request_block_reason, health)


def test_security_headers_are_present():
    assert SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"
    assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in SECURITY_HEADERS["Content-Security-Policy"]


def test_cross_origin_api_request_is_blocked():
    assert _request_block_reason(
        "127.0.0.1:8420", "https://malicious.example", "http", "cross-site"
    ) == (403, "cross-origin request blocked")


def test_same_origin_api_request_is_allowed():
    assert _request_block_reason(
        "127.0.0.1:8420", "http://127.0.0.1:8420", "http", "same-origin"
    ) is None


def test_private_lan_same_origin_is_allowed():
    assert _request_block_reason(
        "192.168.1.20:8420", "http://192.168.1.20:8420", "http", "same-origin"
    ) is None


def test_cross_site_fetch_metadata_is_blocked_without_origin():
    assert _request_block_reason(
        "127.0.0.1:8420", None, "http", "cross-site"
    ) == (403, "cross-site request blocked")


def test_dns_rebinding_host_is_blocked():
    assert _request_block_reason(
        "attacker.example", None, "http", "none"
    ) == (400, "untrusted host")


@pytest.mark.parametrize(
    "host",
    [
        "evil.127.0.0.1.example:8420",
        "",
        "public.example:8420",
    ],
)
def test_untrusted_hosts_are_blocked(host):
    assert _request_block_reason(
        host, None, "http", "none"
    ) == (400, "untrusted host")


def test_oversized_pixel_canvas_is_rejected():
    with pytest.raises(ValueError, match="safety limit"):
        plan(20_000, 20_000, preset="8k")


def test_mobile_upload_and_preview_limits_are_bounded():
    assert 256 * 1024**2 <= MOBILE_UPLOAD_BYTES <= 2 * 1024**3
    assert PREVIEW_UPLOAD_BYTES <= MOBILE_UPLOAD_BYTES


def test_unpaired_lan_health_does_not_disclose_hardware_or_licence():
    request = Request({
        "type": "http", "method": "GET", "path": "/api/health",
        "headers": [(b"host", b"192.168.1.10:8420")],
        "scheme": "http", "client": ("192.168.1.20", 50000),
        "server": ("192.168.1.10", 8420), "query_string": b"",
    })
    PAIRING.enable()
    try:
        body = health(request)
        assert body["status"] == "pairing_required"
        assert "hardware" not in body
        assert "license" not in body
    finally:
        PAIRING.disable()
