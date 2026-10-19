"""Write the Megatherium and Mastodon icons as traced SVG edits of the stock Mammoth icon.

Usage: python3 tools/trace_icons.py      (system python: needs numpy; then tools/rasterize_icons.py)
Input: extracted/icons/Mammoth.png, the stock Mammoth_Icon sprite (exported from the scriptableobjects
bundle; 254x144, white on transparent). Needs potrace.

Both trucks are the Mammoth's body, so their icons are the stock icon with only the differences
edited in, at 8x resolution before tracing:
- Megatherium: 0.37 m longer wheelbase (21 px at the icon's 57.5 px/m): the wheels come out,
  columns are inserted behind the bed's rear stake, so the rear wheel, rear fender and tail move
  back and the bed and chassis rail stretch; the wheels go back in; the staked slat bed becomes a
  stakeless ribbed bed (a stake-free column of the bed repeated along it).
- Mastodon: the Megatherium with the rear door bay of the cab replaced by bed: the bed runs up to
  the cab's B-pillar, which becomes the single cab's rear wall, and the roof starts there with the
  stock roof's rounded rear end.
The result is traced with potrace into vehicles/<name>/icon.svg (gitignored: it is the game's icon, edited), framed like the other icons:
256x256, 2 px end margins, centred vertically.
"""
import os
import re
import subprocess
import tempfile

import numpy as np
from PIL import Image
from scipy import ndimage

UP = 8                       # work resolution, times the stock icon
STRETCH = 21                 # Megatherium wheelbase difference in stock-icon px
CUT = 68                     # insert columns here: behind the rear stake, clear of everything but bed and rail
BED_COL = 45                 # a stake-free column of the bed (rows 0..69: slat bands, gap, chassis rail)
BED_X = (4, 76)              # bed extent in the stock icon
REAR_WHEEL, FRONT_WHEEL = (52, 110), (197, 110)
CANVAS, MARGIN = 256, 2


def load():
    im = Image.open("extracted/icons/Mammoth.png").convert("RGBA").split()[3]
    big = im.resize((im.width * UP, im.height * UP), Image.LANCZOS)
    return np.array(big) >= 128


def u(v):
    return v * UP


def lift_wheel(img, centre):
    """Remove the wheel (tyre ring and hub) whose hub is at centre; return it as its own mask."""
    lab, _ = ndimage.label(img)
    cx, cy = u(centre[0]), u(centre[1])
    ids = {lab[cy, cx], lab[cy - u(23), cx]}            # hub, tyre ring
    ids.discard(0)
    wheel = np.isin(lab, list(ids))
    return img & ~wheel, wheel


def stakeless_bed(img, x0, x1):
    """Replace the bed (rows 0..69 between x0 and x1, upscaled) with the stake-free column, repeated."""
    col = img[: u(70), u(BED_COL): u(BED_COL) + UP]
    reps = (u(x1 + 1) - u(x0)) // UP + 1
    strip = np.tile(col, (1, reps))[:, : u(x1 + 1) - u(x0)]
    img[: u(70), u(x0): u(x1 + 1)] = strip


def megatherium(img):
    img, rear = lift_wheel(img, REAR_WHEEL)
    img, front = lift_wheel(img, FRONT_WHEEL)
    d = u(STRETCH)
    cut = u(CUT)
    left, right = img[:, :cut], img[:, cut:]
    mid = np.repeat(img[:, cut - 1: cut], d, axis=1)
    out = np.concatenate([left, mid, right], axis=1)
    rear = np.concatenate([np.zeros((img.shape[0], d), bool), rear], axis=1)[:, : out.shape[1]]   # keeps its x
    front = np.concatenate([np.zeros((img.shape[0], d), bool), front], axis=1)                    # shifted right with the cab
    out |= rear | front
    stakeless_bed(out, BED_X[0], BED_X[1] + STRETCH)
    return out, STRETCH


def mastodon(img):
    out, s = megatherium(img)
    stock = load()
    bay0, bay1 = 77 + s, 127 + s           # rear door bay (cab rear wall at 80, B-pillar at 132)
    # Bed and chassis rail across the bay, a gap under the rail, the sill below kept.
    stakeless_bed(out, bay0, bay1)
    out[u(70): u(72), u(bay0): u(bay1 + 1)] = False
    # Gap between the bed and the cab, then the stock roof's rounded rear end on the B-pillar.
    out[: u(70), u(128 + s): u(132 + s)] = False
    out[: u(12), u(132 + s): u(139 + s)] = stock[: u(12), u(80): u(87)]
    return out, s


def trace(mask, name):
    rows, cols = np.nonzero(mask)
    y0, y1, x0, x1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    k = (CANVAS - 2 * MARGIN) / (x1 - x0)
    ox = MARGIN - x0 * k
    oy = CANVAS / 2 - (y0 + y1) / 2 * k
    with tempfile.TemporaryDirectory() as tmp:
        pbm = os.path.join(tmp, "in.pbm")
        Image.fromarray(~mask).convert("1").save(pbm)    # potrace traces black
        svg = os.path.join(tmp, "out.svg")
        subprocess.run(["potrace", "-s", "--flat", "-t", "8", "-a", "1.0", "-O", "0.4", "-o", svg, pbm], check=True)
        text = open(svg).read()
    g = re.search(r'<g transform="([^"]+)"', text).group(1)
    paths = re.findall(r'<path d="([^"]+)"', text)
    body = "\n".join(f'<path d="{p}"/>' for p in paths)
    out = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS}" height="{CANVAS}" viewBox="0 0 {CANVAS} {CANVAS}">\n'
           f'<title>Das {name} (traced from the stock Mammoth icon)</title>\n'
           f'<g fill="white" transform="translate({ox:.4f},{oy:.4f}) scale({k:.6f})">\n'
           f'<g transform="{g}">\n{body}\n</g>\n</g>\n</svg>\n')
    path = f"vehicles/{name.lower()}/icon.svg"
    with open(path, "w") as f:
        f.write(out)
    print(path)


if __name__ == "__main__":
    trace(megatherium(load())[0], "Megatherium")
    trace(mastodon(load())[0], "Mastodon")
