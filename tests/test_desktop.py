import json

from pixelith import desktop


def test_free_port_asks_os_for_available_port(monkeypatch):
    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def bind(self, address):
            assert address == ("127.0.0.1", 0)

        def getsockname(self):
            return ("127.0.0.1", 45678)

    monkeypatch.setattr(desktop.socket, "socket", lambda *args: FakeSocket())
    assert desktop.free_port(0) == 45678


def test_diagnostic_is_json_serializable_and_versioned():
    report = desktop.diagnostic()
    assert report["app"] == "Pixelith"
    assert report["version"]
    assert report["os"]
    json.dumps(report)
