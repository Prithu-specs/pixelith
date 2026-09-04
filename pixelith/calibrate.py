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
import time

from .config import CACHE_DIR, ModelSpec

CALIBRATION_FILE = CACHE_DIR / "calibration.json"

# Big enough to be representative, small enough to be quick.
_PROBE = 192
_REPS = 2


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
    return entry.get("provider") if isinstance(entry, dict) else None


def forget() -> None:
    CALIBRATION_FILE.unlink(missing_ok=True)


def measure(
    spec: ModelSpec, model_path, candidates: list[str], opts
) -> tuple[str, dict]:
    """Time one tile through each candidate. Returns the winner and the times."""
    import numpy as np
    import onnxruntime as ort

    probe = np.ascontiguousarray(
        np.random.rand(1, 3, _PROBE, _PROBE).astype(np.float32)
    )
    timings: dict[str, float] = {}

    for provider in candidates:
        try:
            chain = [provider]
            if provider != "CPUExecutionProvider":
                chain.append("CPUExecutionProvider")
            session = ort.InferenceSession(str(model_path), opts, providers=chain)
            if session.get_providers()[0] != provider:
                continue  # silently fell back; not a real candidate
            name = session.get_inputs()[0].name
            session.run(None, {name: probe})          # warm up / compile
            best = None
            for _ in range(_REPS):
                start = time.perf_counter()
                session.run(None, {name: probe})
                elapsed = time.perf_counter() - start
                best = elapsed if best is None else min(best, elapsed)
            timings[provider] = best
            del session
        except Exception:  # noqa: BLE001 - an unusable provider is just skipped
            continue

    if not timings:
        return "CPUExecutionProvider", {}
    winner = min(timings, key=timings.get)
    return winner, timings


def choose(spec: ModelSpec, model_path, candidates: list[str], opts) -> str:
    """Fastest provider for this model on this machine, measured once."""
    key = f"{_machine_key()}:{spec.key}"
    store = _load()
    entry = store.get(key)
    if isinstance(entry, dict) and entry.get("provider") in candidates:
        return entry["provider"]

    winner, timings = measure(spec, model_path, candidates, opts)
    store[key] = {
        "provider": winner,
        "seconds": {k: round(v, 4) for k, v in timings.items()},
        "measured": time.time(),
    }
    _save(store)
    return winner
