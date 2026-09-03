# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Guard: the licence signing key must never be committed.

Anyone holding the Ed25519 private key can mint licence keys for themselves.
Only the public key belongs in this repository.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
# Assembled at runtime so this file does not itself contain the literals it
# searches for, which would make the scan below match its own source.
_B = "BEGIN "
MARKERS = tuple(
    _B + kind + "PRIVATE KEY" for kind in ("", "RSA ", "OPENSSH ", "EC ")
)


def repo_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP for part in path.parts):
            continue
        yield path


def test_no_private_key_material_anywhere_in_the_tree():
    offenders = []
    for path in repo_files():
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if any(m in text for m in MARKERS):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"private key material found in: {offenders}"


def test_only_the_public_key_is_embedded():
    src = (ROOT / "pixelith/licensing.py").read_text()
    assert "PUBLIC_KEY_B64" in src
    assert not any(m in src for m in MARKERS)


def test_gitignore_covers_key_files():
    ignored = (ROOT / ".gitignore").read_text()
    for pattern in ("*.pem", "*private-key*"):
        assert pattern in ignored, f"{pattern} is not gitignored"
