"""
Generates the link buttons used in README.md as small SVG files in assets/buttons/.

Each button is written twice, once for GitHub's light theme and once for dark,
and the README picks the right one with a <picture> element. The look copies
GitHub's own buttons (rounded, 1px border, system font) so they feel native.

Run from the repo root:  python scripts/make_buttons.py
Edit BUTTONS to add, remove or relabel a button, then rerun.
"""
from __future__ import annotations

import os

OUT_DIR = "assets/buttons"
HEIGHT = 34
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"

# 16px Octicons (MIT, github.com/primer/octicons) and the LinkedIn mark.
ICONS = {
    "file": ("0 0 16 16", "M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16h-9.5A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688l-.011-.013-2.914-2.914-.013-.011Z"),
    "globe": ("0 0 16 16", "M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM5.78 8.75a9.64 9.64 0 0 0 1.363 4.177c.255.426.542.832.857 1.215.245-.296.551-.705.857-1.215A9.64 9.64 0 0 0 10.22 8.75Zm4.44-1.5a9.64 9.64 0 0 0-1.363-4.177c-.307-.51-.612-.919-.857-1.215a9.927 9.927 0 0 0-.857 1.215A9.64 9.64 0 0 0 5.78 7.25Zm-5.944 1.5H1.543a6.507 6.507 0 0 0 4.666 5.5c-.123-.181-.24-.365-.352-.552-.715-1.192-1.437-2.874-1.581-4.948Zm-2.733-1.5h2.733c.144-2.074.866-3.756 1.58-4.948.12-.197.237-.381.353-.552a6.507 6.507 0 0 0-4.666 5.5Zm10.181 1.5c-.144 2.074-.866 3.756-1.58 4.948-.12.197-.237.381-.353.552a6.507 6.507 0 0 0 4.666-5.5Zm2.733-1.5a6.507 6.507 0 0 0-4.666-5.5c.123.181.24.365.352.552.715 1.192 1.437 2.874 1.581 4.948Z"),
    "mail": ("0 0 16 16", "M1.75 2h12.5c.966 0 1.75.784 1.75 1.75v8.5A1.75 1.75 0 0 1 14.25 14H1.75A1.75 1.75 0 0 1 0 12.25v-8.5C0 2.784.784 2 1.75 2ZM1.5 12.251c0 .138.112.25.25.25h12.5a.25.25 0 0 0 .25-.25V5.809L8.38 9.397a.75.75 0 0 1-.76 0L1.5 5.809v6.442Zm13-8.181v-.32a.25.25 0 0 0-.25-.25H1.75a.25.25 0 0 0-.25.25v.32L8 7.88Z"),
    "linkedin": ("0 0 24 24", "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"),
}

# name, label, icon, primary?   (primary = filled green like GitHub's main action button)
BUTTONS = [
    ("resume", "Resume", "file", True),
    ("portfolio", "Portfolio", "globe", False),
    ("linkedin", "LinkedIn", "linkedin", False),
    ("email", "Email", "mail", False),
]

THEMES = {
    "light": {
        "bg": "#f6f8fa", "border": "#d0d7de", "text": "#24292f", "icon": "#57606a",
        "primary_bg": "#1f883d", "primary_border": "#1a7f37", "primary_text": "#ffffff",
    },
    "dark": {
        "bg": "#21262d", "border": "#30363d", "text": "#c9d1d9", "icon": "#8b949e",
        "primary_bg": "#238636", "primary_border": "#2ea043", "primary_text": "#ffffff",
    },
}


def text_width(label: str) -> int:
    # Rough width of 13px semibold system text; generous so labels never clip.
    return int(len(label) * 7.6) + 4


def svg(label: str, icon: str, primary: bool, t: dict) -> str:
    pad, icon_px, gap = 14, 16, 8
    w = pad + icon_px + gap + text_width(label) + pad
    h = HEIGHT
    bg = t["primary_bg"] if primary else t["bg"]
    border = t["primary_border"] if primary else t["border"]
    fg = t["primary_text"] if primary else t["text"]
    ic = t["primary_text"] if primary else t["icon"]
    viewbox, path = ICONS[icon]
    scale = icon_px / float(viewbox.split()[2])
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{label}">
  <rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="6" fill="{bg}" stroke="{border}"/>
  <g transform="translate({pad} {(h - icon_px) / 2}) scale({scale:.4f})" fill="{ic}">
    <path d="{path}"/>
  </g>
  <text x="{pad + icon_px + gap}" y="{h / 2}" dominant-baseline="central" font-family="{FONT}" font-size="13" font-weight="600" fill="{fg}">{label}</text>
</svg>
"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, label, icon, primary in BUTTONS:
        for theme, t in THEMES.items():
            path = os.path.join(OUT_DIR, f"{name}-{theme}.svg")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(svg(label, icon, primary, t))
            print("wrote", path)


if __name__ == "__main__":
    main()
