# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. See LICENSE.
"""Advertise a LAN-enabled Pixelith desktop with DNS-SD/mDNS."""
from __future__ import annotations

import socket
from dataclasses import dataclass


@dataclass
class DiscoveryService:
    port: int
    version: str
    _zeroconf: object | None = None
    _info: object | None = None

    def start(self) -> bool:
        try:
            from zeroconf import ServiceInfo, Zeroconf
            from .compat import lan_address

            address = lan_address()
            if not address:
                return False
            hostname = socket.gethostname().split(".")[0] or "Pixelith"
            service_type = "_pixelith._tcp.local."
            self._info = ServiceInfo(
                service_type,
                f"Pixelith on {hostname}.{service_type}",
                addresses=[socket.inet_aton(address)],
                port=self.port,
                properties={
                    b"version": self.version.encode(),
                    b"pairing": b"required",
                    b"path": b"/",
                },
                server=f"{hostname}.local.",
            )
            self._zeroconf = Zeroconf()
            self._zeroconf.register_service(self._info)
            return True
        except Exception:
            self.stop()
            return False

    def stop(self) -> None:
        if self._zeroconf and self._info:
            try:
                self._zeroconf.unregister_service(self._info)
            except Exception:
                pass
        if self._zeroconf:
            try:
                self._zeroconf.close()
            except Exception:
                pass
        self._zeroconf = None
        self._info = None
