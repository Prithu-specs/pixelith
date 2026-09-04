"""Registry invariants."""
import pytest

from pixelith.config import MODELS, PRESETS, UpscaleSettings


def test_every_model_is_well_formed():
    for key, spec in MODELS.items():
        assert spec.key == key
        assert spec.scale >= 2
        assert len(spec.sha256) == 64, f"{key} must pin a sha256"
        assert spec.url.startswith("https://")
        assert spec.cost > 0
        assert spec.default_tile >= 64


def test_presets_are_sane():
    # Not sorted by size on purpose - see test_planning.py for the 180p stop.
    assert PRESETS["8k"] == (7680, 4320)
    assert PRESETS["180p"] == (320, 180)
    assert all(w > 0 and h > 0 for w, h in PRESETS.values())


def test_unknown_model_is_rejected():
    with pytest.raises(ValueError):
        UpscaleSettings(model="nonexistent").resolved_model()


def test_default_settings_resolve():
    assert UpscaleSettings().resolved_model().key == "fast"
