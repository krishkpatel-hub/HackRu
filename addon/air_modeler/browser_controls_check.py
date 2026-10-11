"""Installed-ZIP modal browser dispatch with real TCP and native cancellation.

Generated event objects exercise the actual modal handler and overlay hitboxes;
PASS_THROUGH assertions test dispatch, not physical mouse/keyboard operation.
Run a disposable foreground Blender with isolated BLENDER_USER_RESOURCES.
"""
import importlib.util
import os
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace

import bpy
from mathutils import Vector


spec = importlib.util.spec_from_file_location('browser_face_helpers', Path(__file__).with_name('face_access_check.py'))
face = importlib.util.module_from_spec(spec)
spec.loader.exec_module(face)
clutch, geometry = face.clutch, face.geometry


class Check(face.Check):
    def dispatch(self, event_type, **changes):
        runtime = self.runtime()
        left, bottom, right, top = self.module.viewport.cursor_bounds(runtime.drag.view[0])
        event = dict(type=event_type, value='PRESS', ctrl=False, shift=False,
                     alt=False, oskey=False,
                     mouse_x=self.region.x+(left+right)/2,
                     mouse_y=self.region.y+(bottom+top)/2)
        event.update(changes)
        operator = SimpleNamespace(runtime=runtime)
        with self.override():
            return self.module.bridge.AIRMODELER_OT_connect.modal(operator, bpy.context, SimpleNamespace(**event))

    def button(self, action):
        buttons = self.module.viewport.browser_buttons(self.runtime())
        rectangle = next(rect for key, _, rect in buttons if key == action)
        x0, y0, x1, y1 = rectangle
        return self.dispatch('LEFTMOUSE', mouse_x=self.region.x+(x0+x1)/2,
                             mouse_y=self.region.y+(y0+y1)/2)

    def sequence(self):
        assert self.module.bl_info['version'] == (0, 16, 0)
        self.window.scene.cursor.location = (0, 0, 0)
        self.line('create cube')
        yield from self.until(lambda: len(self.objects()) == 1, 'browser-controls cube')
        self.name = self.window.view_layer.objects.active.name
        baseline = geometry.snapshot(self.obj().data)
        matrix = self.obj().matrix_world.copy()
        rv = self.area.spaces.active.region_3d
        rv.view_location = (0, 0, 0)
        rv.view_rotation = Vector((1, 1, 1)).to_track_quat('Z', 'Y')
        rv.view_distance = 12
        rv.view_perspective = 'ORTHO'
        self.area.spaces.active.show_region_ui = True
        self.area.tag_redraw()
        yield .15
        self.window.scene.cursor.location = (4, 0, 0)
        self.line('create sphere')
        yield from self.until(lambda: len(self.objects()) == 2, 'browser Undo sentinel')
        sentinel = self.window.view_layer.objects.active.name

        drag, before = yield from self.begin()
        assert self.dispatch('RIGHT_BRACKET') == {'RUNNING_MODAL'}
        assert drag.targeting_mode == 'BROWSE' and drag.browser_index == 0
        assert self.dispatch('LEFT_BRACKET') == {'RUNNING_MODAL'}
        assert drag.browser_index == len(drag.browser_candidates)-1
        assert self.dispatch('RET') == {'RUNNING_MODAL'} and drag.browser_confirmed
        yield .28
        assert 0 < drag.dwell.progress < 1 and drag.face_index is None
        assert self.dispatch('RIGHT_BRACKET') == {'RUNNING_MODAL'}
        assert drag.browser_index == 0 and drag.dwell.progress == 0 and not drag.browser_confirmed
        assert self.dispatch('H') == {'RUNNING_MODAL'}
        assert drag.targeting_mode == 'HOVER' and drag.dwell.progress == 0
        assert geometry.snapshot(self.obj().data) == before
        print('PASS keyboard ]/[ Enter/H dispatch selects exact browser candidates and resets confirmation without geometry', flush=True)

        assert self.button('NEXT') == {'RUNNING_MODAL'} and drag.browser_index == 0
        assert self.button('PREVIOUS') == {'RUNNING_MODAL'}
        assert drag.browser_index == len(drag.browser_candidates)-1
        assert self.button('CONFIRM') == {'RUNNING_MODAL'} and drag.browser_confirmed
        yield .28
        assert 0 < drag.dwell.progress < 1
        held = dict(self.hands['Right'])
        self.capture(right=clutch.absent())
        missing_frame = self.capture_id
        yield from self.until(lambda: self.runtime().frame_id >= missing_frame,
                              'invalid browser hand delivered', timeout=.35)
        assert drag.dwell.face is None and drag.dwell.progress == 0 and drag.face_index is None
        held['event'] = 'NONE'
        self.capture(right=held)
        yield .12
        assert drag.face_index is None and drag.dwell.progress < .3
        assert self.button('NEXT') == {'RUNNING_MODAL'}
        assert drag.dwell.progress == 0 and not drag.browser_confirmed
        assert self.button('HOVER') == {'RUNNING_MODAL'} and drag.targeting_mode == 'HOVER'
        assert geometry.snapshot(self.obj().data) == before
        print('PASS rendered overlay hitboxes dispatch Previous/Next/Confirm/Hover; invalid hand revokes dwell without counting loss time', flush=True)

        # Exercise dispatch from the usable viewport; these events are not
        # forwarded into Blender by this harness. Camera movement itself is
        # covered by face_access_check's actual view-orientation changes.
        for event, modifiers in (('NUMPAD_1', {}), ('NUMPAD_3', {}), ('NUMPAD_7', {}),
                                 ('NUMPAD_1', {'ctrl': True}), ('MIDDLEMOUSE', {}),
                                 ('MIDDLEMOUSE', {'shift': True}), ('N', {})):
            self.dispatch('RIGHT_BRACKET')
            self.dispatch('RET')
            assert self.dispatch(event, **modifiers) == {'PASS_THROUGH'}, (event, modifiers)
            assert self.runtime().drag is drag and drag.dwell.progress == 0 and drag.face_index is None
        for event, modifiers in (('N', {'shift': True}), ('NUMPAD_PLUS', {'ctrl': True}),
                                 ('NUMPAD_MINUS', {'ctrl': True}), ('NUMPAD_0', {'ctrl': True, 'alt': True})):
            assert self.dispatch(event, **modifiers) == {'RUNNING_MODAL'}, (event, modifiers)
            assert self.runtime().drag is drag and geometry.snapshot(self.obj().data) == before
        print('PASS normal view navigation passes/reset dwell; edit-normal, select-more/less and camera-move shortcuts blocked', flush=True)

        sidebar = next(region for region in self.area.regions if region.type == 'UI' and region.width > 1)
        point = dict(mouse_x=sidebar.x+sidebar.width/2, mouse_y=sidebar.y+sidebar.height/2)
        assert self.dispatch('WHEELUPMOUSE', **point) == {'PASS_THROUGH'}
        assert self.runtime().drag is None and self.obj().mode == 'OBJECT'
        assert geometry.snapshot(self.obj().data) == baseline
        yield from self.idle()
        drag, before = yield from self.begin()
        assert self.dispatch('RIGHT_BRACKET') == {'RUNNING_MODAL'}
        assert self.dispatch('LEFTMOUSE', **point) == {'PASS_THROUGH'}
        assert self.runtime().drag is None and self.obj().mode == 'OBJECT'
        assert geometry.snapshot(self.obj().data) == baseline
        yield from self.idle()
        self.line('undo')
        yield from self.until_stable(lambda: sentinel not in self.window.scene.objects
                                    and geometry.snapshot(self.obj().data) == baseline
                                    and clutch.same(self.obj().matrix_world, matrix),
                                    'native Undo skips browser/selection cancellation', settle=.15)
        assert self.obj().mode == 'OBJECT'
        print('PASS sidebar wheel/click restore before pass-through; browsing/early cancellation creates no native Undo step', flush=True)

        drag, before = yield from self.begin()
        original = drag.source_mesh
        old = self.runtime()
        assert self.dispatch('RIGHT_BRACKET') == {'RUNNING_MODAL'}
        assert self.obj().mode == 'EDIT'
        # Invalidate the captured scene identity and deliver the UI event in
        # this same main-thread callback, before a TIMER can diagnose it. Keep
        # the native scene intact so ownership permits an exact Object Mode
        # restoration. No automatic/network observation may mask this path.
        self.auto_frames = False
        old.scene_name = self.scene_name + ' (invalid captured context)'
        assert self.dispatch('LEFTMOUSE') == {'CANCELLED'}
        assert self.runtime() is None and old.drag is None
        assert old.timer is None and old.draw_handler is None and old.face_draw_handler is None
        assert old.sock.fileno() == -1
        assert drag.edit.closed and drag.edit._bm is None
        assert self.obj().mode == 'OBJECT' and self.obj().data == original
        assert geometry.snapshot(self.obj().data) == before == baseline
        assert self.obj().select_get() and self.window.view_layer.objects.active == self.obj()
        print('PASS context loss before TIMER cancels LEFTMOUSE dispatch, restores native Object Mode baseline and frees controller/Edit resources', flush=True)

        self.line('quit')
        yield from self.until(lambda: self.runtime() is None, 'browser controls shutdown')
        yield from self.until(lambda: self.process.poll() is not None, 'browser controls peer exit')


check = Check() if __name__ == '__main__' else None
if check is not None:
    check.deadline = time.monotonic() + 45


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
