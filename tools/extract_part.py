"""Save the pieces of a mesh that match any selection as their own OBJ, for insertPart.

Usage: python3 tools/extract_part.py <source obj> <out obj> '<selection json>' ['<selection json>' ...]
Selections are matches_select dicts, e.g. '{"y": [2.55, 3.5]}'. Positions, UVs and normals are
kept as they are, so the part stays in the source's space.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import meshlib  # noqa: E402


def main():
    source, out, *selections = sys.argv[1:]
    part = meshlib.Obj.read(source)
    obj = meshlib.Obj()
    obj.header = [f"# pieces of {os.path.basename(source)} matching {' or '.join(selections)}"]
    added = meshlib.insert_part(obj, part, include=[json.loads(s) for s in selections])
    obj.write(out)
    print(f"{out}: {added} faces, {len(obj.v)} vertices")


if __name__ == "__main__":
    main()
