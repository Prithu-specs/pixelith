# Contributing to Pixelith

Thanks for taking the time. Pixelith is a small project on purpose, and the
easiest way to get a change merged is to understand what "small on purpose"
means here.

---

## Licensing of contributions

Pixelith is copyright &copy; 2026 PGA Tech Solutions and is released under the
[Pixelith End User Licence Agreement 1.0](LICENSE). PGA Tech Solutions also sells
commercial licences to organisations that fall outside those terms.

That second part is why this section exists. If contributors kept copyright in
their patches under personal-tier-only terms, nobody — including PGA Tech
Solutions — could grant a commercial licence covering the whole work, and the
project would quietly become unlicensable.

**By opening a pull request you confirm that:**

1. You wrote the contribution yourself, or have the right to submit it.
2. You grant PGA Tech Solutions a perpetual, worldwide, irrevocable,
   royalty-free licence to use, modify, and distribute your contribution,
   **including the right to license it under commercial terms** alongside the
   rest of Pixelith.
3. You retain your own copyright in what you wrote. This is a licence grant, not
   an assignment — you keep the right to use your own work elsewhere.

If you are contributing on behalf of an employer, make sure they are content
with the above before you open the PR.

Contributions that carry an incompatible licence — code copied from a GPL
project, for example — cannot be merged, regardless of quality. If you are
adapting something from elsewhere, say so in the PR and name the source and its
licence.

---

## Before you write code

