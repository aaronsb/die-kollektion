#!/bin/sh
# Eval loop step: build a vehicle definition's meshes, render four views, and tile them into
# one contact sheet at renders/<codename>.png.
# Usage: tools/preview_vehicle.sh vehicles/<name>.json
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
definition="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
codename=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['codename'].lower())" "$definition")
mesh_dir="$root/plugins/VehicleMods/vehicles/$codename"
out="$root/renders/$codename"
mkdir -p "$root/renders"

python3 "$root/tools/build_vehicle.py" "$definition"
stamp="$root/renders/.preview_start"
touch "$stamp"
log="$root/renders/$codename.blender.log"
blender -b --factory-startup --python "$root/tools/render_vehicle.py" -- "$definition" "$mesh_dir" "$out" > "$log" 2>&1
# A tile older than this run means Blender failed; never tile stale images.
for view in side top rear three_quarter; do
    if [ ! "$out"_$view.png -nt "$stamp" ]; then
        echo "render of $view failed; see $log" >&2
        grep -E 'Error|Traceback' -A3 "$log" | head -20 >&2
        exit 1
    fi
done
"$root/.venv/bin/python" -I - "$out" <<'EOF'
import sys
from PIL import Image, ImageDraw
out = sys.argv[1]
names = ["side", "top", "rear", "three_quarter"]
tiles = [Image.open(f"{out}_{n}.png") for n in names]
w, h = tiles[0].size
sheet = Image.new("RGB", (w * 2, h * 2))
for i, (tile, name) in enumerate(zip(tiles, names)):
    sheet.paste(tile, ((i % 2) * w, (i // 2) * h))
    ImageDraw.Draw(sheet).text(((i % 2) * w + 12, (i // 2) * h + 10), name, fill=(255, 255, 255))
sheet.save(f"{out}.png")
print(f"contact sheet: {out}.png")
EOF
