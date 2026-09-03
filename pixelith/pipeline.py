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
from .config import LARGE_IMAGE_PIXELS, MODELS, PRESETS, UpscaleSettings
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

    def as_dict(self) -> dict:
        return {
            "source_width": self.src_width,
            "source_height": self.src_height,
            "output_width": self.out_width,
            "output_height": self.out_height,
            "passes": self.passes,
            "effective_scale": round(self.effective_scale, 3),
        }


def plan(
    src_w: int,
    src_h: int,
    preset: str | None = None,
    scale: float | None = None,
    model_scale: int = 4,
) -> Plan:
    """Work out the output size and how many network passes get us there."""
    if src_w <= 0 or src_h <= 0:
        raise ValueError("source dimensions must be positive")

    if preset:
        key = preset.lower()
        if key not in PRESETS:
            raise ValueError(f"unknown preset {preset!r}; try {sorted(PRESETS)}")
        box_w, box_h = PRESETS[key]
        # Fit inside the preset box, preserving aspect ratio.
        ratio = min(box_w / src_w, box_h / src_h)
        out_w, out_h = round(src_w * ratio), round(src_h * ratio)
    elif scale:
        if scale <= 0:
            raise ValueError("scale must be positive")
        out_w, out_h = round(src_w * scale), round(src_h * scale)
    else:
        out_w, out_h = src_w * model_scale, src_h * model_scale

    out_w, out_h = max(1, out_w), max(1, out_h)
    needed = max(out_w / src_w, out_h / src_h)

    if needed <= 1.0:
        passes = 0
    else:
        passes = min(MAX_PASSES, math.ceil(math.log(needed, model_scale)))
        passes = max(1, passes)

    return Plan(
        src_w, src_h, out_w, out_h, passes, needed, downsample=needed < model_scale**passes
    )


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
    through the fast model takes 8.3 s wall clock on an M5 Pro, which is
    2.07 MPix / 8.3 s. Timing a single repeated tile suggests something far
    rosier and is wrong - it re-runs one cached shape and skips the tiling
    overhead (a tile grid covers 1.4x-2.3x the real pixel count).
    """
    spec = MODELS[model]
    base = throughput or 0.25  # measured end-to-end: fast model, 1080p, M5 Pro
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
    eng = engine or Engine(spec, settings)

    rgb, alpha, mode = _load_rgb(src)
    h, w = rgb.shape[:2]
    p = plan(w, h, settings.preset, settings.scale, spec.scale)

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
        out = out.resize((p.out_width, p.out_height), Image.LANCZOS)

    out = _postprocess(out, settings)

    if alpha is not None:
        emit(0.97, "restoring transparency")
        a = Image.fromarray(alpha).resize((p.out_width, p.out_height), Image.LANCZOS)
        out = out.convert("RGBA")
        out.putalpha(a)

    emit(0.98, "writing file")
    dest.parent.mkdir(parents=True, exist_ok=True)
    suffix = dest.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        out.convert("RGB").save(dest, quality=settings.quality, subsampling=0,
                                optimize=True, progressive=True)
    elif suffix == ".webp":
        out.save(dest, quality=settings.quality, method=5)
    else:
        out.save(dest, optimize=True)

    emit(1.0, "done")
    return {
        **p.as_dict(),
        "elapsed": round(time.time() - started, 2),
        "model": spec.key,
        "provider": eng.provider,
        "output": str(dest),
        "had_alpha": alpha is not None,
        "source_mode": mode,
    }
