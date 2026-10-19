#!/bin/sh
# Launch Over the Hill through Steam (using the configured launch options), wait until the
# game exits or survives SURVIVE seconds, then report the outcome and log tails.
SURVIVE="${1:-90}"
GAME="${GAME_DIR:-$HOME/.local/share/Steam/steamapps/common/over the hill}"   # set GAME_DIR for another Steam library
PLAYER_LOG="$HOME/.config/unity3d/Funselektor/over the hill/Player.log"
BEPINEX_LOG="$GAME/BepInEx/LogOutput.log"
MAPS="$(dirname "$0")/../data/last_game_maps.txt"

is_running() { pgrep -f "^$GAME/over the hill.x86_64" >/dev/null; }

if is_running; then echo "game already running; quit it first"; exit 1; fi
steam -applaunch 2929250 >/dev/null 2>&1 &

i=0
until is_running; do
    i=$((i + 1)); [ "$i" -gt 60 ] && { echo "game never started"; exit 1; }
    sleep 1
done
echo "started"

i=0
while is_running && [ "$i" -lt "$SURVIVE" ]; do i=$((i + 1)); sleep 1; done
if is_running; then echo "RESULT: alive after ${SURVIVE}s"; else echo "RESULT: exited after ${i}s"; fi

# Keep the latest memory map for the rest of the game's life, so native crash addresses in
# Player.log can be resolved to a module afterwards (tools/resolve_crash.py).
if is_running; then
    pid=$(pgrep -f "^$GAME/over the hill.x86_64")
    (while kill -0 "$pid" 2>/dev/null; do cp "/proc/$pid/maps" "$MAPS.tmp" 2>/dev/null && mv "$MAPS.tmp" "$MAPS"; sleep 5; done) >/dev/null 2>&1 &
    echo "memory map snapshots -> $MAPS"
fi

echo "--- BepInEx log (tail)"; tail -15 "$BEPINEX_LOG"
echo "--- Player.log ($(wc -l < "$PLAYER_LOG") lines)"
if grep -q SIGSEGV "$PLAYER_LOG"; then
    grep -n -B12 -A3 SIGSEGV "$PLAYER_LOG" | head -40
else
    tail -15 "$PLAYER_LOG"
fi
