#!/bin/sh
# Extract the game data the build reads from the player's own install into the gitignored folders:
# the Mammoth donor meshes and its wheel for spare previews (extracted/mammoth/), the mechanic truck
# (extracted/merchant/), the atlas maps and stock icon (extracted/textures/, extracted/icons/), and the
# Mammoth prefab's node facts for contact sheets (extracted/mammoth/nodes.json).
# Nothing under extracted/ is ever committed. Needs a Python with UnityPy (PYTHON, default .venv/bin/python).
# Usage: tools/export_game_data.sh [<game folder>]   (default: GAME_DIR, else Steam's default library)
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
game="${1:-${GAME_DIR:-$HOME/.local/share/Steam/steamapps/common/over the hill}}"
py="${PYTHON:-$root/.venv/bin/python}"
aa="$game/over the hill_Data/StreamingAssets/aa/StandaloneLinux64"
[ -d "$aa" ] || aa="$game/over the hill_Data/StreamingAssets/aa/StandaloneWindows64"
[ -d "$aa" ] || { echo "no Addressables folder under $game; pass the game folder" >&2; exit 1; }
bundle() { set -- "$aa"/"$1"_*.bundle; [ -f "$1" ] || { echo "missing bundle $1" >&2; exit 1; }; echo "$1"; }
cars="$(bundle cars_assets_all)"
objects="$(bundle scriptableobjects_assets_all)"
scene="$(bundle r1_canada_scenes_all)"
cd "$root"

"$py" -I tools/export_car_mesh.py "$cars" Car_Mammoth extracted/mammoth \
    Parts/Mammoth/Mammoth_body_LOD0 Parts/Mammoth/Mammoth_body_LOD1 Parts/Mammoth/Mammoth_body_LOD2 Parts/Mammoth/Mammoth_body_LOD3 \
    Collider/Top Collider/Base \
    Axles/SuspensionRigidFront/SuspensionRigidMesh_LOD0 Axles/SuspensionRigidFront/SuspensionRigidMesh_LOD1 \
    Axles/SuspensionRigidFront/SuspensionRigidMesh_LOD2 Axles/SuspensionRigidFront/SuspensionRigidMesh_LOD3 \
    Axles/SuspensionRigidRear/SuspensionRigidMesh_LOD0 Axles/SuspensionRigidRear/SuspensionRigidMesh_LOD1 \
    Axles/SuspensionRigidRear/SuspensionRigidMesh_LOD2 Axles/SuspensionRigidRear/SuspensionRigidMesh_LOD3
"$py" -I tools/export_named_mesh.py "$scene" extracted/merchant 100 0 -0.071 0.086 \
    Merchant_LOD0 Merchant_LOD1 Merchant_LOD2 Merchant_LOD3
"$py" -I tools/export_named_mesh.py "$cars" extracted/mammoth 1 0 0 0 \
    Mammoth_tyre_LOD0 Mammoth_tyre_LOD1 Mammoth_tyre_LOD2 Mammoth_tyre_LOD3 \
    Mammoth_wheel_LOD0 Mammoth_wheel_LOD1 Mammoth_wheel_LOD2 Mammoth_wheel_LOD3
"$py" -I tools/export_images.py "$cars" extracted/textures Mammoth_masks Mammoth_skin00 Mammoth_AO
"$py" -I tools/export_images.py "$objects" extracted/icons Mammoth_Icon
"$py" -I tools/export_node_facts.py "$cars" Car_Mammoth extracted/mammoth/nodes.json
