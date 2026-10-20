"""A scratch Werkstatt checkout for the Blender tests: the named vehicles' folders copied (their builds and the
extracted data linked, read-only), so a test never writes to the real checkout."""
import os, shutil, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def scratch_checkout(names):
    # A path past 63 characters, like a real checkout's: Blender limits property names to that, and a name built
    # from the path once broke save.
    tmp = tempfile.mkdtemp(prefix="werkstatt-addon-a-checkout-path-longer-than-blender-allows-in-a-property-name-")
    open(os.path.join(tmp, "Makefile"), "w").close()
    os.makedirs(os.path.join(tmp, "vehicles"))
    os.symlink(os.path.join(ROOT, "extracted"), os.path.join(tmp, "extracted"))
    for name in names:
        src = os.path.join(ROOT, "vehicles", name)
        dst = os.path.join(tmp, "vehicles", name)
        if not os.path.isfile(os.path.join(src, "build", "body_LOD0.obj")):
            continue
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("build", "contact", "placements.json"))
        os.symlink(os.path.join(src, "build"), os.path.join(dst, "build"))
    return tmp
