# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Tiled ONNX inference.

Two decisions drive this file:

1. Every tile handed to the network has the *same* shape. CoreML recompiles a
   graph each time it sees a new input shape, so ragged edge tiles would stall
   the run repeatedly. Edge tiles are reflect-padded up to the full tile size
   and cropped afterwards.
2. Tiles overlap and are blended with a feathered weight mask, so no seams
   appear in the output.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Callable

import numpy as np

from .config import ModelSpec, UpscaleSettings
from .models import ensure

log = logging.getLogger("pixelith.engine")

ProgressFn = Callable[[float], None]

_PREFERRED = (
    "CUDAExecutionProvider",
    "CoreMLExecutionProvider",
    "DmlExecutionProvider",
    "ROCMExecutionProvider",
    "CPUExecutionProvider",
)


class Cancelled(Exception):
    """Raised inside a run when the caller asked it to stop."""


def available_providers() -> list[str]:
    import onnxruntime as ort

    return list(ort.get_available_providers())


def choose_providers(
    requested: list[str] | None = None, spec: "ModelSpec | None" = None
) -> list[str]:
    """Rank the runtimes this machine actually has, fastest first.

    Provider speed is a property of the *network*, not just the machine. A
    compact model can lose to plain CPU on Apple silicon because per-dispatch
    overhead dominates its tiny graph, while a deep model wins big on CoreML.
    Each ModelSpec therefore carries its own measured preference.
    """
    have = set(available_providers())
    if requested:
        picked = [p for p in requested if p in have]
        if picked:
            if "CPUExecutionProvider" not in picked:
                picked.append("CPUExecutionProvider")
            return picked
        log.warning("none of the requested providers are available: %s", requested)
    order = list(spec.preferred_providers) if spec and spec.preferred_providers else []
    order += [p for p in _PREFERRED if p not in order]
    ranked = [p for p in order if p in have]
    return ranked or ["CPUExecutionProvider"]


# Measured optimum tile size per execution provider (1080p, compact model,
# Apple M5 Pro, interleaved A/B runs on an idle machine).
#
# The provider does not change *how fast* the machine is nearly as much as the
# tile size changes it. CPU and CoreML land within noise of each other when each
# runs at its own best tile (8.5 s vs 8.7 s), but CPU at CoreML's tile size is
# 30% slower. Threaded CPU kernels want few large tiles; the neural engine wants
# many small ones.
_TILE_BY_PROVIDER = {
    "CPUExecutionProvider": 512,
    "CoreMLExecutionProvider": 192,
    "CUDAExecutionProvider": 512,     # untested; large tiles suit GPU batching
    "DmlExecutionProvider": 384,      # untested
    "ROCMExecutionProvider": 512,     # untested
}


def pick_tile(provider: str, spec: "ModelSpec", ram_bytes: int | None = None) -> int:
    """Best tile size for this provider, reduced when memory is tight.

    Tiles are the main memory lever on low-end machines: a tile of T pixels
    holds T*scale squared floats while it is in flight, on top of the
    whole-image accumulator.
    """
    from .compat import total_ram_bytes

    tile = _TILE_BY_PROVIDER.get(provider, spec.default_tile)
    ram = ram_bytes if ram_bytes is not None else total_ram_bytes()
    gb = ram / 1024**3
    if gb < 4:
        tile = min(tile, 192)
    elif gb < 8:
        tile = min(tile, 256)
    # Deep models hold far more activation memory per tile than compact ones.
    if spec.cost > 3:
        tile = min(tile, 256)
    return max(64, tile)


