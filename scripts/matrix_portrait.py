"""
Matrix "code rain" portrait generator.

Turns a photo into an animated GIF where falling green characters form the
picture. The photo's brightness drives how bright each glyph is, so the subject
stays readable while streams of code rain down over it. If `rembg` is
installed the background is removed first, so only the person is drawn in code
and the rain falls through empty black around them.

Usage (from the repo root):
    python scripts/matrix_portrait.py                        # defaults below
    python scripts/matrix_portrait.py photo.jpg assets/out   # custom input / output stem

Tweak the CONFIG block to change crop, size, speed, colours or density.
Requires: pillow, numpy   (optional: rembg[cpu] for background removal)
"""
from __future__ import annotations

import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

# ----------------------------------------------------------------- CONFIG ----
SRC = sys.argv[1] if len(sys.argv) > 1 else "assets/source-photo.png"
OUT = sys.argv[2] if len(sys.argv) > 2 else "assets/matrix-portrait"

# Crop box (left, top, right, bottom) in source-photo pixels. None = whole image.
CROP = (290, 150, 590, 600)

COLS, ROWS = 36, 54          # character grid (keep roughly the crop's aspect ratio)
CELL_W, CELL_H = 10, 13      # pixel size of one character cell -> 360 x 702 image
FRAMES = 48                  # frames in the loop
FRAME_MS = 70                # delay per frame
DROPS_PER_COL = (1, 2)       # min/max rain streams per column
TRAIL = (8, 24)              # min/max trail length in cells
GLYPH_FLICKER = 0.04         # share of glyphs that change each frame
GAMMA = 0.80                 # <1 brightens mid-tones, >1 darkens them
REMOVE_BG = True             # use rembg to isolate the person (if installed)
SUBJECT_FLOOR = 0.36         # darkest glyph inside the subject (keeps hair/clothes visible)
BG_LEVEL = 0.03              # glyph brightness outside the subject (0 = pure black)
BG_RAIN = 0.35               # how bright rain is outside the subject (1 = same as inside)
SEED = 7

# Characters: half-width katakana (the classic look) plus digits.
CHARS = [chr(c) for c in range(0xFF66, 0xFF9E)] + list("0123456789")
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msgothic.ttc",   # has half-width katakana
    r"C:\Windows\Fonts\consola.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]
# ------------------------------------------------------------------------------

random.seed(SEED)
np.random.seed(SEED)


def load_font():
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, CELL_H + 2)
            except OSError:
                continue
    return ImageFont.load_default()


