"""The Werkstatt sidebar panel (3D view > N panel > Werkstatt) and its operators. Every operator calls api.py with
plain arguments, so scripts can run them too: bpy.ops.werkstatt.nudge(node="BashBar_01", axis="y", steps=2, unit="cm").
The panel's draw only reads (Blender refuses writes to objects while drawing); anything slow (git, reading every
vehicle folder) happens on open, save and the refresh button. Undo steps come from the API calls, so an operator
run from a script undoes like a button press; the operators carry no UNDO flag, which would add a second step."""
import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from . import api, loop, scene, wording

UNIT_ITEMS = [("mm", "1 mm", ""), ("cm", "1 cm", ""), ("dm", "10 cm", "")]
MULT_ITEMS = [(str(n), f"×{n}", "") for n in (1, 5, 10, 20, 50)]
ANGLE_ITEMS = [("0.1", "0.1°", ""), ("0.5", "0.5°", ""), ("1", "1°", ""), ("5", "5°", "")]


NO_VEHICLE = "NONE"


def _report(op, result, done=None):
    if isinstance(result, dict) and not result.get("ok", True):
        op.report({"ERROR"}, result["error"])
        return {"CANCELLED"}
    if done:
        op.report({"INFO"}, done(result))
    refresh_items(bpy.context)
    return {"FINISHED"}


_vehicle_cache = []      # Blender keeps no reference to a dynamic enum's strings; this list does


def refresh_vehicles():
    """Re-reads the checkout's vehicle folders for the dropdown (on open, save and refresh, not on every draw)."""
    result = api.vehicles()
    if not result.get("ok"):
        items = [(NO_VEHICLE, "(no checkout)", result.get("error", ""))]
    else:
        items = [(v["name"], v["codename"] + (" (unreadable)" if v.get("error") else ""),
                  v.get("error") or f"{v['codename']} on the {v['donor']}" + ("" if v["built"] else " (not built)"))
                 for v in result["vehicles"]] or [(NO_VEHICLE, "(no vehicles)", "")]
    _vehicle_cache[:] = items


def _vehicle_items(self, context):
    if not _vehicle_cache:
        refresh_vehicles()
    return _vehicle_cache


class WerkstattItem(bpy.types.PropertyGroup):
    node: StringProperty()
    label: StringProperty()
    detail: StringProperty()        # the row's second column: the slot, a group's options or how the game shows it
    kind: StringProperty()
    shown: BoolProperty()
    mark: StringProperty()          # how the game shows it, when not just with its item (wording.mark)


MARK_ICONS = {"never": "ERROR", "always": "INFO", "tool": "TOOL_SETTINGS"}


def _mark(d):
    return wording.mark(d["in_game"], d.get("tools", ()))


def _select_item(self, context):
    w = context.scene.werkstatt
    if 0 <= w.item_index < len(w.items):
        api.frame(w.items[w.item_index].node) if w.frame_on_select else _select_only(w.items[w.item_index].node)


def _select_only(node):
    empties = scene.editable_empties()
    e = empties.get(node)
    if e is None:
        return
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    e.select_set(True)
    bpy.context.view_layer.objects.active = e


def _ghost_update(self, context):
    scene.set_ghost(self.ghost, self.ghost_offset)


class WerkstattSettings(bpy.types.PropertyGroup):
    vehicle: EnumProperty(name="Vehicle", items=_vehicle_items)
    unit: EnumProperty(name="Step", items=UNIT_ITEMS, default="cm")
    multiplier: EnumProperty(name="Times", items=MULT_ITEMS, default="1")
    angle: EnumProperty(name="Angle", items=ANGLE_ITEMS, default="1")
    slot_filter: StringProperty(name="Slot", description="Show only items of this slot (blank: all)")
    items: CollectionProperty(type=WerkstattItem)
    item_index: IntProperty(update=_select_item)
    frame_on_select: BoolProperty(name="Frame on select", default=True)
    ghost: BoolProperty(name="Ghost of the donor", default=False, update=_ghost_update)
    ghost_offset: FloatProperty(name="Beside by", default=3.0, unit="LENGTH", update=_ghost_update)
    last_clearance: StringProperty()


