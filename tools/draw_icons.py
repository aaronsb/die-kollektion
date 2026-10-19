"""Write the vehicle-select icons as SVG, drawn in the style of the game's stock icons.

Usage: python3 tools/draw_icons.py [Codename ...]   (default: both Glyptodon-family trucks)
       then python3 tools/rasterize_icons.py
The round-cab Megatherium and Mastodon are traced from the stock Mammoth icon instead
(tools/trace_icons.py).

Each truck is a handful of geometric shapes placed from its real dimensions (metres, car-root OBJ
space: z forward, y up; front axle at z 1.22, hub at y 0.45), then mapped onto a 256x256 canvas with
the front to the right, 2 px end margins and the drawing centred vertically. White shapes sit on
transparency; dark gaps are cut with an SVG mask, 4 px for structure and 2 px for bed ribs, as on
the stock Mammoth icon (extracted/icons/Mammoth.png): a roof band over open windows framed by pillars,
a beltline gap, door shut lines and handle slots, horizontal bands below, wheels as a tyre ring, a
gap and a hub disc. The SVGs (vehicles/<name>/icon.svg) are the sources; edit them by hand or here.
"""
import math
import os
import sys

CANVAS, MARGIN = 256, 2
GAP, RIB = 4.0, 2.0              # px
WHEEL_SCALE = 1.10               # stock icons draw wheels a little larger than life
FRONT_AXLE, HUB_Y = 1.22, 0.45


class Icon:
    def __init__(self, zmin, zmax, ytop, radius):
        self.s = (CANVAS - 2 * MARGIN) / (zmax - zmin)
        self.zmin = zmin
        self.R = radius * WHEEL_SCALE * self.s
        ybot = HUB_Y - radius * WHEEL_SCALE
        self.oy = CANVAS / 2 + (ytop + ybot) / 2 * self.s     # canvas y of y = 0
        self.white, self.cut, self.top = [], [], []          # body shapes, mask cuts, unmasked shapes

    def x(self, z): return MARGIN + (z - self.zmin) * self.s
    def y(self, y): return self.oy - y * self.s
    def pt(self, z, y): return f"{self.x(z):.2f},{self.y(y):.2f}"
    def m(self, px): return px / self.s                      # px to metres

    def poly(self, pts, to="white"):
        getattr(self, to).append(f'<polygon points="{" ".join(self.pt(z, y) for z, y in pts)}"/>')

    def rect(self, z0, z1, y0, y1, r=0.0, to="white"):
        x0, x1, ya, yb = self.x(min(z0, z1)), self.x(max(z0, z1)), self.y(max(y0, y1)), self.y(min(y0, y1))
        getattr(self, to).append(f'<rect x="{x0:.2f}" y="{ya:.2f}" width="{x1 - x0:.2f}" height="{yb - ya:.2f}" rx="{r:.2f}"/>')

    def path(self, d, to="white"):
        getattr(self, to).append(f'<path d="{d}"/>')

    def line(self, pts, width=GAP):
        """A cut (dark gap) along a polyline, width in px."""
        self.cut.append(f'<polyline points="{" ".join(self.pt(z, y) for z, y in pts)}" fill="none" '
                        f'stroke="black" stroke-width="{width}" stroke-linecap="butt" stroke-linejoin="miter"/>')

    def circle(self, z, y, r_px, to="white"):
        getattr(self, to).append(f'<circle cx="{self.x(z):.2f}" cy="{self.y(y):.2f}" r="{r_px:.2f}"/>')

    def wheel(self, z):
        """Tyre ring, gap, hub disc (unmasked, over everything), and its arch gap cut into the body."""
        cx, cy, R = self.x(z), self.y(HUB_Y), self.R
        ring = R * 0.39
        hub = R - ring - GAP
        self.circle(z, HUB_Y, R + GAP, to="cut")
        self.top.append(f'<path fill-rule="evenodd" d="M{cx - R:.2f},{cy:.2f} a{R:.2f},{R:.2f} 0 1,0 {2 * R:.2f},0 '
                        f'a{R:.2f},{R:.2f} 0 1,0 {-2 * R:.2f},0 Z M{cx - R + ring:.2f},{cy:.2f} '
                        f'a{R - ring:.2f},{R - ring:.2f} 0 1,0 {2 * (R - ring):.2f},0 '
                        f'a{R - ring:.2f},{R - ring:.2f} 0 1,0 {-2 * (R - ring):.2f},0 Z"/>')
        self.circle(z, HUB_Y, hub, to="top")

    def flare(self, z, width_px, a0=-12, a1=192):
        """A fender band arcing over a wheel from a0 to a1 degrees (0 = rear, 90 = top), with gaps both sides."""
        cx, cy = self.x(z), self.y(HUB_Y)
        r_in, r_out = self.R + GAP, self.R + GAP + width_px
        self.circle(z, HUB_Y, r_out + GAP, to="cut")
        def p(r, a):   # a in degrees, 0 = rearward (-x), 90 = up
            t = math.radians(a)
            return cx - r * math.cos(t), cy - r * math.sin(t)
        x0, y0 = p(r_out, a0); x1, y1 = p(r_out, a1); x2, y2 = p(r_in, a1); x3, y3 = p(r_in, a0)
        big = 1 if (a1 - a0) > 180 else 0
        self.top.append(f'<path d="M{x0:.2f},{y0:.2f} A{r_out:.2f},{r_out:.2f} 0 {big},1 {x1:.2f},{y1:.2f} '
                        f'L{x2:.2f},{y2:.2f} A{r_in:.2f},{r_in:.2f} 0 {big},0 {x3:.2f},{y3:.2f} Z"/>')

    def svg(self, title):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS}" height="{CANVAS}" viewBox="0 0 {CANVAS} {CANVAS}">\n'
                f'<title>{title}</title>\n'
                f'<defs><mask id="cut" maskUnits="userSpaceOnUse" x="0" y="0" width="{CANVAS}" height="{CANVAS}">'
                f'<rect width="{CANVAS}" height="{CANVAS}" fill="white"/>\n' + "\n".join(self.cut) + '\n</mask></defs>\n'
                f'<g fill="white" mask="url(#cut)">\n' + "\n".join(self.white) + '\n</g>\n'
                f'<g fill="white">\n' + "\n".join(self.top) + '\n</g>\n</svg>\n')


