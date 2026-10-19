"""Vehicle-select icons in the stock style, drawn from each truck's built LOD0.

Usage: .venv/bin/python -I tools/make_icons.py [<codename> ...]   (default: every derived truck)

The stock icons (VehiclesIcons atlas, e.g. Mammoth_Icon) are 256x256 sprites at 50 px/unit, pivot
centre: a pure white side view, front to the right, spanning the full width and centred vertically,
built from solid panels separated by a few clean transparent gaps.

The icon is built from solids. Only the camera-side half of the body is rendered (the truck's
right, back faces culled), flat white with the glass black (tools/render_icon.py, 4x), so the
windows are clean holes. Small details are left out rather than allowed to notch the outline:
mirrors and handles standing out from the side glass above the window line, and everything low
behind the front arch (frame, tank, steps, battery boxes, exhaust, guards, flaps, spare carrier,
lamps). A plain frame rail stands in for them. The only gaps are drawn on purpose: the ring round each
tyre and the hub ring, the split between cab and bed, the line under the bed, the bed slats and a
door shut line behind each side window. The result is fitted to the stock framing and written to
vehicles/<name>/icon.png.

Glass faces are those whose UV lands on green in the Mammoth masks texture; bed faces are those on
the repainted-bed atlas point above the tyres and behind the cab's rear wall (the Glyptodon cab is painted
from the same point). The rear wall is where the rear-facing glass sits. With --lines, the same parts are also drawn with
Freestyle crease lines to renders/icons_lines/<Codename>.png for comparison.
"""
import json, os, statistics, subprocess, sys, tempfile
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZE, SS = 256, 4                  # canvas (px) and supersampling
MARGIN = 2                         # px left clear at each end, as on the stock icons
GAP = 3.0                          # gap width (px at 1x)
HUB_RING = 0.62                    # ring gap radius as a share of the tyre radius
SLATS = 4                          # slats drawn on a bed side
BED_UV, BED_MIN_Y = (0.635, 0.59), 1.1
UNDER_Y = 0.98                     # below this, behind the front arch, parts are left out
RAIL_Y = (0.76, 0.94)              # the frame rail drawn in their place
DETAIL_OUT = 0.12                  # parts above the window line this far outboard of the side glass
                                   # (mirrors, handles) are left out; the Glyptodon cab's skin there sits 0.07 out
OPENING = 9                        # px at 4x: protrusions thinner than this are dropped
CREASE, MIN_STROKE = 135.0, 4.0    # --lines variant: crease angle (degrees), shortest line (px at 1x)
MASKS = Image.open(os.path.join(ROOT, "extracted/textures/Mammoth_masks.png")).convert("RGB")


def read_obj(path):
    vs, vts, faces, head = [], [], [], []
    for line in open(path):
        if line.startswith("f "):
            idx = [p.split("/") for p in line.split()[1:]]
            faces.append((line, [int(p[0]) - 1 for p in idx], [int(p[1]) - 1 for p in idx if len(p) > 1 and p[1]]))
            continue
        head.append(line)
        if line.startswith("v "):
            vs.append(tuple(float(x) for x in line.split()[1:4]))
        elif line.startswith("vt "):
            vts.append(tuple(float(x) for x in line.split()[1:3]))
    return head, vs, vts, faces


def is_glass(vts, uv_idx):
    if not uv_idx:
        return False
    w, h = MASKS.size
    u = sum(vts[i][0] for i in uv_idx) / len(uv_idx)
    v = sum(vts[i][1] for i in uv_idx) / len(uv_idx)
    r, g, b = MASKS.getpixel((min(w - 1, max(0, int(u % 1 * (w - 1)))), min(h - 1, max(0, int((1 - v % 1) * (h - 1))))))
    return g > 200 and r < 60 and b < 60


def facing(pts, axis):
    """Whether a face's normal points mostly along the given axis (0 = x, 2 = z)."""
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = pts[:3]
    ux, uy, uz, vx, vy, vz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    length = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5
    return length > 0 and abs(n[axis]) / length > 0.7


