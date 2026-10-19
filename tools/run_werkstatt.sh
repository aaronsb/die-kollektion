#!/bin/sh
# Die Kollektion Werkstatt's launch script. Steam's launch option runs it from the game folder:
#     "./run_werkstatt.sh" %command%
# It starts the game through BepInEx's run_bepinex.sh, with the same arguments. Before that it checks whether
# the game has updated since the last deploy; if so, the plugin is moved aside for this launch (a plugin built
# for the old game can hang it at start, and plain BepInEx regenerates its interop files). Once the game has
# exited, the plugin's DLL is rebuilt against the new files in a separate process and the plugin is installed
# again. Each step is logged to BepInEx/werkstatt-launch.log. When the check can't run, the game starts
# through run_bepinex.sh as it always did.
#
# The rebuild is started with `systemd-run --user` where that works, so it runs outside the game's process
# tree (Steam's reaper is a subreaper and waits for every process below it); elsewhere with setsid, which
# leaves the session but stays below the reaper, so Steam may show the game running until the build ends.
# How Steam reacts to either is untested until a real update.
#
# `make bepinex` and `make deploy` install this file into the game folder and set the line below.
WERKSTATT_DIR=""

here=$(cd "$(dirname "$0")" 2>/dev/null && pwd) || here=.
cd "$here" 2>/dev/null || exec ./run_bepinex.sh "$@"
log="$here/BepInEx/werkstatt-launch.log"
helper="$WERKSTATT_DIR/tools/werkstatt.py"

after=no
if [ -n "$WERKSTATT_DIR" ] && [ -f "$helper" ] && command -v python3 >/dev/null 2>&1; then
    limit=""
    command -v timeout >/dev/null 2>&1 && limit="timeout 60"
    # Exit 3: the plugin is aside for this launch and gets rebuilt after it. Anything else: start normally.
    # The helper runs without the library paths Steam sets for the game.
    $limit env -u LD_PRELOAD -u LD_LIBRARY_PATH GAME_DIR="$here" python3 "$helper" launch-before --log "$log" \
        </dev/null >/dev/null 2>&1
    [ $? -eq 3 ] && after=yes
fi

[ "$after" = yes ] || exec ./run_bepinex.sh "$@"

./run_bepinex.sh "$@"
status=$?
if command -v systemd-run >/dev/null 2>&1 &&
    env -u LD_PRELOAD -u LD_LIBRARY_PATH systemd-run --user --collect --quiet --setenv=GAME_DIR="$here" \
        --setenv=PATH="$PATH" python3 "$helper" launch-after --log "$log" </dev/null >/dev/null 2>&1; then
    :
elif command -v setsid >/dev/null 2>&1; then
    setsid -f env -u LD_PRELOAD -u LD_LIBRARY_PATH GAME_DIR="$here" python3 "$helper" launch-after --log "$log" \
        </dev/null >/dev/null 2>&1
else
    env -u LD_PRELOAD -u LD_LIBRARY_PATH GAME_DIR="$here" python3 "$helper" launch-after --log "$log" \
        </dev/null >/dev/null 2>&1 &
fi
exit $status
