# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 PGA Tech Solutions. Free for noncommercial use;
# commercial use requires a separate licence. See LICENSE.
"""Guards on the licence notice.

The PolyForm Noncommercial terms are enforceable because downstream users are
put on notice. These tests fail the build if that notice is weakened, so a
refactor cannot quietly strip the thing the licence depends on.
"""
from pathlib import Path

import pytest

import pixelith

ROOT = Path(__file__).resolve().parent.parent
LICENSOR = "PGA Tech Solutions"


def test_license_file_carries_the_required_notice():
    text = (ROOT / "LICENSE").read_text()
    first = text.strip().splitlines()[0]
    assert first.startswith("Required Notice:"), (
        "The Required Notice must be the first line; it is the mechanism "
        "PolyForm uses to bind downstream recipients."
    )
    assert LICENSOR in first
    assert "PolyForm Noncommercial License 1.0.0" in text


def test_licensor_is_not_a_placeholder():
    for stale in ("Pixelith contributors", "Yoyodyne", "example.com"):
        assert stale not in (ROOT / "LICENSE").read_text().split("# PolyForm")[0], (
            f"placeholder {stale!r} left in the Required Notice"
        )


def test_runtime_license_metadata_matches_the_file():
    info = pixelith.license_info()
    assert info["licensor"] == LICENSOR
    assert info["spdx"] == "PolyForm-Noncommercial-1.0.0"
    assert info["noncommercial"] is True
    assert "@" in info["commercial_contact"]
    assert LICENSOR in (ROOT / "LICENSE").read_text()
    assert info["required_notice"].startswith("Required Notice:")


@pytest.mark.parametrize(
    "path", sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "pixelith").glob("*.py"))
)
def test_every_source_file_declares_its_licence(path):
    head = (ROOT / path).read_text()[:400]
    assert "SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0" in head, (
        f"{path} is missing its SPDX header"
    )
    assert LICENSOR in head


def test_web_assets_declare_their_licence():
    for name in ("web/app.js", "web/style.css"):
        head = (ROOT / name).read_text()[:400]
        assert "PolyForm-Noncommercial-1.0.0" in head, f"{name} missing SPDX header"


def test_user_facing_docs_name_the_licensor():
    for name in ("README.md", "NOTICE.md", "CONTRIBUTING.md"):
        assert LICENSOR in (ROOT / name).read_text(), f"{name} does not name the licensor"


def test_ui_shows_the_terms_to_anyone_who_opens_it():
    html = (ROOT / "web/index.html").read_text()
    assert LICENSOR in html
    assert "Noncommercial" in html


def test_contributing_grants_the_right_to_relicense_commercially():
    """Without this grant the project could not be licensed commercially at all."""
    text = (ROOT / "CONTRIBUTING.md").read_text().lower()
    assert "commercial terms" in text or "commercial licence" in text
    assert "perpetual" in text and "irrevocable" in text
