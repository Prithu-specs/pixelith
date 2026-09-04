# Pixelith HTTP API (v1)

Server: FastAPI on `http://127.0.0.1:8420`. The web UI is served from `/` and is
static (no build step). All endpoints below are under `/api`.

## GET /api/health
```json
{"status":"ok","version":"0.1.0","providers":["CPUExecutionProvider"],
 "ffmpeg":true,"active":{"fast":"CoreMLExecutionProvider","quality":"CoreMLExecutionProvider"},
 "max_upload_bytes":8589934592}
```

## GET /api/models
```json
[{"key":"fast","label":"Fast (SRVGG general x4v3)","scale":4,"size_mb":4.6,
  "notes":"...","installed":true,"relative_cost":1.0}]
```

## GET /api/presets
Returned in slider order, which is **not** sorted by size: `180p` is the fourth
stop, between `720p` and `1080p`. The order of the keys is the order of the
steps, so render them as returned rather than sorting. `hd` is accepted as an
alias for `1080p`.
```json
{"360p":[640,360],"480p":[854,480],"720p":[1280,720],"180p":[320,180],
 "1080p":[1920,1080],"2k":[2560,1440],"4k":[3840,2160],"6k":[6144,3456],
 "8k":[7680,4320]}
```

## POST /api/estimate
Request: `{"kind":"video","width":1920,"height":1080,"frames":1800,"fps":30,
           "model":"fast","preset":"8k"}`

Pass **either** `preset` **or** `scale` (a float), never both; `preset` wins if
both appear. With neither, the model's native factor is used.

Note on video: browsers cannot read a file's frame rate, so clients should send
`fps: 30` as an assumption. The server re-probes the real rate on submission, so
the job's own `eta_seconds` supersedes this estimate - for 24 or 60 fps footage
the pre-upload figure can be off by up to 2x.
Response:
```json
{"output_width":7680,"output_height":4320,"passes":1,"seconds":6800,
 "human":"about 1 hour 53 minutes","warning":"Long job. Consider 4K or the fast model."}
```
`warning` is `null` when there is nothing to flag.

## POST /api/jobs   (multipart/form-data)
Fields: `file` (required), `model` (`fast`|`quality`), `preset` (`180p`…`8k`, optional),
`scale` (float, optional — used when `preset` is absent), `denoise` (0–1),
`sharpen` (0–1), `format` (`png`|`jpg`|`webp` for images; `mp4`|`mov` for video).

Response `201`: the full job object.

## GET /api/jobs → array of job objects, newest first (descending `created_at`).
## GET /api/jobs/{id} → one job.

### Job object
```json
{"id":"a1b2c3d4","filename":"cat.jpg","kind":"image",
 "status":"running","progress":0.42,"stage":"upscaling","message":"tile 120/288",
 "created_at":1756900000.0,"started_at":1756900001.0,"finished_at":null,
 "source":{"width":800,"height":600,"frames":null,"fps":null,"duration":null},
 "target":{"width":3200,"height":2400},
 "model":"fast","eta_seconds":31.4,"output_name":"cat_3200x2400.png","error":null}
```
`status` ∈ `queued | preparing | running | done | error | cancelled`.
`kind` ∈ `image | video`.
`stage` is a free-text hint, but these values are stable and worth special
handling: `queued`, `preparing`, `downloading_model`, `upscaling`, plus the
terminal statuses. During `downloading_model`, `progress` tracks the weight
download, not the upscale.
`progress` is always a number in 0..1; treat 0 during `preparing` as
indeterminate. `report` is an extra diagnostic object present once a job
finishes; treat it as optional.

## GET /api/jobs/{id}/events
`text/event-stream`. One `data:` line per update, each a complete job object.
Terminates after a job object with a terminal status. Reconnect-safe.

## GET /api/jobs/{id}/download → the finished file (`Content-Disposition: attachment`).
## GET /api/jobs/{id}/thumb?side=before|after → small JPEG for the comparison view.
## POST /api/jobs/{id}/cancel
Returns the job object. Cancellation is **cooperative**: the worker only checks
between tiles and frames, so a running job usually comes back still
`status:"running"` with `message:"stopping..."`, and reaches `"cancelled"` a
moment later. Clients must watch the event stream (or poll) for the terminal
state rather than assuming this response is final. A job still `queued` is
cancelled immediately.
## DELETE /api/jobs/{id} → `{"deleted":true}`; removes the job and its files.

## Errors
Non-2xx return `{"detail":"human readable message"}`.
Oversized upload → `413`. Unsupported type → `415`. Unknown job → `404`.
