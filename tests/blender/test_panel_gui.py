"""The Werkstatt panel drawn by a real Blender window, undo after the API's calls, and Build and check running in
the background while the window keeps drawing.

Usage: xvfb-run -a blender --factory-startup --python tests/blender/test_panel_gui.py -- [<vehicle>]
Blender refuses writes to objects while it draws a panel, which a headless test with a fake layout can't see, so
this one opens a window (Xvfb's), shows the sidebar, selects an item and lets Blender draw. The panel is also
registered under the sidebar's first tab ("Item"), since a script can't switch tabs; its draw is the real one.
Runs on a scratch checkout. Prints ok/FAIL lines and exits non-zero on any failure.
"""
import os, shutil, sys, tempfile, time, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "blender", "addons"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import werkstatt_addon  # noqa: E402
from werkstatt_addon import api, loop, ui  # noqa: E402
from checkout import scratch_checkout  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
VEHICLE = argv[0] if argv else "megaloceros"
failures, draws, loop_draws = [], [], []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what, flush=True)
    if not cond:
        failures.append(what)


class WERKSTATT_PT_gui_test(ui.WERKSTATT_PT_panel):
    bl_idname = "WERKSTATT_PT_gui_test"
    bl_category = "Item"

    def draw(self, context):
        """The real draw, then what its item box read (the API turns an error into a message, which the panel
        would show as "Select an upgrade item")."""
        try:
            super().draw(context)
            job = loop.current()
            if job is not None:
                loop_draws.append((job.state, job.status()["elapsed"]))
            info = api.placement()
            draws.append(None if info.get("ok") else info.get("error"))
        except Exception as e:
            draws.append(f"{type(e).__name__}: {e}")
            raise


def view3d():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                return window, area
    return None, None


def finish(root):
    try:
        bpy.utils.unregister_class(WERKSTATT_PT_gui_test)
        werkstatt_addon.unregister()
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'all checks passed'}", flush=True)
    os._exit(1 if failures else 0)


def main():
    root = scratch_checkout([VEHICLE])
    os.environ["WERKSTATT_DIR"] = root
    werkstatt_addon.register()
    bpy.utils.register_class(WERKSTATT_PT_gui_test)
    opened = api.open_vehicle(VEHICLE, show=["Winch_01"])
    check(opened["ok"], f"the vehicle opens in a window: {opened.get('error')}")
    api.frame("Winch_01")
    winch = api._empty("Winch_01")
    winch.rotation_mode = "XYZ"                          # as Blender's R key can leave it
    window, area = view3d()
    check(area is not None, "Blender has a 3D view")
    area.spaces.active.show_region_ui = True
    ticks = [0]

    def drawn():
        """After a few redraws: the panel drew to its end, with the item selected, and wrote nothing."""
        ticks[0] += 1
        for a in window.screen.areas:
            a.tag_redraw()
        if ticks[0] < 4:
            return 0.3
        try:
            errors = [d for d in draws if d]
            check(len(draws) > 0, f"Blender drew the panel ({len(draws)} draws)")
            check(not errors, f"the panel draws with an item selected and reads its placement, without errors ({errors[:1]})")
            check(winch.rotation_mode == "XYZ", "drawing left the selected empty's rotation mode alone")
            undo(window, area)
            background_loop(window, root)
        except Exception:
            traceback.print_exc()
            failures.append("exception")
            finish(root)
        return None

    bpy.app.timers.register(drawn, first_interval=0.5)


