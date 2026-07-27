#!/usr/bin/env python3
"""Rasterise favicon.svg into every icon the web and PWA installers want.

``favicon.svg`` is the single source of truth for the mark; everything else
here is derived from it, so the icon set can never drift apart. Re-run after
editing the SVG:

    python3 generate-pwa-icons.py

Outputs, all beside this script:

    favicon.ico         16/32/48, for the browser tab and legacy /favicon.ico
    apple-touch-icon.png  180, for "Add to Home Screen" on iOS
    pwa-192.png           192, Android launcher / manifest
    pwa-512.png           512, splash screen and store listing
    pwa-512-maskable.png  512, safe-zone padded for Android adaptive icons

Requires cairosvg. The previous version drew a plain gradient circle with a
hand-rolled PNG encoder, which could not render the actual mark.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "favicon.svg"

# Android adaptive icons crop to a circle inscribed in the middle ~80%, so a
# maskable variant is rendered smaller and centred on the plate colour. Without
# it the launcher shears the tendrils off.
MASKABLE_SCALE = 0.78
PLATE = "#0d0d12"

PNG_TARGETS = [
    ("apple-touch-icon.png", 180, False),
    ("pwa-192.png", 192, False),
    ("pwa-512.png", 512, False),
    ("pwa-512-maskable.png", 512, True),
]
ICO_SIZES = (16, 32, 48)


def _svg_body(markup: str) -> str:
    """Return everything inside the outermost ``<svg>`` element."""
    start = markup.index(">", markup.index("<svg")) + 1
    end = markup.rindex("</svg>")
    return markup[start:end]


def render(size: int, maskable: bool = False) -> bytes:
    """Rasterise the source SVG to a square PNG of ``size`` pixels."""
    import cairosvg

    if not maskable:
        return cairosvg.svg2png(
            url=str(SOURCE), output_width=size, output_height=size
        )

    # Wrap the source in a plate-filled canvas so the mark sits inside the
    # launcher's safe zone instead of being cropped by it.
    #
    # The source is inlined into a <g transform>, not referenced with
    # <image xlink:href>: cairosvg does not resolve external image refs here,
    # and silently produced an empty 1.8 KB plate instead of failing.
    inner = _svg_body(SOURCE.read_text(encoding="utf-8"))
    scale = MASKABLE_SCALE
    offset = (1 - scale) / 2 * 512
    wrapper = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{size}" height="{size}" viewBox="0 0 512 512">'
        f'<rect width="512" height="512" fill="{PLATE}"/>'
        f'<g transform="translate({offset:.2f},{offset:.2f}) scale({scale})">'
        f"{inner}</g></svg>"
    )
    return cairosvg.svg2png(
        bytestring=wrapper.encode("utf-8"),
        output_width=size,
        output_height=size,
    )


def build_ico(pngs: dict[int, bytes]) -> bytes:
    """Pack PNGs into a multi-resolution .ico.

    ICO has embedded-PNG support, so the frames go in verbatim rather than
    being re-encoded as BMP.
    """
    sizes = sorted(pngs)
    header = struct.pack("<HHH", 0, 1, len(sizes))  # reserved, type=icon, count
    offset = len(header) + 16 * len(sizes)

    entries = b""
    body = b""
    for size in sizes:
        data = pngs[size]
        entries += struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0,  # width  (0 means 256)
            size if size < 256 else 0,  # height
            0,  # palette size
            0,  # reserved
            1,  # color planes
            32,  # bits per pixel
            len(data),
            offset,
        )
        body += data
        offset += len(data)
    return header + entries + body


def main() -> int:
    if not SOURCE.exists():
        print(f"missing source: {SOURCE}", file=sys.stderr)
        return 1
    try:
        import cairosvg  # noqa: F401
    except ImportError:
        print(
            "cairosvg is required: pip install --user cairosvg",
            file=sys.stderr,
        )
        return 1

    for name, size, maskable in PNG_TARGETS:
        data = render(size, maskable)
        (HERE / name).write_bytes(data)
        print(f"wrote {name} ({size}x{size}{', maskable' if maskable else ''})")

    ico = build_ico({size: render(size) for size in ICO_SIZES})
    (HERE / "favicon.ico").write_bytes(ico)
    print(f"wrote favicon.ico ({'/'.join(str(s) for s in ICO_SIZES)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
