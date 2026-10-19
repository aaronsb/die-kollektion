"""Export textures and sprites by name from a game bundle to PNG, from the player's own install.

Usage: .venv/bin/python -I tools/export_images.py <bundle> <out dir> <name> [<name> ...]

The icon and render tools read these from extracted/ (never committed):
  cars bundle:              Mammoth_masks, Mammoth_skin00, Mammoth_AO  -> extracted/textures/
  scriptableobjects bundle: Mammoth_Icon                               -> extracted/icons/Mammoth.png
A name matches a Texture2D or Sprite's m_Name exactly; a Sprite named <Car>_Icon is written as <Car>.png.
"""
import os, sys

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.75f1"


def main():
    bundle, out_dir, names = sys.argv[1], sys.argv[2], set(sys.argv[3:])
    os.makedirs(out_dir, exist_ok=True)
    found = set()
    for obj in UnityPy.load(bundle).objects:
        if obj.type.name not in ("Texture2D", "Sprite"):
            continue
        data = obj.read()
        if data.m_Name not in names or data.m_Name in found:
            continue
        name = data.m_Name.removesuffix("_Icon") if obj.type.name == "Sprite" else data.m_Name
        path = os.path.join(out_dir, f"{name}.png")
        data.image.save(path)
        found.add(data.m_Name)
        print(f"{obj.type.name} {data.m_Name} -> {path}")
    missing = names - found
    if missing:
        sys.exit(f"not found: {', '.join(sorted(missing))}")


if __name__ == "__main__":
    main()
