"""Installed-ZIP native face-browser/AUTO regression through real companion TCP.

Use foreground factory startup with isolated BLENDER_USER_RESOURCES. Generated
coherent observations verify interaction and native Undo, not physical hands.
"""
import importlib.util
import math
import os
from pathlib import Path
import sys
import time
import traceback

import bpy
from mathutils import Vector


spec = importlib.util.spec_from_file_location('face_access_clutch', Path(__file__).with_name('clutch_check.py'))
clutch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clutch)
geometry = clutch.geometry


class Check(clutch.Check):
    def face_uv(self, face):
        view = self.runtime().drag.view
        pixel = self.module.visibility.projected(view, face[2])
        assert pixel is not None, 'test face center must project inside the viewport'
        return self.module.viewport.cursor_uv(view[0], pixel)

    def begin(self):
        yield from self.idle()
        before = geometry.snapshot(self.obj().data)
        yield from self.start(right=clutch.palm())
        self.right_pinch((.9, .1), event='START')
        yield from self.lock('EXTRUDE')
        drag = self.runtime().drag
        assert drag.plane_name == 'AUTO' and drag.plane_axis == 'NONE'
        assert self.obj().mode == 'EDIT'
        assert tuple(self.window.scene.tool_settings.mesh_select_mode) == (False, False, True)
        assert drag.face_index is None and drag.geometry is None
        assert geometry.snapshot(self.obj().data) == before
        assert self.runtime().display_stage() == 'EXTRUDE TARGETING'
        return drag, before

    def browse_to(self, index):
        runtime = self.runtime()
        drag = runtime.drag
        for _ in range(len(drag.browser_candidates) + 1):
            if (drag.targeting_mode == 'BROWSE' and drag.browser_index >= 0
                    and drag.browser_candidates[drag.browser_index][0] == index):
                break
            runtime.browse_face('NEXT')
        else:
            raise AssertionError(('face absent from current browser', index))
        choice = drag.browser_candidates[drag.browser_index]
        assert choice[0] == index and drag.face_index is None
        assert not drag.browser_confirmed and drag.dwell.progress == 0
        assert tuple(runtime.face_outline) == tuple(choice[3])
        assert [f.index for f in drag.edit.bmesh(self.obj()).faces if f.select] == [index]
        return choice

    def confirm(self, index, before):
        drag = self.runtime().drag
        self.runtime().browse_face('CONFIRM')
        assert drag.browser_confirmed and drag.dwell.progress == 0
        # Deliberate browsing and incoming hover are distinct: the cursor is off
        # the object, yet confirmation dwells on the exact browsed face only.
        self.right_pinch((.9, .1))
        yield .28
        assert drag.face_index is None and drag.geometry is None
        assert drag.dwell.face == index and 0 < drag.dwell.progress < 1
        assert self.runtime().display_stage() == 'EXTRUDE DWELLING'
        assert geometry.snapshot(self.obj().data) == before
        yield from self.until(lambda: drag.face_index is not None, 'confirmed face dwell', timeout=4)
        assert drag.face_index == index and drag.geometry is None
        assert drag.amount == 0 and geometry.snapshot(self.obj().data) == before
        assert drag.auto_mapping is not None
        assert drag.pinch_reference == (.9, .1)
        assert self.runtime().display_stage() == 'EXTRUDE LOCKED'
        return drag

    def scalar(self, amount, event='NONE'):
        drag = self.runtime().drag
        mapping = drag.auto_mapping
        raw = amount + math.copysign(mapping.distance_band, amount) if amount else 0
        dx, dy = mapping.direction
        uv = (drag.pinch_reference[0] + dx * raw / mapping.sensitivity / mapping.aspect,
              drag.pinch_reference[1] + dy * raw / mapping.sensitivity)
        assert all(0 <= value <= 1 for value in uv), ('invalid fixture cursor', uv)
        self.right_pinch(uv, event)
        return uv

    def preview(self, amount=.2):
        drag = self.runtime().drag
        index, mapping = drag.face_index, drag.auto_mapping
        self.scalar(amount)
        yield from self.until(lambda: drag.geometry is not None and abs(drag.amount - amount) < 1e-5,
                              'signed AUTO preview')
        assert drag.face_index == index and drag.auto_mapping is mapping
        assert drag.geometry.topology_builds == 1
        assert self.runtime().display_stage() == 'EXTRUDE DRAGGING'
        if amount > 0:
            for vertex, base in zip(drag.geometry.cap_vertices, drag.geometry.base):
                actual = self.obj().matrix_world @ vertex.co - self.obj().matrix_world @ base
                assert (actual - drag.locked_normal * amount).length < 2e-5
        return geometry.snapshot(self.obj().data)

    def finish(self, first='Right'):
        drag = self.runtime().drag
        after = geometry.snapshot(self.obj().data)
        if first == 'Right':
            self.scalar(drag.amount, event='END')
        else:
            self.owner_at((.05, .95), 'END')
        yield from self.until(lambda: self.runtime().drag is None, first + ' first completion')
        assert self.obj().mode == 'OBJECT' and self.obj().select_get()
        assert self.window.view_layer.objects.active == self.obj()
        assert geometry.snapshot(self.obj().data) == after
        assert self.runtime().phase == 'NEEDS_RELEASE'
        yield .12
        assert self.runtime().drag is None, 'held second pinch restarted completion'
        self.owner_at(self.start_uv, 'END')
        self.right_pinch(event='END')
        yield from self.idle()
        assert geometry.snapshot(self.obj().data) == after, 'second release changed committed edit'
        return after

    def cancel(self, before):
        self.line('cancel')
        yield from self.until(lambda: self.runtime().drag is None, 'cancel face selection/preview')
        assert self.obj().mode == 'OBJECT' and geometry.snapshot(self.obj().data) == before
        yield from self.idle()

    def sequence(self):
        assert self.module.bl_info['version'] == (0, 16, 0)
        self.window.scene.cursor.location = (0, 0, 0)
        self.line('create cube')
        yield from self.until(lambda: len(self.objects()) == 1, 'face-access cube')
        self.name = self.window.view_layer.objects.active.name
        rv = self.area.spaces.active.region_3d
        self.area.spaces.active.show_region_ui = True
        rv.view_location = (0, 0, 0)
        rv.view_rotation = Vector((1, 1, 1)).to_track_quat('Z', 'Y')
        rv.view_distance = 12
        yield .2
        baseline = geometry.snapshot(self.obj().data)
        matrix = self.obj().matrix_world.copy()
        all_faces = self.module.extrusion.candidates(self.obj())
        assert len(all_faces) == 6

        for perspective in ('PERSP', 'ORTHO'):
            rv.view_perspective = perspective
            self.area.tag_redraw()
            yield .15
            hidden = set()
            for ordinal, (index, normal, _, _) in enumerate(all_faces):
                drag, before = yield from self.begin()
                assert len(drag.browser_candidates) == 6
                assert {face[0] for face in drag.browser_candidates} == set(range(6))
                hidden |= set(range(6)) - {face[0] for face in drag.face_candidates}
                choice = self.browse_to(index)
                assert (choice[1] - normal).length < 1e-6
                # Browsing is candidate-only, never implicit through-mesh hover.
                self.right_pinch((.85, .85))
                yield .12
                assert drag.browser_candidates[drag.browser_index][0] == index
                assert drag.dwell.progress == 0 and drag.face_index is None
                assert geometry.snapshot(self.obj().data) == before
                yield from self.confirm(index, before)
                frozen = drag.auto_mapping
                try:
                    self.runtime().browse_face('NEXT')
                except RuntimeError:
                    pass
                self.line('rotate')
                yield .12
                assert drag.face_index == index and drag.mode == 'EXTRUDE' and drag.auto_mapping is frozen
                assert geometry.snapshot(self.obj().data) == before
                yield from self.preview(.2)
                yield from self.finish('Right' if ordinal % 2 else 'Left')
                yield from self.undo_mesh(baseline, matrix, 'individual native six-face Undo')
            assert hidden, 'fixture did not exercise any occluded face'
            print('PASS', perspective, 'all six signed AUTO faces incl occluded browser, actual Face Select, no hover overwrite/jump, both releases and one Undo', flush=True)

        # Orbit while targeting to expose every direction. No candidate can use
        # progress accumulated against a prior camera projection.
        for ordinal, (index, _, _, _) in enumerate(all_faces):
            drag, before = yield from self.begin()
            visible = drag.face_candidates[0]
            self.right_pinch(self.face_uv(visible))
            yield .45
            assert drag.dwell.progress > .15 and drag.face_index is None
            self.aim(index)
            rv.view_perspective = 'PERSP' if ordinal % 2 else 'ORTHO'
            self.area.tag_redraw()
            yield .15
            assert self.runtime().drag is drag and drag.face_index is None
            assert drag.dwell.progress < .3 and drag.geometry is None
            face = next(face for face in drag.face_candidates if face[0] == index)
            self.right_pinch(self.face_uv(face))
            yield from self.until(lambda: drag.face_index is not None, 'navigated hover lock', timeout=4)
            assert drag.face_index == index and drag.geometry is None
            assert geometry.snapshot(self.obj().data) == before
            assert drag.auto_mapping.fallback, 'front-normal view should use displayed upward fallback'
            yield from self.preview(.2)
            yield from self.cancel(before)
        print('PASS viewport navigation exposes all six faces in PERSP/ORTHO; fresh dwell, upward fallback, exact cancellation and no targeting deformation', flush=True)

        # Candidate changes revoke confirmation. PREVIOUS and HOVER are explicit
        # switches, and a new face cannot inherit an almost-complete dwell.
        drag, before = yield from self.begin()
        self.runtime().browse_face('NEXT')
        first = drag.browser_candidates[drag.browser_index][0]
        self.runtime().browse_face('CONFIRM')
        yield .6
        assert drag.dwell.progress > .3
        self.runtime().browse_face('NEXT')
        second = drag.browser_candidates[drag.browser_index][0]
        assert first != second and not drag.browser_confirmed and drag.dwell.progress == 0
        self.runtime().browse_face('PREVIOUS')
        assert drag.browser_candidates[drag.browser_index][0] == first
        self.runtime().browse_face('HOVER')
        assert drag.targeting_mode == 'HOVER' and drag.dwell.progress == 0
        yield from self.cancel(before)
        print('PASS browser Next/Previous/Hover switches reset confirmation and dwell without geometry', flush=True)

        # Fresh geometry indices after a committed extrusion: cap and one new
        # side each lock/drag through the controller and Undo separately.
        top = max(all_faces, key=lambda item: item[1].z)[0]
        drag, before = yield from self.begin()
        self.browse_to(top)
        yield from self.confirm(top, before)
        yield from self.preview(.4)
        first_mesh = yield from self.finish()
        faces = self.module.extrusion.candidates(self.obj())
        assert len(faces) == 10
        cap = next(face for face in faces if face[1].z > .99 and face[2].z > 1.39)
        side = next(face for face in faces if abs(face[1].z) < .01
                    and min(point.z for point in face[3]) > .99
                    and max(point.z for point in face[3]) > 1.39)
        for face in (cap, side):
            drag, before = yield from self.begin()
            assert len(drag.browser_candidates) == 10
            self.browse_to(face[0])
            yield from self.confirm(face[0], before)
            yield from self.preview(.15)
            yield from self.finish()
            yield from self.undo_mesh(first_mesh, matrix, 'new face own Undo')
        yield from self.undo_mesh(baseline, matrix, 'earlier extrusion remains separately undoable')
        print('PASS committed cap and newly generated side enumerate/lock/extrude with independent consecutive Undo', flush=True)

        for scale in ((1.6, .7, 1.2), (-1.6, .7, 1.2), (-1.6, -.7, -1.2)):
            self.obj().rotation_euler = (.31, -.47, .68)
            self.obj().scale = scale
            self.window.view_layer.update()
            rv.view_rotation = Vector((1, 1, 1)).to_track_quat('Z', 'Y')
            rv.view_location = (0, 0, 0)
            self.area.tag_redraw()
            yield .12
            transformed = self.obj().matrix_world.copy()
            with self.override():
                bpy.ops.ed.undo_push(message='Disposable face mapping transform')
            drag, before = yield from self.begin()
            face = min(drag.browser_candidates, key=lambda item: item[1].x)
            self.browse_to(face[0])
            yield from self.confirm(face[0], before)
            assert (drag.locked_normal - face[1]).length < 1e-6
            assert all((self.obj().matrix_world @ v.co - face[2]).dot(face[1]) < 1e-5
                       for v in drag.source_mesh.vertices), 'world normal points inward under reflection'
            yield from self.preview(.2)
            yield from self.finish()
            yield from self.undo_mesh(before, transformed, 'transformed outward native Undo')
        print('PASS rotated nonuniform/single-negative/triple-negative world normals and exact outward AUTO distance with one Undo', flush=True)

        self.auto_frames = False
        self.line('quit')
        yield from self.until(lambda: self.runtime() is None, 'face-access clean shutdown')
        yield from self.until(lambda: self.process.poll() is not None, 'companion exit')
        print('PASS face-access controller/TCP shutdown; physical camera acceptance NOT RUN', flush=True)


check = Check() if __name__ == '__main__' else None
if check is not None:
    check.deadline = time.monotonic() + 300


def advance():
    try:
        return check.step()
    except Exception:
        traceback.print_exc()
        if check.process:
            check.process.terminate()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)


if check is not None:
    bpy.app.timers.register(advance, first_interval=.2)
