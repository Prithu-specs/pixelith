# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Invisible provenance marking.

Free-tier output carries a machine-readable mark identifying the tier, the
install, and the sequence number at the time it was made. It is disclosed, not
covert: the licence and the interface both say it is there, and a paid licence
turns it off.

The mark lives in the DCT domain rather than the low bits of the pixels.
Low-bit marking is more invisible on paper (89 dB against 44 dB here) but does
not survive being saved as a JPEG, which is what happens to most images the
moment they are shared. Embedding in mid-frequency coefficients puts the mark
where JPEG keeps information, so it survives re-compression down to about
quality 60.
"""
from __future__ import annotations

import hashlib
import zlib

import numpy as np

BLOCK = 8
SEED = b"pixelith-wm-v1"
# Mid-frequency pair: high enough that the eye does not see it, low enough that
# quantisation does not zero it.
_C1, _C2 = (3, 1), (1, 3)
_DELTA = 18.0
_REPS = 9

VERSION = 1
TIER_FREE, TIER_PERSONAL, TIER_COMMERCIAL = 0, 1, 2
PAYLOAD_BYTES = 14          # version + tier + install id (8) + sequence (4)
_MIN_BLOCKS = ((PAYLOAD_BYTES + 4) * 8) * _REPS


class WatermarkError(RuntimeError):
    pass


def _dct_matrix(n: int = BLOCK) -> np.ndarray:
    k = np.arange(n)
    m = np.cos(np.pi * (2 * k[None, :] + 1) * k[:, None] / (2 * n))
    m[0] /= np.sqrt(2)
    return m * np.sqrt(2 / n)


_D = _dct_matrix()


def minimum_size() -> int:
    """Shortest side an image needs for the payload to fit."""
    import math

    side_blocks = math.ceil(math.sqrt(_MIN_BLOCKS))
    return side_blocks * BLOCK


def build_payload(tier: int, install_id: bytes, sequence: int) -> bytes:
    if len(install_id) != 8:
        raise ValueError("install_id must be 8 bytes")
    return (
        bytes([VERSION, tier & 0xFF])
        + install_id
        + max(0, min(sequence, 0xFFFFFFFF)).to_bytes(4, "big")
    )


def parse_payload(payload: bytes) -> dict:
    return {
        "version": payload[0],
        "tier": payload[1],
        "tier_name": {0: "free", 1: "personal", 2: "commercial"}.get(
            payload[1], "unknown"
        ),
        "install_id": payload[2:10].hex(),
        "sequence": int.from_bytes(payload[10:14], "big"),
    }


def _slots(h_blocks: int, w_blocks: int, n_bits: int) -> np.ndarray:
    rng = np.random.default_rng(
        int.from_bytes(hashlib.sha256(SEED).digest()[:8], "big")
    )
    total = h_blocks * w_blocks
    need = n_bits * _REPS
    if need > total:
        raise WatermarkError(
            f"image is too small to mark: needs {need} blocks of "
            f"{BLOCK}x{BLOCK}, has {total}"
        )
    return rng.choice(total, size=need, replace=False)


def _bits(payload: bytes) -> np.ndarray:
    body = payload + zlib.crc32(payload).to_bytes(4, "big")
    return np.unpackbits(np.frombuffer(body, dtype=np.uint8))


def _to_luma(rgb: np.ndarray):
    from PIL import Image

    ycc = np.asarray(
        Image.fromarray(rgb).convert("YCbCr"), dtype=np.float64
    ).copy()
    return ycc, ycc[..., 0]


def embed(rgb: np.ndarray, payload: bytes) -> np.ndarray:
    """Return a copy of the image carrying the payload."""
    from PIL import Image

    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise WatermarkError("expected an (H, W, 3) RGB array")
    ycc, luma = _to_luma(rgb)
    hb, wb = luma.shape[0] // BLOCK, luma.shape[1] // BLOCK
    bits = _bits(payload)
    order = _slots(hb, wb, len(bits))
    sequence = np.tile(bits, _REPS)

    for slot, bit in zip(order, sequence):
        by, bx = divmod(int(slot), wb)
        y0, x0 = by * BLOCK, bx * BLOCK
        coef = _D @ luma[y0 : y0 + BLOCK, x0 : x0 + BLOCK] @ _D.T
        a, b = coef[_C1], coef[_C2]
        if bit and a - b < _DELTA:
            mid = (a + b) / 2
            coef[_C1], coef[_C2] = mid + _DELTA / 2, mid - _DELTA / 2
        elif not bit and b - a < _DELTA:
            mid = (a + b) / 2
            coef[_C1], coef[_C2] = mid - _DELTA / 2, mid + _DELTA / 2
        luma[y0 : y0 + BLOCK, x0 : x0 + BLOCK] = _D.T @ coef @ _D

    ycc[..., 0] = np.clip(luma, 0, 255)
    return np.asarray(
        Image.fromarray(ycc.astype(np.uint8), "YCbCr").convert("RGB")
    )


def extract(rgb: np.ndarray) -> dict | None:
    """Read a payload back, or None if the image carries no readable mark."""
    _, luma = _to_luma(rgb)
    hb, wb = luma.shape[0] // BLOCK, luma.shape[1] // BLOCK
    n_bits = (PAYLOAD_BYTES + 4) * 8
    try:
        order = _slots(hb, wb, n_bits)
    except WatermarkError:
        return None

    votes = np.zeros(n_bits)
    for i, slot in enumerate(order):
        by, bx = divmod(int(slot), wb)
        y0, x0 = by * BLOCK, bx * BLOCK
        coef = _D @ luma[y0 : y0 + BLOCK, x0 : x0 + BLOCK] @ _D.T
        votes[i % n_bits] += 1 if coef[_C1] > coef[_C2] else -1

    data = np.packbits((votes > 0).astype(np.uint8)).tobytes()
    body = data[:PAYLOAD_BYTES]
    crc = int.from_bytes(data[PAYLOAD_BYTES : PAYLOAD_BYTES + 4], "big")
    if zlib.crc32(body) != crc:
        return None
    return parse_payload(body)