def classify(path, front_axle, radius):
    """Splits the camera-side half of a body OBJ into glass, bed and kept body faces, and finds the
    side windows (z ranges and lowest y) and the bed's extent."""
    head, vs, vts, faces = read_obj(path)
    near = [(line, vi, ti) for line, vi, ti in faces if any(vs[i][0] < 0 for i in vi)]   # OBJ +x is the truck's left
    glass = [(line, vi, ti) for line, vi, ti in near if is_glass(vts, ti)]
    side_glass = [[vs[i] for i in vi] for _, vi, _ in glass if facing([vs[i] for i in vi], 0)]
    rear_glass = [[vs[i] for i in vi] for _, vi, _ in glass if facing([vs[i] for i in vi], 2)]
    side_x = statistics.median(p[0] for pts in side_glass for p in pts) if side_glass else -0.9
    # Side windows: side-facing glass grouped into z ranges.
    windows = []
    for pts in sorted(side_glass, key=lambda pts: min(p[2] for p in pts)):
        z0, z1, y0 = min(p[2] for p in pts), max(p[2] for p in pts), min(p[1] for p in pts)
        if windows and z0 <= windows[-1][1] + 0.05:
            windows[-1] = (windows[-1][0], max(windows[-1][1], z1), min(windows[-1][2], y0))
        else:
            windows.append((z0, z1, y0))
    windows = [w for w in windows if w[1] - w[0] > 0.2]
    cab_rear = min(sum(p[2] for p in pts) / len(pts) for pts in rear_glass) if rear_glass else front_axle - 1.5
    window_y = min(w[2] for w in windows) if windows else 1.6
    out = {"glass": [], "bed": [], "body": []}
    dropped = 0
    for line, vi, ti in near:
        pts = [vs[i] for i in vi]
        cy = sum(p[1] for p in pts) / len(pts)
        cz = sum(p[2] for p in pts) / len(pts)
        if is_glass(vts, ti):
            out["glass"].append(line)
        elif cy > BED_MIN_Y and cz < cab_rear - 0.02 and ti and all(abs(vts[i][k] - BED_UV[k]) < 1e-3 for i in ti for k in range(2)):
            out["bed"].append(line)
        elif cy > window_y and all(p[0] < side_x - DETAIL_OUT for p in pts):
            dropped += 1                                   # mirrors, handles
        elif cy < UNDER_Y and cz < front_axle - radius - 0.1:
            dropped += 1                                   # frame, tank, steps, boxes, exhaust, guards, flaps, carrier, lamps
        else:
            out["body"].append(line)
    bed_lines = set(out["bed"])
    bed_pts = [vs[i] for line, vi, ti in near if line in bed_lines for i in vi]
    bed = (min(p[2] for p in bed_pts), max(p[2] for p in bed_pts), min(p[1] for p in bed_pts), max(p[1] for p in bed_pts)) if bed_pts else None
    body_pts = [vs[i] for line, vi, ti in near if not is_glass(vts, ti) for i in vi]
    extent = (min(p[2] for p in body_pts), max(p[2] for p in body_pts), max(p[1] for p in body_pts))
    return head, out, windows, bed, cab_rear, extent, dropped


