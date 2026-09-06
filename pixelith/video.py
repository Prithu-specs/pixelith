# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""The video path: decode -> upscale -> encode, without ever unpacking frames to disk.

Long jobs are the norm here (an 8K pass is measured in hours), so the run is cut
into fixed-length segments that are encoded and kept as they complete. If the
process dies or the user stops it, finished segments survive and the job resumes
from the next one. Frames are streamed through pipes; nothing writes a PNG
sequence, which for 8K would be hundreds of gigabytes.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, asdict
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np

from . import licensing
from .compression import (AUDIO_BITRATE, OutputTooLarge, expansion_ratio,
                          output_budget, video_bitrate)
from .config import VIDEO_FPS_CHOICES, UpscaleSettings
from .engine import Cancelled, Engine
from .pipeline import Plan, fit_to_canvas, plan

SEGMENT_FRAMES = 240  # ~8 s at 30 fps


class VideoError(RuntimeError):
    pass


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise VideoError(
            f"{tool} was not found on PATH. Install FFmpeg "
            "(macOS: brew install ffmpeg, Debian/Ubuntu: apt install ffmpeg)."
        )
    return path


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    frames: int
    duration: float
    has_audio: bool
    codec: str

    def as_dict(self) -> dict:
        return asdict(self)


def probe(path: Path) -> VideoInfo:
    """Read stream metadata. Falls back to duration*fps when the frame count is absent."""
    _require("ffprobe")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise VideoError(f"ffprobe could not read {path.name}: {out.stderr.strip()[:300]}")
    data = json.loads(out.stdout or "{}")
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not v:
        raise VideoError(f"{path.name} contains no video stream.")

    num, _, den = (v.get("avg_frame_rate") or "0/1").partition("/")
    try:
        fps = float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    if fps <= 0:
        fps = 30.0

    duration = float(data.get("format", {}).get("duration") or v.get("duration") or 0.0)
    frames = int(v.get("nb_frames") or 0)
    if frames <= 0:
        frames = int(round(duration * fps)) if duration else 0

    return VideoInfo(
        width=int(v.get("width") or 0),
        height=int(v.get("height") or 0),
        fps=round(fps, 4),
        frames=frames,
        duration=round(duration, 3),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        codec=str(v.get("codec_name") or "?"),
    )


@lru_cache(maxsize=1)
def _available_encoders() -> str:
    return subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True
    ).stdout


def _encoder_args(
    width: int,
    height: int,
    bitrate: int,
    prefer_hw: bool = True,
) -> list[str]:
    """Pick a codec. Above 4K we need HEVC; H.264 levels do not cover 8K."""
    big = (width * height) > (3840 * 2160)
    encoders = _available_encoders()
    rate = [
        "-b:v", str(bitrate),
        "-maxrate", str(int(bitrate * 1.25)),
        "-bufsize", str(bitrate * 2),
    ]

    def has(name: str) -> bool:
        return name in encoders

    if big:
        if prefer_hw and has("hevc_videotoolbox"):
            return ["-c:v", "hevc_videotoolbox", "-allow_sw", "1",
                    *rate, "-tag:v", "hvc1"]
        if has("libx265"):
            return ["-c:v", "libx265", "-preset", "medium", *rate,
                    "-tag:v", "hvc1"]
    if prefer_hw and has("h264_videotoolbox"):
        return ["-c:v", "h264_videotoolbox", "-allow_sw", "1", *rate]
    return ["-c:v", "libx264", "-preset", "medium", *rate]


@lru_cache(maxsize=32)
def _encoder_works(
    encoder_args: tuple[str, ...], width: int, height: int, fps: float
) -> bool:
    """Return whether an advertised hardware encoder can start successfully."""
    check = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
            f"color=c=black:s={width}x{height}:r={fps}",
            "-frames:v", "1", "-an", "-pix_fmt", "yuv420p",
            *encoder_args, "-f", "null", "-",
        ],
        capture_output=True,
        timeout=30,
    )
    return check.returncode == 0


