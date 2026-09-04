# Pixelith

**Upscale images and video up to 8K on your own machine — no account, no API key, nothing uploaded.**

Pixelith is a local AI upscaler. You point it at a photo or a video, pick how
big you want it and how much you care about quality, and it runs a Real-ESRGAN
network over the pixels using whatever accelerator your machine has. There is a
small web UI and a command line. Once the model weights are cached, it works
entirely offline.

It is deliberately small: two models, one HTTP API, one static web page, and an
honest set of numbers about how long things take.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB)
![License: Pixelith EULA 1.0](https://img.shields.io/badge/license-Pixelith%20EULA%201.0-orange)
![Free tier: 100 images + 1 GB video](https://img.shields.io/badge/free%20tier-100%20images%20%2B%201%20GB%20video-brightgreen)
![Runtime: ONNX Runtime](https://img.shields.io/badge/runtime-ONNX%20Runtime-5C6BC0)
![Providers](https://img.shields.io/badge/providers-CUDA%20%7C%20CoreML%20%7C%20DirectML%20%7C%20CPU-607D8B)
![Inference: 100% local](https://img.shields.io/badge/inference-100%25%20local-2E7D32)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-455A64)

---

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Which devices does this run on?](#which-devices-does-this-run-on)
- [Install](#install)
- [Quick start](#quick-start)
- [Models](#models)
- [Performance](#performance)
- [Configuration](#configuration)
- [How it works](#how-it-works)
- [Limitations](#limitations)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [License](#license)
- [Credits](#credits)

---

## Features

- **Images and video**, up to 8K output, from a single tool.
- **Fully local.** Inference happens on your machine. No telemetry, no accounts,
  no API keys, no upload step. After the first run the whole thing works offline.
- **Two models, honestly labelled** — a 4.6 MB compact network for speed and a
  63.9 MB RRDBNet for detail. No sprawling model zoo to guess your way through.
- **Verified weights.** Models download on first use from Hugging Face and are
  checked against a pinned SHA-256 digest before they are ever loaded.
- **Per-model hardware selection.** The execution provider is chosen per network,
  not globally, because the fastest runtime genuinely differs between the two
  (see [Performance](#performance)).
- **Seamless tiling.** Overlapping tiles blended with a feathered weight mask, so
  no grid artefacts even on very large images.
- **Resolution presets** — `hd`, `2k`, `4k`, `6k`, `8k` — or an arbitrary scale factor.
- **Web UI and CLI.** A static single-page UI with a before/after comparison, plus
  `python -m pixelith upscale` for scripts.
- **A time estimator that runs before the job.** `POST /api/estimate` tells you
  what you are in for, and the CLI refuses to silently start anything over about
  15 minutes without asking first.
- **Cancellable jobs** with live progress over server-sent events.

---

## Requirements

| | |
|---|---|
| **Python** | 3.10 or newer |
| **FFmpeg** | Required for all video work; must be on your `PATH` |
| **Disk** | ~70 MB for both model files, plus scratch space while video runs |
| **RAM** | 4 GB minimum, 8 GB workable, 16 GB+ comfortable for 4K and above |
| **Network** | Only on first run, to fetch model weights |
| **GPU** | **Not required.** See below. |

---

## Which devices does this run on?

Pixelith is a small local web server plus a browser interface. That split is what
makes it work everywhere: the computer does the maths, and *any* device with a
browser can drive it.

### Runs the software itself

| Platform | Status | Notes |
|---|---|---|
| **Windows** 10/11 (x64, ARM64) | Supported | Prebuilt wheels for every dependency; no compiler needed |
| **macOS** 12+ (Apple silicon, Intel) | Supported | Uses CoreML when it helps |
| **Linux** (x86-64, aarch64) | Supported | glibc and musl wheels both published |
| **Raspberry Pi 4/5** (64-bit) | Works, slowly | Fine for photos; do not attempt video |

### Uses it from a browser

| Device | How |
|---|---|
| **Android** phone/tablet | Start with `--lan`, open the printed address in Chrome |
| **iPhone / iPad** | Same, in Safari. HEIC photos upload and convert correctly |
| **Any laptop** on the network | Same address, any modern browser |

Android and iOS cannot run the engine themselves — ONNX Runtime publishes no
wheels for either — so there is no standalone mobile app, and this is not a
limitation Pixelith can engineer around. Point the phone at a computer instead:

```bash
python -m pixelith serve --lan
```

```
  this computer   http://127.0.0.1:8420
  phone / tablet  http://192.168.1.104:8420
```

There is **no sign-in, no account and no password** — anyone who opens that
address can use it straight away. That is the point on your own Wi-Fi. The flip
side is that Pixelith does not check who is asking, so use `--lan` on a network
you trust rather than on public café Wi-Fi.

### Running without a GPU

This is the normal case and it is fully supported. There is no CUDA requirement,
no minimum VRAM, and no separate build to install — the default `pip install`
is the CPU build.

Pixelith adapts to the machine it finds. It picks the execution provider *and*
the tile size together, because the two interact: on a CPU-only machine, using
the tile size that suits a neural engine costs about **2x** the runtime. Choosing
correctly is automatic.

| Machine | What happens | 1080p frame, `fast` |
|---|---|---|
| NVIDIA GPU | CUDA, large tiles | Fastest; not benchmarked here |
| Apple silicon | CoreML, tile 192 | ~8.6 s |
| **Any CPU, no GPU** | **CPU, tile 512** | **~8.5 s on an M5 Pro** |
| Windows with AMD/Intel GPU | DirectML, tile 384 | Untested |
| 4 GB RAM machine | Tiles capped at 192 | Slower, but it completes |

On a CPU-only machine an older or slower processor will of course take longer
than the figure above — that row is the same M5 Pro with acceleration disabled,
which isolates the effect of the provider rather than predicting your laptop.
Expect a mainstream 4-core laptop to be a few times slower again. Photos remain
practical; long video does not become practical on any CPU.

If you need to force a choice, `--tile` overrides the automatic pick. Lower it
if you hit an out-of-memory error, and otherwise leave it alone.

---

## Install

The same three steps everywhere: clone, make a virtual environment, install.
The only platform difference is how you get FFmpeg.

### macOS

```bash
brew install ffmpeg

git clone https://github.com/Prithu-specs/pixelith.git
cd pixelith
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The standard `onnxruntime` wheel for macOS includes the CoreML execution
provider, so there is nothing extra to install on Apple silicon.

### Linux

```bash
# Debian / Ubuntu
sudo apt update && sudo apt install -y ffmpeg
# Fedora:  sudo dnf install ffmpeg
# Arch:    sudo pacman -S ffmpeg

git clone https://github.com/Prithu-specs/pixelith.git
cd pixelith
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**With an NVIDIA GPU**, swap the CPU runtime for the CUDA one after the install:

```bash
pip uninstall -y onnxruntime
pip install onnxruntime-gpu
```

Install exactly one ONNX Runtime package. Having both `onnxruntime` and
`onnxruntime-gpu` in the same environment is the single most common reason CUDA
silently fails to appear.

### Windows

Install FFmpeg first, e.g. `winget install Gyan.FFmpeg` (or `choco install
ffmpeg-full`), then open a **new** terminal so the updated `PATH` takes effect.

```powershell
git clone https://github.com/Prithu-specs/pixelith.git
cd pixelith
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**With an NVIDIA GPU:**

```powershell
pip uninstall -y onnxruntime
pip install onnxruntime-gpu
```

**With an AMD or Intel GPU**, use DirectML instead:

```powershell
pip uninstall -y onnxruntime
pip install onnxruntime-directml
```

### Verify the install

```bash
python -m pixelith info
```

That prints the version, the output directory, whether FFmpeg was found, the
execution providers available, and — importantly — which provider each model
will actually run on. If you expected `CUDAExecutionProvider` and do not see it,
see [Troubleshooting](#troubleshooting).

---

## Quick start

### Web UI

```bash
python -m pixelith serve
```

Open <http://127.0.0.1:8420>. Drop in a file, pick a model and a target
resolution, and watch the estimate before you commit to the job. Progress
streams live and jobs can be cancelled mid-run.

The first job with a given model pauses to download its weights (4.6 MB or
63.9 MB). That happens once per model, ever — or run `python -m pixelith
download` up front to get it over with.

`serve` binds to `127.0.0.1:8420` by default. Override with `--host` and
`--port`.

### CLI

```bash
python -m pixelith upscale photo.jpg
```

Output lands in `$PIXELITH_OUT` (by default `~/Pixelith`), named after the
source and the final resolution — for example `photo_3200x2400.png`.

```bash
# Best detail on a still, targeting 4K
python -m pixelith upscale portrait.png --model quality --preset 4k

# A short clip to 4K with the fast model — start small, this takes a while
python -m pixelith upscale clip.mp4 --model fast --preset 4k

# An explicit scale factor instead of a named preset
python -m pixelith upscale scan.tif --scale 2.0
```

| Flag | Meaning |
|---|---|
| `-o`, `--output` | Explicit output path. The **extension decides the format** — there is no separate format flag. |
| `-m`, `--model` | `fast` (default) or `quality` |
| `-p`, `--preset` | `hd`, `2k`, `4k`, `6k`, `8k` |
| `-s`, `--scale` | Scale factor, e.g. `2` or `3.5`. Use instead of `--preset`. |
| `--denoise`, `--sharpen` | Post-process strength, `0.0`–`1.0` |
| `--quality` | JPEG/WebP encoder quality, default `95` |
| `--tile` | Tile size override — lower it if you run out of memory |
| `-y`, `--yes` | Skip the confirmation prompt on long jobs |

Before it starts, `upscale` prints the source and target resolution, the number
of network passes, the estimated time, and where the file will be written. **If
the estimate exceeds 15 minutes it asks you to confirm** — which, for video, it
usually will. Pass `-y` in scripts.

### Other commands

```bash
python -m pixelith info                 # models, providers, paths, FFmpeg status
python -m pixelith download             # pre-fetch both models
python -m pixelith download quality     # or just one
```

`info` is the first thing to run when something is wrong: it prints the
execution providers available, which provider each model will actually use, and
whether FFmpeg was found. `download` pre-seeds the cache, which is what you want
before going offline or onto a metered connection.

Run `python -m pixelith --help`, or `--help` on any subcommand, for the
authoritative list as built.

### HTTP API

The server exposes a small JSON API on the same port — job submission, progress
over server-sent events, download, cancel. It is documented in
[`docs/API.md`](docs/API.md).

**Before you queue any video job, ask the estimator first:**

```bash
curl -s -X POST http://127.0.0.1:8420/api/estimate \
  -H 'Content-Type: application/json' \
  -d '{"kind":"video","width":1920,"height":1080,"frames":1800,"fps":30,
       "model":"fast","preset":"8k"}'
```

```json
{"output_width":7680,"output_height":4320,"passes":1,"seconds":6800,
 "human":"about 1 hour 53 minutes",
 "warning":"Long job. Consider 4K or the fast model."}
```

---

## Models

Both models are native **4x** networks from the Real-ESRGAN family. Any other
scale factor is reached by running the 4x pass and resampling the result, which
matters for how you should read the performance numbers below.

| Key | Network | Architecture | File size | Native scale | Best for |
|---|---|---|---|---|---|
| `fast` | `realesr-general-x4v3` | Compact SRVGG | 4.6 MB | 4x | Video, photo batches, anything where throughput matters. The default. |
| `quality` | Real-ESRGAN x4plus | 23-block RRDBNet | 63.9 MB | 4x | Single stills where you want the most detail and do not mind waiting. |

Relative cost per input pixel is roughly **5.2x** for `quality` against `fast`.
That factor is what makes `quality` a still-image tool and `fast` the only
sensible choice for video.

Weights are fetched on first use from Hugging Face
(`CoderViking/realesr-general-x4v3-onnx` and `SceneWorks/real-esrgan-onnx`),
cached under `$PIXELITH_HOME/models`, and verified against a SHA-256 digest
pinned in `pixelith/config.py`. A file that fails verification is deleted rather
than loaded.

---

## Performance

All figures below were **measured on an Apple M5 Pro (48 GB)**. They are the real
numbers from that machine, not projections. Your hardware will differ — an
NVIDIA GPU will be substantially faster, an older laptop substantially slower —
but the *ratios* between models and providers hold up broadly.

### Measured throughput

Throughput is megapixels of **input** per second, measured end to end: a real
file in, a written file out, including tiling and blending.

| Model | 1080p frame | Effective throughput |
|---|---|---|
| `fast` (SRVGG x4v3) | **~8.6 s** | ~0.24 MPix/s |
| `quality` (x4plus RRDBNet) | ~45 s | ~0.046 MPix/s |

Two things here are worth knowing, because both cost real hours if you get them
wrong.

> **Tile size matters more than the execution provider.** On the same 1080p
> frame, CPU and CoreML finish within noise of each other *when each runs at its
> own best tile size* — 8.5 s and 8.7 s. But CPU forced onto CoreML's tile size
> takes 11.1 s, a 30% penalty for one setting. Threaded CPU kernels want a few
> large tiles; the neural engine wants many small ones. Pixelith picks the tile
> size from the active provider and the machine's RAM, so you should not need to
> touch it.

> **Benchmark a whole frame, not one tile, and do it on an idle machine.** An
> early version of this README claimed CoreML was 1.9x faster than CPU. That was
> wrong. It came from timing a single cached tile while other work was running,
> and from comparing CPU at a bad tile size against CoreML at a good one. The
> numbers above come from interleaved A/B runs on an idle machine.

Tiling also means the network processes more pixels than the image contains. A
tile grid with 16 px of overlap covers about **1.4x** the real pixel count at
1080p, rising to **2.3x** on a 512 x 512 image. That is why small images show
lower throughput than large ones.

### Still images

Measured, `fast` model, native 4x pass, cold input to written file.

| Input | Input MPix | Time | Throughput |
|---|---|---|---|
| 512 x 512 | 0.26 | 1.6 s | 0.17 MPix/s |
| 1024 x 1024 | 1.05 | 5.1 s | 0.21 MPix/s |
| 1920 x 1080 | 2.07 | 9.1 s | 0.23 MPix/s |
| 2560 x 1440 | 3.69 | 15.6 s | 0.24 MPix/s |
| 3840 x 2160 | 8.29 | ~35 s* | ~0.24 MPix/s |

\* extrapolated from the trend; the rest are measured.

The `quality` model costs roughly **5.2x** these times. For a single photo that
is a good trade: a 512 x 512 image takes about 8 s and gains far more real
detail (see [How it works](#how-it-works)).

**Still images are practical.** A phone photo enlarged for print takes seconds
to a minute. That is the good news.

### Video

Here is the bad news, stated plainly.

Video is upscaled frame by frame. There is no temporal shortcut, no keyframe
interpolation, no reuse between frames. One minute of 1080p at 30 fps is 1,800
separate 1080p upscales at ~9 s each, which is **about four and a half hours**.

Times below use the `fast` model with auto-selected tiling. A CUDA GPU will beat
these substantially; a CPU-only laptop lands in the same ballpark as the figures
here, because tile sizing matters more than the provider.

| Source | Per frame | 10 s @30 | 1 min @30 | 5 min @30 | 1 min @60 |
|---|---|---|---|---|---|
| 480p (854 x 480) | ~2.2 s | 11 min | 1.1 h | 5.5 h | 2.2 h |
| 720p | ~4.3 s | 21 min | 2.2 h | 11 h | 4.3 h |
| **1080p** | **9.1 s** | **46 min** | **4.6 h** | **23 h** | **9.1 h** |
| 1440p | 15.6 s | 78 min | 7.8 h | 39 h | 16 h |
| 4K | ~35 s | 2.9 h | 18 h | 3.6 days | 35 h |

Using the `quality` model on video multiplies all of the above by roughly 5.2.
One minute of 1080p becomes about **24 hours**. Pixelith will let you do it.
Please do not.

Because jobs are this long, video is **resumable**. Work is written in ~8 second
segments, so a crash, a reboot, or a cancelled job only loses the segment in
flight — restart the same command and it picks up where it stopped.

### How long will my job take?

Two rules explain almost every number above.

1. **Cost is driven by the input, not the output.** The network always runs one
   native 4x pass; the preset is reached by resampling afterwards. So upscaling a
   1080p source to 8K costs the *same* as upscaling it to 4K. If a job is too
   slow, lowering the target resolution will not help — you need a smaller
   source, a shorter clip, or the `fast` model.
2. **Going beyond 4x needs a second pass, and the second pass is brutal.** It
   runs on input that is already 4x larger, so it costs roughly 16x the first.
   A 480p source to 8K needs two passes: tens of seconds per frame rather than
   ~2 s. Check `passes` in the `/api/estimate` response before committing.

Use this to decide:

| What you want | Do this | Roughly |
|---|---|---|
| A photo enlarged for print or a wallpaper | `quality`, any preset | Seconds to a minute |
| A folder of photos processed overnight | `fast` | ~4 s per megapixel of input |
| A short social clip, a few seconds | `fast`, 4K preset | Tens of minutes |
| A one-minute 1080p video | `fast` | **Start it and come back tomorrow** |
| A five-minute 1080p video | `fast` | ~1 day |
| A full episode or a feature | Use a CUDA GPU, or don't | Weeks |
| Any video at all with `quality` | Reconsider | 5.2x every number above |
| 8K video | Reconsider harder | See [Limitations](#limitations) |

Rule of thumb before starting anything long: **run `POST /api/estimate` first.**
It is free, it is instant, and it will tell you when a job is unreasonable.

## Configuration

Pixelith is configured entirely through two environment variables. There is no
config file.

| Variable | Default | What it holds |
|---|---|---|
| `PIXELITH_HOME` | `~/.cache/pixelith` | Downloaded model weights (`models/`) and scratch space for video frames (`work/`) |
| `PIXELITH_OUT` | `~/Pixelith` | Finished files |

```bash
export PIXELITH_HOME=/mnt/fast-ssd/pixelith
export PIXELITH_OUT=~/Pictures/Upscaled
python -m pixelith serve
```

Both paths are created on startup if they do not exist, and `~` is expanded.

Point `PIXELITH_HOME` at your fastest drive if you work with video: frame
extraction writes every frame of the source to `work/` as an intermediate, which
for long clips is a lot of disk traffic.

Everything else — model, preset, scale, tile size, overlap, denoise, sharpen,
output format — is a per-job choice, made on the CLI or in the API request, not
an ambient setting.

---

## How it works

**1. Decode.** Images go through Pillow. Video is demuxed by FFmpeg into
individual frames in `$PIXELITH_HOME/work`, with the audio track set aside.

**2. Tile.** Anything larger than the model's tile size (256 px for `fast`, 192
px for `quality`) is cut into overlapping tiles. Tiling is what keeps memory flat
regardless of image size — an 8K render never needs an 8K activation buffer.

**3. Constant-shape inference.** Every tile handed to the network has exactly the
same shape, always. This is not an accident of implementation, it is the point:
CoreML recompiles its graph whenever it sees a new input shape, so ragged tiles
along the right and bottom edges would stall the run repeatedly — once per new
shape, and again on every image with different dimensions. Instead, short edge
tiles are reflect-padded up to the full tile size, run, and cropped afterwards.
The graph compiles once and stays compiled.

**4. Feathered blending.** Naively butting tiles together leaves a visible grid.
Pixelith overlaps them and blends with a separable feathered weight mask: a 1-D
ramp that rises across the overlap region, holds at 1 across the tile interior,
and falls again at the far edge, applied on both axes. Contributions accumulate
into a float buffer alongside a weight buffer, and the final pixel is their
ratio. Seams disappear because neighbouring tiles cross-fade rather than abut.

**5. Resample to target.** The network output is a fixed 4x. If your preset asks
for something other than 4x, the result is resampled to hit it exactly, which is
why a 4K target and an 8K target from the same source cost the same. Ratios above
4x trigger a second full pass.

**6. Reassemble.** Stills are written in your chosen format; outputs above 80
megapixels are streamed to disk tile by tile rather than held in RAM. Video
frames are re-encoded by FFmpeg and the original audio is muxed back in.

Provider selection happens once, at model load, using the measured per-model
preference order in `pixelith/config.py`. If a provider fails to initialise,
Pixelith logs a warning and falls back to CPU rather than dying.

---

## Limitations

These are real, and none of them are on a near-term roadmap. Read them before
you decide whether Pixelith fits your problem.

- **Video is slow.** Not "slower than you'd like" — an order of magnitude away
  from real time. One minute of 1080p is about four and a half hours on an M5
  Pro. Nothing
  in this project is intended for live or interactive video use.
- **8K video is impractical on essentially all consumer hardware.** Even at
  `fast` on a good GPU you are looking at days for anything of meaningful length,
  plus enormous intermediate frame storage. The 8K preset exists for stills. It
  is technically reachable for video and you will regret reaching for it.
- **No face restoration.** There is no GFPGAN/CodeFormer stage. Faces get the
  same general-purpose treatment as everything else, and small or heavily
  compressed faces can come out plasticky. This is a known gap, not a hidden bug.
- **Upscaling cannot invent detail that was never captured.** The network
  hallucinates plausible texture from what is there. If the source is out of
  focus, motion blurred, or crushed by heavy compression, the output is a larger
  version of that. Illegible text does not become legible. A blurry licence plate
  stays a blurry licence plate. Anyone who tells you otherwise is selling
  something.
- **No temporal consistency pass.** Frames are upscaled independently, so
  fine-grained hallucinated texture can shimmer slightly between frames on
  detailed surfaces.
- **Two models only.** No anime-specific network, no denoise-strength variants,
  no 2x native model. This is a scope decision.
- **Single job at a time in practice.** Inference is serialised behind a lock;
  queueing several large jobs will not make them finish sooner.
- **Alpha channels are not upscaled by the network.** Input is treated as RGB.

---

## Troubleshooting

### My phone cannot open the page

Start the server with `--lan` — without it Pixelith binds to `127.0.0.1` and is
only reachable from the machine it runs on.

```bash
python -m pixelith serve --lan
```

If it still will not connect: the phone must be on the **same** network (not a
guest VLAN), and the computer's firewall must allow the port. On Windows,
approve the prompt for "Private networks" the first time. On macOS, check System
Settings > Network > Firewall. If `--lan` prints no address, the machine has no
routable LAN interface, which usually means a VPN is capturing the route.

### HEIC photos are rejected

The `.heic` and `.heif` types only appear once `pillow-heif` is installed:

```bash
pip install pillow-heif
```

`python -m pixelith info` reports `HEIC/HEIF: yes` when it is working. Pixelith
deliberately does not advertise formats it cannot decode, so an install without
the plugin will reject iPhone photos at upload rather than failing mid-job.

### It is slow and I have no GPU

That is expected, and the tile size is already chosen for you. Do not lower
`--tile` for speed; on a CPU-only machine smaller tiles are *slower*, sometimes
by 2x. Lower it only to escape an out-of-memory error. Use the `fast` model, and
treat long video as an overnight job or not at all.


**Start here:** run `python -m pixelith info`. It answers most of the questions
below in one go — providers, per-model provider selection, FFmpeg, and paths.

**`ffmpeg` not found / all video jobs fail immediately**
`python -m pixelith info` shows `ffmpeg : NOT FOUND`, and `GET /api/health`
reports `"ffmpeg": false`. Install FFmpeg for your platform (see
[Install](#install)) and, on Windows, open a new terminal so the updated `PATH`
is picked up.

**"failed checksum verification"**
The downloaded weights did not match the pinned SHA-256, usually a truncated or
interrupted download. Delete the file from `$PIXELITH_HOME/models` and run again.
If it fails a second time on a good connection, open an issue — the upstream
Hugging Face file may have been replaced, which is exactly what the check exists
to catch. Pixelith deliberately refuses to load unverified weights.

**Download fails behind a proxy, or the machine is fully offline**
Run `python -m pixelith download` on a machine that does have access, then copy
`$PIXELITH_HOME/models` across. Failing that, fetch the two files by hand from
the Hugging Face repositories listed in [`NOTICE.md`](NOTICE.md) and drop them
into `$PIXELITH_HOME/models` using the exact filenames
`realesr-general-x4v3.onnx` and `real_esrgan_x4.onnx`. Pixelith checks the cache
before it ever touches the network.

**CUDA is installed but Pixelith still uses CPU**
Check the `providers` line from `python -m pixelith info`.
If `CUDAExecutionProvider` is absent, you almost certainly have the CPU-only
`onnxruntime` package installed — possibly alongside `onnxruntime-gpu`, which
breaks it. Uninstall both, then install only `onnxruntime-gpu`. Also confirm your
CUDA and cuDNN versions match what your ONNX Runtime build expects.

**The `fast` model is slower than the table says on my Mac**
Run `python -m pixelith info` and read the `runs on` line under `fast`, or check
`active.fast` in `GET /api/health`. If it reads `CoreMLExecutionProvider`, that
is the slow path for this network — it should be `CPUExecutionProvider`. This
happens when providers were forced explicitly in the request. Let Pixelith choose.

**The first run on Apple silicon has a long pause before any progress**
CoreML compiles the graph on first use. It is cached afterwards. This affects the
`quality` model most, since that is the one that runs on CoreML.

**Out of memory, or the machine starts swapping on a large image**
Lower the tile size for that job: `--tile 128`, or `--tile 96` if that is still
too much. Smaller tiles mean more of them and slightly slower throughput, but a
much flatter memory profile.

**Visible grid or seams in the output**
The overlap was set too low for the tile size. Restore the default (16) — the
feathered blend needs a real overlap region to cross-fade across.

**Port 8420 is already in use**
Something else is bound to it, most likely an earlier Pixelith you did not stop.
Find it with `lsof -i :8420` (macOS, Linux) or
`netstat -ano | findstr :8420` (Windows).

**Video output has no audio, or fails at the encode step**
Your FFmpeg build may lack the encoder needed for the chosen output format.
Check `ffmpeg -version` for the configure flags; H.264 output requires a build
with `libx264`, which not every minimal package includes.

**A job is taking far longer than the estimate**
Confirm it is not doing two passes (`passes` in the estimate response), that the
source resolution is what you think it is, and that you are not running the
`quality` model on video. Those three account for nearly every surprise.

---

## FAQ

**Is it actually free?**
For non-commercial use, yes, and permanently. Commercial use needs a separate
arrangement — see [License](#license).

**Does anything get uploaded?**
No. The only network request Pixelith ever makes is downloading the model files
on first use. After that you can disconnect entirely and everything still works.
There is no telemetry, no analytics, no phone-home.

**Can it upscale video in real time?**
No, and it is not close. See [Performance](#performance). Please plan around
hours, not seconds.

**I asked for 2x. Why does it say the model is 4x?**
Both networks are natively 4x. Pixelith runs the 4x pass and resamples down to
your target. The practical consequence is that lowering your target resolution
does not make a job faster.

**Why did 8K take the same time as 4K?**
Because cost tracks input pixels, not output pixels. Same source, same one pass,
same time. Only the final resample differs.

**Which model should I use?**
`fast` for anything with more than a handful of frames. `quality` for individual
stills you care about. If you are unsure, run one image through both and compare
— it costs seconds.

**Can I use this at work, or for client deliverables?**
That is commercial use, and it is outside the licence. Open an issue to discuss
terms.

**Is there face restoration?**
Not yet. See [Limitations](#limitations).

**Can I make a blurry photo sharp / read the text in this screenshot?**
No. Upscaling adds plausible texture; it does not recover information that was
never recorded. If the detail is not in the source, no model puts it back.

**Can I add my own ONNX model?**
The registry lives in `pixelith/config.py` and is a plain dictionary — a new
entry needs a URL, a SHA-256, a scale, a tile size, and a measured provider
preference order. Please benchmark before proposing one; the per-model provider
ordering is the whole reason this project is fast on Apple silicon.

**Why are the two ONNX files from different Hugging Face uploaders?**
Because those are the conversions that exist and verify cleanly. Pixelith pins
both by digest precisely so it does not have to trust either uploader over time.

**Does it work on AMD or Intel GPUs?**
On Windows, yes, via DirectML (`onnxruntime-directml`). On Linux, ROCm is
recognised if your ONNX Runtime build provides it, but it is untested here.

---

## License

Pixelith is **copyright &copy; 2026 PGA Tech Solutions** and is licensed under the
[**Pixelith End User Licence Agreement 1.0**](LICENSE)
(SPDX: `LicenseRef-Pixelith-EULA-1.0`).

It is **source-available, not open source**. You can read the code, study it and
modify it for your own use. Reading it does not grant rights beyond the licence.

### Pricing

| Tier | India | Elsewhere | Covers |
|---|---|---|---|
| **Free** | &mdash; | &mdash; | Personal use, **100 images** and **1 GB of video input** |
| **Personal** | **&#8377;499** + GST | **$10** | One person, all their devices. Unlimited, for life |
| **Commercial** | **&#8377;7,999** + GST | **$200** | One company. Any commercial use, unlimited, for life |

Indian buyers pay &#8377;589 and &#8377;9,439 respectively, including 18% GST.

One-time payments. Nothing to renew, no subscription, no expiry.

Pixelith is made by PGA Tech Solutions, a sole proprietorship in Uttar Pradesh,
India (GSTIN `09AIAPG7383C1ZE`). **Rupee prices are exclusive of GST**; 18% GST
(SAC 997331) is added at checkout, the all-in total is shown before you pay, and
a tax invoice is issued; prices elsewhere are exclusive of local tax, which is
added at checkout and are exports of service zero-rated under LUT. Which price
applies depends on where you or your organisation are established.

**The two free allowances are independent.** Reaching 100 images does not consume
your video allowance, and vice versa. A single paid licence removes both &mdash;
there is no separate charge for images and video.

**Charities, schools, universities, public research bodies, public health and
safety organisations, and government bodies count as personal use**, regardless
of how they are funded.

**Commercial use needs a licence from the first byte.** There is no free
commercial allowance. Using Pixelith inside a business counts as commercial even
if you never sell the output.

### What the free tier is really worth

The video allowance is more generous than it sounds, because compute time is the
real ceiling, not bytes:

| Your source | 1 GB is about | Time to upscale it to 8K |
|---|---|---|
| Phone 1080p | 8 minutes | ~34 hours |
| Phone 4K | 3 minutes | ~13 hours |
| Screen recording | 45 minutes | ~193 hours |

Most personal users will never reach the limit, because they would need to leave
the machine running for weeks first. If you do reach it, $10 is not a lot to ask.

### How the allowance works

The free allowance is **measured and enforced on your own machine**. Pixelith
keeps a usage record locally, and when you reach a limit it stops and tells you
how to get a licence. Licence keys are Ed25519-signed and verified offline
against a public key built into the app, so activation works with no network at
all.

```
$ pixelith status
Free tier
  images   87 of 100 used, 13 left
  video    0.72 GB of 1.00 GB used, 0.28 GB left
  output   carries an invisible provenance mark
```

**Pixelith still never contacts us.** No telemetry, no usage reports, no
activation server, nothing about you or your files leaves the machine. The only
network access it makes is downloading model weights on first run. You can
verify all of that in the source.

### The mark on free output

Files produced on the free tier carry an **invisible, machine-readable mark**
recording the tier, the installation, and where you were in your allowance. It
is disclosed here, in the licence and in the app, because you are entitled to
know what is in files you make.

- It is **imperceptible** &mdash; measured at ~44 dB PSNR, altering only
  mid-frequency luma coefficients.
- It **survives JPEG re-compression** down to about quality 60, and PNG
  round-trips. Low-bit marking would be more invisible on paper but is destroyed
  the moment an image is saved as a JPEG, which is what happens to most shared
  images.
- It contains **no personal information** &mdash; no name, no file contents, no
  location &mdash; and is never transmitted. It exists only in files you keep.
- A **paid licence turns it off**. Licensed output is clean.

Anyone can read a mark back:

```bash
pixelith verify photo.png
```

### What this does and does not achieve

Being straight about it: the source is public, so a determined user can edit the
check out. Local enforcement raises the bar from *"nothing stops me"* to
*"I would have to modify the program"*, and the mark means free-tier output stays
identifiable if it later turns up in commercial work. It is not DRM and it is not
trying to be. It is there to make paying the easy path.

### Buying a licence

**[licensing@pgatech.solutions](mailto:licensing@pgatech.solutions)**

Tell us which tier you need. For commercial enquiries it helps to say what you
are building and whether you need to redistribute Pixelith or only run it.

### If you redistribute Pixelith

Redistribution needs our written permission (clause 5.2). Where granted, you must
pass on both the licence and this notice, exactly as it appears at the top of
[`LICENSE`](LICENSE):

```
Required Notice: Copyright (c) 2026 PGA Tech Solutions
(https://github.com/Prithu-specs/pixelith)
```

Removing that notice, or the copyright headers in the source files, is a breach
in itself &mdash; it is how the next person downstream learns the terms apply.

### Three things to be aware of

1. **Versions 0.1.x were released under PolyForm Noncommercial 1.0.0.** Those
   rights are not withdrawn and still apply to those versions; the text is kept
   in the repository as
   [`LICENSE-0.1.x-PolyForm-Noncommercial-1.0.0.txt`](LICENSE-0.1.x-PolyForm-Noncommercial-1.0.0.txt).
   The terms above apply from **0.2.0** onward.
2. **This is not an open-source licence.** It restricts commercial use, so code
   hosts will label the repository accordingly and Linux distributions and
   package managers will not redistribute it. That is the deliberate trade for
   keeping it free for everyone who is not selling something.
3. **The licence covers Pixelith's own code only.** Model weights, ONNX Runtime,
   FFmpeg and the Python libraries carry their own terms &mdash; see
   [`NOTICE.md`](NOTICE.md). In particular the Real-ESRGAN weights are BSD
   3-Clause and remain freely usable commercially in their own right. What needs
   a licence from PGA Tech Solutions is Pixelith: the engine, the pipeline, the
   server, the interface and the tooling around them.

The summary above is a convenience. The [`LICENSE`](LICENSE) file is what
governs.

---

## Credits

Pixelith is thin. Almost all of the hard work belongs to other people.

- **[Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)** — Xintao Wang,
  Liangbin Xie, Chao Dong, and Ying Shan. Both networks Pixelith ships come from
  this project. BSD-3-Clause.
- **ONNX conversions** hosted on Hugging Face by
  [CoderViking](https://huggingface.co/CoderViking/realesr-general-x4v3-onnx) and
  [SceneWorks](https://huggingface.co/SceneWorks/real-esrgan-onnx).
- **[ONNX Runtime](https://onnxruntime.ai)** — Microsoft. MIT.
- **[FFmpeg](https://ffmpeg.org)** — the FFmpeg developers. LGPL or GPL depending
  on build.
- **[FastAPI](https://fastapi.tiangolo.com)**, **[Pillow](https://python-pillow.org)**,
  and **[NumPy](https://numpy.org)**.

Full attribution and licence text: [`NOTICE.md`](NOTICE.md).
Contributions welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md).