def make(codename, lines=False):
    definition = json.load(open(os.path.join(ROOT, "vehicles", codename.lower(), "vehicle.json")))
    body_src = os.path.join(ROOT, "vehicles", codename.lower(), "build", "body_LOD0.obj")
    wheel = dict(definition["wheel"], **definition.get("tyre", {}))
    front = definition["donorAxleZ"]["front"]
    axles = (front, front - definition["wheelbase"])
    hub_y, radius = wheel["y"], wheel["radius"]
    head, parts, windows, bed, cab_rear, (z0, z1, y1), dropped = classify(body_src, front, radius)
    z0, z1 = min(z0, axles[1] - radius), max(z1, axles[0] + radius)
    y0 = hub_y - radius
    ppm = (SIZE - 2 * MARGIN) / (z1 - z0) * SS
    cz, cy = (z0 + z1) / 2, (y0 + y1) / 2
    n = SIZE * SS
    with tempfile.TemporaryDirectory() as tmp:
        paths = {}
        for name, faces in parts.items():
            paths[name] = os.path.join(tmp, f"{name}.obj")
            with open(paths[name], "w") as f:
                f.writelines(head + faces)
        raw = os.path.join(tmp, "raw.png")
        subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "1", "--python", os.path.join(ROOT, "tools/render_icon.py"), "--",
                        raw, str(ppm), str(cz), str(cy), str(n), str(n), str(GAP * SS if lines else 0), str(CREASE), str(MIN_STROKE * SS),
                        paths["glass"], paths["bed"], paths["body"]],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        img = Image.open(raw).convert("RGBA")
        if os.environ.get("ICON_KEEP_RAW"):
            img.save(os.path.join(os.environ["ICON_KEEP_RAW"], f"{codename}{'_lines' if lines else ''}_raw.png"))
    r, g, b, a = img.split()
    solid = ImageChops.multiply(a, r.point(lambda p: 255 if p > 128 else 0))            # body or bed
    alpha = solid.filter(ImageFilter.MinFilter(OPENING)).filter(ImageFilter.MaxFilter(OPENING))
    draw = ImageDraw.Draw(alpha)
    px = lambda z: n / 2 + (z - cz) * ppm
    py = lambda y: n / 2 - (y - cy) * ppm
    gap = GAP * SS
    # The frame rail in place of the parts left out, from the bed end to the front arch; it meets
    # the bed when the bed sits low.
    rear = bed[0] if bed else z0
    rail_top = RAIL_Y[1] if not bed or bed[2] - RAIL_Y[1] > 2 * gap / ppm else bed[2]
    draw.rectangle((px(rear), py(rail_top), px(front - radius), py(RAIL_Y[0])), fill=255)
    if bed:
        bz0, bz1, by0, by1 = bed
        draw.rectangle((px(bz0), py(by0) - gap / 2, px(bz1), py(by0) + gap / 2), fill=0)             # under the bed
        draw.rectangle((px(bz1) - gap / 2, py(by1), px(bz1) + gap / 2, py(by0)), fill=0)             # cab / bed split
        for i in range(1, SLATS):
            y = py(by1) + (py(by0) - py(by1)) * i / SLATS
            draw.rectangle((px(bz0), y - gap / 2, px(bz1) - gap / 2, y + gap / 2), fill=0)          # slats
    for wz0, wz1, wy0 in windows:                                                                   # door shut lines
        x = px(wz0 - 0.05)
        draw.rectangle((x - gap / 2, py(wy0) - gap, x + gap / 2, py(UNDER_Y)), fill=0)
    for z in axles:
        x, y = px(z), py(hub_y)
        r = radius * ppm
        draw.ellipse((x - r - gap, y - r - gap, x + r + gap, y + r + gap), fill=0)   # arch gap
        draw.ellipse((x - r, y - r, x + r, y + r), fill=255)                          # tyre
        ring = r * HUB_RING
        draw.ellipse((x - ring, y - ring, x + ring, y + ring), fill=0)                # ring gap
        hub = ring - gap
        draw.ellipse((x - hub, y - hub, x + hub, y + hub), fill=255)                  # hub
    # Fit to the stock framing: full width less the margins, centred vertically.
    left, top, right, bottom = alpha.getbbox()
    scale = (SIZE - 2 * MARGIN) / (right - left)
    drawing = alpha.crop((left, top, right, bottom)).filter(ImageFilter.GaussianBlur(SS * 0.35))
    drawing = drawing.resize((SIZE - 2 * MARGIN, max(1, round((bottom - top) * scale))), Image.LANCZOS)
    mask = Image.new("L", (SIZE, SIZE), 0)
    mask.paste(drawing, (MARGIN, (SIZE - drawing.height) // 2))
    icon = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
    icon.putalpha(mask)
    if lines:
        os.makedirs(os.path.join(ROOT, "renders/icons_lines"), exist_ok=True)
        out = os.path.join(ROOT, "renders/icons_lines", f"{codename}.png")
    else:
        out = os.path.join(ROOT, "vehicles", codename.lower(), "icon.png")
    icon.save(out)
    print(f"{out}: {len(parts['glass'])} glass, {len(parts['bed'])} bed, {len(parts['body'])} body faces, {dropped} left out, "
          f"{len(windows)} side windows, {ppm / SS:.1f} px/m, bbox {mask.getbbox()}")


def compare(names, stock="extracted/icons/Mammoth.png", out="renders/icons_compare.png"):
    """Stock Mammoth icon beside the new ones at native size and 2x: solids (vehicles/<name>/icon.png) on top, and
    the Freestyle-lines variant (renders/icons_lines/) below where it exists."""
    bg, pad, label_h = (52, 54, 72, 255), 16, 20
    stock_icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    stock_icon.alpha_composite(Image.open(os.path.join(ROOT, stock)).convert("RGBA"), (1, 56))   # exported cropped to its texture rect
    variants = [("solids", None)]
    if all(os.path.exists(os.path.join(ROOT, "renders/icons_lines", f"{n}.png")) for n in names):
        variants.append(("lines", "renders/icons_lines"))
    block = label_h + SIZE + pad + 2 * SIZE + pad
    sheet = Image.new("RGBA", (pad + (len(names) + 1) * (2 * SIZE + pad), pad + len(variants) * block), bg)
    draw = ImageDraw.Draw(sheet)
    for row, (variant, folder) in enumerate(variants):
        top = pad + row * block
        paths = {n: os.path.join(ROOT, "vehicles", n.lower(), "icon.png") if folder is None else os.path.join(ROOT, folder, f"{n}.png") for n in names}
        icons = [("stock Mammoth", stock_icon)] + [(f"{n} ({variant})", Image.open(paths[n]).convert("RGBA")) for n in names]
        for i, (label, icon) in enumerate(icons):
            x = pad + i * (2 * SIZE + pad)
            draw.text((x, top), label, fill=(230, 230, 230, 255))
            sheet.alpha_composite(icon, (x, top + label_h))
            draw.rectangle((x, top + label_h, x + SIZE - 1, top + label_h + SIZE - 1), outline=(90, 92, 110, 255))
            sheet.alpha_composite(icon.resize((2 * SIZE, 2 * SIZE), Image.LANCZOS), (x, top + label_h + SIZE + pad))
    sheet.save(os.path.join(ROOT, out))
    print(os.path.join(ROOT, out))


if __name__ == "__main__":
    args = sys.argv[1:]
    lines = "--lines" in args
    names = [a for a in args if not a.startswith("--")] or ["Megatherium", "Mastodon", "Glyptodon", "Megaloceros"]
    for name in names:
        make(name)
        if lines:
            make(name, lines=True)
    compare([n for n in names if n != "Mammoth"])
