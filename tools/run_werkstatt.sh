#!/bin/sh
# Die Kollektion Werkstatt's launch script, kept so a Steam launch option that names it still works:
#     "./run_werkstatt.sh" %command%
# It starts the game through BepInEx's run_bepinex.sh with the same arguments. Plain `"./run_bepinex.sh" %command%`
# does the same: game updates are handled inside the game by Die Kollektion's loader (BepInEx/plugins/
# DieKollektion.Loader.dll), which rebuilds the plugin for the new version before it loads.
#
# Only an install made before the loader existed (the plugin still in BepInEx/plugins/VehicleMods/) gets a check
# first: after a game update its plugin is moved aside for the launch, since a plugin built for the old game can
# hang it at start; `make deploy` then installs the loader. Logged to BepInEx/werkstatt-launch.log. When the
# check can't run, the game starts through run_bepinex.sh as it always did.
#
# `make bepinex` and `make deploy` install this file into the game folder and set the line below.
WERKSTATT_DIR=""

here=$(cd "$(dirname "$0")" 2>/dev/null && pwd) || here=.
cd "$here" 2>/dev/null || exec ./run_bepinex.sh "$@"
helper="$WERKSTATT_DIR/tools/werkstatt.py"

if [ ! -f "$here/BepInEx/plugins/DieKollektion.Loader.dll" ] && [ -d "$here/BepInEx/plugins/VehicleMods" ] &&
    [ -n "$WERKSTATT_DIR" ] && [ -f "$helper" ] && command -v python3 >/dev/null 2>&1; then
    limit=""
    command -v timeout >/dev/null 2>&1 && limit="timeout 60"
    # The helper runs without the library paths Steam sets for the game.
    $limit env -u LD_PRELOAD -u LD_LIBRARY_PATH GAME_DIR="$here" python3 "$helper" launch-before \
        --log "$here/BepInEx/werkstatt-launch.log" </dev/null >/dev/null 2>&1
fi

exec ./run_bepinex.sh "$@"
