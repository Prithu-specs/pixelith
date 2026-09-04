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
from .compat import total_ram_bytes
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
# Providers that tolerate a changing input shape cheaply. CoreML recompiles per
# shape, so it must keep every tile the same size; the others do not, which lets
# them skip padding entirely and process far fewer pixels.
_STABLE_SHAPE_REQUIRED = {"CoreMLExecutionProvider"}

_TILE_BY_PROVIDER = {
    "CPUExecutionProvider": 1024,
    "CoreMLExecutionProvider": 192,
    "CUDAExecutionProvider": 1024,    # untested; large tiles suit GPU batching
    "DmlExecutionProvider": 384,      # untested
    "ROCMExecutionProvider": 1024,    # untested
}


# Measured peak RSS for a 1080p -> 8K job on an M5 Pro, which is the worst
# realistic case. Memory is what stops a small machine, so the tile is chosen
# from a budget rather than from a guess about the class of computer.
#
#   tile 1024 -> 2262 MB, 3.5 s      tile 256 -> 556 MB, 6.1 s
#   tile  512 -> 1154 MB, 4.5 s      tile 192 -> 449 MB, 7.1 s
_TILE_BUDGET_MB = ((1024, 2300), (512, 1200), (384, 850), (256, 600), (192, 460))


def pick_tile(
    provider: str, spec: "ModelSpec", ram_bytes: int | None = None
) -> int:
    """Largest tile whose peak memory fits comfortably in this machine's RAM.

    Bigger tiles are faster, so this takes the biggest one that leaves the rest
    of the system room to breathe: at most a quarter of total memory, and never
    more than the provider actually benefits from.
    """
    from .compat import total_ram_bytes

    ceiling = _TILE_BY_PROVIDER.get(provider, spec.default_tile)
    ram = ram_bytes if ram_bytes is not None else total_ram_bytes()
    budget_mb = (ram / 1024**2) * 0.25

    # The deep model holds far more activation memory per tile.
    if spec.cost > 3:
        ceiling = min(ceiling, 256)
        budget_mb *= 0.6

    for tile, needs_mb in _TILE_BUDGET_MB:
        if tile <= ceiling and needs_mb <= budget_mb:
            return tile
    return max(64, min(ceiling, 192))


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

        # Which provider wins depends on the machine, not just the model, so
        # measure it once here rather than trusting a preference measured
        # somewhere else. Explicit --providers skips this entirely.
        if not self.settings.providers and len(providers) > 1:
            try:
                from .calibrate import choose as calibrated

                best = calibrated(spec, path, providers, opts)
                if best in providers:
                    providers = [best] + [p for p in providers if p != best]
            except Exception:  # noqa: BLE001 - fall back to the static order
                pass

        try:
            self.session = ort.InferenceSession(str(path), opts, providers=providers)
        except Exception as exc:  # noqa: BLE001 - fall back rather than die
            log.warning("provider set %s failed (%s); using CPU", providers, exc)
            self.session = ort.InferenceSession(
                str(path), opts, providers=["CPUExecutionProvider"]
            )

        self.provider = self.session.get_providers()[0]

        # Optional second worker on a different provider. Tiles are shared
        # between them, so a slower device simply does fewer. Worth having
        # where the two are genuinely separate silicon; on a shared-memory
        # machine the gain is small, because dispatching to the neural engine
        # still costs CPU. Skipped when memory is tight, since each session
        # carries its own working buffers.
        self.extra: list = []
        # A second worker only pays when it is competitive at the tile size in
        # use. A small tile count means there is nothing to share anyway.
        if self.settings.hybrid and total_ram_bytes() >= 12 * 1024**3:
            for alt in providers:
                if alt == self.provider or alt == "CPUExecutionProvider":
                    continue
                try:
                    self.extra.append(
                        ort.InferenceSession(str(path), opts, providers=[alt,
                                             "CPUExecutionProvider"])
                    )
                except Exception:  # noqa: BLE001 - a second worker is a bonus
                    pass
                break
            if not self.extra and self.provider != "CPUExecutionProvider":
                try:
                    self.extra.append(
                        ort.InferenceSession(str(path), opts,
                                             providers=["CPUExecutionProvider"])
                    )
                except Exception:  # noqa: BLE001
                    pass
        self.input_name = self.session.get_inputs()[0].name
        # An explicit --tile always wins; otherwise adapt to provider and RAM.
        self.tile = int(self.settings.tile or pick_tile(self.provider, spec))
        self.overlap = max(0, int(self.settings.overlap))
        # Constant-shape tiles cost padding; only pay it where it buys something.
        self.pad_tiles = self.provider in _STABLE_SHAPE_REQUIRED
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

    def _run_tile(self, tile: np.ndarray, session=None) -> np.ndarray:
        """tile: (h,w,3) float32 in [0,1] -> (h*s,w*s,3) float32."""
        batch = np.ascontiguousarray(
            tile.transpose(2, 0, 1)[None], dtype=np.float32
        )
        # ORT sessions are safe to call concurrently, so workers need no lock.
        out = (session or self.session).run(None, {self.input_name: batch})[0]
        return out[0].transpose(1, 2, 0)

    @property
    def workers(self) -> int:
        return 1 + len(self.extra)

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

        # The output is assembled a band at a time. A whole-image float
        # accumulator costs four times the finished picture: at 8K that is
        # 530 MB before any working buffer, which is the difference between
        # running and not running on a small machine. A band only has to be as
        # tall as one row of tiles.
        out = np.empty((h * s, w * s, 3), dtype=np.uint8)
        band_h = min(T, h) * s
        acc = np.zeros((band_h, w * s, 3), dtype=np.float32)
        wsum = np.zeros((band_h, w * s, 1), dtype=np.float32)

        sessions = [self.session, *self.extra]
        pool = None
        if len(sessions) > 1 and len(xs) > 1:
            from concurrent.futures import ThreadPoolExecutor

            pool = ThreadPoolExecutor(max_workers=len(sessions))
        write_lock = threading.Lock()

        total = len(ys) * len(xs)
        done = 0
        margin = V

        def one_tile(y: int, x: int, session) -> None:
            """Run a single tile into the current band. Concurrency-safe."""
            y1, x1 = min(y + T, h), min(x + T, w)
            patch = src[y:y1, x:x1]
            ph, pw = patch.shape[:2]

            if self.pad_tiles:
                # CoreML recompiles per input shape, so tiles are padded up to
                # the full tile size and cropped afterwards.
                if ph != T or pw != T:
                    patch = np.pad(
                        patch,
                        ((0, T - ph), (0, T - pw), (0, 0)),
                        mode="reflect" if min(ph, pw) > 1 else "edge",
                    )
                up = self._run_tile(patch, session)[: ph * s, : pw * s]
            else:
                # Elsewhere, run the tile at its real size and reflect only a
                # small margin at the true image boundary. Padding every tile to
                # full size runs up to twice the real pixel count.
                pt = margin if y == 0 else 0
                pl = margin if x == 0 else 0
                pb = margin if y1 == h else 0
                pr = margin if x1 == w else 0
                if (pt or pl or pb or pr) and min(ph, pw) > 1:
                    patch = np.pad(
                        patch, ((pt, pb), (pl, pr), (0, 0)), mode="reflect"
                    )
                else:
                    pt = pl = pb = pr = 0
                up = self._run_tile(patch, session)
                if pt or pl or pb or pr:
                    up = up[
                        pt * s : up.shape[0] - pb * s if pb else None,
                        pl * s : up.shape[1] - pr * s if pr else None,
                    ]

            mask = (
                _feather(ph * s, V * s)[:, None]
                * _feather(pw * s, V * s)[None, :]
            )[..., None]
            contribution = up * mask

            with write_lock:
                acc[: ph * s, x * s : x * s + pw * s] += contribution
                wsum[: ph * s, x * s : x * s + pw * s] += mask

        def flush(top: int, rows: int) -> None:
            """Finish `rows` of the band and copy them into the output."""
            if rows <= 0:
                return
            a, wt = acc[:rows], wsum[:rows]
            np.maximum(wt, 1e-6, out=wt)
            a /= wt
            a *= 255.0
            a += 0.5
            np.clip(a, 0, 255, out=a)
            out[top : top + rows] = a.astype(np.uint8)

        try:
            for row, y in enumerate(ys):
                if should_cancel and should_cancel():
                    raise Cancelled()

                if pool is None:
                    for x in xs:
                        if should_cancel and should_cancel():
                            raise Cancelled()
                        one_tile(y, x, self.session)
                else:
                    # Tiles in a row are independent, so they can be shared
                    # across workers. Rows still complete in order, which is
                    # what keeps the banding valid.
                    jobs = [
                        pool.submit(one_tile, y, x, sessions[i % len(sessions)])
                        for i, x in enumerate(xs)
                    ]
                    for job in jobs:
                        job.result()

                done += len(xs)
                if progress:
                    progress(min(1.0, done / total))

                top = y * s
                settled = (
                    (ys[row + 1] - y) * s if row + 1 < len(ys) else h * s - top
                )
                settled = min(settled, h * s - top, band_h)
                flush(top, settled)

                if row + 1 < len(ys):
                    keep = band_h - settled
                    if keep > 0:
                        acc[:keep] = acc[settled : settled + keep]
                        wsum[:keep] = wsum[settled : settled + keep]
                    acc[keep:] = 0.0
                    wsum[keep:] = 0.0
        finally:
            if pool is not None:
                pool.shutdown(wait=True)

        return out
