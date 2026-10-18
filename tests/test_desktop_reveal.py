# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
"""Desktop bridge: reveal finished outputs in the platform file manager."""
import sys

import pytest

from pixelith.desktop import DesktopApi


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr("pixelith.desktop.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("pixelith.desktop.subprocess.Popen", lambda cmd: None)
    return DesktopApi()


def _file(tmp_path, name="movie_1920x1080.mp4"):
    p = tmp_path / name
    p.write_bytes(b"x" * 128)
    return p


def test_reveal_accepts_outputs_inside_the_output_dir(tmp_path, api):
    target = _file(tmp_path)
    assert api.reveal_output(str(target)) is True


def test_reveal_refuses_paths_outside_pixelith(tmp_path, api):
    outside = tmp_path.parent / "evil.mp4"
    outside.write_bytes(b"x")
    assert api.reveal_output(str(outside)) is False


def test_reveal_refuses_missing_files(tmp_path, api):
    assert api.reveal_output(str(tmp_path / "never_rendered.mp4")) is False


def test_reveal_picks_platform_opener(tmp_path, api, monkeypatch):
    target = _file(tmp_path)
    sent = []
    monkeypatch.setattr("pixelith.desktop.subprocess.Popen",
                        lambda cmd, **k: sent.append(cmd))
    monkeypatch.setattr(sys, "platform", "Darwin")
    api.reveal_output(str(target))
    assert sent[-1][:2] == ["open", "-R"]

    monkeypatch.setattr(sys, "platform", "win32")
    api.reveal_output(str(target))
    assert sent[-1][0] == "explorer" and "/select," in sent[-1][1]

    monkeypatch.setattr(sys, "platform", "Linux")
    api.reveal_output(str(target))
    assert sent[-1][0] == "xdg-open"