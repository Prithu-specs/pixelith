# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
"""Long-job triage: the estimate payload must carry the Quick-resize switch."""
from pixelith.server import EstimateRequest, estimate


def test_long_ai_video_flags_quick_resize_alternative():
    common = dict(kind="video", width=856, height=482, frames=140400, fps=30,
                  preset="1080p", model="fast", source_bytes=394_000_000)
    ai = estimate(EstimateRequest(**common, video_processing="ai"))
    assert ai["long_job"] is True
    assert "Quick resize" in ai["warning"]


def test_short_or_native_jobs_do_not_flag():
    short = estimate(EstimateRequest(kind="video", width=640, height=360, frames=150,
                     fps=30, preset="1080p", model="fast", source_bytes=10_000_000))
    assert short["long_job"] is False

    native = estimate(EstimateRequest(kind="video", width=856, height=482, frames=140400,
                      fps=30, preset="1080p", model="fast",
                      video_processing="native", source_bytes=394_000_000))
    assert native["long_job"] is False
    assert native["seconds"] is None