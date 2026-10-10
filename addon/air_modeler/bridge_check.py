"""Disposable Blender-native bridge check. Use --factory-startup and isolated user resources.

Exercises the real foreground modal timer and Undo. No scripts or ZIPs are
imported into an existing Blender session. Do not run with --background:
Blender 5.2's redo HUD requires a live viewport for this operator context.
"""

from pathlib import Path
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
from uuid import uuid4

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[2]


def event(shape="cube", identifier=None):
    return {"type": "command", "payload": {"id": identifier or str(uuid4()), "action": "spawn", "shape": shape}}


class Check:
    def __init__(self):
        assert not bpy.app.background, "Run this modal/undo check in a disposable foreground process"
        assert os.environ.get("BLENDER_USER_RESOURCES"), "Isolate Blender user resources before running"
        self.process = None
        self.logs = queue.Queue()
        self.ready = None
        self.last_status = ""
        self.deadline = time.monotonic() + 30
        self.stage = "startup"
        self.sent_at = 0
        self.count = 0
        self.ids = [str(uuid4()) for _ in range(4)]
        self.shapes = ("cube", "sphere", "cylinder", "prism")
        self.saved_session = None
        self.undo_count = 0
        self.cycles = 0
        self.module = None
        self.install()
        self.window = bpy.context.window
        self.window.scene = bpy.data.scenes.new("Disposable Bridge Check")
        self.scene_name = self.window.scene.name
        self.area = next(a for a in self.window.screen.areas if a.type == "VIEW_3D")
        self.region = next(r for r in self.area.regions if r.type == "WINDOW")
        self.window.scene.cursor.location = (2.5, -3.0, 4.25)
        self.start_server()

    def install(self):
        bpy.ops.preferences.addon_install(filepath=str(ROOT / "dist" / "air_modeler.zip"))
        self.module = addon_utils.enable("air_modeler", default_set=False)
        assert self.module is not None
        assert Path(self.module.__file__).resolve().is_relative_to(Path(os.environ["BLENDER_USER_RESOURCES"]).resolve())
        assert Path(self.module.bridge.protocol.__file__).read_bytes() == (ROOT / "shared" / "protocol.py").read_bytes()

    def override(self):
        return bpy.context.temp_override(window=self.window, area=self.area, region=self.region,
                                         scene=self.window.scene, view_layer=self.window.view_layer)

    def connect(self):
        with self.override():
            assert bpy.ops.air_modeler.connect() == {"RUNNING_MODAL"}
        assert self.module.bridge._runtime.timer is not None
        with self.override():
            assert not bpy.ops.air_modeler.connect.poll(), "Duplicate controller allowed"

    def start_server(self):
        self.ready = None
        self.process = subprocess.Popen(
            [shutil.which("python3"), "-u", str(ROOT / "tests" / "bridge_driver.py")],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True,
        )
        def reader(process):
            for line in process.stdout:
                self.logs.put(line.rstrip())
        threading.Thread(target=reader, args=(self.process,), daemon=True).start()

    def send(self, value):
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()
        self.sent_at = time.monotonic()

    def objects(self):
        return list(bpy.data.scenes[self.scene_name].objects)

    def step(self):
        while not self.logs.empty():
            line = self.logs.get_nowait()
            print(f"PEER {line}", flush=True)
            if line.startswith("READY session="):
                self.ready = line.split("=", 1)[1]
            if line.startswith("STATUS"):
                self.last_status = line
            if line.startswith("Listening") and self.stage == "startup":
                self.connect()
                self.stage = "handshake"
        assert time.monotonic() < self.deadline, f"Timeout stage={self.stage}, UI={self.module.bridge.ui_state()}"
        runtime = self.module.bridge._runtime
        if self.stage == "handshake" and self.ready and self.module.bridge.ui_state()[0] == "Connected":
            self.saved_session = self.ready
            self.send(event(self.shapes[0], self.ids[0]))
            self.stage = "spawning"
        elif self.stage == "spawning" and len(self.objects()) == self.count + 1:
            obj = self.window.view_layer.objects.active
            shape = self.shapes[self.count]
            assert obj.type == "MESH" and tuple(obj.location) == (2.5, -3.0, 4.25)
            assert [o for o in self.objects() if o.select_get()] == [obj]
            if shape == "prism":
                assert len(obj.data.vertices) == 6 and len(obj.data.polygons) == 5
            print(f"PASS external spawn {shape}: {obj.name}", flush=True)
            self.count += 1
            if self.count < 4:
                self.send(event(self.shapes[self.count], self.ids[self.count]))
            else:
                self.send(event("cube", self.ids[0]))
                self.stage = "duplicate"
        elif self.stage == "duplicate" and time.monotonic() - self.sent_at > .3:
            assert len(self.objects()) == 4
            assert self.module.bridge._runtime.session.duplicates == 1
            print("PASS duplicate command ID creates no extra object", flush=True)
            self.send({"test": "faults", "event": event("cube")})
            self.stage = "faults"
        elif self.stage == "faults" and len(self.objects()) == 5:
            print("PASS malformed JSON, wrong version/session/shape followed by valid spawn", flush=True)
            with self.override():
                bpy.ops.object.mode_set(mode="EDIT")
            self.send(event("sphere"))
            self.stage = "edit_rejection"
        elif self.stage == "edit_rejection" and "Object Mode" in self.last_status:
            assert len(self.objects()) == 5
            with self.override():
                bpy.ops.object.mode_set(mode="OBJECT")
            self.module.bridge.disconnect("Test disconnect")
            assert runtime.timer is None and runtime.sock.fileno() == -1
            assert runtime.session.session_id is None and runtime.channel.pending_bytes == 0
            self.ready = None
            self.sent_at = time.monotonic()
            self.stage = "reconnect_wait"
        elif self.stage == "reconnect_wait" and time.monotonic() - self.sent_at > .15:
            self.connect()
            self.stage = "reconnected"
        elif self.stage == "reconnected" and self.ready and self.module.bridge.ui_state()[0] == "Connected":
            assert self.ready != self.saved_session
            self.sent_at = time.monotonic()
            self.stage = "no_replay"
        elif self.stage == "no_replay" and time.monotonic() - self.sent_at > .25:
            assert len(self.objects()) == 5
            print("PASS reconnect has fresh session and no stale replay", flush=True)
            # Undo-specific creations after reconnect: no mode-switch undo steps between them.
            self.send(event("cylinder"))
            self.stage = "undo_spawn_one"
        elif self.stage == "undo_spawn_one" and len(self.objects()) == 6:
            self.send(event("prism"))
            self.stage = "undo_spawn_two"
        elif self.stage == "undo_spawn_two" and len(self.objects()) == 7:
            self.stage = "undo"
        elif self.stage == "undo":
            with self.override():
                assert bpy.ops.ed.undo() == {"FINISHED"}
            self.undo_count += 1
            assert len(self.objects()) == 7 - self.undo_count
            print(f"PASS modal-spawn Undo step {self.undo_count}", flush=True)
            if self.undo_count < 2:
                return
            self.stage = "cycles"
        elif self.stage == "cycles":
            old = self.module.bridge._runtime
            addon_utils.disable("air_modeler", default_set=False)
            assert old.timer is None and old.sock.fileno() == -1
            assert self.module.bridge._runtime is None
            assert self.module.bridge.on_load_pre not in bpy.app.handlers.load_pre
            self.module = addon_utils.enable("air_modeler", default_set=False)
            assert bpy.app.handlers.load_pre.count(self.module.bridge.on_load_pre) == 1
            self.cycles += 1
            self.ready = None
            self.sent_at = time.monotonic()
            self.stage = "cycle_wait"
        elif self.stage == "cycle_wait" and time.monotonic() - self.sent_at > .15:
            self.connect()
            self.stage = "cycle_connected"
        elif self.stage == "cycle_connected" and self.ready and self.module.bridge.ui_state()[0] == "Connected":
            if self.cycles < 2:
                self.stage = "cycles"
            else:
                print("PASS repeated enable/disable cleans timers, socket and load handler", flush=True)
                old = self.module.bridge._runtime
                self.module.bridge.on_load_pre(None)
                assert old.timer is None and old.sock.fileno() == -1
                assert self.module.bridge._runtime is None
                print("PASS file-load cleanup handler releases resources", flush=True)
                self.ready = None
                self.sent_at = time.monotonic()
                self.stage = "load_wait"
        elif self.stage == "load_wait" and time.monotonic() - self.sent_at > .15:
            self.connect()
            self.stage = "load_connected"
        elif self.stage == "load_connected" and self.ready and self.module.bridge.ui_state()[0] == "Connected":
            self.area.type = "CONSOLE"
            self.stage = "context_lost"
        elif self.stage == "context_lost" and self.module.bridge._runtime is None:
            assert "viewport" in self.module.bridge.ui_state()[2]
            self.area.type = "VIEW_3D"
            self.region = next(r for r in self.area.regions if r.type == "WINDOW")
            print("PASS lost viewport stops the controller cleanly", flush=True)
            self.ready = None
            self.sent_at = time.monotonic()
            self.stage = "context_wait"
        elif self.stage == "context_wait" and time.monotonic() - self.sent_at > .15:
            self.connect()
            self.stage = "context_connected"
        elif self.stage == "context_connected" and self.ready and self.module.bridge.ui_state()[0] == "Connected":
            self.send({"type": "command", "payload": {"id": str(uuid4()), "action": "set_mode", "mode": "ROTATE", "axis": "X"}})
            self.stage = "unsupported"
        elif self.stage == "unsupported" and "not implemented" in self.last_status:
            print("PASS unsupported modeling action is visibly rejected", flush=True)
            self.send({"test": "quit"})
            self.stage = "shutdown"
        elif self.stage == "shutdown" and self.module.bridge._runtime is None:
            print("PASS server shutdown disconnects Blender", flush=True)
            self.connect()
            self.stage = "absent"
        elif self.stage == "absent" and self.module.bridge._runtime is None:
            assert self.module.bridge.ui_state()[2]
            print("PASS absent server fails without blocking Blender", flush=True)
            self.stage = "finished"

    def close(self):
        if self.module is not None:
            addon_utils.disable("air_modeler", default_set=False)
        if self.process is not None:
            if self.process.poll() is None:
                self.process.stdin.close()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    self.process.wait(timeout=2)


def main():
    check = Check()
    def advance():
        try:
            check.step()
            if check.stage != "finished":
                return .05
            print("PASS FOREGROUND MODAL BRIDGE CHECK", flush=True)
            check.close()
            bpy.ops.wm.quit_blender()
        except Exception:
            traceback.print_exc()
            check.close()
            # Test process only; nonzero exit makes timer callback failures visible.
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(1)
        return None
    bpy.app.timers.register(advance, first_interval=.1)


if __name__ == "__main__":
    main()
