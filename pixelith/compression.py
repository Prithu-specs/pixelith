# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Output-size policy shared by still images and video."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from .config import MAX_OUTPUT_BYTES, MAX_OUTPUT_MULTIPLIER

AUDIO_BITRATE = 160_000


class OutputTooLarge(ValueError):
    pass


def output_budget(source_bytes: int, multiplier: float = MAX_OUTPUT_MULTIPLIER) -> int:
    """Return the strict output ceiling: at most 3x source and at most 1 GB."""
    if source_bytes <= 0:
        raise ValueError("source size must be positive")
    factor = max(1.0, min(MAX_OUTPUT_MULTIPLIER, float(multiplier)))
    return min(MAX_OUTPUT_BYTES, max(1, int(source_bytes * factor)))


def expansion_ratio(source_bytes: int, output_bytes: int) -> float:
    return output_bytes / max(1, source_bytes)


def video_bitrate(duration: float, budget_bytes: int, has_audio: bool) -> int:
    """Average video bitrate with headroom for audio, muxing and VBR peaks."""
    if duration <= 0:
        raise ValueError("video duration must be positive")
    audio_bytes = AUDIO_BITRATE * duration / 8 if has_audio else 0
    available = budget_bytes * 0.86 - audio_bytes
    if available <= 0:
        raise OutputTooLarge("the source-size budget is too small for this video")
    return max(64_000, int(available * 8 / duration))


def save_image(
    image: Image.Image,
    dest: Path,
    requested_quality: int,
    budget_bytes: int,
) -> tuple[int, int | None]:
    """Encode an image without ever promoting an oversized partial file.

    Lossy formats step quality down to 35 when necessary. PNG remains lossless;
    if lossless data cannot meet the budget the job fails with an actionable
    message instead of silently changing formats or producing a huge file.
    """
    suffix = dest.suffix.lower()
    temp = dest.with_name(f".{dest.name}.part")
    temp.unlink(missing_ok=True)
    try:
        if suffix in (".jpg", ".jpeg", ".webp"):
            start = max(35, min(100, int(requested_quality)))
            qualities = list(range(start, 34, -5))
            if qualities[-1] != 35:
                qualities.append(35)
            for quality in qualities:
                temp.unlink(missing_ok=True)
                if suffix in (".jpg", ".jpeg"):
                    rgb = image.convert("RGB")
                    try:
                        rgb.save(
                            temp,
                            "JPEG",
                            quality=quality,
                            subsampling=0,
                            optimize=True,
                            progressive=True,
                        )
                    except OSError:
                        # Some libjpeg builds cannot optimise very noisy images.
                        temp.unlink(missing_ok=True)
                        rgb.save(temp, "JPEG", quality=quality, subsampling=0)
                else:
                    image.save(temp, "WEBP", quality=quality, method=5)
                size = temp.stat().st_size
                if size <= budget_bytes:
                    temp.replace(dest)
                    return size, quality
        else:
            image.save(temp, "PNG", optimize=True, compress_level=9)
            size = temp.stat().st_size
            if size <= budget_bytes:
                temp.replace(dest)
                return size, None

        raise OutputTooLarge(
            f"compressed output would exceed {budget_bytes / 1_000_000:.1f} MB; "
            "choose JPEG or WEBP, lower the target resolution, or use a larger "
            "source file"
        )
    finally:
        temp.unlink(missing_ok=True)
