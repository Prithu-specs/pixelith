# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
"""CPU+GPU co-execution (hybrid) behavior."""
import sys

import pytest

from pixelith import hardware
from pixelith.hardware import auxiliary_providers, describe_hybrid
from pixelith.config import MODELS


def test_coreml_mac_adds_cpu_coworker(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(hardware, "total_ram_bytes", lambda: 16 * 1024**3)
    ranked = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    assert auxiliary_providers("CoreMLExecutionProvider", ranked) == [
        "CPUExecutionProvider"
    ]


def test_coreml_mac_respects_opt_out(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(hardware, "total_ram_bytes", lambda: 16 * 1024**3)
    monkeypatch.setenv("PIXELITH_NO_HYBRID", "1")
    ranked = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    assert auxiliary_providers("CoreMLExecutionProvider", ranked) == []


def test_small_mac_stays_single_device(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(hardware, "total_ram_bytes", lambda: 6 * 1024**3)
    ranked = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    assert auxiliary_providers("CoreMLExecutionProvider", ranked) == []


def test_nnapi_and_openvino_stay_exclusive():
    ranked = ["NnapiExecutionProvider", "CPUExecutionProvider"]
    assert (
        auxiliary_providers("NnapiExecutionProvider", ranked) == []
    )


def test_discrete_gpu_takes_cpu_worker():
    ranked = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    assert auxiliary_providers("CUDAExecutionProvider", ranked) == [
        "CPUExecutionProvider"
    ]


def test_describe_hybrid_reports_the_coreml_exception(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(hardware, "total_ram_bytes", lambda: 16 * 1024**3)
    call = describe_hybrid(
        ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    )
    assert call["co_execution"] is True
    assert call["devices"] == [
        "CoreMLExecutionProvider",
        "CPUExecutionProvider",
    ]


def test_describe_hybrid_without_hardware(monkeypatch):
    monkeypatch.delenv("PIXELITH_NO_HYBRID", raising=False)
    call = describe_hybrid(["CPUExecutionProvider"])
    assert call["co_execution"] is False