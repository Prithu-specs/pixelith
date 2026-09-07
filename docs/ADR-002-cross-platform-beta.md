# ADR-002: Cross-platform beta distribution

**Status:** Accepted  
**Date:** 2026-09-07  
**Decider:** PGA Tech Solutions

## Context

Pixelith needs beta applications for Windows, macOS, Linux, Android and iOS.
The Python/ONNX engine is production-shaped on desktop operating systems but is
not a native Android or iOS runtime. Calling the existing mobile browser client
"on-device AI" would promise something the software does not do.

## Decision

Ship two honest application classes:

1. **Desktop engine apps** for Windows, macOS and Linux. PyInstaller bundles
   Python, the local API, web UI and CPU-capable ONNX Runtime. A pywebview native
   window owns the local server lifecycle. GPU/NPU providers are used whenever
   the packaged runtime and device expose them; CPU remains universal.
2. **Installable mobile companion app** for Android and iOS. The PWA runs the
   responsive Pixelith interface and controls a desktop engine over trusted
   local Wi-Fi. It never uploads media to PGA Tech Solutions or a cloud AI.

Native phone-side inference remains a separate ORT Mobile project. It requires
mobile model packaging, thermal/memory limits, accelerator fallback testing,
Android signing and Apple TestFlight signing before it can be described as a
Pixelith mobile engine.

## Consequences

- Beta downloads can be produced automatically for Windows x64, Linux x64 and
  ARM64, macOS Intel and Apple Silicon.
- Android and iOS gain an app-like home-screen experience immediately, without
  an account, password or cloud media service.
- Mobile users still need a Windows, macOS or Linux computer on the same trusted
  network to perform the upscale.
- macOS builds are unsigned until PGA Tech Solutions supplies an Apple Developer
  signing identity; Windows builds are unsigned until a code-signing certificate
  is configured.
- App Store, TestFlight and Play Store distribution are explicitly out of this
  beta until signing identities and store accounts exist.

## Acceptance criteria

- Every desktop package executes `--diagnose` on its native runner.
- The full no-model test suite passes before artifacts are uploaded.
- The mobile manifest, icon, service worker and no-API-cache policy are tested.
- A tagged build publishes all successful packages as a GitHub prerelease.
