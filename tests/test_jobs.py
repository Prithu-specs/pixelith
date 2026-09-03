"""File classification and job bookkeeping."""
import pytest

from pixelith.jobs import classify


@pytest.mark.parametrize("name", ["a.png", "b.JPG", "c.jpeg", "d.webp", "e.HEIC"])
def test_images(name):
    assert classify(name) == "image"


@pytest.mark.parametrize("name", ["a.mp4", "b.MOV", "c.mkv", "d.webm"])
def test_videos(name):
    assert classify(name) == "video"


@pytest.mark.parametrize("name", ["a.txt", "b.pdf", "noextension", "c.exe"])
def test_rejects_everything_else(name):
    with pytest.raises(ValueError):
        classify(name)
