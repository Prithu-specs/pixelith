---
name: Bug report
about: Something crashed, produced a wrong result, or behaved unexpectedly
title: "[Bug] "
labels: bug
assignees: ''
---

## What happened

<!-- One or two sentences. What did you expect, and what did you get instead? -->

## Steps to reproduce

1.
2.
3.

Command or request used:

```
# e.g. python -m pixelith upscale photo.jpg --model quality --preset 4k
```

## Input details

| Field | Value |
|---|---|
| Kind | image / video |
| Source resolution | e.g. 1920x1080 |
| Source format | e.g. JPEG, PNG, MP4 (H.264) |
| Duration / frames (video only) | |
| Model | `fast` / `quality` |
| Preset or scale | e.g. `4k`, or `2.0` |

## Environment

Paste the output of `GET /api/health` if the server was running, or fill this in:

| Field | Value |
|---|---|
| Pixelith version | |
| OS and version | e.g. macOS 15.4, Ubuntu 24.04, Windows 11 |
| CPU / GPU | e.g. Apple M5 Pro, RTX 4070 |
| RAM | |
| Python version | `python3 --version` |
| ONNX Runtime package and version | e.g. `onnxruntime` 1.20, `onnxruntime-gpu` |
| Execution provider reported | e.g. `CoreMLExecutionProvider` |
| FFmpeg version | `ffmpeg -version \| head -n 1` |

## Logs and error output

<details>
<summary>Full traceback / console output</summary>

```
paste here
```

</details>

## Checklist

- [ ] I am on the latest `main` (or I have stated my version above).
- [ ] I have not modified the model registry or checksums in `pixelith/config.py`.
- [ ] If this is a slowness report, I have read the Performance section of the
      README and I am reporting something slower than the figures there, not
      simply that video upscaling is slow. Video upscaling is expected to be slow.
- [ ] I can reproduce this on a fresh run (model cache intact, no partial downloads).
