# Pixelith platform beta

## Desktop applications

Download the package for your system from the latest GitHub prerelease, extract
it, and open **Pixelith**. No Python installation, account, API key or password
is required. The compact AI model downloads and verifies itself on first use.

| Package | Compatibility | Acceleration |
|---|---|---|
| Windows x64 | Windows 10/11 | CPU; DirectML/CUDA when included by a compatible runtime |
| macOS Apple Silicon | macOS 12+ | CPU, GPU and Neural Engine through Core ML |
| macOS Intel | macOS 12+ | CPU and compatible Core ML devices |
| Linux x64 | Modern glibc distributions | CPU; CUDA/ROCm/OpenVINO with a compatible runtime |
| Linux ARM64 | Modern glibc distributions, including capable SBCs | CPU |

These first beta packages are not code-signed. Windows SmartScreen or macOS
Gatekeeper may therefore display an unknown-publisher warning. Published hashes
and GitHub Actions provenance should be verified before running them.

FFmpeg is still required for video. Images work without it. Install FFmpeg with
`winget install Gyan.FFmpeg`, `brew install ffmpeg`, or your Linux package
manager, then restart Pixelith.

## Android and iOS companion application

The mobile beta is an installable companion for the desktop engine:

1. Open Pixelith on a computer with LAN access enabled (`pixelith serve --lan`
   when using the command-line build).
2. Put the phone and computer on the same trusted Wi-Fi.
3. Open the printed local address in Chrome on Android or Safari on iPhone/iPad.
4. Choose **Install app** / **Add to Home Screen** from the browser menu where
   available.

The phone selects and uploads a file directly to your computer over local Wi-Fi.
The computer performs the upscale. Nothing is sent to PGA Tech Solutions and the
media is not used for AI training.

The current mobile beta does **not** run inference on the phone's NPU. Native
on-device Android/iOS inference is tracked separately because it needs ORT
Mobile, model and memory validation, heat/battery testing, and signed store
builds. iPhones run iOS; they are not Linux devices.

Use LAN mode only on a trusted network. Pixelith intentionally has no sign-in or
password, so another person on the same network who knows the address could open
the interface.
