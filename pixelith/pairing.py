# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. See LICENSE.
"""Temporary-code pairing and authenticated LAN sessions.

There are deliberately no Pixelith accounts.  A short-lived code proves that
the phone is physically near the desktop; successful pairing creates a random
session secret that is kept only in the phone's session storage and in memory
on the desktop.  Restarting Pixelith revokes every session.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque


class PairingError(ValueError):
    pass


class PairingManager:
    CODE_TTL = 5 * 60
    SESSION_TTL = 12 * 60 * 60
    MAX_ATTEMPTS = 5
    ATTEMPT_WINDOW = 60

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._enabled = False
        self._code = ""
        self._code_expires = 0.0
        self._sessions: dict[str, float] = {}
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> str:
        with self._lock:
            self._enabled = True
            return self.rotate_code()

    def disable(self) -> None:
        with self._lock:
            self._enabled = False
            self._code = ""
            self._sessions.clear()
            self._attempts.clear()

    def rotate_code(self) -> str:
        with self._lock:
            self._code = f"{secrets.randbelow(1_000_000):06d}"
            self._code_expires = time.time() + self.CODE_TTL
            return self._code

    def current_code(self) -> tuple[str, int]:
        with self._lock:
            if not self._code or time.time() >= self._code_expires:
                self.rotate_code()
            return self._code, max(0, int(self._code_expires - time.time()))

    def status(self) -> dict:
        with self._lock:
            self._prune()
            return {
                "pairing_required": self._enabled,
                "code_expires_in": max(0, int(self._code_expires - time.time())),
                "active_sessions": len(self._sessions),
            }

    def pair(self, code: str, client: str) -> tuple[str, int]:
        now = time.time()
        with self._lock:
            if not self._enabled:
                raise PairingError("LAN pairing is not enabled")
            attempts = self._attempts[client]
            while attempts and attempts[0] < now - self.ATTEMPT_WINDOW:
                attempts.popleft()
            if len(attempts) >= self.MAX_ATTEMPTS:
                raise PairingError("too many attempts; wait one minute")
            attempts.append(now)
            valid = now < self._code_expires and hmac.compare_digest(
                str(code).strip(), self._code
            )
            if not valid:
                raise PairingError("the pairing code is invalid or expired")

            token = secrets.token_urlsafe(32)
            digest = self._digest(token)
            self._sessions[digest] = now + self.SESSION_TTL
            # One-time means one successful use.  The desktop UI can display
            # the newly generated code when another device needs pairing.
            self.rotate_code()
            return token, self.SESSION_TTL

    def authenticate(self, token: str | None) -> bool:
        if not self._enabled:
            return True
        if not token:
            return False
        with self._lock:
            self._prune()
            expiry = self._sessions.get(self._digest(token))
            return bool(expiry and expiry > time.time())

    def revoke(self, token: str | None) -> None:
        if token:
            with self._lock:
                self._sessions.pop(self._digest(token), None)

    def _digest(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _prune(self) -> None:
        now = time.time()
        self._sessions = {key: expiry for key, expiry in self._sessions.items()
                          if expiry > now}


PAIRING = PairingManager()
