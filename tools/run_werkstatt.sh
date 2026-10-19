#!/bin/sh
# Die Kollektion Werkstatt's launch script. Steam's launch option runs it from the game folder:
#     "./run_werkstatt.sh" %command%
# It starts the game through BepInEx's run_bepinex.sh, with the same arguments. Before that it checks whether
# the game has updated since the last deploy; if so, the plugin is moved aside for this launch (a plugin built
# for the old game can hang it at start, and plain BepInEx regenerates its interop files), and once the game
# has exited the plugin is rebuilt against the new files and installed again, in the background, so Steam sees
# the game stop at once. Each step is logged to BepInEx/werkstatt-launch.log. When the check can't run, the
# game starts through run_bepinex.sh as it always did.
#
# `make bepinex` and `make deploy` install this file into the game folder and set the line below.
WERKSTATT_DIR=""

here=$(cd "$(dirname "$0")" 2>/dev/null && pwd) || here=.
cd "$here" 2>/dev/null || exec ./run_bepinex.sh "$@"
log="$here/BepInEx/werkstatt-launch.log"

# Werkstatt's Python helper, without the library paths Steam sets for the game. $1: a time limit ("" for none).
werkstatt() {
    limit=$1; shift
    $limit env -u LD_PRELOAD -u LD_LIBRARY_PATH GAME_DIR="$here" python3 "$WERKSTATT_DIR/tools/werkstatt.py" "$@"
}

after=no
if [ -n "$WERKSTATT_DIR" ] && [ -f "$WERKSTATT_DIR/tools/werkstatt.py" ] && command -v python3 >/dev/null 2>&1; then
    limit=""
    command -v timeout >/dev/null 2>&1 && limit="timeout 60"
    # Exit 3: the plugin is aside for this launch and gets rebuilt after it. Anything else: start normally.
    werkstatt "$limit" launch-before >>"$log" 2>&1
    [ $? -eq 3 ] && after=yes
fi

[ "$after" = yes ] || exec ./run_bepinex.sh "$@"

./run_bepinex.sh "$@"
status=$?
# Detached, so Steam shows the game as stopped while the plugin builds.
if command -v setsid >/dev/null 2>&1; then
    setsid -f env -u LD_PRELOAD -u LD_LIBRARY_PATH GAME_DIR="$here" \
        python3 "$WERKSTATT_DIR/tools/werkstatt.py" launch-after </dev/null >>"$log" 2>&1
else
    werkstatt "" launch-after </dev/null >>"$log" 2>&1 &
fi
exit $status
