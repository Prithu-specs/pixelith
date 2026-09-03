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
    from pixelith.engine import Engine

    yy, xx = np.mgrid[0:160, 0:160].astype(np.float32)
    img = np.stack([yy, xx, (yy + xx) / 2], -1).astype(np.uint8)
    whole = Engine(MODELS["fast"], UpscaleSettings(tile=512, overlap=0)).upscale(img)
    tiled = Engine(MODELS["fast"], UpscaleSettings(tile=64, overlap=16)).upscale(img)
    assert np.abs(whole.astype(int) - tiled.astype(int)).max() <= 12
