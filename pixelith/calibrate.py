# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Measure this machine instead of guessing about it.

Which execution provider is fastest depends on the network, the silicon and how
many cores there are, and the answer is not stable across machines: the compact
model is faster on plain CPU on a workstation, but on a three-core laptop the
neural engine may well win. Rather than bake in one machine's answer, time each
available provider once on a small tile and remember the result.

The whole thing costs a fraction of a second and happens once per install.
"""
from __future__ import annotations

import json
import platform
import statistics
import time

from .config import CACHE_DIR, ModelSpec

CALIBRATION_FILE = CACHE_DIR / "calibration.json"

# A small real-frame workload catches tile-grid, padding and dispatch costs that
# a repeatedly cached square tile hides. This still finishes in a few seconds.
_PROBE = 240
_PROBE_WIDTH = 360
_REPS = 3
_FORMAT = 2


def _machine_key() -> str:
    import os

    return f"{platform.system()}-{platform.machine()}-{os.cpu_count()}"


def _load() -> dict:
    try:
        return json.loads(CALIBRATION_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    try:
        CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        CALIBRATION_FILE.write_text(json.dumps(data, indent=2))
    except OSError:
        pass  # a cache that cannot be written is not a failure


def cached(model_key: str) -> str | None:
    entry = _load().get(f"{_machine_key()}:{model_key}")
    if isinstance(entry, dict) and entry.get("format") == _FORMAT:
        return entry.get("provider")
    return None


def forget() -> None:
    CALIBRATION_FILE.unlink(missing_ok=True)


def measure(
    spec: ModelSpec, model_path, candidates: list[str], opts
) -> tuple[str, dict]:
    """Time a representative tiled frame through every candidate."""
    import numpy as np
    import onnxruntime as ort

    from .engine import pick_tile
    from .hardware import configured, profile

    rng = np.random.default_rng(0)
    timings: dict[str, float] = {}

    for provider in candidates:
        try:
            chain: list = [configured(provider)]
            if provider != "CPUExecutionProvider":
                chain.append("CPUExecutionProvider")
            try:
                session = ort.InferenceSession(
                    str(model_path), opts, providers=chain
                )
            except Exception:
                raw = [provider]
                if provider != "CPUExecutionProvider":
                    raw.append("CPUExecutionProvider")
                session = ort.InferenceSession(str(model_path), opts, providers=raw)
            if session.get_providers()[0] != provider:
                continue  # silently fell back; not a real candidate

            name = session.get_inputs()[0].name
            tile = pick_tile(provider, spec)
            step = max(1, tile - 32)
            shapes: list[tuple[int, int]] = []
            for y in range(0, _PROBE, step):
                for x in range(0, _PROBE_WIDTH, step):
                    height = min(tile, _PROBE - y)
                    width = min(tile, _PROBE_WIDTH - x)
                    if profile(provider).stable_shape:
                        height = width = tile
                    shapes.append((height, width))

            probes = {
                shape: np.ascontiguousarray(
                    rng.random((1, 3, *shape), dtype=np.float32)
                )
                for shape in set(shapes)
            }
            session.run(None, {name: probes[shapes[0]]})  # warm up / compile
            samples: list[float] = []
            for _ in range(_REPS):
                start = time.perf_counter()
                for shape in shapes:
                    session.run(None, {name: probes[shape]})
                samples.append(time.perf_counter() - start)
            timings[provider] = statistics.median(samples)
            del session
        except Exception:  # noqa: BLE001 - an unusable provider is just skipped
            continue

    if not timings:
        return "CPUExecutionProvider", {}
    fastest = min(timings.values())
    # Do not let sub-millisecond noise reorder the model's known-good priority.
    winner = next(
        provider
        for provider in candidates
        if provider in timings and timings[provider] <= fastest * 1.05
    )
    return winner, timings


def choose(spec: ModelSpec, model_path, candidates: list[str], opts) -> str:
    """Fastest provider for this model on this machine, measured once."""
    key = f"{_machine_key()}:{spec.key}"
    store = _load()
    entry = store.get(key)
    if (
        isinstance(entry, dict)
        and entry.get("format") == _FORMAT
        and entry.get("provider") in candidates
    ):
        return entry["provider"]

    winner, timings = measure(spec, model_path, candidates, opts)
    store[key] = {
        "format": _FORMAT,
        "provider": winner,
        "tile": pick_tile_for_cache(spec, winner),
        "seconds": {k: round(v, 4) for k, v in timings.items()},
        "measured": time.time(),
    }
    _save(store)
    return winner


def pick_tile_for_cache(spec: ModelSpec, provider: str) -> int:
    """Late import avoids an engine/calibration import cycle at module load."""
    from .engine import pick_tile

    return pick_tile(provider, spec)
