# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Pixelith - AI image and video upscaling, up to 8K."""

__version__ = "0.2.0"

# Licensing identity. Surfaced by the CLI, the HTTP API and the web UI so that
# anyone running Pixelith is on notice about the terms, not just anyone who
# happens to open the LICENSE file.
LICENSE_ID = "LicenseRef-Pixelith-EULA-1.0"
LICENSE_NAME = "Pixelith End User Licence Agreement 1.0"
LICENSE_URL = "https://github.com/Prithu-specs/pixelith/blob/main/LICENSE"
LICENSOR = "PGA Tech Solutions"
COPYRIGHT = "Copyright (c) 2026 PGA Tech Solutions"
COMMERCIAL_CONTACT = "licensing@pgatech.solutions"
# Shown on Indian tax invoices and the pricing page. Set the real number here.
GSTIN = "09AIAPG7383C1ZE"
GST_STATE = "Uttar Pradesh"
GST_RATE = 0.18
GST_SAC = "997331"  # licensing services for the right to use software
REQUIRED_NOTICE = (
    "Required Notice: Copyright (c) 2026 PGA Tech Solutions "
    "(https://github.com/Prithu-specs/pixelith)"
)

# Versions 0.1.x shipped under PolyForm Noncommercial 1.0.0. Rights granted for
# those versions stand; these terms apply from 0.2.0 onward.
PRIOR_LICENSE = "PolyForm-Noncommercial-1.0.0 (versions 0.1.x)"

# The free allowance. Nothing in the Software measures or enforces these - see
# clause 7 of the LICENCE. They are stated so users know where the line is.
FREE_VIDEO_BYTES = 1_073_741_824       # 1 GB of video input
FREE_IMAGE_COUNT = 100                 # 100 still images

# Pricing is regional. India is the home market and is priced for it; the rest
# of the world pays the international price. Indian payments settle through an
# Indian gateway at about 2.4% all-in, while international sales go through a
# merchant of record that handles VAT in the buyer's country and consolidates
# everything into one inbound remittance - which is what keeps FEMA and e-FIRC
# paperwork manageable from India.
CURRENCIES = {
    "INR": {
        "symbol": "\u20b9",
        "region": "India",
        "personal": 513,
        "commercial": 8228,
        # Quoted exclusive of GST, which is added at checkout and shown on the
        # tax invoice. The all-in figure is published too, so nobody is
        # surprised by the total at the payment step.
        "tax_included": False,
        "tax_label": "+ 18% GST",
        "note": "Pay by UPI, card or net banking. Tax invoice issued.",
    },
    "USD": {
        "symbol": "$",
        "region": "Rest of the world",
        "personal": 10,
        "commercial": 200,
        "tax_included": False,
        "tax_label": "plus local tax at checkout",
        "note": "An export of service from India, zero-rated under LUT.",
    },
}
DEFAULT_CURRENCY = "INR"

# Checkout links. Fill these in once the accounts exist; until then the paywall
# falls back to the email route. Override without editing code by setting
# PIXELITH_PAY_INR_PERSONAL and friends.
import os as _os


def _pay_url(currency: str, tier: str) -> str:
    return _os.environ.get(f"PIXELITH_PAY_{currency}_{tier.upper()}", "")


def pricing() -> dict:
    """Regional prices plus whatever checkout links are configured."""
    out = {}
    for code, data in CURRENCIES.items():
        out[code] = {
            **{k: v for k, v in data.items()},
            "personal_url": _pay_url(code, "personal"),
            "commercial_url": _pay_url(code, "commercial"),
            "personal_total": (
                round(data["personal"] * (1 + GST_RATE))
                if code == "INR" else data["personal"]
            ),
            "commercial_total": (
                round(data["commercial"] * (1 + GST_RATE))
                if code == "INR" else data["commercial"]
            ),
        }
    return out


TIERS = (
    {
        "key": "free",
        "name": "Free",
        "use": "personal",
        "images": FREE_IMAGE_COUNT,
        "video_bytes": FREE_VIDEO_BYTES,
        "summary": "Personal use, up to 100 images and 1 GB of video input.",
    },
    {
        "key": "personal",
        "name": "Personal",
        "use": "personal",
        "images": None,
        "video_bytes": None,
        "summary": "One person, all their devices. Unlimited images and video, for life.",
    },
    {
        "key": "commercial",
        "name": "Commercial",
        "use": "commercial",
        "images": None,
        "video_bytes": None,
        "summary": "One company. Any commercial use, unlimited, for life.",
    },
)


def tier_price(tier: str, currency: str = DEFAULT_CURRENCY) -> str:
    cur = CURRENCIES.get(currency, CURRENCIES[DEFAULT_CURRENCY])
    if tier == "free":
        return "free"
    return f"{cur['symbol']}{cur[tier]:,}"


def tier_total(tier: str, currency: str = DEFAULT_CURRENCY) -> str:
    """What the buyer actually pays, tax included."""
    cur = CURRENCIES.get(currency, CURRENCIES[DEFAULT_CURRENCY])
    if tier == "free":
        return "free"
    amount = cur[tier]
    if not cur.get("tax_included") and currency == "INR":
        amount = round(amount * (1 + GST_RATE))
    return f"{cur['symbol']}{amount:,}"


def license_info() -> dict:
    """Machine-readable licence terms, for the API and any downstream tool."""
    return {
        "spdx": LICENSE_ID,
        "name": LICENSE_NAME,
        "url": LICENSE_URL,
        "licensor": LICENSOR,
        "copyright": COPYRIGHT,
        "commercial_contact": COMMERCIAL_CONTACT,
        "required_notice": REQUIRED_NOTICE,
        "prior_license": PRIOR_LICENSE,
        "free_allowance": {
            "images": FREE_IMAGE_COUNT,
            "video_bytes": FREE_VIDEO_BYTES,
        },
        "tiers": [dict(t) for t in TIERS],
        "pricing": pricing(),
        "default_currency": DEFAULT_CURRENCY,
        # The allowance is measured and enforced locally; free output is
        # marked. Nothing is transmitted. See clause 7 of the LICENCE.
        "enforced_in_software": True,
        "telemetry": False,
        "free_output_watermarked": True,
    }
