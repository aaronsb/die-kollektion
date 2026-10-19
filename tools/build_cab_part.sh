#!/bin/sh
# Export a cab master's game LODs: meshes/glyptodon/<name>_master.blend -> meshes/glyptodon/<name>_LOD0-3.obj.
# With --derive, first rebuild the far LODs (LOD1-3) of every LOD0 part edited since, and save the master
# (tools/export_master.py). Then rebuild the trucks that use it (tools/make_*.py, tools/build_vehicle.py).
# Usage: tools/build_cab_part.sh meshes/glyptodon/cab_glyptodon_master.blend [--derive]
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
master="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
shift
log="${TMPDIR:-/tmp}/$(basename "$master" .blend).export.log"
blender -b "$master" --python "$root/tools/export_master.py" -- "$@" > "$log" 2>&1 \
    || { grep -E 'Error|Traceback' -A5 "$log" >&2; exit 1; }
grep -E '^(LOD|derived)' "$log"
