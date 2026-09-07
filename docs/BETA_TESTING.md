# Pixelith beta testing guide

Pixelith needs measured reports from ordinary computers, especially Windows,
older CPUs, Linux, and browser control from Android and iPhone. A useful report
takes about two minutes and does not require sending us your media.

## Install and run

Download the latest tracked beta package from the
[release page](https://github.com/Prithu-specs/pixelith/releases/tag/v0.40b4),
extract it, and follow the README quick start. Start with one image or a
5–10-second video rather than a full-length clip.

## Suggested trial matrix

Pick one or two rows. Every test is useful; nobody is expected to run all of
them.

| Trial | Source | Target | What it checks |
|---|---|---|---|
| Quick image | 480p–1080p JPEG | 2K or 4K, Fast | Installation and first result |
| Quality image | Same image | 2K or 4K, Quality | Detail versus processing time |
| SD widescreen | 640×480 image/video | 720p, 16:9 Fit | Aspect conversion and bars |
| Short video | 5–10 seconds | 1080p, Fast | Progress, audio and compression |
| Frame rate | 24 or 30 FPS clip | 60 FPS | Duration and audio synchronization |
| Mobile control | Any small file | Any target | Android/iPhone browser workflow |

Do not start with 8K video. Preview one frame first and read the estimate.

## Record these results

- Pixelith version and operating system
- CPU, GPU/NPU if present, and approximate RAM
- Execution provider shown by Pixelith
- Media type, source resolution and video duration
- Model, target resolution, aspect/framing and FPS
- Estimated time and actual time
- Source size, output size and displayed size ratio
- A 1–5 output-quality rating
- Whether the job completed, failed or was cancelled

Submit them with the
[beta trial form](https://github.com/Prithu-specs/pixelith/issues/new?template=beta_trial.yml).
Reports are public, so never attach private media, licence keys, personal data,
or local file paths.

## How trial data is used

PGA Tech Solutions can group public reports by platform, hardware class,
execution provider, settings and outcome. This reveals where estimates are
wrong, which devices fail, and which workflows create good results. Pixelith
does not silently transmit analytics; only information a tester deliberately
submits through GitHub is collected.
