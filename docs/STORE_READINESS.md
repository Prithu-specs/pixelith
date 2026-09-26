# Mobile store readiness

## Implemented in this branch

- One-time five-minute desktop pairing code and 12-hour authenticated session.
- Rate-limited pairing, one-time code rotation, session revocation on exit.
- `_pixelith._tcp.local` automatic desktop discovery via mDNS/DNS-SD.
- Native browser/photo/video pickers with a least-access explanation.
- Adaptive mobile queue, preview, RAM and storage budgets.
- Cooperative cancellation and deletion of partial output and segment scratch.
- Public privacy and support links: https://pixelith.in/privacy.html and
  https://pixelith.in/support.html.
- Store copy and review instructions under `store/`.

## Required OS declarations

### iOS

- `NSLocalNetworkUsageDescription`: “Pixelith finds and securely connects to
  your Pixelith desktop on the same Wi-Fi. Media stays on your devices.”
- `NSBonjourServices`: `_pixelith._tcp`
- Use `PHPickerViewController`; do not request full-library permission.

### Android

- `INTERNET`, `ACCESS_NETWORK_STATE`, and multicast support for DNS-SD.
- Use Android Photo Picker (`PickVisualMedia`/`PickMultipleVisualMedia`) so the
  user grants access only to selected media.
- Cleartext LAN traffic must be restricted to private addresses; production
  should prefer TLS and certificate/public-key pinning.

## Real-device release gate

The following cannot be truthfully completed in a simulator-only repository.
Record results in `store/REAL_DEVICE_RESULTS.md` before submission:

1. iPhone/iPad with 3–4 GB RAM and current iOS.
2. Oldest iOS version supported by the store build.
3. Android Go/4 GB device and one current flagship.
4. Pairing success, wrong/expired code, desktop restart, Wi-Fi change.
5. 250 MB, 1 GB and device-limit media selection.
6. Background/foreground, cancellation, force-close, low-storage conditions.
7. VoiceOver/TalkBack, large text, reduced motion, dark mode.