def bed(ic, z_end, z_front, y_bot, y_top, ribs):
    """Flat bed side: a panel with rib gaps, a gap to the cab."""
    ic.rect(z_end, z_front, y_bot, y_top)
    h = y_top - y_bot
    for f in ribs:
        ic.line([(z_end, y_bot + f * h), (z_front, y_bot + f * h)], RIB)


# --- the Glyptodon family ------------------------------------------------------------------------

ROOF_435 = 2.43
A_TOP, A_BOT = (1.18, ROOF_435), (1.44, 1.80)      # windscreen line (the A-pillar's front edge)
BELT_435 = 1.84


def a_line(y, inset=0.0):
    """z of the A-pillar front edge at height y, moved back by inset."""
    (z1, y1), (z0, y0) = A_TOP, A_BOT
    return z0 + (y - y0) * (z1 - z0) / (y1 - y0) - inset


def front_435(ic, z_rear, snorkel=True):
    """Cab shell from z_rear forward, nose, bumper, flare, intake, snorkel."""
    roof_band = ROOF_435 - ic.m(6)
    win_top = roof_band - ic.m(GAP)
    # Cab and hood as one shell; the bumper and flare are separate shapes.
    ic.poly([(z_rear - 0.025, ROOF_435), (A_TOP[0] - 0.05, ROOF_435), (A_TOP[0] + 0.02, ROOF_435 - 0.05), A_BOT,
             (1.50, 1.78), (1.96, 1.64), (2.04, 1.58), (2.07, 1.48), (2.07, 1.06), (1.70, 1.06), (1.70, 0.98),
             (z_rear, 0.98), (z_rear, ROOF_435 - 0.06), (z_rear - 0.025, ROOF_435 - 0.06)])
    ic.line([(z_rear - 0.05, roof_band - ic.m(GAP / 2)), (a_line(roof_band - ic.m(GAP / 2), 0.0) + 0.02, roof_band - ic.m(GAP / 2))])
    ic.line([(z_rear, BELT_435), (a_line(BELT_435, 0.0), BELT_435)])
    # Bumper with a gap to the nose.
    ic.rect(1.96, 2.30, 0.80, 1.04, r=1.0)
    ic.line([(1.70, 1.05), (2.32, 1.05)])
    # Side intake ahead of the A-pillar: a dark panel with two louvres.
    ic.rect(1.47, 1.74, 1.36, 1.60, r=1.0, to="cut")
    for y in (1.44, 1.52):
        ic.cut.append(f'<rect x="{ic.x(1.50):.2f}" y="{ic.y(y + 0.03):.2f}" width="{ic.x(1.71) - ic.x(1.50):.2f}" '
                      f'height="{ic.m(0) + 1.6:.2f}" fill="white"/>')
    ic.flare(FRONT_AXLE, 6)
    if snorkel:   # right A-pillar intake rising just above the roof
        ic.rect(1.08, 1.17, ROOF_435, ROOF_435 + 0.10, to="top")
        ic.rect(1.01, 1.24, ROOF_435 + 0.08, ROOF_435 + 0.15, r=1.5, to="top")
        ic.line([(1.0, ROOF_435 + ic.m(GAP / 2)), (1.25, ROOF_435 + ic.m(GAP / 2))])


