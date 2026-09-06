# ADR-001: Adaptive CPU, GPU and NPU inference

**Status:** Accepted

**Date:** 2026-09-06

**Decider:** PGA Tech Solutions

## Context

Pixelith must use the best processors available without making a GPU mandatory.
Execution-provider names are not one-to-one with physical devices: Core ML,
Android NNAPI and OpenVINO AUTO can already distribute a model over CPU, GPU
and NPU. Running another CPU session beside them can reduce performance through
contention. Discrete CUDA, DirectML, ROCm/MIGraphX and QNN HTP devices can leave
CPU capacity available for independent image tiles.

## Decision

Use two levels of heterogeneous scheduling:

1. Prefer platform runtimes that manage multiple compute units themselves:
   Core ML with `MLComputeUnits=ALL`, OpenVINO `AUTO`, and Android NNAPI.
2. For independent accelerators, create a CPU session when at least 8 GB RAM is
   available. Workers pull from a shared tile queue, so throughput determines
   the work split rather than fixed round-robin assignment.

Provider options are optional. Pixelith retries with the provider's defaults so
an older ONNX Runtime wheel does not turn an acceleration preference into a
startup failure. CPU remains the universal fallback.

## Platform mapping

| Platform | Preferred path | Fallback |
|---|---|---|
| Windows x64 | CUDA, DirectML/WinML, OpenVINO AUTO | CPU |
| Windows ARM64 | QNN HTP or WinML | CPU |
| Linux | CUDA, MIGraphX/ROCm, OpenVINO AUTO | CPU/XNNPACK |
| Android | QNN HTP or NNAPI through a native ORT Mobile client | XNNPACK/CPU |
| iOS/iPadOS | Core ML with all compute units through a native client | XNNPACK/CPU |

The Python web server does not execute locally on ordinary Android or iOS
devices. Native mobile clients require ORT Mobile packaging and reuse the same
model, tiling contract and output tests. iPhone is an iOS target, not a general
Linux target.

## Consequences

- Machines without accelerators continue to work unchanged.
- Faster independent processors naturally receive more tiles.
- Apple/Android/Intel platform schedulers retain control of shared silicon.
- Additional sessions use memory, so independent cooperation is disabled below
  8 GB RAM.
- Native Android and iOS applications remain separate deliverables; browser
  control of a desktop server does not use the phone's NPU.

## Acceptance criteria

- Output from single-device and heterogeneous modes is visually and
  numerically equivalent within the existing tiled-inference tolerance.
- Heterogeneous mode is retained only when end-to-end throughput improves by at
  least 10% on the target hardware.
- Peak memory remains below 25% of installed RAM for working buffers.
- Every mobile model passes CPU, accelerator and fallback tests on real devices.
