# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Guards on the stylesheet's theming.

A colour that only resolves in one theme is the classic way an interface ends
up with light-theme text on a dark background. These catch it at build time
rather than in a screenshot.
"""
import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "web" / "style.css"

# Set from JavaScript on the compare slider, not declared in the stylesheet.
RUNTIME_TOKENS = {"--split"}


def stylesheet() -> str:
    return CSS.read_text()


def declared_tokens(css: str) -> set[str]:
    tokens: set[str] = set()
    for block in re.findall(r"(?::root|\[data-theme[^\]]*\])[^{]*\{([^}]*)\}", css):
        tokens |= set(re.findall(r"(--[a-z0-9-]+)\s*:", block))
    return tokens


def used_tokens(css: str) -> set[str]:
    return set(re.findall(r"var\((--[a-z0-9-]+)", css))


def test_every_token_used_is_actually_declared():
    """An undeclared token silently falls back, and a hardcoded fallback is
    almost always a single-theme colour."""
    css = stylesheet()
    missing = used_tokens(css) - declared_tokens(css) - RUNTIME_TOKENS
    assert not missing, (
        f"undeclared custom properties: {sorted(missing)}. They fall back to a "
        "literal, which will be wrong in one of the two themes."
    )


def test_no_hardcoded_light_colours_hide_behind_a_fallback():
    """var(--x, #fff) renders white even in dark mode if --x does not exist."""
    css = stylesheet()
    offenders = []
    for token, fallback in re.findall(r"var\((--[a-z0-9-]+),\s*([^)]+)\)", css):
        literal = fallback.strip().lower()
        if literal in {"#fff", "#ffffff", "white", "#111", "#000", "black"}:
            if token not in declared_tokens(css):
                offenders.append(f"var({token}, {fallback.strip()})")
    assert not offenders, (
        f"single-theme fallbacks on undeclared tokens: {offenders}"
    )


def test_both_themes_define_the_same_token_set():
    """Redefining only some tokens for dark mode leaves the rest light."""
    css = stylesheet()
    root = re.search(r":root\s*\{([^}]*)\}", css)
    assert root, "no :root block"
    base = set(re.findall(r"(--[a-z0-9-]+)\s*:", root.group(1)))

    for pattern in (r'@media \(prefers-color-scheme: dark\)[^{]*\{\s*:root[^{]*\{([^}]*)\}',
                    r':root\[data-theme="dark"\]\s*\{([^}]*)\}'):
        m = re.search(pattern, css)
        if not m:
            continue
        dark = set(re.findall(r"(--[a-z0-9-]+)\s*:", m.group(1)))
        assert dark <= base, (
            f"dark theme introduces tokens the light theme lacks: {sorted(dark - base)}"
        )
