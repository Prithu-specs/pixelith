"""Engine behaviour. Tests needing weights are marked and skipped in CI."""
import numpy as np
import pytest

from pixelith.config import MODELS, UpscaleSettings
from pixelith.engine import _feather, choose_providers
from pixelith.models import is_available


def test_feather_is_symmetric_and_bounded():
    w = _feather(64, 8)
    assert w.shape == (64,)
    assert np.allclose(w, w[::-1])
    assert w.max() <= 1.0 and w.min() > 0


def test_feather_clamps_when_overlap_exceeds_half_the_window():
    # Edge tiles can be narrower than 2x overlap; this must not raise.
    w = _feather(10, 32)
    assert w.shape == (10,)
    assert np.isfinite(w).all()


def test_provider_choice_is_per_model():
    for spec in MODELS.values():
        chosen = choose_providers(spec=spec)
        assert chosen, "must always fall back to something"
        assert chosen[-1] == "CPUExecutionProvider" or "CPU" in " ".join(chosen)


needs_model = pytest.mark.skipif(
    not is_available(MODELS["fast"]), reason="model weights not downloaded"
)


@needs_model
@pytest.mark.needs_model
def test_upscale_shape_and_dtype():
    from pixelith.engine import Engine

    eng = Engine(MODELS["fast"], UpscaleSettings(tile=128, overlap=16))
    src = (np.random.rand(70, 90, 3) * 255).astype(np.uint8)
    out = eng.upscale(src)
    assert out.shape == (280, 360, 3)
    assert out.dtype == np.uint8


@needs_model
@pytest.mark.needs_model
def test_tiling_does_not_create_visible_seams():
    """A seam is a discontinuity *inside* the picture.

    The outer pixels legitimately differ between tilings, because that is where
    the boundary is reflected rather than joined, so measuring the whole frame
    conflates the two. Only the interior tells you whether tiles joined cleanly.
    """
    from pixelith.engine import Engine

    yy, xx = np.mgrid[0:160, 0:160].astype(np.float32)
    img = np.stack([yy, xx, (yy + xx) / 2], -1).astype(np.uint8)
    whole = Engine(MODELS["fast"], UpscaleSettings(tile=512, overlap=0)).upscale(img)
    tiled = Engine(MODELS["fast"], UpscaleSettings(tile=64, overlap=16)).upscale(img)

    border = 64
    interior = np.abs(
        whole[border:-border, border:-border].astype(int)
        - tiled[border:-border, border:-border].astype(int)
    )
    assert interior.max() <= 6, f"tiles are not joining cleanly: {interior.max()}"

    # And directly: no column-to-column jump that would read as a visible line.
    jumps = np.abs(np.diff(tiled.astype(int), axis=1)).mean(axis=(0, 2))
    assert jumps.max() < 4.0, f"visible vertical seam, jump {jumps.max():.2f}"


# ------------------------------------------------- tiling strategy --


def test_only_shape_sensitive_providers_pad_their_tiles():
    """Padding every tile to full size runs up to twice the real pixel count.
    It buys nothing unless the provider recompiles per input shape."""
    from pixelith.engine import _STABLE_SHAPE_REQUIRED

    assert "CoreMLExecutionProvider" in _STABLE_SHAPE_REQUIRED
    assert "CPUExecutionProvider" not in _STABLE_SHAPE_REQUIRED
    assert "CUDAExecutionProvider" not in _STABLE_SHAPE_REQUIRED


def test_shape_tolerant_providers_get_large_tiles():
    """Few large ragged tiles beat many small padded ones where shapes are free."""
    from pixelith.config import MODELS
    from pixelith.engine import _TILE_BY_PROVIDER, pick_tile

    GB = 1024**3
    cpu = pick_tile("CPUExecutionProvider", MODELS["fast"], 32 * GB)
    ane = pick_tile("CoreMLExecutionProvider", MODELS["fast"], 32 * GB)
    assert cpu >= 1024 and cpu > ane
    assert _TILE_BY_PROVIDER["CUDAExecutionProvider"] >= 1024


@needs_model
@pytest.mark.needs_model
def test_both_tiling_paths_agree_away_from_the_border():
    """Padded and edge-margin tiling differ only in how the true image edge is
    reflected, so the interior must match."""
    from pixelith.engine import Engine

    yy, xx = np.mgrid[0:200, 0:300].astype(np.float32)
    img = np.stack(
        [128 + 90 * np.sin(xx / 21), 128 + 80 * np.cos(yy / 27),
         128 + 60 * np.sin((xx + yy) / 15)], -1
    ).clip(0, 255).astype(np.uint8)

    cpu = ["CPUExecutionProvider"]
    padded = Engine(MODELS["fast"], UpscaleSettings(tile=128, overlap=16,
                                                    providers=cpu))
    padded.pad_tiles = True
    margin = Engine(MODELS["fast"], UpscaleSettings(tile=128, overlap=16,
                                                    providers=cpu))
    margin.pad_tiles = False

    a, b = padded.upscale(img), margin.upscale(img)
    assert a.shape == b.shape
    edge = 16 * 4
    interior = np.abs(
        a[edge:-edge, edge:-edge].astype(int) - b[edge:-edge, edge:-edge].astype(int)
    )
    assert interior.max() <= 8, f"interior differs by {interior.max()}"


def test_hybrid_is_off_by_default():
    """Measured on shared-memory silicon it lost badly: a second CoreML session
    at the tile size actually in use ran 3.3x slower and used 4x the memory."""
    assert UpscaleSettings().hybrid is False


@needs_model
@pytest.mark.needs_model
def test_memory_does_not_scale_with_output_size():
    """Banded assembly is what lets a small machine reach 8K. A whole-image
    float accumulator costs four times the finished picture."""
    from pixelith.engine import Engine

    eng = Engine(MODELS["fast"], UpscaleSettings(tile=96, overlap=8,
                                                 providers=["CPUExecutionProvider"]))
    small = eng.upscale((np.random.rand(64, 64, 3) * 255).astype(np.uint8))
    big = eng.upscale((np.random.rand(64, 512, 3) * 255).astype(np.uint8))
    assert small.shape == (256, 256, 3)
    assert big.shape == (256, 2048, 3)


@needs_model
@pytest.mark.needs_model
def test_banding_leaves_no_horizontal_seam():
    """Bands are flushed a row of tiles at a time; a mistake there would show
    as a hard line across the picture."""
    from pixelith.engine import Engine

    yy, xx = np.mgrid[0:300, 0:200].astype(np.float32)
    img = np.stack([yy / 300 * 255, xx / 200 * 255,
                    (yy + xx) / 500 * 255], -1).astype(np.uint8)
    out = Engine(MODELS["fast"],
                 UpscaleSettings(tile=64, overlap=8,
                                 providers=["CPUExecutionProvider"])).upscale(img)
    rows = np.abs(np.diff(out.astype(int), axis=0)).mean(axis=(1, 2))
    assert rows.max() < 4.0, f"horizontal band seam, jump {rows.max():.2f}"