def glyph_masks(font) -> np.ndarray:
    """Render every character once as a (CELL_H, CELL_W) float mask in 0..1."""
    masks = []
    for ch in CHARS:
        im = Image.new("L", (CELL_W, CELL_H), 0)
        d = ImageDraw.Draw(im)
        bbox = d.textbbox((0, 0), ch, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = (CELL_W - w) / 2 - bbox[0], (CELL_H - h) / 2 - bbox[1]
        d.text((x, y), ch, fill=255, font=font)
        d.text((x + 1, y), ch, fill=255, font=font)   # fake bold: thicker strokes read better
        masks.append(np.asarray(im, dtype=np.float32) / 255.0)
    arr = np.stack(masks)
    keep = arr.reshape(len(CHARS), -1).max(axis=1) > 0.2   # drop glyphs the font lacks
    return arr[keep]


def subject_mask(im: Image.Image) -> np.ndarray | None:
    """Alpha mask (0..1) of the person, or None if rembg is not available."""
    if not REMOVE_BG:
        return None
    try:
        from rembg import remove
    except ImportError:
        print("rembg not installed; rendering without background removal")
        return None
    cut = remove(im.convert("RGB"))                       # RGBA with background cleared
    alpha = cut.getchannel("A").filter(ImageFilter.GaussianBlur(1.5))
    return np.asarray(alpha.resize((COLS, ROWS), Image.LANCZOS), dtype=np.float32) / 255.0


def luminance_grid() -> tuple[np.ndarray, np.ndarray]:
    """Returns (brightness grid 0..1, subject mask 0..1) at COLS x ROWS."""
    im = Image.open(SRC)
    im = ImageOps.exif_transpose(im)
    if CROP:
        im = im.crop(CROP)
    mask = subject_mask(im)

    g = ImageOps.autocontrast(im.convert("L"), cutoff=1)
    L = np.asarray(g.resize((COLS, ROWS), Image.LANCZOS), dtype=np.float32) / 255.0
    L = np.clip(L, 0, 1) ** GAMMA

    if mask is None:
        mask = np.ones_like(L)
    # Inside the subject: lift the floor so dark hair/clothes still read as a shape.
    inside = SUBJECT_FLOOR + (1 - SUBJECT_FLOOR) * L
    return inside * mask + BG_LEVEL * (1 - mask), mask


def make_drops():
    """Rain streams that wrap exactly every FRAMES frames so the GIF loops cleanly."""
    drops = []
    for c in range(COLS):
        for _ in range(random.randint(*DROPS_PER_COL)):
            length = random.randint(*TRAIL)
            period = ROWS + length                      # cells travelled per wrap
            laps = random.choice([1, 1, 2])             # wraps per loop
            speed = laps * period / FRAMES              # cells per frame
            drops.append((c, random.uniform(0, period), speed, length, period))
    return drops


def colourise(b: np.ndarray) -> np.ndarray:
    """Brightness 0..1 -> RGB. Dim = deep green, bright = near-white green."""
    r = 255 * (0.95 * b ** 3)
    g = 255 * np.clip(b * 1.05, 0, 1)
    bl = 255 * (0.25 * b + 0.70 * b ** 3)
    return np.stack([r, g, bl], axis=-1)


def main():
    font = load_font()
    masks = glyph_masks(font)
    n_glyphs = len(masks)
    base, subject = luminance_grid()
    drops = make_drops()
    G = np.random.randint(0, n_glyphs, size=(ROWS, COLS))

    frames = []
    for t in range(FRAMES):
        flip = np.random.rand(ROWS, COLS) < GLYPH_FLICKER
        G[flip] = np.random.randint(0, n_glyphs, size=flip.sum())

        bright = base * 0.9                                   # resting portrait layer
        for c, y0, speed, length, period in drops:
            head = (y0 + speed * t) % period
            for k in range(length):
                y = int(head) - k
                if 0 <= y < ROWS:
                    fade = (1 - k / length) ** 1.6
                    s = subject[y, c]
                    scale = BG_RAIN + (1 - BG_RAIN) * s           # rain is dimmer off-subject
                    if k == 0:
                        v = (0.75 + 0.25 * base[y, c]) * scale    # head: bright, almost white
                    else:
                        v = fade * (0.35 + 0.65 * base[y, c]) * scale
                    bright[y, c] = max(bright[y, c], v)

        glyph = masks[G].transpose(0, 2, 1, 3).reshape(ROWS * CELL_H, COLS * CELL_W)
        b = np.repeat(np.repeat(bright, CELL_H, axis=0), CELL_W, axis=1) * glyph
        frames.append(Image.fromarray(colourise(np.clip(b, 0, 1)).astype(np.uint8), "RGB"))

    # Shared palette keeps the GIF small and avoids colour flicker between frames.
    palette_src = frames[FRAMES // 3].quantize(colors=96, method=Image.Quantize.MEDIANCUT)
    pal_frames = [f.quantize(colors=96, palette=palette_src, dither=Image.Dither.NONE) for f in frames]
    pal_frames[0].save(OUT + ".gif", save_all=True, append_images=pal_frames[1:],
                       duration=FRAME_MS, loop=0, optimize=True, disposal=1)
    frames[FRAMES // 3].save(OUT + ".png", optimize=True)
    print(f"wrote {OUT}.gif ({os.path.getsize(OUT + '.gif') // 1024} KB) and {OUT}.png "
          f"[{COLS * CELL_W}x{ROWS * CELL_H}, {FRAMES} frames, {n_glyphs} glyphs]")


if __name__ == "__main__":
    main()
