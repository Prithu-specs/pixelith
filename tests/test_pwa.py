import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PwaTests(unittest.TestCase):
    def test_manifest_is_installable(self):
        manifest = json.loads((ROOT / "web/manifest.webmanifest").read_text())
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["start_url"], "/")
        self.assertTrue(manifest["icons"])

    def test_shell_files_exist_and_api_is_not_cached(self):
        for name in ("index.html", "style.css", "app.js", "manifest.webmanifest", "icon.svg", "sw.js"):
            self.assertTrue((ROOT / "web" / name).is_file(), name)
        worker = (ROOT / "web/sw.js").read_text()
        self.assertIn("pathname.startsWith('/api/')", worker)

    def test_html_links_manifest_and_mobile_metadata(self):
        html = (ROOT / "web/index.html").read_text()
        self.assertIn('rel="manifest"', html)
        self.assertIn('apple-mobile-web-app-capable', html)
        self.assertIn('id="pairing-dialog"', html)
        self.assertIn('id="photo-input"', html)
        self.assertIn('id="video-input"', html)
        self.assertIn('https://pixelith.in/privacy.html', html)
        self.assertIn('https://pixelith.in/support.html', html)

    def test_mobile_limits_and_pairing_are_enforced_in_client(self):
        app = (ROOT / "web/app.js").read_text()
        self.assertIn("max_queue_files", app)
        self.assertIn("ensurePairing", app)
        self.assertIn("X-Pixelith-Mobile", app)


if __name__ == "__main__":
    unittest.main()
