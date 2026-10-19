"""Rasterize icons/src/*.svg to the 256x256 PNGs the plugin loads, and draw a comparison sheet.

Usage: python3 -I tools/rasterize_icons.py [--out DIR] [--compare REV]
  --out DIR      write PNGs there instead of icons/ (for previews)
  --compare REV  also put REV's icons/*.png (e.g. HEAD) in renders/icons_compare.png

Needs rsvg-convert. The sheet shows the stock Mammoth icon (data/icons/Mammoth.png) and each truck at
native size and 2x on the menu's dark background.
"""
import argparse
import glob
import io
import os
import subprocess

from PIL import Image, ImageDraw

BG = (52, 52, 70, 255)


def rasterize(svg, png):
    subprocess.run(["rsvg-convert", "-w", "256", "-h", "256", "-f", "png", "-o", png, svg], check=True)
    im = Image.open(png).convert("RGBA")
    a = im.split()[3]
    Image.merge("RGBA", (a.point(lambda _: 255),) * 3 + (a,)).save(png)   # pure white, alpha only


def on_canvas(im):
    c = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    c.alpha_composite(im, ((256 - im.width) // 2, (256 - im.height) // 2))
    return c


def sheet(rows, out):
    cols = max(len(r[1]) for r in rows)
    cw, ch = 700, 280
    img = Image.new("RGBA", (cols * cw + 20, len(rows) * (ch + 30) + 20), BG)
    d = ImageDraw.Draw(img)
    for ri, (label, items) in enumerate(rows):
        y0 = 20 + ri * (ch + 30)
        d.text((10, y0 - 15), label, fill=(220, 220, 230))
        for ci, (name, im) in enumerate(items):
            x0 = 10 + ci * cw
            d.text((x0, y0), name, fill=(200, 200, 210))
            img.alpha_composite(im, (x0, y0 + 14))
            d.rectangle([x0, y0 + 14, x0 + 255, y0 + 269], outline=(90, 90, 110))
            img.alpha_composite(im.resize((512, 512), Image.LANCZOS).crop((0, 100, 512, 412)).resize((420, 256), Image.LANCZOS), (x0 + 262, y0 + 14))
    img.save(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="icons")
    ap.add_argument("--compare")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    names = []
    for svg in sorted(glob.glob("icons/src/*.svg")):
        name = os.path.splitext(os.path.basename(svg))[0]
        png = os.path.join(args.out, name + ".png")
        rasterize(svg, png)
        names.append(name)
        print(png)
    order = [n for n in ("Megatherium", "Mastodon", "Glyptodon", "Megaloceros") if n in names]
    stock = ("stock Mammoth", on_canvas(Image.open("data/icons/Mammoth.png").convert("RGBA")))
    rows = [("SVG", [stock] + [(n, Image.open(os.path.join(args.out, n + ".png")).convert("RGBA")) for n in order])]
    if args.compare:
        prev = []
        for n in order:
            blob = subprocess.run(["git", "show", f"{args.compare}:icons/{n}.png"], capture_output=True).stdout
            if blob:
                prev.append((n, Image.open(io.BytesIO(blob)).convert("RGBA")))
        rows.append((f"pipeline ({args.compare})", [stock] + prev))
    sheet(rows, "renders/icons_compare.png")
    print("renders/icons_compare.png")


if __name__ == "__main__":
    main()
