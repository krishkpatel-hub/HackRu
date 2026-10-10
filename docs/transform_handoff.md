> Current 0.7.0 controls and verification: [clutch handoff](clutch_handoff.md). The material below is historical and does not establish a combined 0.7.0 live pass.

> Current 0.6.0 integration: [two-hand selection and precision handoff](enhancement_handoff.md). The dated results below are historical evidence, not a combined 0.6.0 live pass.

# Current extrusion support

Version 0.5.0 adds EXTRUDE; see [Extrusion handoff](extrusion_handoff.md). The following records 0.4.0 transform behavior and verification. Its unsupported-extrusion statements are historical. Live voice verification was subsequently recorded by V in [voice handoff](voice_handoff.md); sponsor attribution remains unconfirmed.

# ROTATE and uniform SCALE handoff (P, add-on 0.4.0)

Extends MOVE baseline `236991fce5af63b8136abe9cf815fcbbcf3548ab` on `feature/blender`. One controller, picker, gesture lifecycle, tracking watchdog, transport writer, and Undo strategy remain in use. No public protocol/callback changes or teammate-module edits. Root README has no horizontal-scale statement and remains unchanged. EXTRUDE is still explicitly unsupported.

## Commands and mapping

Start the existing external Python 3.12 environment:

```sh
cd /Users/krishpatel/HackRu
.venv/bin/python -m companion.main
```

After connecting Blender, type one phrase per line:

```text
create cube
rotate
rotate x
rotate y
rotate z
scale
move
cancel
undo
status
quit
```

These use V's existing parser. Bare `rotate` defaults to world Z. A mode command arms the next pinch; it does not transform the selected object immediately. Start must hit an eligible mesh using its own coordinates. A missed pinch retains the armed mode but requires release before retrying. During DRAGGING, spawn and mode commands are rejected without queuing or changing the active operation. Existing sidebar spawn polling also rejects dragging.

ROTATE uses `theta = rotation_sensitivity * (current_u - start_u)`. Default sensitivity is **2π radians per full normalized viewport width**: moving right by one quarter width rotates +90°, moving left rotates negatively. Positive rotation follows the right-hand rule about the selected **world** X/Y/Z axis; apparent screen direction depends on the view. The original object origin stays fixed. The delta premultiplies the original orientation, preserving nonuniform scale proportions.

SCALE intentionally uses **vertical movement**, as authorized for this milestone: `factor = exp(scale_sensitivity * (start_v - current_v))`. Since v grows downward, upward enlarges and downward shrinks. Default sensitivity is **ln(10) per full normalized viewport height**; up 0.1 height gives about 1.259×, down 0.1 gives about 0.794×. Factor is clamped to **0.1–10 relative to the starting size**. With the default sensitivity, a pinch near the center cannot reach both extremes before the cursor reaches the edge; release/rearm for additional scaling. Every original scale component receives the same positive factor, retaining proportions/signs, orientation, and origin.

Configuration lives only in `addon/air_modeler/transforms.py`: frozen `TransformConfig` and `CONFIG`. Edit those P-owned defaults and rebuild/reinstall the ZIP to tune sensitivity/bounds. Each start captures that immutable config alongside mode, axis, start u/v, original world matrix, original scale-sign convention, locked object ID, and gesture ID. Changing configuration later cannot alter an active gesture. No independent UI copies of these values exist.

Every preview is calculated from the original matrix; frames never accumulate transforms. Returning to start restores the original preview within numerical tolerance. The calculation is equivalent to `T(origin) @ R_world(theta) @ T(-origin) @ M_initial`, or the corresponding uniform scale matrix. The implementation transforms the original basis then retains its translation to avoid cancellation of large translations. Blender's matrix setter can canonicalize reflections into three negative scale channels; `apply_matrix` compensates paired rotation/scale sign flips to retain the original scale-sign pattern without changing the desired world matrix.

The sidebar and cursor text display the armed mode/world rotation axis, angle in **degrees**, or current scale factor. Internally rotation uses radians. Status reports the actual `mode` and `phase` through the unchanged schema; axis and numeric preview values are local display information because status has no axis/amount fields. No fields are overloaded with unrelated text.

