"""Cross-platform capability detection and memory-aware tuning."""
import platform

import pytest

from pixelith import compat
from pixelith.config import MODELS
from pixelith.engine import pick_tile

GB = 1024**3


def test_platform_summary_is_complete():
    s = compat.summary()
    for key in ("os", "arch", "python", "cpus", "ram_gb", "heic", "ffmpeg"):
        assert key in s
    assert s["cpus"] >= 1
    assert s["ram_gb"] > 0


def test_os_name_is_recognised():
    assert compat.os_name() in {"macOS", "Windows", "Linux", platform.system()}


def test_ram_detection_returns_something_plausible():
    # Every supported platform must return a real number, never zero.
    assert compat.total_ram_bytes() >= 1 * GB


def test_only_decodable_formats_are_advertised():
    suffixes = compat.image_suffixes()
    assert {".png", ".jpg", ".webp"} <= suffixes
    # HEIC may only be claimed when the plugin actually loaded.
    assert (".heic" in suffixes) == compat.HEIF_OK


def test_cpu_and_neural_engine_want_different_tiles():
    """The whole point of adaptive tiling: one size does not fit both."""
    cpu = pick_tile("CPUExecutionProvider", MODELS["fast"], 32 * GB)
    ane = pick_tile("CoreMLExecutionProvider", MODELS["fast"], 32 * GB)
    assert cpu > ane, "threaded CPU kernels need larger tiles than the ANE"


@pytest.mark.parametrize(
    "ram_gb,ceiling", [(2, 192), (3, 192), (6, 256), (7, 256)]
)
def test_low_memory_machines_get_smaller_tiles(ram_gb, ceiling):
    for provider in ("CPUExecutionProvider", "CUDAExecutionProvider"):
        assert pick_tile(provider, MODELS["fast"], ram_gb * GB) <= ceiling


def test_deep_model_is_capped_regardless_of_memory():
    # The 23-block network holds far more activation memory per tile.
    assert pick_tile("CPUExecutionProvider", MODELS["quality"], 128 * GB) <= 256


def test_unknown_provider_falls_back_to_the_model_default():
    spec = MODELS["fast"]
    assert pick_tile("SomeFutureProvider", spec, 32 * GB) == spec.default_tile


def test_tile_is_never_degenerate():
    for provider in ("CPUExecutionProvider", "CoreMLExecutionProvider", "??"):
        for gb in (1, 2, 4, 8, 64):
            assert pick_tile(provider, MODELS["fast"], gb * GB) >= 64


def test_lan_address_is_an_address_or_none():
    ip = compat.lan_address()
    if ip is not None:
        parts = ip.split(".")
        assert len(parts) == 4 and all(p.isdigit() for p in parts)
        assert not ip.startswith("127.")
