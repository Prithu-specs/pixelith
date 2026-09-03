# Third-party notices

Pixelith is copyright **&copy; 2026 PGA Tech Solutions** and its own source code
is licensed under the **PolyForm Noncommercial License 1.0.0**
(see [`LICENSE`](LICENSE)). That licence covers only the code in this
repository. Commercial licences are available from PGA Tech Solutions at
licensing@pgatech.solutions.

It does **not** cover the third-party software Pixelith depends on, and it does
**not** cover the neural-network weights Pixelith downloads at runtime. Those
carry their own licences, reproduced or referenced below. Where a third-party
licence is more permissive than PolyForm Noncommercial, the third-party terms
govern that component — Pixelith's noncommercial restriction is not imposed on
anyone else's work.

If you redistribute Pixelith, ship this file alongside `LICENSE`.

---

## 1. Model architecture and original weights

### Real-ESRGAN

- **Authors:** Xintao Wang, Liangbin Xie, Chao Dong, Ying Shan
  (Tencent ARC Lab / ARC Lab, Tencent PCG)
- **Project:** https://github.com/xinntao/Real-ESRGAN
- **Paper:** *Real-ESRGAN: Training Real-World Blind Super-Resolution with Pure
  Synthetic Data*, ICCV Workshops 2021
- **Licence:** BSD 3-Clause "New" or "Revised" License

Both networks Pixelith ships in its registry originate from this project:

| Pixelith key | Upstream network | Architecture |
|---|---|---|
| `fast` | `realesr-general-x4v3` | Compact SRVGG |
| `quality` | `RealESRGAN_x4plus` | 23-block RRDBNet |

> Copyright (c) 2021, Xintao Wang
> All rights reserved.
>
> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions are met:
>
> 1. Redistributions of source code must retain the above copyright notice, this
>    list of conditions and the following disclaimer.
>
> 2. Redistributions in binary form must reproduce the above copyright notice,
>    this list of conditions and the following disclaimer in the documentation
>    and/or other materials provided with the distribution.
>
> 3. Neither the name of the copyright holder nor the names of its contributors
>    may be used to endorse or promote products derived from this software
>    without specific prior written permission.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
> AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
> IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
> DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
> FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
> DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
> SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
> CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
> OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
> OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

Some Real-ESRGAN training code derives from BasicSR, ESRGAN, and related
projects by the same authors; consult the upstream repository for the full
provenance of each component.

---

## 2. ONNX weight conversions

Pixelith does not train or convert models itself. It downloads pre-converted
ONNX exports of the Real-ESRGAN networks from Hugging Face on first use, then
verifies each file against a SHA-256 digest pinned in `pixelith/config.py`.

| Pixelith key | Hugging Face repository | File | Size |
|---|---|---|---|
| `fast` | [`CoderViking/realesr-general-x4v3-onnx`](https://huggingface.co/CoderViking/realesr-general-x4v3-onnx) | `realesr-general-x4v3.onnx` | 4.6 MB |
| `quality` | [`SceneWorks/real-esrgan-onnx`](https://huggingface.co/SceneWorks/real-esrgan-onnx) | `real_esrgan_x4.onnx` | 63.9 MB |

These are third-party redistributions. Thanks to their maintainers for hosting
them. The underlying weights remain subject to the Real-ESRGAN licence above;
check each Hugging Face repository's model card for any additional terms the
converter has attached.

Pixelith exercises no control over these repositories. The pinned SHA-256
digests are the mechanism that keeps a silently changed file from being loaded.

---

## 3. Runtime and library dependencies

| Component | Licence | Copyright / project |
|---|---|---|
| [ONNX Runtime](https://onnxruntime.ai) | MIT | Copyright (c) Microsoft Corporation |
| [FFmpeg](https://ffmpeg.org) | LGPL-2.1-or-later, **or** GPL-2.0-or-later depending on build | The FFmpeg developers |
| [FastAPI](https://fastapi.tiangolo.com) | MIT | Copyright (c) 2018 Sebastián Ramírez |
| [Pillow](https://python-pillow.org) | MIT-CMU (HPND) | Copyright (c) 2010 Jeffrey A. Clark and contributors; based on PIL, copyright (c) 1997-2011 Secret Labs AB and 1995-2011 Fredrik Lundh |
| [NumPy](https://numpy.org) | BSD 3-Clause | Copyright (c) 2005-present, NumPy Developers |

### A note on FFmpeg

FFmpeg is invoked as an **external program**, not linked into Pixelith. Pixelith
neither bundles nor redistributes an FFmpeg binary; you install it yourself
through your platform's package manager.

FFmpeg's effective licence depends on how the build you install was configured.
A default build is LGPL-2.1-or-later. Builds configured with `--enable-gpl` (as
most distribution and Homebrew packages are, because that is what pulls in
x264 and x265) are GPL-2.0-or-later, and some third-party builds are
GPL-3.0-or-later. Builds with `--enable-nonfree` may not be redistributed at
all. If you plan to redistribute anything that includes an FFmpeg binary, check
`ffmpeg -version` for the configure flags of that specific build.

### Other direct and transitive dependencies

`requirements.txt` lists two further direct dependencies:

| Component | Licence | Copyright / project |
|---|---|---|
| [Uvicorn](https://www.uvicorn.org) | BSD 3-Clause | Copyright (c) 2017-present, Encode OSS Ltd. |
| [python-multipart](https://github.com/Kludex/python-multipart) | Apache-2.0 | Copyright (c) 2012-2013, Andrew Dunham |

Pixelith requests `uvicorn[standard]`, which additionally pulls in optional
components (`uvloop`, `httptools`, `websockets`, `watchfiles`, `python-dotenv`,
`PyYAML`), each under its own terms.

Beyond those, installing `requirements.txt` resolves further transitive
dependencies (Starlette, Pydantic, protobuf, coloredlogs, sympy, and others),
each under its own licence — predominantly MIT, BSD, and Apache-2.0. Run
`pip-licenses` in your virtual environment for the exact set resolved on your
machine.

---

## 4. Corrections

If you maintain any of the above and this file misattributes your work, states
your licence incorrectly, or you would like an attribution changed or removed,
please open an issue. Attribution problems are treated as bugs and fixed
promptly.