## Commit, cancel, and reusable interfaces

Matching end coordinates calculate the final result. The controller restores the original matrix before invoking one short-lived undoable `air_modeler.commit_transform` operator. Meaningful change is an **absolute difference greater than 1e-6 in any world-matrix element**; unchanged releases and previews add no Undo step. A full 360° rotation within this tolerance is likewise unchanged. After a completed or unchanged operation the controller returns to MOVE/IDLE. Cancellation restores baseline and returns to MOVE/NEEDS_RELEASE. Only the missed-start path preserves the armed special mode.

Existing behavior remains: matching gesture IDs only; duplicate starts ignored; absent hand freezes without reading null coordinates; brief recovery can continue the same gesture; sustained loss or a stopped stream cancels after 0.5 seconds. Escape, explicit cancellation, disconnect, target/context loss, file load, and disable restore previews. Undo during dragging restores/cancels first, then reverses the previous completed modeling action and reacquires references. Navigation is blocked during dragging and available while idle. Open the hand visibly after interruption before retrying.

Reusable P-owned interfaces:

```python
# bridge.Client: sole interaction owner
client.set_mode(mode, axis="Z")  # rejects active drag and unsupported mode
client.preview(uv)               # calculates from locked original state
client.cancel_drag()            # restore, MOVE, NEEDS_RELEASE

# transforms.py: no scene mutation except apply_matrix
preview_matrix(initial, mode, axis, start, current, config)  # matrix, radians/factor
changed(initial, final, tolerance)
flatten(matrix)                 # 16 row-major values
apply_matrix(obj, matrix, scale_signs)

# controller restores baseline before this explicit Undo-enabled call
bpy.ops.air_modeler.commit_transform(
    "EXEC_DEFAULT", True,
    target_name=name, matrix=flatten(final), scale_signs=original_scale,
)
```

The old internal `commit_move` operator has been generalized to `commit_transform`; it was not a public wire/callback interface. MOVE now uses the same full-matrix commit. New tools should reuse this controller/lifecycle rather than add timers or managers. The transport, H/V `emit(event)` contracts, and companion flags remain unchanged.

## Update/install and live launch

1. Save user work; disconnect the old add-on, disable/remove it in Preferences, then **quit and restart Blender** to clear cached modules.
2. Build the package:

   ```sh
   cd /Users/krishpatel/HackRu
   .venv/bin/python tools/package_addon.py
   ```

3. **Edit > Preferences > Add-ons > Install from Disk**, select `/Users/krishpatel/HackRu/dist/air_modeler.zip`, enable Air Modeler, and verify **0.4.0**. Never import the ZIP into the user's live Python console.
4. In a disposable scene, use Object Mode and enable Global Undo. Start the companion, open **N > Air Modeler**, click **Connect**, and wait for Connected/READY. Type `create cube`, then arm a mode before pinching the target.
5. For actual hands, use the camera index established by H's rehearsal, or discover it locally:

   ```sh
   .venv/bin/python -m companion.hands --list-cameras
   .venv/bin/python -m companion.main --camera N
   ```

   Replace N with the discovered index. Preview remains false in the worker; thresholds 0.35/0.60 and loss timeout 0.5s are unchanged. Camera permission/setup and optional microphone flags remain documented in `docs/move_handoff.md`. No new dependencies are required.

## Automated verification

Run from the repository root. Do not run bridge checks concurrently: they use port 8765. Each Blender invocation installs the ZIP into isolated resources, opens its own disposable process/scene, and exits without touching `demo.blend` or user preferences.

