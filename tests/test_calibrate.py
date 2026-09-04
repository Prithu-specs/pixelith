# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Per-machine provider calibration."""
import json

import pytest

from pixelith import calibrate
from pixelith.config import MODELS
from pixelith.models import is_available, model_path


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(calibrate, "CALIBRATION_FILE", tmp_path / "cal.json")
    yield


def test_machine_key_covers_what_changes_the_answer():
    key = calibrate._machine_key()
    assert key.count("-") >= 2, "key should carry OS, architecture and core count"
    assert calibrate._machine_key() == key, "key must be stable"


def test_nothing_cached_to_begin_with():
    assert calibrate.cached("fast") is None


def test_a_missing_cache_file_is_not_an_error():
    calibrate.forget()
    assert calibrate.cached("fast") is None


def test_a_corrupt_cache_falls_back_rather_than_raising():
    calibrate.CALIBRATION_FILE.write_text("{ not json at all")
    assert calibrate.cached("fast") is None


def test_probe_is_small_enough_to_be_quick():
    """Calibration runs on first use, so it must not feel like a hang."""
    assert calibrate._PROBE <= 256
    assert calibrate._REPS <= 3


@pytest.mark.skipif(
    not is_available(MODELS["fast"]), reason="model weights not downloaded"
)
@pytest.mark.needs_model
def test_measuring_picks_a_provider_and_records_its_timings():
    import onnxruntime as ort

    spec = MODELS["fast"]
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    candidates = list(ort.get_available_providers())

    winner = calibrate.choose(spec, model_path(spec), candidates, opts)
    assert winner in candidates

    stored = json.loads(calibrate.CALIBRATION_FILE.read_text())
    entry = next(iter(stored.values()))
    assert entry["provider"] == winner
    assert entry["seconds"], "timings should be recorded, not just the winner"
    # The winner must actually be the fastest thing measured.
    assert entry["provider"] == min(entry["seconds"], key=entry["seconds"].get)


@pytest.mark.skipif(
    not is_available(MODELS["fast"]), reason="model weights not downloaded"
)
@pytest.mark.needs_model
def test_the_second_look_is_free():
    import time

    import onnxruntime as ort

    spec = MODELS["fast"]
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    candidates = list(ort.get_available_providers())

    calibrate.choose(spec, model_path(spec), candidates, opts)
    start = time.perf_counter()
    calibrate.choose(spec, model_path(spec), candidates, opts)
    assert time.perf_counter() - start < 0.05, "cached lookup should not re-measure"
