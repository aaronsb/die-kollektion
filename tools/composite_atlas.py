"""Bakes a car's atlas the way the game's car shader appears to shade it, for offline renders.

Usage: python3 tools/composite_atlas.py <Donor> [--tint r,g,b]    e.g. Mammoth -> extracted/textures/Mammoth_composite.png

The car material (Shader Graphs/CarMainShader) takes the livery texture (<Donor>_skin00 for the stock
livery) as albedo and a mask texture whose channels sort the atlas, read from where the stock cars
use them: blue = body paint, green alone = glass, red with green = lamp lenses (the lamps' glow comes
from <Donor>_lights: red brake/tail, green headlight, blue reverse). Glass shades dark in game
whatever the albedo under it, so this bakes green-only texels to a dark glass grey; everything else
keeps the livery's colour. The rule is inferred from the stock textures and in-game screenshots (the
compiled shader is SMOL-V and was not decoded); it explains an orange-albedo, green-only lens
rendering black.

--tint multiplies the blue (paint) texels by a colour (0-1 per channel, doubled about mid grey), to
show which parts a player's paint colour reaches; it is illustrative, the in-game blend is unknown.
"""
import os, sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLASS = np.array([38, 40, 44])


def composite(donor, tint=None):
    textures = os.path.join(ROOT, "extracted/textures")
    skin = np.array(Image.open(os.path.join(textures, f"{donor}_skin00.png")).convert("RGB")).astype(float)
    mask = Image.open(os.path.join(textures, f"{donor}_masks.png")).convert("RGB").resize(skin.shape[1::-1], Image.NEAREST)
    mask = np.array(mask).astype(int)
    glass = (mask[:, :, 1] > 127) & (mask[:, :, 0] <= 127)
    out = skin.copy()
    out[glass] = GLASS
    if tint is not None:
        paint = mask[:, :, 2] > 127
        out[paint] = np.clip(out[paint] * np.array(tint) * 2.0, 0, 255)
    path = os.path.join(textures, f"{donor}_composite.png")
    Image.fromarray(out.astype(np.uint8)).save(path)
    return path, int(glass.sum())


if __name__ == "__main__":
    tint = [float(c) for c in sys.argv[sys.argv.index("--tint") + 1].split(",")] if "--tint" in sys.argv else None
    path, n = composite(sys.argv[1], tint)
    print(f"{path}: {n} glass texels baked dark")
