"""Real encoding and failure cases for explicit video quality/speed choices."""
from pathlib import Path
import shutil
import subprocess

import pytest

from pixelith.config import UpscaleSettings
from pixelith.engine import Cancelled
from pixelith.server import EstimateRequest, estimate
from pixelith.video import _encoder_args, probe, upscale_video


def test_quality_mode_does_not_squeeze_long_hd_video_into_one_gb(monkeypatch):
    monkeypatch.setattr(
        "pixelith.video._available_encoders",
        lambda: pytest.fail("quality mode probed FFmpeg encoders"),
    )
    common = dict(kind="video", width=546, height=420, frames=135200, fps=25,
                  preset="1080p", aspect_ratio="16:9", source_bytes=297638055)
    limited = estimate(EstimateRequest(**common))
    quality = estimate(EstimateRequest(**common, video_encoding="quality"))
    assert limited["target_video_bitrate"] < 1_000_000
    assert "Visible compression" in limited["warning"]
    assert quality["size_budget_bytes"] is None
    assert quality["target_video_bitrate"] is None
    assert quality["compression_policy"] == "constant_quality"
    assert "black bars" in quality["warning"]
    args = _encoder_args(1920, 1080, None)
    assert "-crf" in args and "-b:v" not in args


def test_native_estimate_does_not_claim_ai_speed_or_passes():
    result = estimate(EstimateRequest(kind="video", width=546, height=420,
                      frames=135200, fps=25, preset="1080p", video_processing="native"))
    assert result["seconds"] is None
    assert result["passes"] == 0


def test_large_video_uses_one_ai_pass_then_resamples_to_target():
    result = estimate(EstimateRequest(kind="video", width=546, height=420,
                      frames=135200, fps=25, preset="4k", model="fast"))
    assert result["passes"] == 1
    assert result["ai_frames"] == 135200
    assert result["seconds"] < 100_000


@pytest.fixture
def clip(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg required")
    src = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=s=160x120:r=25:d=1", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=1", "-c:v", "libx264",
                    "-c:a", "aac", "-shortest", str(src)], check=True)
    return src


@pytest.mark.parametrize("framing", ["fit", "fill", "stretch"])
def test_native_actual_video_has_expected_canvas_audio_and_source_fps(clip, tmp_path, monkeypatch, framing):
    # Loading any neural model defeats this mode's central guarantee.
    monkeypatch.setattr("pixelith.video.Engine", lambda *a, **k: pytest.fail("loaded AI model"))
    monkeypatch.setattr("pixelith.licensing.check_allowance", lambda *a, **k: None)
    monkeypatch.setattr("pixelith.licensing.record", lambda *a, **k: None)
    out = tmp_path / "out.mp4"
    settings = UpscaleSettings(preset="360p", aspect_ratio="16:9", aspect_mode=framing,
                               video_processing="native", video_encoding="quality")
    report = upscale_video(clip, out, settings, tmp_path / "work")
    info = probe(out)
    assert (info.width, info.height, info.fps) == (640, 360, 25)
    assert info.has_audio and abs(info.duration - 1) < .15
    assert report["passes"] == 0 and report["size_budget_bytes"] is None
    rgb = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(out),
                                   "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    import numpy as np
    frame = np.frombuffer(rgb, dtype=np.uint8).reshape(360, 640, 3)
    if framing == "fit":
        assert frame[:, :50].mean() < 3
    else:
        assert frame[:, :50].mean() > 10


def test_native_cancel_preserves_existing_output_and_cleans_partial(clip, tmp_path, monkeypatch):
    monkeypatch.setattr("pixelith.licensing.check_allowance", lambda *a, **k: None)
    monkeypatch.setattr("pixelith.licensing.record", lambda *a, **k: pytest.fail("recorded cancelled job"))
    out = tmp_path / "out.mp4"
    out.write_bytes(b"existing")
    with pytest.raises(Cancelled):
        upscale_video(clip, out, UpscaleSettings(preset="360p", video_processing="native",
                      video_encoding="quality"), tmp_path / "work", should_cancel=lambda: True)
    assert out.read_bytes() == b"existing"
    assert not list(tmp_path.glob(".pixelith-*"))


def test_native_preview_works_without_model(clip, monkeypatch):
    from pixelith import preview
    monkeypatch.setattr(preview, "Engine", lambda *a, **k: pytest.fail("loaded AI model"))
    result = preview.run(clip, "video", UpscaleSettings(preset="360p", aspect_ratio="16:9",
                         aspect_mode="fill", video_processing="native"))
    assert (result.out_width, result.out_height) == (640, 360)
    assert result.after.exists()


def test_ai_fps_increase_happens_after_inference(clip, tmp_path, monkeypatch):
    import numpy as np
    from PIL import Image

    class FakeEngine:
        tile = 192
        overlap = 16
        provider = "test"
        active_providers = ["test"]

        def upscale(self, frame, should_cancel=None):
            return np.asarray(Image.fromarray(frame).resize(
                (frame.shape[1] * 4, frame.shape[0] * 4), Image.Resampling.NEAREST
            ))

    monkeypatch.setattr("pixelith.licensing.check_allowance", lambda *a, **k: None)
    monkeypatch.setattr("pixelith.licensing.record", lambda *a, **k: None)
    out = tmp_path / "fps-60.mp4"
    report = upscale_video(
        clip,
        out,
        UpscaleSettings(preset="360p", target_fps=60, video_encoding="quality"),
        tmp_path / "ai-work",
        engine=FakeEngine(),
    )
    info = probe(out)
    assert info.fps == 60
    assert abs(info.duration - 1) < .15
    assert report["ai_frames"] == 25
    assert report["frames"] == 60
    assert report["frames_processed"] == 25