def door_435(ic, dz, handle=True):
    """A Glyptodon-family door (window with raked front edge and vent divider, shut lines, handle), shifted dz back."""
    roof_band = ROOF_435 - ic.m(6)
    win_top = roof_band - ic.m(GAP)
    yb = BELT_435 + ic.m(GAP)
    front_b, front_t = a_line(yb, 0.17) - dz, a_line(win_top, 0.17) - dz
    rear = 0.31 - dz
    ic.poly([(rear, yb), (front_b, yb), (front_t, win_top), (rear, win_top)], to="cut")
    vent = front_b - 0.20
    ic.cut.append(f'<rect x="{ic.x(vent):.2f}" y="{ic.y(win_top):.2f}" width="1.6" height="{ic.y(yb) - ic.y(win_top):.2f}" fill="white"/>')
    ic.line([(0.235 - dz, 1.00), (0.235 - dz, win_top)])                                 # rear shut line
    ic.line([(front_b + 0.05, BELT_435), (front_b + 0.09, 1.12), (1.36 - dz if dz else 1.36, 1.00)])  # front shut line
    if handle:
        ic.rect(0.40 - dz, 0.56 - dz, 1.64, 1.64 + ic.m(3), to="cut")


def glyptodon_icon(zmin, z_rear, z_bed_front, wheelbase, crew_cab):
    ic = Icon(zmin, 2.30, ROOF_435 + 0.15, 0.545)
    rear_axle = FRONT_AXLE - wheelbase
    # Frame rail under the bed, out to the front flare; the bed above it.
    ic.rect(zmin + 0.06, 1.10, 0.80, 0.93)
    bed(ic, zmin, z_bed_front, 1.143, 1.718, ribs=(0.30, 0.52, 0.74))
    ic.line([(z_bed_front + ic.m(GAP / 2), 1.0), (z_bed_front + ic.m(GAP / 2), 1.80)])
    ic.line([(zmin, 1.143 - ic.m(GAP / 2)), (z_bed_front, 1.143 - ic.m(GAP / 2))])
    if crew_cab:   # spare standing upright behind the cab (far side), above the bed side
        ic.rect(z_rear - 0.44, z_rear - 0.08, 1.20, 2.31, r=5, to="white")
        ic.line([(z_rear - 0.46, 1.718 + ic.m(GAP / 2)), (z_rear - 0.06, 1.718 + ic.m(GAP / 2))])
    front_435(ic, z_rear)
    door_435(ic, 0.0)
    if crew_cab:
        door_435(ic, 1.127)
    ic.wheel(FRONT_AXLE)
    ic.wheel(rear_axle)
    return ic


TRUCKS = {
    "Glyptodon": lambda: glyptodon_icon(-3.325, 0.0, -0.03, 3.25, crew_cab=False),
    "Megaloceros": lambda: glyptodon_icon(-3.775, -1.13, -1.16, 3.70, crew_cab=True),
}

if __name__ == "__main__":
    names = sys.argv[1:] or list(TRUCKS)
    for name in names:
        path = f"vehicles/{name.lower()}/icon.svg"
        with open(path, "w") as f:
            f.write(TRUCKS[name]().svg(f"Das {name}"))
        print(path)
