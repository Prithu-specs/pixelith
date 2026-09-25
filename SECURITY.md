# Pixelith security policy

Pixelith processes media locally and does not require an account, cloud upload,
API key, or subscription. Local processing reduces exposure, but no software can
be guaranteed immune from every attack. PGA Tech Solutions treats security as a
continuous engineering process.

## Supported version

Security fixes are provided for the latest beta release. At present that is
Pixelith 1.00 Beta 1 (`v1.00-beta.1`).

## Safe deployment

- The server listens on loopback by default. Keep this default for normal use.
- LAN mode is unauthenticated and is intended only for a private, trusted home
  or office network. Never expose port 8420 directly to the public internet.
- Download Pixelith only from the official GitHub repository and verify release
  checksums where provided.
- Keep Pixelith, Python, FFmpeg, and the operating system updated.

## Built-in protections

- Host and same-origin validation blocks DNS-rebinding and cross-site browser
  requests against the local API.
- Restrictive browser security headers prevent framing and limit executable or
  remotely loaded page content.
- Upload, source-image, and output-canvas limits reduce memory and disk
  exhaustion risk.
- Model downloads use HTTPS and pinned SHA-256 checksums.
- FFmpeg and helper commands use argument arrays rather than a command shell.
- CI audits Python dependencies and rejects high-severity static findings.

## Reporting a vulnerability

Please do not disclose an unpatched exploit in a public issue. Use GitHub's
private vulnerability reporting for `Prithu-specs/pixelith` when available, or
email `licensing@pgatech.solutions` with `SECURITY` in the subject. Include the
affected version, operating system, reproduction steps, and impact. Do not send
private media or credentials.

We will acknowledge a reproducible report and coordinate a fix and disclosure.
