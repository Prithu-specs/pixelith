# Native companion integration

These small, dependency-free platform modules are the security-sensitive edges
for the Android and iOS companion shells:

- discover `_pixelith._tcp.local` desktops with the OS DNS-SD API;
- use the OS media picker, granting access only to selected items;
- navigate the companion WebView to the resolved desktop and complete the
  six-digit pairing flow served by Pixelith.

They are source components, not signed store binaries. Bundle identifiers,
signing teams, provisioning profiles, minimum OS versions, and final WebView
transport pinning must be supplied in the native Xcode/Gradle projects before
submission. See `docs/STORE_READINESS.md` for declarations and release gates.
