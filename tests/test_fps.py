"""Video frame-rate selection and estimate behavior."""
from pathlib import Path

import pytest
from fastapi import HTTPException

from pixelith.config import UpscaleSettings, VIDEO_FPS_CHOICES
from pixelith.server import EstimateRequest, estimate
from pixelith.video import VideoInfo, _open_decoder


def test_supported_frame_rates_and_source_default():
    assert VIDEO_FPS_CHOICES == (24, 30, 60, 120)
    assert UpscaleSettings().target_fps is None


def test_decoder_filters_to_requested_fps_without_changing_geometry(monkeypatch):
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
    assert args[args.index("-vf") + 1] == "fps=60.0"
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


def test_60_fps_estimate_accounts_for_twice_as_many_frames():
    common = dict(
        kind="video", width=640, height=480, frames=300, fps=30,
        model="fast", preset="720p", source_bytes=10_000_000,
    )
    source = estimate(EstimateRequest(**common))
    sixty = estimate(EstimateRequest(**common, target_fps=60))

    assert sixty["output_fps"] == 60
    assert sixty["output_frames"] == 600
    assert sixty["seconds"] > source["seconds"] * 1.9


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
