# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Model acquisition: download on first use, verify, cache."""
from __future__ import annotations

import hashlib
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .config import MODEL_DIR, MODELS, ModelSpec

ProgressFn = Callable[[float, str], None]
_CHUNK = 1 << 20


class ModelError(RuntimeError):
    """Raised when a model cannot be fetched or fails verification."""


def model_path(spec: ModelSpec) -> Path:
    return MODEL_DIR / spec.filename


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def is_available(spec: ModelSpec) -> bool:
    return model_path(spec).exists()


def ensure(spec: ModelSpec, progress: ProgressFn | None = None) -> Path:
    """Return a local, checksum-verified path to the model's weights."""
    dest = model_path(spec)
    if dest.exists():
        return dest

    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.unlink(missing_ok=True)

    def emit(frac: float, msg: str) -> None:
        if progress:
            progress(frac, msg)

    emit(0.0, f"downloading {spec.filename} ({spec.size_mb:.1f} MB)")
    try:
        req = urllib.request.Request(
            spec.url, headers={"User-Agent": "pixelith/0.1"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            with tmp.open("wb") as out:
                while chunk := resp.read(_CHUNK):
                    out.write(chunk)
                    done += len(chunk)
                    if total:
                        emit(done / total, f"downloading {spec.filename}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        tmp.unlink(missing_ok=True)
        raise ModelError(
            f"could not download {spec.filename} from {spec.url}: {exc}"
        ) from exc

    digest = _sha256(tmp)
    if spec.sha256 and digest != spec.sha256:
        tmp.unlink(missing_ok=True)
        raise ModelError(
            f"{spec.filename} failed checksum verification "
            f"(expected {spec.sha256[:16]}…, got {digest[:16]}…). "
            "Refusing to load possibly corrupted or tampered weights."
        )

    shutil.move(str(tmp), str(dest))
    emit(1.0, f"{spec.filename} ready")
    return dest


def status() -> list[dict]:
    """Registry contents plus whether each model is already on disk."""
    return [
        {
            "key": s.key,
            "label": s.label,
            "scale": s.scale,
            "size_mb": s.size_mb,
            "notes": s.notes,
            "installed": is_available(s),
            "relative_cost": s.cost,
        }
        for s in MODELS.values()
    ]
