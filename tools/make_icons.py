"""Erzeugt die PNG-Icons für die PWA aus app/static/icon.svg.

Nur beim Entwickeln nötig (die PNGs liegen im Repo). Braucht Google Chrome.
Aufruf:  .venv/bin/python tools/make_icons.py

- apple-touch-icon.png (180 px): ohne Rundung, iOS rundet selbst ab (Motiv wie im SVG)
- icon-192.png / icon-512.png: wie das SVG (abgerundet, Ecken transparent)
- icon-maskable-512.png: Hintergrund bis zum Rand, Motiv verkleinert, damit
  Android es beliebig zuschneiden kann
Alle in der hellen Fassung (Home-Bildschirm-Icons wechseln nicht mit dem Modus).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "app/static/icon.svg"
OUT = ROOT / "app/static/icons"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def variant(svg: str, *, full_bleed: bool, scale: float = 1.0) -> str:
    svg = re.sub(r"@media \(prefers-color-scheme: dark\) \{.*?\n    \}\n", "", svg, flags=re.S)
    if full_bleed:
        svg = svg.replace('<rect class="bg" width="512" height="512" rx="114"/>', '<rect class="bg" width="512" height="512"/>')
    if scale != 1.0:
        svg = svg.replace(
            '<g id="art" transform="scale(5.12)">',
            f'<g id="art" transform="translate(256 256) scale({scale}) translate(-256 -256) scale(5.12)">',
        )
    return svg


def render(svg: str, size: int, target: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "icon.html"
        page.write_text(
            f'<!doctype html><html><body style="margin:0;background:transparent">'
            f'<div style="width:{size}px;height:{size}px">{svg.replace("<svg ", f"<svg width={size} height={size} ", 1)}</div>'
            f"</body></html>",
            encoding="utf-8",
        )
        subprocess.run(
            [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
             "--default-background-color=00000000", f"--window-size={size},{size}",
             f"--screenshot={target}", page.as_uri()],
            check=True, capture_output=True,
        )
    print("geschrieben:", target.relative_to(ROOT))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    svg = SRC.read_text(encoding="utf-8")
    render(variant(svg, full_bleed=True), 180, OUT / "apple-touch-icon.png")
    render(variant(svg, full_bleed=False), 192, OUT / "icon-192.png")
    render(variant(svg, full_bleed=False), 512, OUT / "icon-512.png")
    render(variant(svg, full_bleed=True, scale=0.78), 512, OUT / "icon-maskable-512.png")


if __name__ == "__main__":
    main()
