"""Output size and compression policy."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pixelith.compression import (OutputTooLarge, output_budget, save_image,
                                  video_bitrate)
from pixelith.config import MAX_OUTPUT_BYTES


def test_250_mb_source_is_capped_at_750_mb():
    assert output_budget(250_000_000) == 750_000_000


def test_one_gb_is_an_absolute_ceiling():
    assert output_budget(500_000_000) == MAX_OUTPUT_BYTES


def test_multiplier_cannot_be_raised_above_three():
    assert output_budget(10_000_000, multiplier=30) == 30_000_000


def test_video_bitrate_leaves_mux_and_audio_headroom():
    budget = 750_000_000
    bitrate = video_bitrate(duration=600, budget_bytes=budget, has_audio=True)
    projected_video_bytes = bitrate * 600 / 8
    assert projected_video_bytes < budget * 0.86


def test_jpeg_encoder_steps_down_until_it_meets_budget(tmp_path: Path):
    rng = np.random.default_rng(0)
    image = Image.fromarray(rng.integers(0, 256, (256, 256, 3), dtype=np.uint8))
    dest = tmp_path / "bounded.jpg"
    size, quality = save_image(image, dest, requested_quality=95, budget_bytes=60_000)
    assert dest.exists()
    assert size <= 60_000
    assert quality is not None and quality < 95


def test_oversized_lossless_output_is_not_promoted(tmp_path: Path):
    rng = np.random.default_rng(1)
    image = Image.fromarray(rng.integers(0, 256, (128, 128, 3), dtype=np.uint8))
    dest = tmp_path / "too-large.png"
    with pytest.raises(OutputTooLarge):
        save_image(image, dest, requested_quality=95, budget_bytes=100)
    assert not dest.exists()


def test_video_encoder_uses_the_calculated_bitrate(monkeypatch):
    from pixelith import video

    monkeypatch.setattr(video, "_available_encoders", lambda: "libx264 libx265")
    args = video._encoder_args(1280, 720, bitrate=4_000_000, prefer_hw=False)
    assert "-crf" not in args
    assert args[args.index("-b:v") + 1] == "4000000"
    assert args[args.index("-maxrate") + 1] == "5000000"


def test_video_encoder_falls_back_when_hardware_preflight_fails(
    monkeypatch, tmp_path: Path
):
    from pixelith import video

    monkeypatch.setattr(
        video, "_available_encoders", lambda: "h264_videotoolbox libx264"
    )
    monkeypatch.setattr(video, "_encoder_works", lambda *args: False)
    captured = {}

    class FakeProcess:
        pass

    def fake_popen(args, **kwargs):
        captured["args"] = args
        return FakeProcess()

    monkeypatch.setattr(video.subprocess, "Popen", fake_popen)
    video._open_encoder(tmp_path / "out.mp4", 1280, 720, 30.0, 4_000_000)

    assert "libx264" in captured["args"]
    assert "h264_videotoolbox" not in captured["args"]


def test_estimate_reports_video_compression_budget():
    from pixelith.server import EstimateRequest, estimate

    result = estimate(EstimateRequest(
        kind="video",
        width=640,
        height=480,
        frames=1800,
        fps=30,
        model="fast",
        preset="720p",
        aspect_ratio="16:9",
        source_bytes=250_000_000,
    ))

    assert result["output_width"] == 1280
    assert result["output_height"] == 720
    assert result["size_budget_bytes"] == 750_000_000
    assert result["max_size_ratio"] == 3.0
    assert result["target_video_bitrate"] > 0
    assert result["compression_policy"] == "adaptive_bitrate"
