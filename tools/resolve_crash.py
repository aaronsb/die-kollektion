"""Resolve the native stack frames Unity printed in Player.log to module + offset.

Usage: python3 resolve_crash.py [Player.log] [maps snapshot]
The maps snapshot is written by launch_test.sh while the game runs.
"""
import os, re, sys

here = os.path.dirname(os.path.abspath(__file__))
log = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.config/unity3d/Funselektor/over the hill/Player.log")
maps = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, "..", "data", "last_game_maps.txt")

regions = []
for line in open(maps):
    parts = line.split()
    if len(parts) < 6: continue
    lo, hi = (int(x, 16) for x in parts[0].split("-"))
    regions.append((lo, hi, int(parts[2], 16), parts[5]))

text = open(log, errors="replace").read()
crash = text.rfind("Received signal")
print(text[crash:text.find("\n", crash)])
for m in re.finditer(r"#(\d+)\s+0x([0-9a-f]+) in (\S+)", text[crash:]):
    addr = int(m.group(2), 16)
    hit = next(((lo, off, path) for lo, hi, off, path in regions if lo <= addr < hi), None)
    where = f"{os.path.basename(hit[2])}+0x{addr - hit[0] + hit[1]:x}" if hit else "?"
    print(f"#{m.group(1):>2} 0x{addr:x} {m.group(3):12} {where}")
