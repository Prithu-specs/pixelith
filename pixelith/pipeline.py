# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Scale planning, time estimation, and the still-image path.

The networks have a fixed 4x factor, but people ask for "8K" or "2x". Planning
turns a requested target into a number of network passes plus a final resample,
because running the net and then resampling down beats resampling alone.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from . import compat  # registers the HEIF opener as a side effect
from . import licensing, watermark
from .compression import expansion_ratio, output_budget, save_image
from .config import (ASPECT_MODES, ASPECT_RATIOS, LARGE_IMAGE_PIXELS, MODELS,
                     PRESETS, UpscaleSettings, resolve_preset)
from .engine import Engine

Image.MAX_IMAGE_PIXELS = None  # we do our own size guarding

MAX_PASSES = 2  # 4x per pass; 16x is already an extreme ask


@dataclass
class Plan:
    src_width: int
    src_height: int
    out_width: int
    out_height: int
    passes: int
    effective_scale: float
    downsample: bool
    aspect_ratio: str = "source"
    aspect_mode: str = "fit"

    def as_dict(self) -> dict:
        return {
            "source_width": self.src_width,
            "source_height": self.src_height,
            "output_width": self.out_width,
            "output_height": self.out_height,
            "passes": self.passes,
            "effective_scale": round(self.effective_scale, 3),
            "aspect_ratio": self.aspect_ratio,
            "aspect_mode": self.aspect_mode,
        }


def _aspect_dimensions(width: int, height: int, aspect_ratio: str) -> tuple[int, int]:
    ratio = ASPECT_RATIOS[aspect_ratio]
    if ratio is None:
        return width, height
    numerator, denominator = ratio
    if numerator >= denominator:
        return max(1, round(height * numerator / denominator)), height
    return height, max(1, round(height * denominator / numerator))


def plan(
    src_w: int,
    src_h: int,
    preset: str | None = None,
    scale: float | None = None,
    model_scale: int = 4,
    aspect_ratio: str = "source",
    aspect_mode: str = "fit",
) -> Plan:
    """Work out the output size and how many network passes get us there."""
    if src_w <= 0 or src_h <= 0:
        raise ValueError("source dimensions must be positive")
    if aspect_ratio not in ASPECT_RATIOS:
        raise ValueError(f"unknown aspect ratio {aspect_ratio!r}")
    if aspect_mode not in ASPECT_MODES:
        raise ValueError(f"unknown aspect mode {aspect_mode!r}")

    if preset:
        key = resolve_preset(preset)
        if key not in PRESETS:
            raise ValueError(f"unknown preset {preset!r}; try {sorted(PRESETS)}")
        box_w, box_h = PRESETS[key]
        if aspect_ratio == "source":
            # Fit inside the preset box, preserving source aspect ratio.
            ratio = min(box_w / src_w, box_h / src_h)
            out_w, out_h = round(src_w * ratio), round(src_h * ratio)
        else:
            out_w, out_h = _aspect_dimensions(box_w, box_h, aspect_ratio)
    elif scale:
        if scale <= 0:
            raise ValueError("scale must be positive")
        out_w, out_h = round(src_w * scale), round(src_h * scale)
        if aspect_ratio != "source":
            out_w, out_h = _aspect_dimensions(out_w, out_h, aspect_ratio)
    else:
        out_w, out_h = src_w * model_scale, src_h * model_scale

    out_w, out_h = max(1, out_w), max(1, out_h)
    if aspect_mode == "fit" and aspect_ratio != "source":
        needed = min(out_w / src_w, out_h / src_h)
    else:
        needed = max(out_w / src_w, out_h / src_h)

    if needed <= 1.0:
        passes = 0
    else:
        passes = min(MAX_PASSES, math.ceil(math.log(needed, model_scale)))
        passes = max(1, passes)

    return Plan(
        src_w,
        src_h,
        out_w,
        out_h,
        passes,
        needed,
        downsample=needed < model_scale**passes,
        aspect_ratio=aspect_ratio,
        aspect_mode=aspect_mode,
    )


def fit_to_canvas(
    image: Image.Image,
    size: tuple[int, int],
    mode: str = "fit",
) -> Image.Image:
    """Render an image into a fixed canvas by fitting, cropping or stretching."""
    if mode not in ASPECT_MODES:
        raise ValueError(f"unknown aspect mode {mode!r}")
    if mode == "stretch":
        return image.resize(size, Image.LANCZOS)
    if mode == "fill":
        return ImageOps.fit(image, size, Image.LANCZOS, centering=(0.5, 0.5))

    fitted = ImageOps.contain(image, size, Image.LANCZOS)
    if image.mode == "RGBA":
        colour = (0, 0, 0, 0)
    elif image.mode == "L":
        colour = 0
    else:
        colour = (0, 0, 0)
    canvas = Image.new(image.mode, size, colour)
    canvas.paste(
        fitted,
        ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2),
    )
    return canvas


def estimate_seconds(
    src_w: int,
    src_h: int,
    p: Plan,
    model: str = "fast",
    frames: int = 1,
    throughput: float | None = None,
) -> float:
    """Rough wall-clock estimate, in seconds.

    `throughput` is input megapixels/second for the *fast* model on this
    machine; each model scales it by its measured relative cost.

    The figure below is deliberately an end-to-end number: a 1920x1080 frame
    through the fast model takes 3.7 s wall clock on an M5 Pro, which is
    2.07 MPix / 3.7 s. Timing a single repeated tile suggests something far
    rosier and is wrong - it re-runs one cached shape and ignores tiling
    entirely.
    """
    spec = MODELS[model]
    base = throughput or 0.56  # measured end-to-end: fast model, 1080p, M5 Pro
    rate = base / spec.cost

    total = 0.0
    w, h = src_w, src_h
    for _ in range(p.passes):
        total += (w * h) / 1e6 / rate
        w, h = w * spec.scale, h * spec.scale
    total *= max(1, frames)
    # Decode/encode/resample overhead.
    return total * 1.12 + (1.5 if frames == 1 else 8.0)