def _feather(size: int, overlap: int) -> np.ndarray:
    """A 1-D ramp that rises over `overlap`, holds at 1, then falls."""
    w = np.ones(size, dtype=np.float32)
    overlap = min(overlap, size // 2)
    if overlap > 0:
        ramp = (np.arange(overlap, dtype=np.float32) + 0.5) / overlap
        w[:overlap] = ramp
        w[-overlap:] = ramp[::-1]
    return w


@dataclass
class EngineInfo:
    model: str
    scale: int
    provider: str
    tile: int
    overlap: int


class Engine:
    """A loaded network, ready to upscale arrays."""

    def __init__(
        self,
        spec: ModelSpec,
        settings: UpscaleSettings | None = None,
        progress: Callable[[float, str], None] | None = None,
    ) -> None:
        import onnxruntime as ort

        self.spec = spec
        self.settings = settings or UpscaleSettings(model=spec.key)
        path = ensure(spec, progress)

        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        threads = os.cpu_count() or 4
        opts.intra_op_num_threads = threads

        providers = choose_providers(self.settings.providers or None, spec)
        try:
            self.session = ort.InferenceSession(str(path), opts, providers=providers)
        except Exception as exc:  # noqa: BLE001 - fall back rather than die
            log.warning("provider set %s failed (%s); using CPU", providers, exc)
            self.session = ort.InferenceSession(
                str(path), opts, providers=["CPUExecutionProvider"]
            )

        self.provider = self.session.get_providers()[0]
        self.input_name = self.session.get_inputs()[0].name
        # An explicit --tile always wins; otherwise adapt to provider and RAM.
        self.tile = int(self.settings.tile or pick_tile(self.provider, spec))
        self.overlap = max(0, int(self.settings.overlap))
        if self.overlap * 2 >= self.tile:
            self.overlap = max(0, self.tile // 8)
        self._lock = threading.Lock()

    @property
    def scale(self) -> int:
        return self.spec.scale

    def info(self) -> EngineInfo:
        return EngineInfo(
            self.spec.key, self.scale, self.provider, self.tile, self.overlap
        )

    def _run_tile(self, tile: np.ndarray) -> np.ndarray:
        """tile: (T,T,3) float32 in [0,1] -> (T*s,T*s,3) float32."""
        batch = np.ascontiguousarray(
            tile.transpose(2, 0, 1)[None], dtype=np.float32
        )
        with self._lock:
            out = self.session.run(None, {self.input_name: batch})[0]
        return out[0].transpose(1, 2, 0)

    def upscale(
        self,
        image: np.ndarray,
        progress: ProgressFn | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> np.ndarray:
        """Upscale an (H,W,3) uint8 array by the model's native factor."""
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"expected an (H,W,3) RGB array, got {image.shape}")

        src = image.astype(np.float32) / 255.0
        h, w, _ = src.shape
        s, T, V = self.scale, self.tile, self.overlap
        step = max(1, T - 2 * V)

        ys = list(range(0, max(1, h), step))
        xs = list(range(0, max(1, w), step))
        acc = np.zeros((h * s, w * s, 3), dtype=np.float32)
        wsum = np.zeros((h * s, w * s, 1), dtype=np.float32)

        total = len(ys) * len(xs)
        done = 0
        for y in ys:
            for x in xs:
                if should_cancel and should_cancel():
                    raise Cancelled()

                y1, x1 = min(y + T, h), min(x + T, w)
                patch = src[y:y1, x:x1]
                ph, pw = patch.shape[:2]

                # Constant shape for every call: reflect-pad short edges.
                if ph != T or pw != T:
                    patch = np.pad(
                        patch,
                        ((0, T - ph), (0, T - pw), (0, 0)),
                        mode="reflect" if min(ph, pw) > 1 else "edge",
                    )

                up = self._run_tile(patch)[: ph * s, : pw * s]
                mask = (
                    _feather(ph * s, V * s)[:, None]
                    * _feather(pw * s, V * s)[None, :]
                )[..., None]

                acc[y * s : y * s + ph * s, x * s : x * s + pw * s] += up * mask
                wsum[y * s : y * s + ph * s, x * s : x * s + pw * s] += mask

                done += 1
                if progress:
                    progress(done / total)

        np.maximum(wsum, 1e-6, out=wsum)
        acc /= wsum
        return np.clip(acc * 255.0 + 0.5, 0, 255).astype(np.uint8)