```sh
.venv/bin/python -m pytest -q
.venv/bin/python tools/package_addon.py
BLENDER_USER_RESOURCES="$(mktemp -d /tmp/air-smoke.XXXXXX)" \
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python-exit-code 1 --python addon/air_modeler/smoke_check.py
BLENDER_USER_RESOURCES="$(mktemp -d /tmp/air-transform.XXXXXX)" \
  /Applications/Blender.app/Contents/MacOS/Blender --factory-startup \
  --python-exit-code 1 --python addon/air_modeler/transform_check.py
BLENDER_USER_RESOURCES="$(mktemp -d /tmp/air-move.XXXXXX)" \
  /Applications/Blender.app/Contents/MacOS/Blender --factory-startup \
  --python-exit-code 1 --python addon/air_modeler/move_check.py
BLENDER_USER_RESOURCES="$(mktemp -d /tmp/air-bridge.XXXXXX)" \
  /Applications/Blender.app/Contents/MacOS/Blender --factory-startup \
  --python-exit-code 1 --python addon/air_modeler/bridge_check.py
```

Verified on Blender 5.2.2 LTS / Python 3.13.13 with external Python 3.12.15:

- Existing 63 tests plus 78 subtests pass; no teammate test changes.
- Packaged primitive installation/geometry/lifecycle regression passes.
- Transform check sends typed commands and complete gestures through the **actual companion runner/TCP/modal timer**. It compares object world matrices against independently constructed origin-pivot matrices for world X/Y/Z on an already rotated, nonuniformly scaled target, in perspective and orthographic views.
- Up/down scaling, invariant position/orientation/proportions, stationary no-drift, return-to-start, final end coordinates, mismatched/duplicate IDs, brief loss, mid-drag mode/spawn rejection, and default MOVE on the next pinch are covered. Transform followed by MOVE has two distinct Undo steps.
- Cancellation, sustained loss, stale input, disconnect, release gate, missed-pinch mode retention, unchanged release with no Undo entry, and Undo during a preview are covered for ROTATE and SCALE.
- Scale bounds use a deliberately higher **test-only** sensitivity so normalized cursor input reaches both bounds. Restoring the global config mid-gesture verifies start-time capture. Negative scale-sign preservation is exercised in Euler, quaternion, and axis-angle rotation representations.
- MOVE and original bridge regressions pass against the generalized commit operator. Original unsupported-mode regression now tests EXTRUDE instead of the newly supported ROTATE.

These are automated foreground Blender checks, **not manual UI or live-hand verification**. H handles live camera/MOVE rehearsal separately. No new camera, microphone, physical-hand, manual Preferences, overlay visual, or physical shortcut rehearsal is claimed here.

## Team rehearsal and limitations

In a disposable scene: type `rotate x`, pinch a previously rotated/nonuniform cube, move horizontally both ways, pause, return to start, then release elsewhere. Confirm world-axis behavior, fixed origin, angle readout and MOVE reset. Repeat Y and bare `rotate` (Z). Type `scale`, move up/down, pause, return to start, and release; confirm factor readout, fixed origin/orientation, and retained proportions. Undo twice after two different operations. Miss a pinch and retry after release with the mode still armed. During each tool try Escape, `cancel`, brief/long tracking loss, and companion shutdown; verify restoration and open-hand rearming. Attempt mode/spawn commands while dragging. Finally pinch without arming a mode and verify ordinary MOVE.

Existing restrictions remain: eligible visible editable unparented meshes without enabled modifiers, constraints, or animation; one ordinary viewport, no Quad View; no multi-hand/depth inference or automatic reconnect. Huge-coordinate scenes and pathological transform precision are not guaranteed by the absolute tolerance. Live gesture sensitivity/comfort, venue lighting and physical UI behavior remain to be rehearsed. EXTRUDE and completion of live speech remain outside this milestone.

Changed P-owned files: add-on `transforms.py`, `bridge.py`, `operators.py`, `panel.py`, `viewport.py`, `__init__.py`, `transform_check.py`, `move_check.py`, `bridge_check.py`, `smoke_check.py`, `HANDOFF.md`; `tools/package_addon.py`; `docs/protocol.md`, `docs/move_handoff.md`, and this handoff. Generated ZIP/environment files remain ignored; unrelated `demo.blend` is excluded.

Next bounded milestone: **single-face extrusion using the same gesture lifecycle**, initially cube/prism faces, one topology creation per gesture, baseline restoration on cancellation, and one Undo step on commit.
