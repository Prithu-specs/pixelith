# ADR-003: Secure local mobile companion

**Status:** Accepted  
**Date:** 2026-09-26  
**Decider:** PGA Tech Solutions

## Context

Pixelith has no cloud account and performs inference on a desktop. Android and
iOS clients therefore need to find and control a desktop on the same LAN
without turning an open HTTP port into a remote-control surface.

## Decision

- LAN mode is opt-in. Loopback desktop use remains frictionless.
- The desktop advertises `_pixelith._tcp.local` with DNS-SD/mDNS.
- A six-digit code is shown only on the desktop, expires after five minutes,
  and rotates after one successful use.
- A successful pairing creates a 256-bit random session token. Only its SHA-256
  digest is retained by the desktop; sessions expire after 12 hours and all are
  revoked when Pixelith exits.
- Protected LAN API routes require the session in an HttpOnly, SameSite=Strict
  cookie. Pairing guesses are rate limited.
- Host/origin/fetch-metadata checks remain in force, providing a separate DNS
  rebinding and cross-site-request boundary.
- Store builds should use TLS or native transport security/pinning in addition
  to this authenticated session. HTTP is permitted only on the private local
  network for the browser companion.

## Options considered

| Option | Assessment |
|---|---|
| Open LAN server | Rejected: convenient but unauthenticated |
| Permanent Pixelith account | Rejected: contradicts local-first promise |
| Temporary code + session | Accepted: low friction and no identity service |
| Self-signed TLS only | Rejected as sole control: browser trust UX is poor |

## Consequences

- No account, email address, password database, telemetry, or cloud service is
  introduced.
- Pairing must be repeated after the desktop restarts or after 12 hours.
- Native store clients must declare local-network/Bonjour access and explain it
  before the operating-system prompt.

