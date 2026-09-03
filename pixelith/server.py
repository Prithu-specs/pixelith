# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 PGA Tech Solutions. Free for noncommercial use;
# commercial use requires a separate licence. See LICENSE.
"""FastAPI app serving the REST API in docs/API.md plus the static web UI."""
from __future__ import annotations

import io
import json
import logging
import shutil
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, license_info
from .config import MODELS, PRESETS, WORK_DIR, UpscaleSettings
from .engine import available_providers, choose_providers
from .compat import summary as platform_summary
from .jobs import IMAGE_SUFFIXES, VIDEO_SUFFIXES, MANAGER, classify
from .models import status as model_status
from .pipeline import estimate_seconds, human_time, plan
from .video import have_ffmpeg

log = logging.getLogger("pixelith.server")

MAX_UPLOAD_BYTES = 8 * 1024**3          # 8 GiB
UPLOAD_DIR = WORK_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Pixelith", version=__version__)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


class EstimateRequest(BaseModel):
    kind: str = "image"
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    frames: int | None = None
    fps: float | None = None
    model: str = "fast"
    preset: str | None = None
    scale: float | None = None


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "providers": available_providers(),
        "ffmpeg": have_ffmpeg(),
        "active": {k: choose_providers(spec=s)[0] for k, s in MODELS.items()},
        # Published so clients can reject a file before spending an upload on it.
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        # Advertise only what this install can actually decode. HEIC needs the
        # optional pillow-heif plugin, and video needs FFmpeg on PATH.
        "formats": {
            "image": sorted(IMAGE_SUFFIXES),
            "video": sorted(VIDEO_SUFFIXES) if have_ffmpeg() else [],
        },
        "platform": platform_summary(),
        "license": license_info(),
    }


@app.get("/api/models")
def models() -> list[dict]:
    return model_status()


@app.get("/api/presets")
def presets() -> dict:
    return {k: list(v) for k, v in PRESETS.items()}


@app.post("/api/estimate")
def estimate(req: EstimateRequest) -> dict:
    if req.model not in MODELS:
        raise HTTPException(400, f"unknown model {req.model!r}")
    spec = MODELS[req.model]
    try:
        p = plan(req.width, req.height, req.preset, req.scale, spec.scale)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    frames = max(1, req.frames or 1) if req.kind == "video" else 1
    seconds = estimate_seconds(req.width, req.height, p, spec.key, frames=frames)

    warning = None
    if p.passes == 0:
        warning = (
            "The target is smaller than the source, so this only resamples down "
            "- no detail will be added."
        )
    elif seconds > 3600:
        warning = (
            f"This is a long job ({human_time(seconds)}). Consider the 4K preset "
            "or the fast model. You can close the page; the job keeps running."
        )
    elif seconds > 600:
        warning = f"This will take a while ({human_time(seconds)})."

    return {
        "output_width": p.out_width,
        "output_height": p.out_height,
        "passes": p.passes,
        "seconds": round(seconds, 1),
        "human": human_time(seconds),
        "warning": warning,
    }


@app.post("/api/jobs", status_code=201)
async def create_job(
    file: UploadFile = File(...),
    model: str = Form("fast"),
    preset: str | None = Form(None),
    scale: float | None = Form(None),
    denoise: float = Form(0.0),
    sharpen: float = Form(0.0),
    quality: int = Form(95),
    format: str | None = Form(None),
) -> JSONResponse:
    name = Path(file.filename or "upload").name
    try:
        classify(name)
    except ValueError as exc:
        raise HTTPException(415, str(exc)) from exc
    if model not in MODELS:
        raise HTTPException(400, f"unknown model {model!r}")
    if preset and preset.lower() not in PRESETS:
        raise HTTPException(400, f"unknown preset {preset!r}")

    dest = UPLOAD_DIR / f"{int(time.time() * 1000)}_{name}"
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "file is larger than the 8 GiB limit")
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "the uploaded file was empty")

    settings = UpscaleSettings(
        model=model,
        preset=(preset.lower() if preset else None),
        scale=scale if (scale and not preset) else None,
        denoise=max(0.0, min(1.0, denoise)),
        sharpen=max(0.0, min(1.0, sharpen)),
        quality=max(1, min(100, quality)),
    )
    try:
        job = MANAGER.submit(dest, name, settings, out_format=format)
    except Exception as exc:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse(job.as_dict(), status_code=201)


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    return MANAGER.all()


def _job_or_404(job_id: str):
    job = MANAGER.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return _job_or_404(job_id).as_dict()


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str, request: Request) -> StreamingResponse:
    _job_or_404(job_id)

    def stream():
        for snap in MANAGER.subscribe(job_id):
            yield f"data: {json.dumps(snap)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    job = MANAGER.cancel(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return job.as_dict()


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    if not MANAGER.delete(job_id):
        raise HTTPException(404, "no such job")
    return {"deleted": True}


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str):
    job = _job_or_404(job_id)
    if job.status != "done" or not job.output_path or not job.output_path.exists():
        raise HTTPException(409, "this job has no finished output yet")
    return FileResponse(
        job.output_path, filename=job.output_path.name,
        media_type="application/octet-stream",
    )


@app.get("/api/jobs/{job_id}/thumb")
def thumb(job_id: str, side: str = "after"):
    """Small JPEG for the before/after comparison."""
    from PIL import Image, ImageOps

    job = _job_or_404(job_id)
    if side == "before":
        path = job.source_path
    else:
        if job.status != "done" or not job.output_path:
            raise HTTPException(409, "the result is not ready yet")
        path = job.output_path

    if job.kind == "video":
        raise HTTPException(415, "thumbnails are only available for images")
    if not path or not Path(path).exists():
        raise HTTPException(404, "file is gone")

    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((1400, 1400), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=88)
    except OSError as exc:
        raise HTTPException(500, f"could not render a preview: {exc}") from exc
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="image/jpeg", headers={"Cache-Control": "max-age=60"}
    )


@app.exception_handler(404)
async def spa_fallback(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "not found"}, status_code=404)
    index = WEB_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "web UI not built"}, status_code=404)


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


def serve(host: str = "127.0.0.1", port: int = 8420, reload: bool = False) -> None:
    import uvicorn
    uvicorn.run("pixelith.server:app", host=host, port=port, reload=reload,
                log_level="info")
