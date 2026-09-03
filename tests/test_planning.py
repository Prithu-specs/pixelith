"""Scale planning and time formatting - pure logic, no model needed."""
import pytest

from pixelith.pipeline import human_time, plan


def test_preset_preserves_aspect_ratio():
    p = plan(1920, 1080, preset="8k")
    assert (p.out_width, p.out_height) == (7680, 4320)
    assert p.passes == 1


def test_non_16_9_source_fits_inside_the_preset_box():
    p = plan(4032, 3024, preset="8k")          # 4:3 into a 16:9 box
    assert p.out_height == 4320
    assert p.out_width <= 7680
    assert abs(p.out_width / p.out_height - 4 / 3) < 0.01


def test_small_source_needs_two_passes():
    p = plan(854, 480, preset="4k")
    assert p.passes == 2


def test_downscale_requests_use_no_network_passes():
    p = plan(3840, 2160, preset="hd")
    assert p.passes == 0
    assert (p.out_width, p.out_height) == (1920, 1080)


def test_explicit_scale():
    p = plan(800, 600, scale=2.0)
    assert (p.out_width, p.out_height) == (1600, 1200)


def test_passes_are_capped():
    p = plan(10, 10, scale=64.0)
    assert p.passes <= 2


@pytest.mark.parametrize("bad", [(0, 100), (100, 0), (-5, 5)])
def test_rejects_bad_dimensions(bad):
    with pytest.raises(ValueError):
        plan(*bad, preset="4k")


def test_rejects_unknown_preset():
    with pytest.raises(ValueError):
        plan(100, 100, preset="12k")


@pytest.mark.parametrize(
    "seconds,expected",
    [(0.2, "under a second"), (1, "about 1 second"), (45, "about 45 seconds")],
)
def test_human_time(seconds, expected):
    assert human_time(seconds) == expected


def test_human_time_pluralisation_never_says_one_seconds():
    assert "1 seconds" not in human_time(1.0)
