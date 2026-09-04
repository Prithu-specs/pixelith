# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Paths, model registry, and resolution presets."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "pixelith"


def _env_path(var: str, default: Path) -> Path:
    return Path(os.environ.get(var, default)).expanduser()


CACHE_DIR = _env_path("PIXELITH_HOME", Path.home() / ".cache" / APP_NAME)
MODEL_DIR = CACHE_DIR / "models"
WORK_DIR = CACHE_DIR / "work"
OUTPUT_DIR = _env_path("PIXELITH_OUT", Path.home() / "Pixelith")

for _d in (MODEL_DIR, WORK_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ModelSpec:
    """One upscaling network."""

    key: str
    filename: str
    url: str
    scale: int
    sha256: str
    size_mb: float
    label: str
    notes: str
    # Relative cost per input pixel; used by the time estimator.
    cost: float
    default_tile: int = 256
    # Measured fastest-first runtime order for THIS network. Benchmarked on
    # Apple silicon; CUDA still leads wherever it is present.
    preferred_providers: tuple[str, ...] = ()


MODELS: dict[str, ModelSpec] = {
    "fast": ModelSpec(
        key="fast",
        filename="realesr-general-x4v3.onnx",
        url=(
            "https://huggingface.co/CoderViking/realesr-general-x4v3-onnx/"
            "resolve/main/realesr-general-x4v3.onnx"
        ),
        scale=4,
        sha256="1940a93ee08283a0a7286183186357b1688fe9fa8ede74604b424586aaddf112",
        size_mb=4.6,
        label="Fast (SRVGG general x4v3)",
        notes="Compact network. The right default for video and for batches of photos.",
        cost=1.0,
        default_tile=192,
        preferred_providers=(
            "CUDAExecutionProvider",
            "CoreMLExecutionProvider",
            "CPUExecutionProvider",
        ),
    ),
    "quality": ModelSpec(
        key="quality",
        filename="real_esrgan_x4.onnx",
        url=(
            "https://huggingface.co/SceneWorks/real-esrgan-onnx/"
            "resolve/main/real_esrgan_x4.onnx"
        ),
        scale=4,
        sha256="5c586662929cbc686c1a5c38d9c060dbdb4ea5863a1f7672b8c0761e6b89c033",
        size_mb=63.9,
        label="Quality (Real-ESRGAN x4plus)",
        notes="23-block RRDBNet. Best detail on stills; too slow for long video.",
        cost=5.2,
        default_tile=192,
        preferred_providers=(
            "CUDAExecutionProvider",
            "CoreMLExecutionProvider",
            "CPUExecutionProvider",
        ),
    ),
}

DEFAULT_MODEL = "fast"

# Named output targets. Height is the authoritative axis; width follows aspect.
# The resolution ladder, ascending. Order matters: the interface presents these
# as a slider, so the sequence here is the sequence the user scrolls through.
PRESETS: dict[str, tuple[int, int]] = {
    "180p": (320, 180),
    "360p": (640, 360),
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "2k": (2560, 1440),
    "4k": (3840, 2160),
    "6k": (6144, 3456),
    "8k": (7680, 4320),
}

# Older builds called 1080p "hd". Accepted so saved settings and existing links
# keep working.
PRESET_ALIASES: dict[str, str] = {"hd": "1080p", "fhd": "1080p", "1440p": "2k",
                                  "2160p": "4k", "4320p": "8k"}


def resolve_preset(name: str) -> str:
    """Canonical preset key for a user-supplied name."""
    key = name.strip().lower()
    return PRESET_ALIASES.get(key, key)

# Above this many output pixels a still image is streamed tile-by-tile to disk
# rather than assembled in RAM.
LARGE_IMAGE_PIXELS = 80_000_000


@dataclass
class UpscaleSettings:
    """User-facing knobs shared by the image and video paths."""

    model: str = DEFAULT_MODEL
    preset: str | None = None
    scale: float | None = None
    tile: int | None = None
    overlap: int = 16
    denoise: float = 0.0
    sharpen: float = 0.0
    quality: int = 95
    providers: list[str] = field(default_factory=list)

    def resolved_model(self) -> ModelSpec:
        if self.model not in MODELS:
            raise ValueError(
                f"unknown model {self.model!r}; choose one of {sorted(MODELS)}"
            )
        return MODELS[self.model]
