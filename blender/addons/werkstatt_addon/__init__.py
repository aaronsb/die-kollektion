"""Die Kollektion Werkstatt in Blender: open a vehicle as parts, attach points and upgrade nodes, nudge items into
place, save its placements.json. See docs/blender_addon.md.

The pure model (model.py) loads without Blender, for tests; the scene, API and panel need bpy."""

bl_info = {
    "name": "Die Kollektion Werkstatt",
    "author": "Die Kollektion Werkstatt contributors",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > Werkstatt",
    "description": "Fit upgrade parts on Werkstatt vehicles and save their placements",
    "doc_url": "https://github.com/aaronsb/die-kollektion/blob/main/docs/blender_addon.md",
    "category": "Import-Export",
}

try:
    import bpy  # noqa: F401
except ImportError:          # tests import the model without Blender
    bpy = None

if bpy is not None:
    if "ui" in locals():                     # Reload Scripts: reload the submodules too, model first
        import importlib
        for module in (model, scene, api, ui):  # noqa: F821
            importlib.reload(module)
    from . import model, api, scene, ui  # noqa: F401

    def register():
        ui.register()

    def unregister():
        ui.unregister()
