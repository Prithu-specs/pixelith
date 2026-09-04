# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Guards on the licence notice.

Pixelith is not metered: nothing in the software checks a key or counts usage,
so the terms rest entirely on users being told what they are. These tests fail
the build if that notice is weakened, or if the published prices and allowances
drift out of step with the licence text.
"""
from pathlib import Path

import pytest

import pixelith

ROOT = Path(__file__).resolve().parent.parent
LICENSOR = "PGA Tech Solutions"


def licence_text() -> str:
    """LICENSE with runs of whitespace collapsed.

    The agreement is hard-wrapped at 78 columns, so a clause quoted in a test
    would otherwise fail purely because a line break fell inside it.
    """
    return " ".join((ROOT / "LICENSE").read_text().split())


def test_license_file_carries_the_required_notice():
    text = (ROOT / "LICENSE").read_text()
    head = text[:600]
    assert "Required Notice:" in head, (
        "The Required Notice must appear at the top of the agreement; it is "
        "what downstream recipients are obliged to carry."
    )
    notice = head[head.index("Required Notice:"):]
    assert LICENSOR in notice.splitlines()[0]
    assert "Pixelith End User Licence Agreement" in text


def test_licensor_is_not_a_placeholder():
    head = (ROOT / "LICENSE").read_text()[:600]
    for stale in ("Pixelith contributors", "Yoyodyne", "example.com"):
        assert stale not in head, f"placeholder {stale!r} left in the Required Notice"


def test_runtime_license_metadata_matches_the_file():
    info = pixelith.license_info()
    assert info["licensor"] == LICENSOR
    assert info["spdx"] == "LicenseRef-Pixelith-EULA-1.0"
    assert "@" in info["commercial_contact"]
    assert LICENSOR in (ROOT / "LICENSE").read_text()
    assert info["required_notice"].startswith("Required Notice:")


@pytest.mark.parametrize(
    "path", sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "pixelith").glob("*.py"))
)
def test_every_source_file_declares_its_licence(path):
    head = (ROOT / path).read_text()[:400]
    assert "SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0" in head, (
        f"{path} is missing its SPDX header"
    )
    assert LICENSOR in head


def test_web_assets_declare_their_licence():
    for name in ("web/app.js", "web/style.css"):
        head = (ROOT / name).read_text()[:400]
        assert "LicenseRef-Pixelith-EULA-1.0" in head, f"{name} missing SPDX header"


def test_user_facing_docs_name_the_licensor():
    for name in ("README.md", "NOTICE.md", "CONTRIBUTING.md"):
        assert LICENSOR in (ROOT / name).read_text(), f"{name} does not name the licensor"


def test_ui_shows_the_terms_to_anyone_who_opens_it():
    html = (ROOT / "web/index.html").read_text()
    assert LICENSOR in html
    assert "$10" in html and "$200" in html


def test_contributing_grants_the_right_to_relicense_commercially():
    """Without this grant the project could not be licensed commercially at all."""
    text = (ROOT / "CONTRIBUTING.md").read_text().lower()
    assert "commercial terms" in text or "commercial licence" in text
    assert "perpetual" in text and "irrevocable" in text


# --------------------------------------------------------------- the tiers --


def test_published_prices_match_the_licence_text():
    """A price typo in the UI or the licence would be a public pricing error."""
    licence = licence_text()
    for token in ("Rs 513", "US$10", "Rs 8,228", "US$200"):
        assert token in licence, f"{token!r} missing from the licence"

    inr = pixelith.CURRENCIES["INR"]
    usd = pixelith.CURRENCIES["USD"]
    assert (inr["personal"], inr["commercial"]) == (513, 8228)
    assert (usd["personal"], usd["commercial"]) == (10, 200)


def test_indian_prices_are_quoted_exclusive_of_gst():
    """Prices are ex-GST, but the all-in total must be published alongside."""
    inr = pixelith.CURRENCIES["INR"]
    assert inr["tax_included"] is False
    assert "GST" in inr["tax_label"]

    licence = licence_text()
    assert "exclusive of GST" in licence
    assert "including GST is shown before you pay" in licence
    assert pixelith.GST_SAC in licence


def test_the_all_in_total_is_computed_and_published():
    p = pixelith.pricing()["INR"]
    assert p["personal_total"] == round(513 * 1.18) == 605
    assert p["commercial_total"] == round(8228 * 1.18) == 9709
    assert pixelith.tier_total("personal", "INR") == "\u20b9605"
    # Dollar prices carry no Indian GST, so total equals price.
    usd = pixelith.pricing()["USD"]
    assert usd["personal_total"] == usd["personal"] == 10


def test_no_separate_payment_processing_charge_is_levied():
    """RBI bars merchants from passing card and UPI costs to the customer, so
    the agreement commits to not doing it."""
    licence = licence_text()
    assert "No separate charge is made for payment processing" in licence


def test_export_sales_are_described_as_zero_rated():
    """Sales outside India are exports of service, zero-rated under LUT."""
    licence = licence_text()
    assert "zero-rated" in licence and "Letter of Undertaking" in licence


_GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _gstin_checksum_ok(gstin: str) -> bool:
    """The 15th character is a weighted checksum over the first 14."""
    if len(gstin) != 15 or any(c not in _GST_CHARS for c in gstin):
        return False
    total = 0
    for i, ch in enumerate(gstin[:14]):
        product = _GST_CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return gstin[14] == _GST_CHARS[(36 - total % 36) % 36]


def test_gstin_is_present_and_passes_its_checksum():
    """A mistyped GSTIN on a tax invoice is a real compliance problem."""
    assert pixelith.GSTIN, "GSTIN is not set"
    assert _gstin_checksum_ok(pixelith.GSTIN), (
        f"{pixelith.GSTIN} fails the GSTIN checksum - it is mistyped"
    )
    assert pixelith.GSTIN in licence_text()
    assert "[INSERT GSTIN]" not in licence_text()


def test_gstin_state_code_matches_the_stated_state():
    assert pixelith.GSTIN.startswith("09")          # 09 = Uttar Pradesh
    assert pixelith.GST_STATE == "Uttar Pradesh"
    assert "Uttar Pradesh" in licence_text()


def test_the_checksum_helper_actually_rejects_bad_numbers():
    """Guard the guard: a broken validator would pass anything."""
    good = pixelith.GSTIN
    assert _gstin_checksum_ok(good)
    bad = good[:14] + ("A" if good[14] != "A" else "B")
    assert not _gstin_checksum_ok(bad)
    assert not _gstin_checksum_ok("09AIAPG7383C1Z")      # too short
    assert not _gstin_checksum_ok("")


def test_regional_pricing_is_exposed_to_clients():
    p = pixelith.pricing()
    assert set(p) == {"INR", "USD"}
    for code, data in p.items():
        assert "personal_url" in data and "commercial_url" in data
    assert pixelith.DEFAULT_CURRENCY == "INR"


def test_currency_toggle_exists_in_the_interface():
    html = (ROOT / "web/index.html").read_text()
    assert 'data-currency="INR"' in html and 'data-currency="USD"' in html


def test_the_html_fallback_prices_match_the_configured_ones():
    """The markup carries a default price that shows before the API responds.
    If it drifts, buyers see the wrong number for a moment."""
    html = (ROOT / "web/index.html").read_text()
    inr = pixelith.CURRENCIES["INR"]
    for amount in (inr["personal"], inr["commercial"]):
        assert f"&#8377;{amount:,}" in html, (
            f"the markup fallback does not show \u20b9{amount:,}"
        )


def test_free_allowance_is_consistent_everywhere():
    assert pixelith.FREE_IMAGE_COUNT == 100
    assert pixelith.FREE_VIDEO_BYTES == 1_073_741_824      # exactly 1 GiB

    licence = licence_text()
    assert "100 Still Images" in licence
    assert "1,073,741,824 bytes" in licence

    info = pixelith.license_info()["free_allowance"]
    assert info["images"] == pixelith.FREE_IMAGE_COUNT
    assert info["video_bytes"] == pixelith.FREE_VIDEO_BYTES


def test_commercial_tier_has_no_free_allowance():
    """Commercial use needs a licence from the first byte, not after a trial."""
    assert "does not permit Commercial Use in any volume" in licence_text()


def test_licence_text_matches_what_the_software_actually_does():
    """The agreement describes local metering, offline key checks and a mark on
    free output. If the code stops doing any of that the licence becomes a false
    statement about the product, so the two are pinned together here."""
    info = pixelith.license_info()
    assert info["enforced_in_software"] is True
    assert info["free_output_watermarked"] is True
    assert info["telemetry"] is False

    licence = licence_text()
    assert "keeps a usage record on your own computer" in licence
    assert "verified on your machine using a public key" in licence
    assert "does not contact us" in licence
    assert "invisible, machine-readable mark" in licence
    assert "carries no mark" in licence


def test_the_watermark_is_disclosed_not_covert():
    """Users are entitled to know what is embedded in files they produce."""
    licence = licence_text()
    assert "We disclose the mark here" in licence
    assert "does not contain your name" in licence
    assert "provenance mark" in (ROOT / "web/index.html").read_text()


def test_prior_polyform_rights_are_preserved():
    """0.1.x went out under PolyForm; those rights cannot be withdrawn."""
    assert "PolyForm" in pixelith.license_info()["prior_license"]
    assert (ROOT / "LICENSE-0.1.x-PolyForm-Noncommercial-1.0.0.txt").exists()
    assert "0.1.x were released under the PolyForm" in licence_text()


def test_governing_law_is_set_and_the_venue_is_complete():
    """India is settled; the city for the courts clause is not."""
    licence = licence_text()
    assert "governed by the laws of India" in licence
    if "[INSERT CITY]" in licence:
        pytest.skip(
            "the courts clause still needs a city - PGA Tech Solutions must "
            "name the venue in Uttar Pradesh before relying on this agreement"
        )
    assert "exclusive jurisdiction" in licence
