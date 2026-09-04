# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""One-frame preview: the answer to 'is this worth four hours'."""
import shutil

import numpy as np
import pytest
from PIL import Image

from pixelith import preview
from pixelith.config import MODELS, UpscaleSettings
from pixelith.models import is_available

needs_model = pytest.mark.skipif(
    not is_available(MODELS["fast"]), reason="model weights not downloaded"
)
needs_ffmpeg = pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="ffmpeg not installed"
)


def test_store_is_bounded():
    """Previews are disposable; they must not accumulate on disk for ever."""
    assert preview.MAX_KEPT <= 32


def test_unknown_preview_is_not_found():
    assert preview.get("nope") is None


@needs_model
@pytest.mark.needs_model
def test_image_preview_produces_both_sides(tmp_path):
    src = tmp_path / "in.png"
    Image.fromarray(
        (np.random.rand(200, 300, 3) * 255).astype(np.uint8)
    ).save(src)

    result = preview.run(src, "image", UpscaleSettings(preset="720p"))
    assert result.before.exists() and result.after.exists()
    assert (result.source_width, result.source_height) == (300, 200)
    assert result.out_width > result.source_width
    assert result.seconds > 0
    assert result.frame_index is None
    assert preview.get(result.id) is result

    with Image.open(result.after) as im:
        assert im.width > 0


@needs_ffmpeg
@needs_model
@pytest.mark.needs_model
def test_video_preview_takes_a_frame_from_the_middle(tmp_path):
    import subprocess

    clip = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", "testsrc2=s=160x120:d=2:r=30", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", str(clip)],
        check=True,
    )

    frame, index = preview.extract_frame(clip)
    assert frame.shape == (120, 160, 3)
    # 60 frames in, so the middle is around 30 - not the first frame, which
    # would make the preview useless on a clip that fades in.
    assert 20 <= index <= 40

    result = preview.run(clip, "video", UpscaleSettings(scale=2.0))
    assert result.frame_index == index
    assert result.before.exists() and result.after.exists()
    assert result.seconds > 0


@needs_ffmpeg
def test_a_file_with_no_video_stream_is_refused(tmp_path):
    from pixelith.video import VideoError

    bogus = tmp_path / "not-a-video.mp4"
    bogus.write_bytes(b"this is not a video file at all")
    with pytest.raises(VideoError):
        preview.extract_frame(bogus)
