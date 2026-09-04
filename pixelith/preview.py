# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Run one frame through the real pipeline before committing to the whole job.

A video job here can take hours, and until now the only way to find out whether
the settings were right was to wait for it. This runs a single frame at exactly
the chosen settings, which answers the question in seconds.

It also measures what one frame actually costs on this machine, so the estimate
stops being a projection.
"""
from __future__ import annotations

import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import WORK_DIR, UpscaleSettings
from .engine import Engine
from .pipeline import _postprocess, plan
from .video import VideoError, probe

PREVIEW_DIR = WORK_DIR / "previews"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

# Previews are disposable; keep only the most recent few.
MAX_KEPT = 12


@dataclass
class Preview:
    id: str
    kind: str
    source_width: int
    source_height: int
    out_width: int
    out_height: int
    seconds: float
    frame_index: int | None
    before: Path
    after: Path
    created: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "source": {"width": self.source_width, "height": self.source_height},
            "output": {"width": self.out_width, "height": self.out_height},
            "seconds": round(self.seconds, 2),
            "frame_index": self.frame_index,
        }


_STORE: dict[str, Preview] = {}


def get(preview_id: str) -> Preview | None:
    return _STORE.get(preview_id)


def _remember(p: Preview) -> None:
    _STORE[p.id] = p
    while len(_STORE) > MAX_KEPT:
        oldest = min(_STORE.values(), key=lambda x: x.created)
        _STORE.pop(oldest.id, None)
        for path in (oldest.before, oldest.after):
            path.unlink(missing_ok=True)


def extract_frame(src: Path, index: int | None = None) -> tuple[np.ndarray, int]:
    """Pull one decoded frame from a video, by default from the middle."""
    info = probe(src)
    if info.frames <= 0:
        raise VideoError(f"could not read the frame count of {src.name}")
    target = info.frames // 2 if index is None else max(0, min(index, info.frames - 1))

    # Seek by time, then decode a single frame. Fast even on long files.
    seconds = target / info.fps if info.fps else 0
    frame_bytes = info.width * info.height * 3
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{seconds:.3f}", "-i", str(src),
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
    )
    if proc.returncode != 0 or len(proc.stdout) < frame_bytes:
        raise VideoError(
            f"could not extract a frame from {src.name}: "
            f"{proc.stderr.decode(errors='replace')[:200]}"
        )
    frame = np.frombuffer(proc.stdout[:frame_bytes], dtype=np.uint8)
    return frame.reshape(info.height, info.width, 3), target


def run(
    src: Path,
    kind: str,
    settings: UpscaleSettings,
    engine: Engine | None = None,
    frame_index: int | None = None,
) -> Preview:
    """Upscale one frame (or the image itself) and keep both sides on disk."""
    from PIL import Image, ImageOps

    spec = settings.resolved_model()
    eng = engine or Engine(spec, settings)

    if kind == "video":
        rgb, used_index = extract_frame(src, frame_index)
    else:
        with Image.open(src) as im:
            rgb = np.asarray(ImageOps.exif_transpose(im).convert("RGB"))
        used_index = None

    h, w = rgb.shape[:2]
    p = plan(w, h, settings.preset, settings.scale, spec.scale)

    started = time.perf_counter()
    current = rgb
    for _ in range(p.passes):
        current = eng.upscale(current)
    out = Image.fromarray(current)
    if (out.width, out.height) != (p.out_width, p.out_height):
        out = out.resize((p.out_width, p.out_height), Image.LANCZOS)
    out = _postprocess(out, settings)
    elapsed = time.perf_counter() - started

    pid = uuid.uuid4().hex[:12]
    before = PREVIEW_DIR / f"{pid}_before.jpg"
    after = PREVIEW_DIR / f"{pid}_after.jpg"

    src_img = Image.fromarray(rgb)
    src_img.thumbnail((1400, 1400), Image.LANCZOS)
    src_img.save(before, "JPEG", quality=88)
    shown = out.copy()
    shown.thumbnail((1400, 1400), Image.LANCZOS)
    shown.convert("RGB").save(after, "JPEG", quality=88)

    preview = Preview(
        id=pid, kind=kind, source_width=w, source_height=h,
        out_width=p.out_width, out_height=p.out_height,
        seconds=elapsed, frame_index=used_index, before=before, after=after,
    )
    _remember(preview)
    return preview
