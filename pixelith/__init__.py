# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 PGA Tech Solutions. Free for noncommercial use;
# commercial use requires a separate licence. See LICENSE.
"""Pixelith - AI image and video upscaling, up to 8K."""

__version__ = "0.1.0"

# Licensing identity. Surfaced by the CLI, the HTTP API and the web UI so that
# anyone running Pixelith is on notice about the terms, not just anyone who
# happens to open the LICENSE file.
LICENSE_ID = "PolyForm-Noncommercial-1.0.0"
LICENSE_NAME = "PolyForm Noncommercial License 1.0.0"
LICENSE_URL = "https://polyformproject.org/licenses/noncommercial/1.0.0"
LICENSOR = "PGA Tech Solutions"
COPYRIGHT = "Copyright (c) 2026 PGA Tech Solutions"
COMMERCIAL_CONTACT = "licensing@pgatech.solutions"
REQUIRED_NOTICE = (
    "Required Notice: Copyright (c) 2026 PGA Tech Solutions "
    "(https://github.com/Prithu-specs/pixelith)"
)


def license_info() -> dict:
    """Machine-readable licence terms, for the API and any downstream tool."""
    return {
        "spdx": LICENSE_ID,
        "name": LICENSE_NAME,
        "url": LICENSE_URL,
        "licensor": LICENSOR,
        "copyright": COPYRIGHT,
        "noncommercial": True,
        "commercial_contact": COMMERCIAL_CONTACT,
        "required_notice": REQUIRED_NOTICE,
    }
