# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Streaming FFmpeg resize for users who choose speed over neural enhancement.

No model, RGB round trips, or per-frame Python processing. Never uploads media.
"""
from __future__ import annotations

import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from . import licensing
from .compression import output_budget, video_bitrate
from .config import VIDEO_FPS_CHOICES
from .engine import Cancelled
from .pipeline import plan


def filters(width: int, height: int, settings) -> str:
    """Geometry shared by native export and preview. Input bars are preserved."""
    if settings.aspect_mode == "fit":
        geometry = (f"scale={width}:{height}:flags=lanczos:"
                    "force_original_aspect_ratio=decrease:force_divisible_by=2,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black")
    elif settings.aspect_mode == "fill":
        geometry = (f"scale={width}:{height}:flags=lanczos:"
                    "force_original_aspect_ratio=increase:force_divisible_by=2,"
                    f"crop={width}:{height}")
    elif settings.aspect_mode == "stretch":
        geometry = f"scale={width}:{height}:flags=lanczos"
    else:
        raise ValueError("unknown framing mode")
    parts = [geometry, "setsar=1"]
    if settings.denoise:
        # A spatial denoiser: identical behavior in still preview and video.
        strength = 1 + 3 * settings.denoise
        parts.append(f"hqdn3d={strength}:{strength}:0:0")
    if settings.sharpen:
        parts.append(f"unsharp=5:5:{settings.sharpen}:5:5:0")
    if settings.target_fps:
        parts.append(f"fps={settings.target_fps}")
    return ",".join(parts)


def convert(src, dest, settings, work_dir, progress=None, should_cancel=None):
    from .video import VideoError, _encoder_args, _encoder_works, probe

    info = probe(src)
    if settings.target_fps and settings.target_fps not in VIDEO_FPS_CHOICES:
        raise VideoError("unsupported output frame rate")
    if info.duration <= 0 or info.frames <= 0:
        raise VideoError("could not determine video duration")
    p = plan(info.width, info.height, settings.preset, settings.scale,
             settings.resolved_model().scale, settings.aspect_ratio,
             settings.aspect_mode)
    w, h = max(2, p.out_width // 2 * 2), max(2, p.out_height // 2 * 2)
    fps = settings.target_fps or info.fps
    budget = (output_budget(src.stat().st_size, settings.max_output_multiplier)
              if settings.video_encoding == "bounded" else None)
    bitrate = video_bitrate(info.duration, budget, info.has_audio) if budget else None
    codec = _encoder_args(w, h, bitrate)
    if any("videotoolbox" in arg for arg in codec):
        try:
            usable = _encoder_works(tuple(codec), w, h, fps)
        except (OSError, subprocess.TimeoutExpired):
            usable = False
        if not usable:
            codec = _encoder_args(w, h, bitrate, prefer_hw=False)

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # A unique sibling is atomically promoted only on success.
    with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=".pixelith-",
                                     suffix=dest.suffix, delete=False) as out:
        partial = Path(out.name)
    args = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(src),
            "-map", "0:v:0", "-map", "0:a:0?", "-vf", filters(w, h, settings),
            *codec, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160000",
            "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(partial)]
    started = time.perf_counter()
    events = queue.Queue()
    proc = None
    frames = 0
    try:
        with tempfile.TemporaryFile(mode="w+") as errors:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors,
                                    text=True)

            def collect():
                for line in proc.stdout:
                    events.put(line.strip())
                events.put(None)

            reader = threading.Thread(target=collect, daemon=True)
            reader.start()
            while True:
                if should_cancel and should_cancel():
                    raise Cancelled()
                try:
                    line = events.get(timeout=0.2)
                except queue.Empty:
                    if proc.poll() is not None and not reader.is_alive():
                        break
                    continue
                if line is None:
                    break
                key, _, value = line.partition("=")
                if key == "frame":
                    frames = int(value)
                if key == "out_time_us" and value != "N/A" and progress:
                    fraction = max(0, min(0.99, int(value) / 1e6 / info.duration))
                    elapsed = time.perf_counter() - started
                    progress(fraction, "resizing and encoding video", {
                        "eta_seconds": elapsed * (1 / fraction - 1) if fraction > .01 else None,
                    })
            if proc.wait() != 0:
                errors.seek(0)
                raise VideoError("video conversion failed: " + errors.read(1200))
            if should_cancel and should_cancel():
                raise Cancelled()
        size = partial.stat().st_size
        if not size or (budget is not None and size > budget):
            raise VideoError("output exceeded the size limit; choose Preserve quality")
        result = probe(partial)
        if (result.width, result.height) != (w, h):
            raise VideoError("unexpected output dimensions")
        partial.replace(dest)
    finally:
        if proc is not None:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            if proc.stdout:
                proc.stdout.close()
        partial.unlink(missing_ok=True)
    licensing.record(video_bytes=src.stat().st_size)
    elapsed = time.perf_counter() - started
    if progress:
        progress(1, "done", {"eta_seconds": 0})
    return {**p.as_dict(), "passes": 0, "output_width": w, "output_height": h,
            "model": "none", "provider": "FFmpeg", "providers": ["FFmpeg"],
            "video_processing": "native", "video_encoding": settings.video_encoding,
            "frames": result.frames, "frames_processed": frames, "fps": result.fps,
            "source_fps": info.fps, "elapsed": round(elapsed, 3),
            "output_bytes": size, "source_bytes": src.stat().st_size,
            "size_ratio": round(size / src.stat().st_size, 3),
            "size_budget_bytes": budget, "target_video_bitrate": bitrate,
            "audio": result.has_audio, "output": str(dest), "resumable": False}
