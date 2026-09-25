"""Video frame-rate selection and estimate behavior."""
from pathlib import Path

import pytest
from fastapi import HTTPException

from pixelith.config import UpscaleSettings, VIDEO_FPS_CHOICES
from pixelith.server import EstimateRequest, estimate
from pixelith.video import VideoInfo, _frame_rates, _open_decoder, _open_encoder


def test_supported_frame_rates_and_source_default():
    assert VIDEO_FPS_CHOICES == (24, 30, 60, 120)
    assert UpscaleSettings().target_fps is None


def test_decoder_does_not_duplicate_frames_before_ai(monkeypatch):
    captured = {}

    class FakeProcess:
        pass

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr("pixelith.video.subprocess.Popen", fake_popen)
    info = VideoInfo(640, 480, 24.0, 240, 10.0, True, "h264")
    _open_decoder(Path("clip.mp4"), info, 60.0)

    args = captured["args"]
    assert "-vf" not in args
    assert captured["kwargs"]["bufsize"] == 640 * 480 * 3 * 2


def test_source_fps_skips_unnecessary_filter(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "pixelith.video.subprocess.Popen",
        lambda args, **kwargs: captured.setdefault("args", args),
    )
    info = VideoInfo(640, 480, 30.0, 300, 10.0, False, "h264")
    _open_decoder(Path("clip.mp4"), info, 30.0)
    assert "-vf" not in captured["args"]


@pytest.mark.parametrize("source_fps", [24.0, 30.0, 60.0, 120.0])
def test_source_default_preserves_original_frame_rate(source_fps):
    info = VideoInfo(640, 480, source_fps, int(source_fps * 10), 10.0,
                     False, "h264")
    processing_fps, output_fps, ai_frames, output_frames = _frame_rates(info, None)
    assert processing_fps == source_fps
    assert output_fps == source_fps
    assert ai_frames == int(source_fps * 10)
    assert output_frames == int(source_fps * 10)


def test_60_fps_estimate_duplicates_after_ai_instead_of_doubling_inference():
    common = dict(
        kind="video", width=640, height=480, frames=300, fps=30,
        model="fast", preset="720p", source_bytes=10_000_000,
    )
    source = estimate(EstimateRequest(**common))
    sixty = estimate(EstimateRequest(**common, target_fps=60))

    assert sixty["output_fps"] == 60
    assert sixty["output_frames"] == 600
    assert sixty["ai_frames"] == 300
    assert sixty["seconds"] == source["seconds"]


def test_frame_rate_plan_drops_before_ai_and_duplicates_after_ai():
    info = VideoInfo(640, 480, 30.0, 300, 10.0, False, "h264")
    assert _frame_rates(info, 24) == (24.0, 24.0, 240, 240)
    assert _frame_rates(info, 120) == (30.0, 120.0, 300, 1200)


def test_encoder_applies_higher_output_fps_after_raw_ai_frames(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("pixelith.video._encoder_args", lambda *a, **k: ["-c:v", "libx264"])
    monkeypatch.setattr(
        "pixelith.video.subprocess.Popen",
        lambda args, **kwargs: captured.setdefault("args", args),
    )
    _open_encoder(tmp_path / "clip.mp4", 640, 480, 30.0, 1_000_000, output_fps=120.0)
    args = captured["args"]
    assert args[args.index("-r") + 1] == "30.0"
    assert args[args.index("-vf") + 1] == "fps=120.0"


def test_api_rejects_unsupported_fps():
    with pytest.raises(HTTPException) as exc:
        estimate(EstimateRequest(
            kind="video", width=640, height=480, frames=300, fps=30,
            model="fast", preset="720p", target_fps=25,
        ))
    assert exc.value.status_code == 400


def test_cli_accepts_supported_fps():
    from pixelith.cli import build_parser

    args = build_parser().parse_args(["upscale", "clip.mp4", "--fps", "120"])
    assert args.fps == 120
