# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
"""Capability test: real 10-second clip 360p -> 8K through the shipped pipeline."""
import json, shutil, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, ".")
from pixelith.config import UpscaleSettings
from pixelith.jobs import MANAGER

work = Path("/tmp/px_8k_test"); shutil.rmtree(work, ignore_errors=True); work.mkdir(parents=True)
result = {}

# 1) Make a real 10-second 640x360@24 source, exactly the "short clip" use case.
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "testsrc2=size=640x360:rate=24:duration=10", "-c:v", "libx264",
                "-preset", "veryfast", str(work / "ten_sec.mp4")], check=True)
src = work / "ten_sec.mp4"
probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                       "format=duration,size", "-of", "csv=p=0", str(src)],
                       capture_output=True, text=True)
result["source"] = {"probe": probe.stdout.strip().strip(",\n")}

# 2) AI 8K.
t0 = time.time()
job = MANAGER.submit(src, "ten_sec.mp4", UpscaleSettings(preset="8k", video_processing="ai",
                                                         video_encoding="quality"))
deadline = time.time() + 3600
while time.time() < deadline:
    j = MANAGER.get(job.id)
    if j.status in ("done", "error", "cancelled"):
        break
    time.sleep(2)
j = MANAGER.get(job.id)
r = j.report or {}
result["ai_8k"] = {
    "status": j.status, "error": j.error, "wall_seconds": round(time.time() - t0, 1),
    "provider": r.get("provider"), "devices": r.get("devices"),
    "seconds_per_frame": r.get("seconds_per_frame"), "output": r.get("output"),
    "output_bytes": r.get("output_bytes"), "out_frames": r.get("frames"),
}

# 3) Native 8K for comparison.
t0 = time.time()
job2 = MANAGER.submit(src, "ten_sec.mp4", UpscaleSettings(preset="8k", video_processing="native",
                                                          video_encoding="quality"))
deadline = time.time() + 1200
while time.time() < deadline:
    j2 = MANAGER.get(job2.id)
    if j2.status in ("done", "error", "cancelled"):
        break
    time.sleep(1)
j2 = MANAGER.get(job2.id)
r2 = j2.report or {}
result["native_8k"] = {
    "status": j2.status, "error": j2.error, "wall_seconds": round(time.time() - t0, 1),
    "output": r2.get("output"), "output_bytes": r2.get("output_bytes"),
}

print(json.dumps(result, indent=2))