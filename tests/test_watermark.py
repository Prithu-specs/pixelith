# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""The invisible provenance mark on free-tier output."""
import hashlib
import io

import numpy as np
import pytest
from PIL import Image

from pixelith import watermark as wm


def photo(h=720, w=1280):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    return np.stack(
        [128 + 90 * np.sin(xx / 57), 128 + 80 * np.cos(yy / 71),
         128 + 70 * np.sin((xx + yy) / 97)], -1
    ).clip(0, 255).astype(np.uint8)


def payload(tier=wm.TIER_FREE, seq=42):
    return wm.build_payload(tier, hashlib.sha256(b"install").digest()[:8], seq)


def psnr(a, b):
    mse = ((a.astype(float) - b.astype(float)) ** 2).mean()
    return 99.0 if mse == 0 else 10 * np.log10(255 * 255 / mse)


def test_payload_round_trips():
    img = photo()
    marked = wm.embed(img, payload(seq=1234))
    got = wm.extract(marked)
    assert got is not None
    assert got["tier_name"] == "free"
    assert got["sequence"] == 1234
    assert got["install_id"] == hashlib.sha256(b"install").digest()[:8].hex()


def test_mark_is_imperceptible():
    img = photo()
    marked = wm.embed(img, payload())
    # 40 dB is the usual threshold for "cannot be seen in a photograph".
    assert psnr(img, marked) > 40


def test_mark_survives_jpeg_compression():
    """The point of using the DCT domain: most shared images are JPEGs."""
    marked = wm.embed(photo(), payload(seq=7))
    for quality in (95, 85, 75, 60):
        buf = io.BytesIO()
        Image.fromarray(marked).save(buf, "JPEG", quality=quality)
        out = np.asarray(Image.open(buf).convert("RGB"))
        got = wm.extract(out)
        assert got is not None and got["sequence"] == 7, f"lost at q{quality}"


def test_mark_survives_a_png_round_trip():
    marked = wm.embed(photo(), payload(seq=3))
    buf = io.BytesIO()
    Image.fromarray(marked).save(buf, "PNG")
    assert wm.extract(np.asarray(Image.open(buf).convert("RGB")))["sequence"] == 3


def test_unmarked_images_report_nothing():
    """No false positives: an ordinary photo must not appear to carry a mark."""
    for _ in range(3):
        assert wm.extract(photo()) is None
    rng = np.random.default_rng(0)
    assert wm.extract((rng.random((400, 400, 3)) * 255).astype(np.uint8)) is None


def test_tier_is_recorded_in_the_mark():
    for tier, name in ((wm.TIER_FREE, "free"), (wm.TIER_PERSONAL, "personal")):
        marked = wm.embed(photo(), payload(tier=tier))
        assert wm.extract(marked)["tier_name"] == name


def test_images_below_the_minimum_size_are_refused_cleanly():
    small = photo(64, 64)
    with pytest.raises(wm.WatermarkError):
        wm.embed(small, payload())
    assert wm.extract(small) is None      # never raises on read


def test_minimum_size_is_reported():
    assert 128 <= wm.minimum_size() <= 512