def human_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 1:
        return "under a second"
    if seconds < 60:
        n = round(seconds)
        return f"about {n} second{'' if n == 1 else 's'}"
    mins, secs = divmod(int(seconds + 0.5), 60)
    if mins < 60:
        return f"about {mins} min {secs:02d} s"
    hours, mins = divmod(mins, 60)
    if hours < 48:
        return f"about {hours} h {mins:02d} min"
    days = hours // 24
    return f"about {days} day{'' if days == 1 else 's'}"


def _load_rgb(path: Path) -> tuple[np.ndarray, np.ndarray | None, str]:
    """Return (RGB uint8, alpha or None, original mode)."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)  # honour camera rotation
        mode = im.mode
        alpha = None
        if mode in ("RGBA", "LA", "PA"):
            alpha = np.asarray(im.convert("RGBA").split()[-1], dtype=np.uint8)
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
    return rgb, alpha, mode


def _postprocess(im: Image.Image, settings: UpscaleSettings) -> Image.Image:
    if settings.denoise > 0:
        radius = 0.4 + 1.6 * float(settings.denoise)
        im = im.filter(ImageFilter.GaussianBlur(radius=radius * 0.35))
    if settings.sharpen > 0:
        amount = float(settings.sharpen)
        im = im.filter(
            ImageFilter.UnsharpMask(radius=1.4, percent=int(60 * amount), threshold=3)
        )
        im = ImageEnhance.Sharpness(im).enhance(1.0 + 0.35 * amount)
    return im


def upscale_image(
    src: Path,
    dest: Path,
    settings: UpscaleSettings,
    engine: Engine | None = None,
    progress: Callable[[float, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict:
    """Upscale one still image. Returns a small report dict."""
    started = time.time()
    spec = settings.resolved_model()

    # Checked before any work, so a blocked job costs the user nothing.
    licensing.check_allowance("image")

    eng = engine or Engine(spec, settings)
    rgb, alpha, mode = _load_rgb(src)
    h, w = rgb.shape[:2]
    p = plan(
        w,
        h,
        settings.preset,
        settings.scale,
        spec.scale,
        settings.aspect_ratio,
        settings.aspect_mode,
    )

    if (p.out_width * p.out_height) > LARGE_IMAGE_PIXELS * 4:
        raise ValueError(
            f"requested output is {p.out_width}x{p.out_height} "
            f"({p.out_width * p.out_height / 1e6:.0f} MPix), which is beyond "
            "what this tool will attempt in one piece."
        )

    def emit(frac: float, msg: str) -> None:
        if progress:
            progress(max(0.0, min(1.0, frac)), msg)

    current = rgb
    for i in range(p.passes):
        lo, span = i / p.passes, 1 / p.passes
        emit(lo, f"upscaling pass {i + 1} of {p.passes}")
        current = eng.upscale(
            current,
            progress=lambda f, lo=lo, span=span: emit(lo + f * span, "upscaling"),
            should_cancel=should_cancel,
        )

    out = Image.fromarray(current)
    if (out.width, out.height) != (p.out_width, p.out_height):
        emit(0.94, "resampling to target size")
        out = fit_to_canvas(
            out, (p.out_width, p.out_height), settings.aspect_mode
        )

    out = _postprocess(out, settings)

    # Free-tier output carries a machine-readable provenance mark. A paid
    # licence turns it off. Disclosed in the licence and the interface - it is
    # a mark of where the file came from, not a covert tracker.
    marked = False
    if licensing.current_tier() not in licensing.PAID_TIERS:
        try:
            usage = licensing.load_usage()
            payload = watermark.build_payload(
                watermark.TIER_FREE,
                bytes.fromhex(usage.install_id),
                usage.images + 1,
            )
            out = Image.fromarray(
                watermark.embed(np.asarray(out.convert("RGB")), payload)
            )
            marked = True
        except (watermark.WatermarkError, ValueError):
            # Too small to carry a mark; not a reason to fail the job.
            marked = False

    if alpha is not None:
        emit(0.97, "restoring transparency")
        a = fit_to_canvas(
            Image.fromarray(alpha),
            (p.out_width, p.out_height),
            settings.aspect_mode,
        )
        out = out.convert("RGBA")
        out.putalpha(a)

    emit(0.98, "writing file")
    dest.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = src.stat().st_size
    budget_bytes = output_budget(source_bytes, settings.max_output_multiplier)
    output_bytes, encoded_quality = save_image(
        out, dest, settings.quality, budget_bytes
    )

    licensing.record(images=1)

    emit(1.0, "done")
    return {
        **p.as_dict(),
        "watermarked": marked,
        "elapsed": round(time.time() - started, 2),
        "model": spec.key,
        "provider": eng.provider,
        "providers": eng.active_providers,
        "output": str(dest),
        "had_alpha": alpha is not None,
        "source_mode": mode,
        "source_bytes": source_bytes,
        "output_bytes": output_bytes,
        "size_ratio": round(expansion_ratio(source_bytes, output_bytes), 3),
        "size_budget_bytes": budget_bytes,
        "encoded_quality": encoded_quality,
    }
