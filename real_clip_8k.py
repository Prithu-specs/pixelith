# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
"""Prithu's real 10-second clip: 1024x576 -> 8K. AI and native, timed precisely."""
import json, shutil, sys, time
from pathlib import Path

sys.path.insert(0, ".")
from pixelith.config import UpscaleSettings
from pixelith.jobs import MANAGER
from pixelith.server import estimate, EstimateRequest

SRC = Path("/home/adminstrator/.hermes/cache/videos/video_86f9be99daf0.mp4")
work = Path("/tmp/px_8k_real"); shutil.rmtree(work, ignore_errors=True); work.mkdir(parents=True)
out = {}

# Up-front honest estimate (the new machine-measured estimator).
est = estimate(EstimateRequest(kind="video", width=1024, height=576, frames=240, fps=24,
                               model="fast", preset="8k", video_processing="ai",
                               video_encoding="quality", source_bytes=SRC.stat().st_size))
out["estimate_before"] = {"human": est["human"], "provider": est["provider"],
                          "devices": est["devices"], "warning": est["warning"]}

# AI 8K.
t0 = time.time()
job = MANAGER.submit(SRC, "clip.mp4", UpscaleSettings(preset="8k", video_processing="ai",
                                                      video_encoding="quality"))
last = ""
while True:
    j = MANAGER.get(job.id)
    if j.status in ("done", "error", "cancelled"):
        break
    if j.message != last:
        last = j.message
    time.sleep(3)
j = MANAGER.get(job.id)
r = j.report or {}
out["ai_8k"] = {
    "status": j.status, "error": j.error,
    "wall_seconds": round(time.time() - t0, 1),
    "provider": r.get("provider"), "providers": r.get("providers"),
    "devices": r.get("devices"), "seconds_per_frame": r.get("seconds_per_frame"),
    "output": r.get("output"), "output_mb": round((r.get("output_bytes") or 0) / 1e6, 1),
    "frames": r.get("frames"),
}
print(json.dumps(out, indent=2), flush=True)

# Native (Quick resize) 8K for the speed ceiling.
t0 = time.time()
job2 = MANAGER.submit(SRC, "clip2.mp4", UpscaleSettings(preset="8k", video_processing="native",
                                                        video_encoding="quality"))
while True:
    j2 = MANAGER.get(job2.id)
    if j2.status in ("done", "error", "cancelled"):
        break
    time.sleep(2)
j2 = MANAGER.get(job2.id)
r2 = j2.report or {}
out["native_8k"] = {
    "status": j2.status, "error": j2.error,
    "wall_seconds": round(time.time() - t0, 1),
    "output": r2.get("output"), "output_mb": round((r2.get("output_bytes") or 0) / 1e6, 1),
}
print(json.dumps(out, indent=2))