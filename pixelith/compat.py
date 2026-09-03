# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Platform capability detection and optional format plugins.

Pixelith runs natively on Windows, macOS and Linux. Phones and tablets are
supported as *browser clients* pointed at one of those machines: there is no
ONNX Runtime wheel for Android or iOS, so the inference has to live on a
desktop, a laptop, or a server on the same network.
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
from functools import lru_cache

# ---------------------------------------------------------------- HEIC / HEIF

HEIF_OK = False
try:  # optional: iPhone and modern Android photos are HEIC by default
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:  # noqa: BLE001 - any failure just means no HEIC support
    HEIF_OK = False


def image_suffixes() -> set[str]:
    """Only advertise formats we can actually decode on this machine."""
    base = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
    if HEIF_OK:
        base |= {".heic", ".heif"}
    return base


# ------------------------------------------------------------------- platform


@lru_cache(maxsize=1)
def os_name() -> str:
    return {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(
        platform.system(), platform.system() or "unknown"
    )


@lru_cache(maxsize=1)
def total_ram_bytes() -> int:
    """Best-effort physical memory, on every platform, with no dependencies."""
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")  # Linux
    except (ValueError, AttributeError, OSError):
        pass
    if sys.platform == "darwin":
        try:
            import subprocess

            out = subprocess.run(
                ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True
            )
            return int(out.stdout.strip())
        except (OSError, ValueError):
            pass
    if sys.platform == "win32":
        try:
            import ctypes

            class _Status(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            st = _Status()
            st.dwLength = ctypes.sizeof(_Status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return int(st.ullTotalPhys)
        except Exception:  # noqa: BLE001
            pass
    return 4 * 1024**3  # conservative fallback


def cpu_count() -> int:
    return os.cpu_count() or 4


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def summary() -> dict:
    return {
        "os": os_name(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "cpus": cpu_count(),
        "ram_gb": round(total_ram_bytes() / 1024**3, 1),
        "heic": HEIF_OK,
        "ffmpeg": have_ffmpeg(),
    }


def lan_address() -> str | None:
    """This machine's address on the local network, for phones and tablets.

    Uses a UDP socket to a public address purely to ask the OS which interface
    it would route through; no packet is actually sent.
    """
    import socket

    for probe in ("192.168.1.1", "8.8.8.8"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(0.3)
            s.connect((probe, 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        except OSError:
            continue
        finally:
            s.close()
    return None