def background_loop(window, root):
    """Build and check with a fake make on PATH that keeps running: the button starts it and returns, Blender's own
    timer streams the output into the text while the panel keeps drawing the running state, and Cancel stops it.
    Nothing here pumps the job by hand: only the add-on's timer moves output."""
    bin_dir = tempfile.mkdtemp(prefix="werkstatt-fake-make-")
    os.symlink(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_make"), os.path.join(bin_dir, "make"))
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]
    os.environ["FAKE_MAKE_SLOW"] = "1"
    t = time.monotonic()
    started = bpy.ops.werkstatt.run_loop()
    took = time.monotonic() - t
    check(started == {"FINISHED"} and took < 0.5, f"Build and check returns at once ({took:.2f} s)")
    check(not bpy.ops.werkstatt.run_loop.poll(), "the button is off while the loop runs")
    ticks = [0]

    def watch():
        ticks[0] += 1
        for a in window.screen.areas:
            a.tag_redraw()
        text = bpy.data.texts.get(loop.LOG_TEXT)
        streamed = text is not None and "step 3" in text.as_string()
        if not streamed and ticks[0] < 40:
            return 0.2
        try:
            running = [d for d in loop_draws if d[0] == "running"]
            check(streamed, "Blender's timer streams the output into the text while the loop runs")
            check(len(running) >= 2 and running[-1][1] > running[0][1],
                  f"the panel keeps drawing the running state, its time going up ({len(running)} draws)")
            check(bpy.ops.werkstatt.cancel_loop() == {"FINISHED"}, "Cancel stops it")
        except Exception:
            traceback.print_exc()
            failures.append("exception")
        bpy.app.timers.register(stopped, first_interval=0.2)
        return None

    def stopped():
        job = loop.current()
        if job is not None and job.ended is None and ticks[0] < 80:
            ticks[0] += 1
            return 0.2
        check(job is not None and job.state == "cancelled", f"and the loop reads as cancelled: {job.state if job else None}")
        shutil.rmtree(bin_dir, ignore_errors=True)
        finish(root)
        return None

    bpy.app.timers.register(watch, first_interval=0.2)


def undo(window, area):
    """Ctrl+Z after API calls (as an agent makes them over MCP) and after the panel's operators."""
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=window, area=area, region=region):
        start = api.placement("Winch_01")["offset"]
        api.nudge("Winch_01", "y", 1, "cm")
        api.nudge("Winch_01", "y", 1, "cm")
        bpy.ops.ed.undo()
        after = api.placement("Winch_01")
        check(after["ok"] and abs(after["offset"][1] - start[1] - 0.01) < 1e-6, f"undo takes back one API nudge: {after.get('offset')}")
        bpy.ops.werkstatt.nudge(node="Winch_01", axis="z", steps=3, unit="cm")
        bpy.ops.ed.undo()
        after = api.placement("Winch_01")
        check(after["ok"] and abs(after["offset"][2] - start[2]) < 1e-6, f"undo takes back the panel's nudge: {after.get('offset')}")
        bpy.ops.ed.undo()
        check(abs(api.placement("Winch_01")["offset"][1] - start[1]) < 1e-6, "and the API nudge before it")
        # A copy saved, then undone: the scene owns it by rule, so the undo is an unsaved change and the next
        # save takes it out of the file.
        keg = "Parts/Mammoth_CosmeticParts/Visual/Bed/Party_Bed/AccessoryBeerBarrel"
        copy = api.duplicate(keg)["node"]
        api.save()
        path = os.path.join(api._vehicle().folder, "placements.json")
        bpy.ops.ed.undo()
        check(copy not in api.items()["items"].__repr__() and api.unsaved()["unsaved"], "undoing a saved copy is an unsaved change")
        r = api.save()
        check(r["ok"] and (not os.path.isfile(path) or copy not in open(path).read()), f"and the save drops it from the file: {r}")
        # Save, then undo past it, then lose the session's record (Reload Scripts): undo puts the older hash back
        # on the root collection, but the window manager's record, which undo leaves alone, still knows the file.
        api.nudge("Winch_01", "y", 1, "cm")
        api.save()
        bpy.ops.ed.undo()
        api._state["sha"] = {}
        r = api.save()
        check(r["ok"], f"after an undo past a save and a reload, an unchanged file still saves: {r.get('error') or r.get('result')}")


try:
    main()
except Exception:
    traceback.print_exc()
    print("FAILED: exception", flush=True)
    os._exit(1)