Please read the [Limitations](README.md#limitations) section of the README
first. Several things that look like bugs are documented, deliberate trade-offs:
video is slow, there is no face restoration, and no model can recover detail
that was never captured.

### What the project is trying to be

- **Local and offline.** No accounts, no API keys, no telemetry, no third-party
  service in the hot path. If a change requires user data to leave the machine,
  it is out of scope regardless of how useful it is.
- **Small.** Two models, one HTTP API, one static web page, two environment
  variables. Every added knob is a permanent maintenance cost and one more thing
  a user has to understand before they can upscale a photo.
- **Honest about performance.** The numbers in the README are measured, not
  projected. Nothing in this project should imply video upscaling is fast.

### Good contributions

Bug fixes, correctness improvements, memory reductions, clearer error messages,
platform support fixes, documentation corrections, and tests. Measured
performance work is especially welcome.

### Contributions that need a conversation first

Open an issue before writing the code if your change adds a model, adds a
dependency, adds a configuration surface, changes the HTTP API contract in
`docs/API.md`, or changes a default. A rejected pull request is a waste of your
evening, and an issue costs you five minutes.

---

## Development setup

```bash
git clone https://github.com/Prithu-specs/pixelith.git
cd pixelith
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install pytest ruff
```

You also need FFmpeg on your `PATH` for anything touching video — see the
[Install](README.md#install) section for per-platform instructions.

Keep your model cache and outputs out of the working tree by pointing the
environment variables somewhere scratch:

```bash
export PIXELITH_HOME=/tmp/pixelith-home
export PIXELITH_OUT=/tmp/pixelith-out
```

---

## Tests

```bash
pytest tests -v
```

### The `needs_model` marker

Real model weights are 4.6 MB and 63.9 MB, and CI must never download them. Any
test that needs actual weights must be marked:

```python
import pytest

@pytest.mark.needs_model
def test_upscales_a_real_image():
    ...
```

CI runs `pytest tests -v -m "not needs_model"`. Run the same selection locally to
see what CI will see:

```bash
pytest tests -v -m "not needs_model"     # what CI runs
pytest tests -v -m needs_model           # the ones CI skips; downloads weights
```

If a test can be written against a small synthetic array and a stubbed session
instead of real weights, write it that way. The tiling, feathering, padding,
provider-selection, preset, and estimator logic are all testable without ever
loading a network, and those are where the interesting bugs live.

### Linting

```bash
ruff check pixelith
```

Ruff runs in CI with `continue-on-error`, so lint findings are advisory and will
not block a merge. Please still fix what your change introduces.

---

## Style

- Target **Python 3.10+**. The CI matrix is 3.10, 3.11, and 3.12; do not use
  syntax newer than 3.10.
- `from __future__ import annotations` at the top of every module, as the
  existing code does.
- Type-annotate public functions. Use dataclasses for structured values.
- Comments should explain *why*, not *what*. The existing comments about
  constant-shape tiles and per-model provider ordering are the model here: each
  one records a non-obvious decision that a future reader would otherwise undo.
- Keep user-facing error messages actionable. `"could not download X from URL:
  reason"` beats `"download failed"`.

---

## Performance claims

**Every performance number in this repository must be measured on real hardware,
and must say which hardware.** The README's figures are from an Apple M5 Pro
(48 GB). If you change something that affects throughput, or you want to add
numbers for another machine, include in your pull request:

- The exact hardware (CPU, GPU, RAM)
- OS and version
- ONNX Runtime package and version, and the active execution provider
- Model, input resolution, and tile size
- How you measured, and how many runs you averaged

Do not extrapolate one machine's numbers to another. Do not round in the
project's favour. If a change makes something slower, say so in the pull request
— a slower-but-correct change is fine; a silently slower one is not.

---

## Adding a model

The registry is a plain dictionary in `pixelith/config.py`. A new entry is a
real commitment, so it needs all of the following:

1. **A permissive, compatible licence** for both the architecture and the
   weights, and an entry added to [`NOTICE.md`](NOTICE.md).
2. **A stable download URL** and the **SHA-256 digest** of the exact file. Never
   add a model without a digest — the verification step in `pixelith/models.py`
   is the only thing standing between a user and a silently swapped weight file.
3. **A measured `cost`** relative to `fast` (which is 1.0), so the time estimator
   stays accurate.
4. **A measured `preferred_providers` order for that network specifically.** Do
   not copy another model's ordering. The whole reason Pixelith is quick on
   Apple silicon is that `fast` is ranked CPU-before-CoreML while `quality` is
   ranked the other way, and that ordering was benchmarked, not assumed.
5. **A `default_tile`** that does not blow up memory at 8K.
6. **A clear answer to "what does this do that `fast` and `quality` don't?"**
   A third model that is between the two on both axes is not worth the choice it
   forces on users.

---

## Pull requests

- Branch from `main`, one logical change per pull request.
- Say what you changed, why, and how you verified it. Include before/after
  images for anything that affects output quality.
- Update `docs/API.md` in the same pull request if you change the HTTP contract,
  and the README if you change behaviour a user would notice.
- Make sure `pytest tests -m "not needs_model"` passes on Python 3.10.

---

## Reporting bugs and requesting features

Use the [issue templates](.github/ISSUE_TEMPLATE). For bugs, the environment
block matters more than you would expect — the active execution provider, the
ONNX Runtime package, and the FFmpeg build explain a large share of reports.
`GET /api/health` gives you most of it in one go.

Please do not file "video upscaling is slow" as a bug. It is documented, it is
measured, and it is inherent to running a neural network on every frame. A
report that a specific configuration is *slower than the published figures* is a
genuine bug and very welcome.

---

## Security

If you find something with security impact — particularly anything touching
model download and checksum verification, or path handling in the upload and
job endpoints — please report it privately through GitHub's security advisory
form rather than opening a public issue.

---

## Licensing of contributions

Pixelith is licensed under the [Pixelith End User Licence Agreement 1.0](LICENSE),
which is **not** an OSI-approved open-source licence. Please make sure you are
comfortable with that before contributing.

By submitting a pull request you agree that your contribution is licensed under
the same terms as the project, and you confirm you have the right to submit it —
that it is your own work, or that you have permission, and that your employer
has no claim on it that would conflict.

One thing worth stating plainly rather than burying: because the project offers
commercial licences separately for use the free tier does not permit, the
maintainers may include contributed code under those commercial terms. If that
is not acceptable to you, please say so on the issue before you write the code
rather than after.