def _open_decoder(
    src: Path, info: VideoInfo, target_fps: float | None = None
) -> subprocess.Popen:
    args = ["ffmpeg", "-v", "error", "-i", str(src)]
    if target_fps is not None and abs(target_fps - info.fps) > 0.001:
        # FFmpeg's fps filter preserves duration: it drops frames when reducing
        # FPS and duplicates the nearest frame when increasing it.
        args += ["-vf", f"fps={target_fps}"]
    args += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    return subprocess.Popen(
        args,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        bufsize=info.width * info.height * 3 * 2,
    )


def _open_encoder(
    dest: Path, w: int, h: int, fps: float, bitrate: int
) -> subprocess.Popen:
    encoder_args = _encoder_args(w, h, bitrate)
    if any("videotoolbox" in arg for arg in encoder_args):
        try:
            usable = _encoder_works(tuple(encoder_args), w, h, fps)
        except (OSError, subprocess.TimeoutExpired):
            usable = False
        if not usable:
            encoder_args = _encoder_args(w, h, bitrate, prefer_hw=False)
    args = ["ffmpeg", "-v", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-",
            "-an", "-pix_fmt", "yuv420p",
            *encoder_args, str(dest)]
    return subprocess.Popen(args, stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def upscale_video(
    src: Path,
    dest: Path,
    settings: UpscaleSettings,
    work_dir: Path,
    engine: Engine | None = None,
    progress: Callable[[float, str, dict], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    resume: bool = True,
) -> dict:
    """Upscale a video file. Returns a report dict."""
    _require("ffmpeg")
    started = time.time()
    spec = settings.resolved_model()

    # Video counts against the allowance by input file size, checked up front.
    licensing.check_allowance("video", video_bytes=src.stat().st_size)

    eng = engine or Engine(spec, settings)
    info = probe(src)
    if info.frames <= 0:
        raise VideoError(f"could not determine the frame count of {src.name}.")
    if settings.target_fps is not None and settings.target_fps not in VIDEO_FPS_CHOICES:
        raise VideoError(
            f"unsupported output FPS {settings.target_fps}; "
            f"choose one of {VIDEO_FPS_CHOICES}"
        )

    output_fps = float(settings.target_fps or info.fps)
    output_frames = (
        max(1, round(info.duration * output_fps))
        if settings.target_fps and info.duration > 0
        else max(1, info.frames)
    )

    p: Plan = plan(
        info.width,
        info.height,
        settings.preset,
        settings.scale,
        spec.scale,
        settings.aspect_ratio,
        settings.aspect_mode,
    )
    out_w, out_h = p.out_width - (p.out_width % 2), p.out_height - (p.out_height % 2)
    source_bytes = src.stat().st_size
    budget_bytes = output_budget(source_bytes, settings.max_output_multiplier)
    try:
        target_bitrate = video_bitrate(info.duration, budget_bytes, info.has_audio)
    except (ValueError, OutputTooLarge) as exc:
        raise VideoError(str(exc)) from exc

    work_dir.mkdir(parents=True, exist_ok=True)
    seg_dir = work_dir / "segments"
    seg_dir.mkdir(exist_ok=True)
    state_file = work_dir / "state.json"

    # Anything that changes output pixels belongs in the signature, otherwise a
    # re-run with different settings would silently reuse stale segments.
    signature = {
        "src": str(src), "size": src.stat().st_size, "mtime": int(src.stat().st_mtime),
        "out": [out_w, out_h], "model": spec.key, "passes": p.passes,
        "source_fps": info.fps, "fps": output_fps,
        "tile": eng.tile, "overlap": eng.overlap,
        "denoise": round(float(settings.denoise), 4),
        "sharpen": round(float(settings.sharpen), 4),
        "aspect_ratio": settings.aspect_ratio,
        "aspect_mode": settings.aspect_mode,
        "target_bitrate": target_bitrate,
        "size_budget": budget_bytes,
    }
    done_segments = 0
    if resume and state_file.exists():
        try:
            prev = json.loads(state_file.read_text())
            if prev.get("signature") == signature:
                done_segments = int(prev.get("done_segments", 0))
            else:
                shutil.rmtree(seg_dir); seg_dir.mkdir()
        except (json.JSONDecodeError, OSError):
            done_segments = 0
    # Trust only segments that actually exist on disk.
    while done_segments and not (seg_dir / f"seg_{done_segments - 1:05d}.mp4").exists():
        done_segments -= 1

    total_segments = max(1, -(-output_frames // SEGMENT_FRAMES))
    start_frame = done_segments * SEGMENT_FRAMES
    frame_bytes = info.width * info.height * 3

    def emit(frac: float, msg: str, extra: dict | None = None) -> None:
        if progress:
            progress(max(0.0, min(1.0, frac)), msg, extra or {})

    if done_segments:
        emit(start_frame / output_frames,
             f"resuming after {done_segments} finished segment(s)", {})

    dec = _open_decoder(src, info, output_fps)
    enc: subprocess.Popen | None = None
    seg_index = done_segments
    frames_in_segment = 0
    processed = 0
    per_frame_times: list[float] = []

    try:
        # Skip frames belonging to already-finished segments. Decoding is
        # milliseconds per frame against seconds of inference, so this is cheap.
        for _ in range(start_frame):
            if len(dec.stdout.read(frame_bytes)) < frame_bytes:
                break

        while True:
            if should_cancel and should_cancel():
                raise Cancelled()

            buf = dec.stdout.read(frame_bytes)
            if not buf or len(buf) < frame_bytes:
                break

            if enc is None:
                enc = _open_encoder(
                    seg_dir / f"seg_{seg_index:05d}.part.mp4",
                    out_w,
                    out_h,
                    output_fps,
                    target_bitrate,
                )
                frames_in_segment = 0

            t0 = time.time()
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(
                info.height, info.width, 3
            )
            cur = frame
            for _ in range(p.passes):
                cur = eng.upscale(cur, should_cancel=should_cancel)

            if (cur.shape[1], cur.shape[0]) != (out_w, out_h):
                from PIL import Image
                cur = np.asarray(fit_to_canvas(
                    Image.fromarray(cur),
                    (out_w, out_h),
                    settings.aspect_mode,
                ))
            if settings.denoise > 0 or settings.sharpen > 0:
                from PIL import Image
                from .pipeline import _postprocess
                cur = np.asarray(
                    _postprocess(Image.fromarray(cur), settings).convert("RGB")
                )

            try:
                enc.stdin.write(cur.tobytes())
            except BrokenPipeError as exc:
                err = enc.stderr.read().decode(errors="replace")[:400]
                raise VideoError(f"the encoder stopped unexpectedly: {err}") from exc

            per_frame_times.append(time.time() - t0)
            processed += 1
            frames_in_segment += 1
            absolute = start_frame + processed

            recent = per_frame_times[-20:]
            avg = sum(recent) / len(recent)
            emit(
                absolute / output_frames,
                f"frame {absolute} of {output_frames}",
                {
                    "frames_done": absolute,
                    "frames_total": output_frames,
                    "seconds_per_frame": round(avg, 3),
                    "eta_seconds": round(avg * (output_frames - absolute), 1),
                },
            )

            if frames_in_segment >= SEGMENT_FRAMES:
                _close_segment(enc, seg_dir, seg_index)
                enc = None
                seg_index += 1
                state_file.write_text(
                    json.dumps({"signature": signature, "done_segments": seg_index})
                )

        if enc is not None:
            _close_segment(enc, seg_dir, seg_index)
            enc = None
            seg_index += 1
            state_file.write_text(
                json.dumps({"signature": signature, "done_segments": seg_index})
            )
    except Cancelled:
        if enc is not None:
            enc.stdin.close(); enc.wait(timeout=30)
            (seg_dir / f"seg_{seg_index:05d}.part.mp4").unlink(missing_ok=True)
        raise
    finally:
        try:
            dec.stdout.close()
        except OSError:
            pass
        dec.terminate()
        try:
            dec.wait(timeout=10)
        except subprocess.TimeoutExpired:
            dec.kill()

    emit(0.97, "joining segments and adding audio", {})
    _concat(seg_dir, seg_index, src, dest, info.has_audio)

    output_bytes = dest.stat().st_size if dest.exists() else 0
    if output_bytes > budget_bytes:
        dest.unlink(missing_ok=True)
        raise VideoError(
            f"compressed output exceeded its {budget_bytes / 1_000_000:.1f} MB "
            "size budget; try a lower resolution"
        )

    # Segments exist only to survive a crash. Once the real output is on disk
    # they are dead weight - an 8K run leaves tens of gigabytes behind.
    if dest.exists() and dest.stat().st_size > 0:
        shutil.rmtree(seg_dir, ignore_errors=True)
        state_file.unlink(missing_ok=True)
    licensing.record(video_bytes=src.stat().st_size)
    emit(1.0, "done", {})

    elapsed = time.time() - started
    return {
        **p.as_dict(),
        "output_width": out_w, "output_height": out_h,
        "frames": output_frames, "fps": output_fps,
        "source_frames": info.frames, "source_fps": info.fps,
        "frames_processed": processed,
        "resumed_from": start_frame,
        "segments": seg_index,
        "elapsed": round(elapsed, 2),
        "seconds_per_frame": round(elapsed / processed, 3) if processed else None,
        "model": spec.key, "provider": eng.provider,
        "providers": eng.active_providers,
        "audio": info.has_audio, "output": str(dest),
        "source_bytes": source_bytes,
        "output_bytes": output_bytes,
        "size_ratio": round(expansion_ratio(source_bytes, output_bytes), 3),
        "size_budget_bytes": budget_bytes,
        "target_video_bitrate": target_bitrate,
    }


def _close_segment(enc: subprocess.Popen, seg_dir: Path, index: int) -> None:
    enc.stdin.close()
    if enc.wait(timeout=600) != 0:
        err = enc.stderr.read().decode(errors="replace")[:400]
        raise VideoError(f"encoding segment {index} failed: {err}")
    part = seg_dir / f"seg_{index:05d}.part.mp4"
    part.replace(seg_dir / f"seg_{index:05d}.mp4")


def _concat(
    seg_dir: Path, count: int, original: Path, dest: Path, has_audio: bool
) -> None:
    listing = seg_dir / "segments.txt"
    lines = []
    for i in range(count):
        name = f"seg_{i:05d}.mp4"
        if not (seg_dir / name).exists():
            raise VideoError(f"segment {i} is missing; cannot assemble the output.")
        # Relative names, resolved against the listing's own directory. Absolute
        # Windows paths would put a drive letter and backslashes inside the
        # demuxer's quoted-path syntax, which it does not parse reliably.
        lines.append(f"file '{name}'")
    listing.write_text("\n".join(lines) + "\n")

    dest.parent.mkdir(parents=True, exist_ok=True)
    args = ["ffmpeg", "-v", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", listing.name]
    if has_audio:
        args += ["-i", str(original.resolve()), "-map", "0:v:0", "-map", "1:a:0",
                 "-c:a", "aac", "-b:a", str(AUDIO_BITRATE), "-shortest"]
    args += ["-c:v", "copy", "-movflags", "+faststart", str(dest.resolve())]

    res = subprocess.run(args, capture_output=True, text=True, cwd=str(seg_dir))
    if res.returncode != 0:
        raise VideoError(f"assembling the final file failed: {res.stderr.strip()[:400]}")
