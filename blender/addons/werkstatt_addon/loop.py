"""`make loop` for the open vehicle as a background job, so Blender stays responsive while it builds, runs the gates
and renders the contact sheet (minutes, with Blender processes of its own).

One job at a time. It runs in its own process group (a session on Linux and macOS), so Cancel and cleanup stop
make and everything under it: Python, the gates, the contact sheet's `blender -b`. A reader thread collects the
output; a Blender timer moves it into the werkstatt-loop.log text and redraws the panel. Nothing touches Blender
data from the thread, and the panel's draw only reads the job's state. The job is stopped when the add-on is
unregistered (Reload Scripts too), when another .blend is loaded and when Blender quits.
"""
import atexit, os, signal, subprocess, threading, time

import bpy

LOG_TEXT = "werkstatt-loop.log"
LOG_LINES = 2000            # the text keeps the last lines only; a contact sheet run prints a few hundred
TAIL_LINES = 15
GRACE = 5.0                 # seconds between asking the job's processes to stop and killing them
TICK = 0.25

_job = None


class Job:
    def __init__(self, command, cwd, vehicle):
        self.command, self.vehicle = command, vehicle
        self.header = f"$ {' '.join(command)}   ({cwd})"
        self.started, self.ended, self.code = time.monotonic(), None, None
        self.cancelled_at = None
        self.lines, self.pending, self.lock = [], [], threading.Lock()
        posix = os.name == "posix"
        self.proc = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1,
                                     start_new_session=posix,
                                     creationflags=0 if posix else subprocess.CREATE_NEW_PROCESS_GROUP)
        self.reader = threading.Thread(target=self._read, name="werkstatt-loop-reader", daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.proc.stdout:
            with self.lock:
                self.pending.append(line.rstrip("\n"))
        self.proc.stdout.close()

    def take(self):
        """The lines read since the last call (they are kept in self.lines too, capped)."""
        with self.lock:
            new, self.pending = self.pending, []
        self.lines.extend(new)
        del self.lines[:-LOG_LINES]
        return new

    def poll(self):
        """Notices the end of the job (once the reader has the last of its output) and escalates a cancel."""
        if self.ended is None:
            code = self.proc.poll()
            if code is not None and not self.reader.is_alive():
                self.ended, self.code = time.monotonic(), code
            elif self.cancelled_at is not None and time.monotonic() - self.cancelled_at > GRACE:
                self._signal(kill=True)
        return self.ended is not None

    def cancel(self):
        if self.ended is None and self.cancelled_at is None:
            self.cancelled_at = time.monotonic()
            self._signal(kill=False)

    def _signal(self, kill):
        """Stops the whole process group: make, and the Python and Blender processes it started."""
        try:
            if os.name == "posix":
                os.killpg(self.proc.pid, signal.SIGKILL if kill else signal.SIGTERM)
            elif kill:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)
            else:
                self.proc.send_signal(signal.CTRL_BREAK_EVENT)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def stop(self, wait=GRACE):
        """Cancels and waits for the group to go, killing it after `wait` seconds (cleanup on unregister or quit)."""
        self.cancel()
        deadline = time.monotonic() + wait
        while self.proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        self._signal(kill=True)              # anything left in the group, make's children included
        self.reader.join(timeout=1.0)
        self.poll()

    @property
    def state(self):
        if self.ended is None:
            return "cancelling" if self.cancelled_at is not None else "running"
        if self.cancelled_at is not None:
            return "cancelled"
        return "passed" if self.code == 0 else "failed"

    def status(self):
        end = self.ended if self.ended is not None else time.monotonic()
        return {"state": self.state, "vehicle": self.vehicle, "elapsed": round(end - self.started, 1),
                "code": self.code, "tail": self.lines[-TAIL_LINES:], "log": f"{LOG_TEXT} (Blender text)"}


# ---- Blender side: the text block, the timer, cleanup ----------------------------------------------------------

def _write_text(job):
    block = bpy.data.texts.get(LOG_TEXT) or bpy.data.texts.new(LOG_TEXT)
    block.from_string("\n".join([job.header] + job.lines))


def pump():
    """Moves the job's new output into the text and notices its end; returns the job (None when there is none)."""
    if _job is None:
        return None
    _job.poll()
    if _job.take() or not bpy.data.texts.get(LOG_TEXT):
        _write_text(_job)
    return _job


def _redraw():
    wm = bpy.context.window_manager
    for window in (wm.windows if wm else ()):
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _tick():
    job = pump()
    _redraw()
    return TICK if job is not None and job.ended is None else None


def start(command, cwd, vehicle):
    """Starts a job unless one is running; returns (job, started)."""
    global _job
    if _job is not None and _job.ended is None:
        return _job, False
    _job = Job(command, cwd, vehicle)
    _write_text(_job)
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=TICK)
    return _job, True


def current():
    """The job, read-only (the panel's draw calls this)."""
    return _job


def cancel():
    if _job is not None:
        _job.cancel()
    return _job


def shutdown():
    """Stops a running job and its children and forgets it: unregister, Reload Scripts, a .blend load, quit."""
    global _job
    if _job is not None and _job.ended is None:
        _job.stop()
    _job = None
    try:
        if bpy.app.timers.is_registered(_tick):
            bpy.app.timers.unregister(_tick)
    except (AttributeError, RuntimeError):        # Blender is shutting down
        pass


@bpy.app.handlers.persistent
def _on_load(*_args):
    shutdown()


def register():
    if _on_load not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_on_load)
    atexit.register(shutdown)


def unregister():
    shutdown()
    if _on_load in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load)
    atexit.unregister(shutdown)