def refresh_items(context):
    w = getattr(context.scene, "werkstatt", None)
    if w is None:
        return
    w.items.clear()
    result = api.items(slot=w.slot_filter or None)
    if not isinstance(result, dict) or not result.get("ok"):
        return
    for d in result["items"]:
        if d["kind"] not in ("option", "copy", "group", "piece"):
            continue
        item = w.items.add()
        item.node = d["node"]
        item.label = d["node"].rsplit("/", 1)[-1]
        # A slot group's slot is mostly its own name, so it shows its options' count instead; otherwise the Rollcage
        # group and its one option, rollcage, read alike.
        mark = _mark(d)
        if d["kind"] == "group":
            item.detail = f"{d['options']} option{'' if d['options'] == 1 else 's'}"
        else:
            item.detail = wording.MARKS[mark] if mark else d["slot"] or ""
        item.kind = d["kind"]
        item.shown = d["shown"]
        item.mark = mark or ""


class WERKSTATT_UL_items(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        icon_for = {"option": "OBJECT_DATA", "copy": "DUPLICATE", "group": "GROUP", "piece": "MESH_CUBE"}
        row = layout.row(align=True)
        row.label(text=item.label, icon=icon_for.get(item.kind, "DOT"))
        row.label(text=item.detail, icon=MARK_ICONS.get(item.mark, "NONE"))
        if item.kind in ("option", "copy", "piece"):
            op = row.operator("werkstatt.show", text="", icon="HIDE_OFF" if item.shown else "HIDE_ON", emboss=False)
            op.node = item.node
            op.shown = not item.shown


class _NodeOp:
    node: StringProperty(name="Node", description="Node path or unique suffix; blank: the selected item")


class WERKSTATT_OT_open_vehicle(bpy.types.Operator):
    """Build the vehicle's scene from its files (parts, attach points, references, upgrades)"""
    bl_idname = "werkstatt.open_vehicle"
    bl_label = "Open vehicle"
    bl_options = {"REGISTER"}
    name: StringProperty(name="Vehicle")
    force: BoolProperty(name="Drop unsaved changes", description="Open even when the open vehicle has unsaved changes",
                        options={"SKIP_SAVE"})

    def invoke(self, context, event):
        if api.unsaved().get("unsaved"):
            self.force = True
            return context.window_manager.invoke_confirm(self, event, title="Unsaved placements",
                                                         message="The open vehicle has changes that aren't saved. Open anyway and drop them?",
                                                         confirm_text="Drop and open", icon="WARNING")
        return self.execute(context)

    def execute(self, context):
        name = self.name or context.scene.werkstatt.vehicle
        if name == NO_VEHICLE:
            self.report({"ERROR"}, "no vehicle to open: set the Werkstatt folder in the add-on's preferences")
            return {"CANCELLED"}
        result = api.open_vehicle(name, force=self.force)
        refresh_vehicles()
        return _report(self, result, lambda r: f"Opened {r['codename']}: {r['options']} upgrade options, {r['placements']} placements")


class WERKSTATT_OT_nudge(_NodeOp, bpy.types.Operator):
    """Move the item along a game axis (x right, y up, z forward) of its parent's frame"""
    bl_idname = "werkstatt.nudge"
    bl_label = "Nudge"
    bl_options = {"REGISTER"}
    axis: EnumProperty(items=[("x", "x (right)", ""), ("y", "y (up)", ""), ("z", "z (forward)", "")])
    steps: IntProperty(default=1)
    unit: StringProperty(description="mm, cm, dm or m; blank: the panel's step")

    def execute(self, context):
        w = context.scene.werkstatt
        steps = self.steps * (int(w.multiplier) if not self.unit else 1)
        return _report(self, api.nudge(self.node or None, self.axis, steps, self.unit or w.unit))


class WERKSTATT_OT_rotate(_NodeOp, bpy.types.Operator):
    """Turn the item about a game axis of its parent's frame (x pitch, y yaw, z roll), about its pivot"""
    bl_idname = "werkstatt.rotate"
    bl_label = "Rotate"
    bl_options = {"REGISTER"}
    axis: EnumProperty(items=[("x", "pitch (x)", ""), ("y", "yaw (y)", ""), ("z", "roll (z)", "")])
    steps: IntProperty(default=1)
    degrees: FloatProperty(default=0.0, description="Degrees per step; 0: the panel's angle")

    def execute(self, context):
        w = context.scene.werkstatt
        steps = self.steps * (int(w.multiplier) if not self.degrees else 1)
        return _report(self, api.rotate(self.node or None, self.axis, steps, self.degrees or float(w.angle)))


class WERKSTATT_OT_reset(_NodeOp, bpy.types.Operator):
    """Put the item back at its base pose"""
    bl_idname = "werkstatt.reset"
    bl_label = "Reset"
    bl_options = {"REGISTER"}

    def execute(self, context):
        return _report(self, api.reset(self.node or None))


class WERKSTATT_OT_duplicate(_NodeOp, bpy.types.Operator):
    """Add a copy of the selected option or piece, shown whenever the item is fitted"""
    bl_idname = "werkstatt.duplicate"
    bl_label = "Duplicate"
    bl_options = {"REGISTER"}

    def execute(self, context):
        return _report(self, api.duplicate(self.node or None), lambda r: f"Added {r['node']}")


class WERKSTATT_OT_delete_copy(_NodeOp, bpy.types.Operator):
    """Remove the selected copy"""
    bl_idname = "werkstatt.delete_copy"
    bl_label = "Delete copy"
    bl_options = {"REGISTER"}

    def execute(self, context):
        return _report(self, api.delete_copy(self.node or None))


class WERKSTATT_OT_show(_NodeOp, bpy.types.Operator):
    """Show or hide an upgrade option"""
    bl_idname = "werkstatt.show"
    bl_label = "Show"
    bl_options = {"REGISTER"}
    shown: BoolProperty(default=True)

    def execute(self, context):
        return _report(self, api.show(self.node or None, self.shown))


class WERKSTATT_OT_show_slot(bpy.types.Operator):
    """Show or hide every option of a slot"""
    bl_idname = "werkstatt.show_slot"
    bl_label = "Show slot"
    bl_options = {"REGISTER"}
    slot: StringProperty()
    shown: BoolProperty(default=True)

    def execute(self, context):
        return _report(self, api.show_slot(self.slot or context.scene.werkstatt.slot_filter, self.shown))


class WERKSTATT_OT_frame(_NodeOp, bpy.types.Operator):
    """Point the view at the item"""
    bl_idname = "werkstatt.frame"
    bl_label = "Frame"

    def execute(self, context):
        return _report(self, api.frame(self.node or None))


class WERKSTATT_OT_clearance(_NodeOp, bpy.types.Operator):
    """Measure the gap between the item and the body (or how deep it sits inside it)"""
    bl_idname = "werkstatt.clearance"
    bl_label = "Clearance"

    def execute(self, context):
        result = api.clearance(self.node or None)
        if result.get("ok"):
            if (result["intersecting"] or result["inside"]) and result["nudge_by"] is not None:
                axis, sign = result["clear_by"]
                text = f"nudge {axis} {'+' if sign > 0 else '-'}{result['nudge_by'] * 1000:.0f} mm to clear {result['touches']}"
            elif (result["intersecting"] or result["inside"]) and result["penetration"] is not None:
                text = f"{result['penetration'] * 1000:.0f} mm {result['direction']} clears {result['touches']}"
            elif result["intersecting"] or result["inside"]:
                text = f"{'inside' if result['inside'] else 'into'} {result['touches']}: {result.get('note', '')}"
            elif result["gap"] is not None:
                text = f"{result['gap'] * 1000:.0f} mm from {result['touches']}"
            else:
                text = result.get("note", "")
            context.scene.werkstatt.last_clearance = text
        return _report(self, result, lambda r: context.scene.werkstatt.last_clearance)


class WERKSTATT_OT_save(bpy.types.Operator):
    """Write the vehicle's placements.json (only the file; committing it is yours)"""
    bl_idname = "werkstatt.save"
    bl_label = "Save placements"
    force: BoolProperty(name="Overwrite", description="Write even when the file changed on disk since it was read",
                        options={"SKIP_SAVE"})

    def invoke(self, context, event):
        if not self.force and api.changed_on_disk().get("changed"):
            self.force = True                    # Save on a file changed on disk asks, as Overwrite does
        if self.force:
            return context.window_manager.invoke_confirm(
                self, event, title="Overwrite placements.json",
                message="Write the scene's placements over the file, even if it changed on disk since it was read?",
                confirm_text="Overwrite", icon="WARNING")
        return self.execute(context)

    def execute(self, context):
        result = api.save(force=self.force)
        refresh_vehicles()
        return _report(self, result, lambda r: f"{r['file']}: {r['result']} ({r['placements']} placements, {r['copies']} copies"
                                               + (f", {r['kept']} kept from the file" if r["kept"] else "") + ")")


class WERKSTATT_OT_run_loop(bpy.types.Operator):
    """Run `make loop` for the vehicle in the background (build, gates, contact sheet); Blender stays usable"""
    bl_idname = "werkstatt.run_loop"
    bl_label = "Build and check"

    @classmethod
    def poll(cls, context):
        job = loop.current()
        return job is None or job.ended is not None

    def execute(self, context):
        return _report(self, api.start_loop(), lambda r: f"make loop started for {r['vehicle']}; its output is in the {loop.LOG_TEXT} text")


class WERKSTATT_OT_cancel_loop(bpy.types.Operator):
    """Stop the running `make loop` and everything it started"""
    bl_idname = "werkstatt.cancel_loop"
    bl_label = "Cancel"

    @classmethod
    def poll(cls, context):
        job = loop.current()
        return job is not None and job.ended is None

    def execute(self, context):
        return _report(self, api.cancel_loop(), lambda r: "make loop: stopping")


def _loop_summary(job):
    """One line on the loop for the panel (read-only: the panel's draw calls it)."""
    status = job.status()
    if job.ended is None:
        return f"{job.vehicle}: {status['state']}… {status['elapsed']:.0f} s", "TIME"
    last = status["tail"][-1] if status["tail"] else ""
    return {"passed": f"passed: {last}", "failed": f"failed ({job.code}): {last}",
            "cancelled": "cancelled"}[status["state"]], "CHECKMARK" if job.code == 0 else "ERROR"


class WERKSTATT_OT_refresh(bpy.types.Operator):
    """Re-read the item list, the vehicle folders and the checkout's state"""
    bl_idname = "werkstatt.refresh"
    bl_label = "Refresh"

    def execute(self, context):
        api.status(refresh=True)
        refresh_vehicles()
        refresh_items(context)
        return {"FINISHED"}


class WERKSTATT_PT_panel(bpy.types.Panel):
    bl_label = "Werkstatt"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Werkstatt"

    def draw(self, context):
        layout = self.layout
        w = context.scene.werkstatt
        status = api.status()
        box = layout.box()
        if not status.get("ok"):
            box.label(text=status["error"], icon="ERROR")
            return
        box.label(text=status["root"], icon="FILE_FOLDER")
        box.label(text=f"Branch: {status['branch'] or '?'}" + ("  (uncommitted changes)" if status["uncommitted"] else ""), icon="LINKED")
        if status.get("vehicle_root"):
            box.label(text=f"Open vehicle is from {status['vehicle_root']}: open it again to save", icon="ERROR")
        row = layout.row(align=True)
        row.prop(w, "vehicle", text="")
        row.operator("werkstatt.open_vehicle", text="Open", icon="IMPORT")
        row.operator("werkstatt.refresh", text="", icon="FILE_REFRESH")
        if not status.get("vehicle"):
            return
        layout.label(text=f"Open: {status['vehicle']}", icon="AUTO")

        col = layout.column()
        row = col.row(align=True)
        row.prop(w, "slot_filter", text="", icon="VIEWZOOM")
        row.operator("werkstatt.refresh", text="", icon="FILE_REFRESH")
        row = col.row(align=True)
        op = row.operator("werkstatt.show_slot", text="Show slot")
        op.shown = True
        op = row.operator("werkstatt.show_slot", text="Hide slot")
        op.shown = False
        col.template_list("WERKSTATT_UL_items", "", w, "items", w, "item_index", rows=8)
        col.prop(w, "frame_on_select")

        box = layout.box()
        active = context.view_layer.objects.active
        info = api.placement() if active is not None else {"ok": False}
        if info.get("ok"):
            box.label(text=info["node"].rsplit("/", 1)[-1], icon="EMPTY_ARROWS")
            mark = _mark(info)
            if mark:
                box.label(text=info["in_game_note"], icon=MARK_ICONS[mark])
            box.label(text="offset " + ", ".join(f"{v * 100:+.1f}" for v in info["offset"]) + " cm")
            box.label(text="rotation " + ", ".join(f"{v:+.1f}" for v in info["rotation"]) + "°")
        else:
            box.label(text="Select an upgrade item", icon="INFO")
        row = box.row(align=True)
        row.prop(w, "unit", text="")
        row.prop(w, "multiplier", text="")
        for axis, minus, plus in (("x", "Left", "Right"), ("y", "Down", "Up"), ("z", "Back", "Forward")):
            row = box.row(align=True)
            op = row.operator("werkstatt.nudge", text=minus)
            op.axis, op.steps = axis, -1
            op = row.operator("werkstatt.nudge", text=plus)
            op.axis, op.steps = axis, 1
        row = box.row(align=True)
        row.prop(w, "angle", text="")
        for axis, name in (("x", "Pitch"), ("y", "Yaw"), ("z", "Roll")):
            row = box.row(align=True)
            op = row.operator("werkstatt.rotate", text=f"{name} −")
            op.axis, op.steps = axis, -1
            op = row.operator("werkstatt.rotate", text=f"{name} +")
            op.axis, op.steps = axis, 1
        row = box.row(align=True)
        row.operator("werkstatt.clearance", icon="SNAP_FACE")
        if w.last_clearance:
            row.label(text=w.last_clearance)
        row = box.row(align=True)
        row.operator("werkstatt.reset", icon="LOOP_BACK")
        row.operator("werkstatt.duplicate", icon="DUPLICATE")
        row.operator("werkstatt.delete_copy", text="", icon="TRASH")

        row = layout.row(align=True)
        row.prop(w, "ghost")
        row.prop(w, "ghost_offset", text="")
        row = layout.row(align=True)
        row.operator("werkstatt.save", icon="FILE_TICK")
        op = row.operator("werkstatt.save", text="Overwrite", icon="ERROR")
        op.force = True
        row = layout.row(align=True)
        row.operator("werkstatt.run_loop", icon="PLAY")
        job = loop.current()
        if job is not None and job.ended is None:
            row.operator("werkstatt.cancel_loop", icon="CANCEL")
        if job is not None:
            text, icon = _loop_summary(job)
            layout.label(text=text, icon=icon)


class WerkstattPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    werkstatt_dir: StringProperty(name="Werkstatt folder", subtype="DIR_PATH",
                                  description="The Werkstatt checkout to work in; blank: the one this add-on sits in, or WERKSTATT_DIR")

    def draw(self, context):
        self.layout.prop(self, "werkstatt_dir")


CLASSES = (WerkstattItem, WerkstattSettings, WERKSTATT_UL_items, WERKSTATT_OT_open_vehicle, WERKSTATT_OT_nudge,
           WERKSTATT_OT_rotate, WERKSTATT_OT_reset, WERKSTATT_OT_duplicate, WERKSTATT_OT_delete_copy, WERKSTATT_OT_show,
           WERKSTATT_OT_show_slot, WERKSTATT_OT_frame, WERKSTATT_OT_clearance, WERKSTATT_OT_save, WERKSTATT_OT_run_loop, WERKSTATT_OT_cancel_loop,
           WERKSTATT_OT_refresh,
           WERKSTATT_PT_panel, WerkstattPreferences)


def register():
    loop.register()
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.werkstatt = PointerProperty(type=WerkstattSettings)


def unregister():
    loop.unregister()
    del bpy.types.Scene.werkstatt
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
