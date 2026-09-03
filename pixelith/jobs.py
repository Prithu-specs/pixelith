# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Job queue: one worker, live progress, cancellation, and SSE fan-out.

Deliberately single-worker. Inference already saturates every core, so running
two jobs at once makes both slower and doubles peak memory.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .compat import image_suffixes
from .config import OUTPUT_DIR, WORK_DIR, UpscaleSettings
from .models import is_available
from .engine import Cancelled, Engine
from .pipeline import estimate_seconds, plan, upscale_image
from .video import VideoError, have_ffmpeg, probe, upscale_video

log = logging.getLogger("pixelith.jobs")

# Only what this machine can actually decode: HEIC needs the optional
# pillow-heif plugin, and claiming it without the plugin fails at open() time.
IMAGE_SUFFIXES = image_suffixes()
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpg", ".mpeg"}

TERMINAL = {"done", "error", "cancelled"}


def classify(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    raise ValueError(f"unsupported file type {suffix or '(none)'}")


@dataclass
class Job:
    id: str
    filename: str
    kind: str
    settings: UpscaleSettings
    source_path: Path
    status: str = "queued"
    progress: float = 0.0
    stage: str = "queued"
    message: str = "waiting to start"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    source: dict = field(default_factory=dict)
    target: dict = field(default_factory=dict)
    eta_seconds: float | None = None
    output_path: Path | None = None
    error: str | None = None
    report: dict | None = None
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 4),
            "stage": self.stage,
            "message": self.message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "source": self.source,
            "target": self.target,
            "model": self.settings.model,
            "eta_seconds": (
                round(self.eta_seconds, 1) if self.eta_seconds is not None else None
            ),
            "output_name": self.output_path.name if self.output_path else None,
            "error": self.error,
            "report": self.report,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.RLock()
        self._subs: dict[str, list[queue.Queue]] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._engines: dict[tuple, Engine] = {}
        self._worker = threading.Thread(target=self._run_forever, daemon=True)
        self._worker.start()

    # ---------------------------------------------------------------- public

    def submit(self, source: Path, filename: str, settings: UpscaleSettings,
               out_format: str | None = None) -> Job:
        kind = classify(filename)
        if kind == "video" and not have_ffmpeg():
            raise VideoError(
                "FFmpeg is required for video but was not found on PATH."
            )

        job = Job(
            id=uuid.uuid4().hex[:12],
            filename=filename,
            kind=kind,
            settings=settings,
            source_path=source,
        )
        self._describe(job, out_format)

        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
        self._queue.put(job.id)
        self._publish(job)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> list[dict]:
        with self._lock:
            return [self._jobs[i].as_dict() for i in reversed(self._order)
                    if i in self._jobs]

    def cancel(self, job_id: str) -> Job | None:
        job = self.get(job_id)
        if not job:
            return None
        if job.status in TERMINAL:
            return job
        job._cancel.set()
        if job.status == "queued":
            self._finish(job, "cancelled", "cancelled before it started")
        else:
            # Cancellation is cooperative: the worker checks between tiles and
            # frames, so the job settles a moment later. Say so meanwhile.
            job.message = "stopping..."
            self._publish(job)
        return job

    def delete(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job:
            return False
        job._cancel.set()
        with self._lock:
            self._jobs.pop(job_id, None)
            if job_id in self._order:
                self._order.remove(job_id)
        for path in (job.source_path, job.output_path):
            try:
                if path and Path(path).exists():
                    Path(path).unlink()
            except OSError:
                pass
        return True

    def subscribe(self, job_id: str) -> Iterator[dict]:
        """Yield job snapshots until the job reaches a terminal state."""
        q: queue.Queue = queue.Queue(maxsize=64)
        with self._lock:
            self._subs.setdefault(job_id, []).append(q)
        job = self.get(job_id)
        if job:
            yield job.as_dict()
            if job.status in TERMINAL:
                self._unsubscribe(job_id, q)
                return
        try:
            while True:
                try:
                    snap = q.get(timeout=20)
                except queue.Empty:
                    current = self.get(job_id)
                    if current is None:
                        return
                    yield current.as_dict()          # heartbeat
                    if current.status in TERMINAL:
                        return
                    continue
                yield snap
                if snap.get("status") in TERMINAL:
                    return
        finally:
            self._unsubscribe(job_id, q)

    # --------------------------------------------------------------- private

    def _unsubscribe(self, job_id: str, q: queue.Queue) -> None:
        with self._lock:
            subs = self._subs.get(job_id, [])
            if q in subs:
                subs.remove(q)
            if not subs:
                self._subs.pop(job_id, None)

    def _publish(self, job: Job) -> None:
        snap = job.as_dict()
        with self._lock:
            subs = list(self._subs.get(job.id, []))
        for q in subs:
            try:
                q.put_nowait(snap)
            except queue.Full:
                pass

    def _describe(self, job: Job, out_format: str | None) -> None:
        """Fill in source/target metadata and the initial time estimate."""
        spec = job.settings.resolved_model()
        if job.kind == "image":
            from PIL import Image, ImageOps
            with Image.open(job.source_path) as im:
                im = ImageOps.exif_transpose(im)
                w, h = im.size
            job.source = {"width": w, "height": h,
                          "frames": None, "fps": None, "duration": None}
            frames = 1
            ext = (out_format or Path(job.filename).suffix.lstrip(".") or "png").lower()
            if ext not in ("png", "jpg", "jpeg", "webp"):
                ext = "png"
        else:
            info = probe(job.source_path)
            w, h = info.width, info.height
            job.source = {"width": w, "height": h, "frames": info.frames,
                          "fps": info.fps, "duration": info.duration}
            frames = max(1, info.frames)
            ext = (out_format or "mp4").lower()
            if ext not in ("mp4", "mov"):
                ext = "mp4"

        p = plan(w, h, job.settings.preset, job.settings.scale, spec.scale)
        job.target = {"width": p.out_width, "height": p.out_height}
        job.eta_seconds = estimate_seconds(w, h, p, spec.key, frames=frames)

        stem = Path(job.filename).stem or "upscaled"
        safe = "".join(c for c in stem if c.isalnum() or c in "-_ ").strip() or "upscaled"
        job.output_path = OUTPUT_DIR / f"{safe}_{p.out_width}x{p.out_height}.{ext}"
        n = 1
        while job.output_path.exists():
            job.output_path = (
                OUTPUT_DIR / f"{safe}_{p.out_width}x{p.out_height}_{n}.{ext}"
            )
            n += 1

    def _engine_for(self, settings: UpscaleSettings,
                    on_download: Any = None) -> Engine:
        key = (settings.model, settings.tile, settings.overlap,
               tuple(settings.providers))
        with self._lock:
            eng = self._engines.get(key)
        if eng is None:
            eng = Engine(settings.resolved_model(), settings, progress=on_download)
            with self._lock:
                self._engines[key] = eng
        return eng

    def _update(self, job: Job, *, progress: float | None = None,
                stage: str | None = None, message: str | None = None,
                eta: float | None = None) -> None:
        if progress is not None:
            job.progress = progress
        if stage is not None:
            job.stage = stage
        if message is not None:
            job.message = message
        if eta is not None:
            job.eta_seconds = eta
        self._publish(job)

    def _finish(self, job: Job, status: str, message: str,
                error: str | None = None) -> None:
        job.status = status
        job.stage = status
        job.message = message
        job.error = error
        job.finished_at = time.time()
        if status == "done":
            job.progress = 1.0
            job.eta_seconds = 0.0
        self._publish(job)

    def _run_forever(self) -> None:
        while True:
            job_id = self._queue.get()
            job = self.get(job_id)
            if job is None or job._cancel.is_set():
                if job:
                    self._finish(job, "cancelled", "cancelled before it started")
                continue
            try:
                self._execute(job)
            except Exception as exc:  # noqa: BLE001 - a job must never kill the worker
                log.exception("job %s failed", job.id)
                self._finish(job, "error", "failed", str(exc))

    def _execute(self, job: Job) -> None:
        job.status = "preparing"
        job.started_at = time.time()
        self._update(job, stage="preparing", message="loading model", progress=0.0)

        spec = job.settings.resolved_model()
        if not is_available(spec):
            self._update(
                job, stage="downloading_model", progress=0.0,
                message=f"downloading {spec.label} ({spec.size_mb:.1f} MB)",
            )

        def on_download(frac: float, msg: str) -> None:
            # A first run on an uninstalled model would otherwise sit silent
            # through a 64 MB fetch.
            self._update(job, stage="downloading_model", progress=frac, message=msg)

        engine = self._engine_for(job.settings, on_download)
        job.status = "running"
        started = time.time()

        def cancelled() -> bool:
            return job._cancel.is_set()

        try:
            if job.kind == "image":
                def prog(frac: float, msg: str) -> None:
                    elapsed = time.time() - started
                    eta = (elapsed / frac - elapsed) if frac > 0.02 else None
                    self._update(job, progress=frac, stage="upscaling",
                                 message=msg, eta=eta)

                report = upscale_image(
                    job.source_path, job.output_path, job.settings,
                    engine=engine, progress=prog, should_cancel=cancelled,
                )
            else:
                def vprog(frac: float, msg: str, extra: dict) -> None:
                    self._update(job, progress=frac, stage="upscaling", message=msg,
                                 eta=extra.get("eta_seconds"))

                report = upscale_video(
                    job.source_path, job.output_path, job.settings,
                    work_dir=WORK_DIR / job.id, engine=engine,
                    progress=vprog, should_cancel=cancelled,
                )
            job.report = report
            self._finish(job, "done", f"saved to {job.output_path.name}")
        except Cancelled:
            self._finish(job, "cancelled", "cancelled")
        except Exception as exc:  # noqa: BLE001
            self._finish(job, "error", "failed", str(exc))
            raise


MANAGER = JobManager()
