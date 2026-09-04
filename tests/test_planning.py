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


# ------------------------------------------------- the resolution ladder --


def test_the_ladder_is_ordered_and_complete():
    """The interface renders these as a slider, so order is the step order."""
    from pixelith.config import PRESETS

    assert list(PRESETS) == [
        "180p", "360p", "480p", "720p", "1080p", "2k", "4k", "6k", "8k"
    ]
    areas = [w * h for w, h in PRESETS.values()]
    assert areas == sorted(areas), "the slider would jump backwards"


def test_every_step_is_16_by_9():
    from pixelith.config import PRESETS

    for name, (w, h) in PRESETS.items():
        assert abs(w / h - 16 / 9) < 0.01, f"{name} is not 16:9"


def test_old_preset_names_still_resolve():
    """Saved settings and existing links must not break."""
    from pixelith.config import resolve_preset

    assert resolve_preset("hd") == "1080p"
    assert resolve_preset("HD") == "1080p"
    assert resolve_preset("2160p") == "4k"
    assert resolve_preset("4k") == "4k"          # already canonical
    assert plan(1280, 720, preset="hd").out_height == 1080


def test_steps_below_the_source_are_a_plain_downscale():
    p = plan(1920, 1080, preset="360p")
    assert p.passes == 0
    assert (p.out_width, p.out_height) == (640, 360)


def test_the_lowest_step_still_works_on_a_tiny_source():
    p = plan(160, 90, preset="180p")
    assert (p.out_width, p.out_height) == (320, 180)
    assert p.passes == 1


def test_cli_lists_presets_in_ladder_order_not_alphabetically():
    """Sorted alphabetically, 1080p comes before 180p, which reads as a bug."""
    from pixelith.cli import build_parser
    from pixelith.config import PRESETS

    import argparse

    parser = build_parser()
    subparsers = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )
    help_text = subparsers.choices["upscale"].format_help()

    assert all(name in help_text for name in PRESETS)
    positions = [help_text.index(name) for name in ("180p", "1080p", "8k")]
    assert positions == sorted(positions), "presets are not in ladder order"


def test_cli_accepts_the_hd_alias_like_the_api_does():
    from pixelith.cli import build_parser

    args = build_parser().parse_args(["upscale", "x.png", "-p", "hd"])
    assert args.preset == "1080p"
