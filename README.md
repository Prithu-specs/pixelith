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
![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-orange)
![Runtime: ONNX Runtime](https://img.shields.io/badge/runtime-ONNX%20Runtime-5C6BC0)
![Providers](https://img.shields.io/badge/providers-CUDA%20%7C%20CoreML%20%7C%20DirectML%20%7C%20CPU-607D8B)
![Inference: 100% local](https://img.shields.io/badge/inference-100%25%20local-2E7D32)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-455A64)

---

## Contents

- [Features](#features)
- [Requirements](#requirements)
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
| **Disk** | ~70 MB for both model files, plus scratch space for video frames |
| **RAM** | 8 GB is workable; 16 GB+ is comfortable for 4K and above |
| **Network** | Only on first run, to fetch model weights |

Acceleration is optional. Pixelith runs on plain CPU everywhere and will use a
faster execution provider when one is available:

| Platform | Provider | Notes |
|---|---|---|
| NVIDIA (Linux, Windows) | `CUDAExecutionProvider` | Fastest option wherever present |
| Apple silicon | `CoreMLExecutionProvider` | Helps the `quality` model; **hurts** the `fast` one |
| Windows (any GPU) | `DmlExecutionProvider` | DirectML, including AMD and Intel |
| Everything else | `CPUExecutionProvider` | Always available; the fallback |

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

| Model | Best provider | 1080p frame | Effective throughput |
|---|---|---|---|
| `fast` (SRVGG x4v3) | CoreML, tile 192 | **9.1 s** | ~0.23 MPix/s |
| `quality` (x4plus RRDBNet) | CoreML, tile 192 | ~47 s | ~0.044 MPix/s |

Two things here are worth knowing, because both cost real hours if you get them
wrong.

> **Benchmark a whole frame, not one tile.** Timing a single tile in a loop
> suggested the `fast` model ran at 0.52 MPix/s and that plain CPU beat CoreML.
> Both conclusions were wrong. That loop re-runs one cached shape with no memory
> pressure and ignores tiling overhead. On real 1080p frames CoreML is **1.9x
> faster** than CPU (8.3 s vs 16.0 s), and true throughput is less than half the
> micro-benchmark figure.

> **Tile size matters more than you would expect.** On the same 1080p frame the
> `fast` model takes 8.3 s at tile 192 but 14.2 s at tile 256 — a 1.7x penalty
> for one setting. The defaults are the measured optimum; `--tile` is there for
> memory-constrained machines, not for speed.

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

Times below use the `fast` model on its best provider. There is no faster
configuration.

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

Pixelith is released under the
[**PolyForm Noncommercial License 1.0.0**](LICENSE).

### License, in plain English

**You may use Pixelith freely, at no cost, for any non-commercial purpose.**
That covers, explicitly:

- Personal projects, hobby work, and your own photos and videos
- Learning, teaching, coursework, and academic research
- Experimentation and testing
- Use by charities, schools, universities, public research bodies, public safety
  and health organisations, environmental organisations, and government bodies —
  regardless of how they are funded

You may modify it, build on it, and share it, as long as your use stays
non-commercial and you pass this licence along with it.

**What is not covered:** using Pixelith as part of a business, in commercial
production work, in client deliverables, in a paid product or service, or in
anything with an anticipated commercial application. If you want to do any of
that, open an issue and we will sort out terms. The answer is not automatically
no — it just needs to be an actual arrangement.

### Two things to be aware of

1. **This is not an OSI-approved open-source licence.** PolyForm Noncommercial
   restricts a field of use, which is incompatible with the Open Source
   Definition. GitHub will label this repository accordingly (or as
   "unrecognised"), and Debian, Fedora, Homebrew core, conda-forge and most other
   distribution channels will not package it. That is expected, and it is the
   deliberate trade for keeping the software free for everyone who is not
   selling something.
2. **The licence covers Pixelith's own code only.** Model weights, ONNX Runtime,
   FFmpeg, and the Python libraries all carry their own terms — see
   [`NOTICE.md`](NOTICE.md). Nothing here imposes Pixelith's noncommercial
   restriction on anyone else's work.

The plain-English summary above is a convenience, not a substitute. The
[`LICENSE`](LICENSE) file is what governs.

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
