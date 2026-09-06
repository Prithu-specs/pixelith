# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Execution-provider capabilities and safe platform defaults.

ONNX Runtime exposes hardware through execution providers, but a provider is
not necessarily one physical processor. Core ML, NNAPI and OpenVINO AUTO can
already partition or schedule work across CPU, GPU and NPU. Starting another
CPU session beside those runtimes often creates contention rather than useful
parallelism, so the engine treats them as managed heterogeneous providers.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    kind: str
    tile: int
    stable_shape: bool = False
    managed_heterogeneous: bool = False
    options: dict[str, str] = field(default_factory=dict)


# Ordered by the acceleration normally available to an image-to-image network.
# Calibration still makes the final decision on the current machine and model.
PROFILES: tuple[ProviderProfile, ...] = (
    ProviderProfile("TensorrtExecutionProvider", "gpu", 1024),
    ProviderProfile("CUDAExecutionProvider", "gpu", 1024),
    ProviderProfile(
        "OpenVINOExecutionProvider",
        "heterogeneous",
        512,
        stable_shape=True,
        managed_heterogeneous=True,
        options={"device_type": "AUTO"},
    ),
    ProviderProfile(
        "CoreMLExecutionProvider",
        "heterogeneous",
        192,
        stable_shape=True,
        managed_heterogeneous=True,
        options={
            "ModelFormat": "MLProgram",
            "MLComputeUnits": "ALL",
            "RequireStaticInputShapes": "0",
            "EnableOnSubgraphs": "0",
        },
    ),
    ProviderProfile(
        "QNNExecutionProvider",
        "npu",
        256,
        stable_shape=True,
        options={"backend_type": "htp", "htp_performance_mode": "balanced"},
    ),
    ProviderProfile(
        "NnapiExecutionProvider",
        "heterogeneous",
        192,
        stable_shape=True,
        managed_heterogeneous=True,
    ),
    ProviderProfile("DmlExecutionProvider", "gpu", 384, stable_shape=True),
    ProviderProfile("MIGraphXExecutionProvider", "gpu", 1024),
    ProviderProfile("ROCMExecutionProvider", "gpu", 1024),
    ProviderProfile("WebGpuExecutionProvider", "gpu", 384, stable_shape=True),
    ProviderProfile("XNNPACKExecutionProvider", "cpu", 512),
    ProviderProfile("CPUExecutionProvider", "cpu", 1024),
)

_BY_NAME = {profile.name: profile for profile in PROFILES}


def profile(name: str) -> ProviderProfile:
    """Return known capabilities, with conservative defaults for future EPs."""
    return _BY_NAME.get(name, ProviderProfile(name, "accelerator", 192, True))


def configured(name: str):
    """Return the value accepted by ``InferenceSession(providers=...)``."""
    item = profile(name)
    return (name, dict(item.options)) if item.options else name


def describe(available: list[str]) -> list[dict]:
    """JSON-safe hardware information for the CLI and web health endpoint."""
    return [
        {
            "provider": name,
            "kind": profile(name).kind,
            "managed_heterogeneous": profile(name).managed_heterogeneous,
        }
        for name in available
    ]


def auxiliary_providers(primary: str, ranked: list[str]) -> list[str]:
    """Independent workers worth trying alongside ``primary``.

    Managed providers already coordinate the processors behind their API. For
    discrete GPU/NPU providers, a separate CPU session can consume otherwise
    idle tiles. Dynamic scheduling in :mod:`pixelith.engine` ensures the faster
    worker naturally takes more of the queue.
    """
    if profile(primary).managed_heterogeneous:
        return []

    result: list[str] = []
    for name in ranked:
        if name == primary or profile(name).managed_heterogeneous:
            continue
        if profile(name).kind == "cpu" and profile(primary).kind != "cpu":
            result.append(name)
            break
    return result
