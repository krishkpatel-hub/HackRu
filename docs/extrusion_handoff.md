# Single-face EXTRUDE handoff — P, version 0.5.0

Implemented on `feature/blender` after the 0.4.0 transform milestone `82da74c` and voice documentation merge `e40e1dc`. This adds geometry editing to the existing controller, picker, gesture lifecycle, loss watchdog, and restore-then-commit Undo strategy. No protocol, callback, teammate implementation, or root README changes. The teammates' 0.4.0 camera/UI rehearsal remains separate evidence.

## Run and update

The existing external Python 3.12 environment and dependencies are unchanged. Tested Blender is **5.2.2 LTS**, bundled Python **3.13.13**; companion Python **3.12.15**. No camera/audio dependencies belong inside Blender.

```sh
cd /Users/krishpatel/HackRu
.venv/bin/python tools/package_addon.py
.venv/bin/python -m companion.main
```

1. Save user work. Disconnect the old add-on; disable/remove it in Preferences. **Quit and restart Blender** to clear cached 0.4.0 modules.
2. In **Edit > Preferences > Add-ons > Install from Disk**, install `/Users/krishpatel/HackRu/dist/air_modeler.zip`. Enable Air Modeler and verify **0.5.0**. Do not import the ZIP into a live console.
3. Use a disposable scene, Object Mode, one ordinary VIEW_3D, and Global Undo enabled. Open **N > Air Modeler**, click **Connect**, and wait for Connected/READY.
4. Type `create cube` or `create triangular prism`, then `extrude`. Existing `move`, `rotate x/y/z`, `scale`, `cancel`, and `undo` remain available.
5. An eligible hovered face gets a yellow outline. Sidebar feedback identifies the face or explains rejection. Pinch over that face; move upward to extend outward; lower toward the start to reduce distance; release to commit. The next gesture defaults to MOVE, so type `extrude` again to extend the new cap.
6. Escape or `cancel` restores baseline. `undo` during a preview cancels first, then undoes the previous completed action. After interruption, visibly open the hand before retrying.

For live hands, use the camera index discovered on the demo laptop, not a hardcoded teammate index:

```sh
.venv/bin/python -m companion.hands --list-cameras
.venv/bin/python -m companion.main --camera N
```

Replace N with the actual index. Existing `preview=False`, thresholds 0.35/0.60, and 0.5-second loss timeout are unchanged. Optional `--mic` uses the existing voice worker; typed fallback remains available. V's live voice verification is recorded in `docs/voice_handoff.md` and is teammate evidence, not a new extrusion end-to-end speech check. Realtime API access works; sponsor attribution remains unconfirmed.

## Distance and supported geometry

Configuration is centralized in `addon/air_modeler/extrusion.py`, frozen `ExtrusionConfig` / `CONFIG`:

| Setting | Default |
| --- | --- |
| sensitivity | 4 Blender world units per normalized viewport height |
| maximum_distance | 4 world units per gesture |
| negligible_distance | 0.00001 world units |
| geometry_tolerance | 0.000001 mesh-local units for face eligibility |

`distance = clamp(sensitivity * (start_v - current_v), 0, maximum_distance)`. Upward extends along the captured outward normal. Downward returns toward zero; inward extrusion is not supported. Starting at viewport center leaves about half a viewport of upward travel, so the default reachable distance there is about 2 units. Config is captured at start; source edits require rebuilding/reinstalling the package.

Initially supported targets are **flat, strictly convex triangular or quad faces** on closed, consistently wound outward meshes, including cube faces, prism triangular caps, prism side faces, and newly extruded caps. Eligibility does not depend on object names or initial face counts. The chosen face must be on a supporting plane: all original mesh vertices lie on or behind it. This conservative restriction prevents the new outward prism from crossing the rest of the object; recessed faces are rejected. It is not a general arbitrary-mesh extrusion tool or a global self-intersection repair/checker.

Existing editable/visible/unparented/no-constraint/no-animation restrictions remain. EXTRUDE additionally rejects:

- Enabled modifiers, so evaluated topology cannot be confused with original faces.
- Shared, linked, library-override, or fake-user mesh data; make a dedicated local single-user mesh first.
- Shape keys, mesh animation, and custom split normals.
- Singular or reflected transforms; rotation and positive-determinant nonuniform scaling are supported.
- Open/inconsistently wound/nonmanifold or degenerate geometry, invalid indices, nonfinite coordinates, nonplanar/concave target faces, and unsupported custom attribute types.

Supported BMesh-compatible attribute types are float, integer, vector, float/byte color, boolean, and float2/UV data. Blender's internal structural attributes are handled by its mesh/BMesh conversion. Existing point-float values, face-integer values, UV data and material assignments are covered by checks; other custom-layer combinations require separate rehearsal. No unrelated source datablock is edited.

Original face picking builds a BVH directly from the original mesh's vertex/polygon arrays. It never consumes an evaluated object face index. Before mutation, the index is bounds-checked and the BMesh face's original vertex loop is verified against that mesh polygon. The start event repicks using its own u/v; it does not trust old hover state. A missed/rejected pinch retains EXTRUDE armed, requires release, and cannot acquire another face while held.

For linear world transform A, the captured normal is `normalize(A.inverted().transposed() @ local_normal)`. A world displacement of `world_normal * distance` becomes `A.inverted() @ world_displacement` in local space. Only the new cap vertices are moved from saved local base coordinates; the object matrix never changes. World-distance assertions cover rotated and nonuniformly scaled targets.

## Topology, ownership and Undo

The installed Blender 5.2 BMesh operator was probed before gesture integration. With only a single face in `geom`, `extrude_face_region(..., use_keep_orig=False)` **retains the original interior cap**. Production explicitly deletes that original face with `context='FACES_ONLY'` after identifying the new cap; original boundary vertices/edges remain attached to the surrounding shell and side walls.

One gesture owns one isolated preview mesh copy and one BMesh. The original source mesh remains unchanged. The new cap vertices are selected explicitly from the operator's returned BMVerts; exactly one returned face must use precisely that set. No other returned vertices are moved. Topology is created once; subsequent frames set only cap coordinates from saved bases, update normals, and write into the same preview copy. Zero-distance previews temporarily contain coincident cap/boundary vertices and zero-area side walls, but such topology is never committed.

Cancellation reattaches the original mesh, frees the BMesh, clears all BMFace/BMVert references, and removes the preview datablock. Baseline topology, coordinates, tested attributes/materials, and original transform are recovered. If the target was deleted, the preview is freed without dereferencing deleted object RNA; the original user mesh is not destroyed by cancellation. On Edit Mode interruption, restoration first exits Edit Mode to flush Blender's cached edit BMesh, swaps back the source, then reenters the requested mode on the baseline. This prevents a later Edit Mode exit from writing preview geometry into the source.

On matching end, final coordinates determine distance. The controller first restores/disposes the preview, then calls a **geometry-specific** undoable `air_modeler.commit_extrusion`. It recreates the same extrusion from the original face and distance in another isolated copy. Before adopting it, positive results must pass consistent manifold winding, nonzero-area, cap-normal and expected signed-volume checks. Success transfers that completed copy to the object, frees BMesh references, and removes the now-unused single-user baseline mesh. Blender Undo restores the complete prior datablock/state. This avoids a growing orphan-mesh collection after repeated commits. Exceptions restore source and remove owned preview resources.

Each positive completed extrusion creates one modeling Undo step and returns to MOVE/IDLE. Zero/negligible end distance restores source, creates no Undo step, and returns to MOVE/IDLE. Interrupted gestures return to MOVE/NEEDS_RELEASE. Previews never push Undo. Matching IDs, duplicate suppression, immediate absent-hand freeze, short-loss resume, 0.5-second loss/stale cancellation, navigation blocking, and mid-drag spawn/mode rejection are inherited from the same controller.

Reusable interfaces:

```python
# extrusion.py; no timers, transport, mode manager or Undo pushes
face_info(obj, face_index, config)          # validation and original local face geometry
ray_hit(obj, world_origin, world_direction) # original-mesh point/index
preview = Preview(obj, face_index, config) # owns isolated mesh + BMesh
preview.update(world_distance)             # same topology, cap coordinates only
preview.outline()                          # copied world points for passive drawing
preview.restore(obj_or_none)               # reattach baseline, dispose resources
commit(obj, face_index, world_distance, config) # transactional final geometry helper

# controller calls only after restoring baseline; explicit Undo step
bpy.ops.air_modeler.commit_extrusion(
    'EXEC_DEFAULT', True, target_name=name, face_index=index,
    distance=amount, maximum_distance=config.maximum_distance,
    negligible_distance=config.negligible_distance,
)
```

`commit_transform` remains exclusively for MOVE/ROTATE/SCALE. Geometry is not committed by changing an object matrix. No BMesh references survive restore, commit, or Undo; each later operation reacquires mesh/object data.

## Validation performed

Automated checks use isolated resources and disposable processes/scenes. No saved user scene, live installed add-on, or Preferences were modified.

- **63 Python tests and 78 subtests** passed.
- Initial fixed-distance proof: all six cube faces produce 12 vertices, 20 edges, 10 faces, volume 10 from a side-2 cube with 0.5-unit extrusion. Checked cap normal against original outward normal, no old face at the interior cap center, positive face areas, two incident faces per edge, contiguous winding, and no duplicate/loose elements.
- Installed-package geometry checks cover fixed cap topology, vertex-float and face-integer attributes, UV baseline restoration, material slots/cap assignments, constant preview counts, no mesh-count growth, rejection before mutation, injected commit-update failure, and deleted-target cleanup.
- **Actual companion runner + TCP + Blender modal timer** checks cover cube faces, prism triangular caps and side faces, fixed preview topology across repeated updates, reducing to zero, final release coordinates, world-distance/origin assertions on rotated and nonuniformly scaled objects, duplicate/mismatched IDs, brief-loss freeze, and mid-drag command rejection.
- Two successive extrusions include the newly created cap. Each Undo restores one entire extrusion and its attributes. Positive results are inspected for manifold edges, winding, positive signed volume, nondegenerate faces and absence of duplicate/loose geometry; manifold edge counts alone are not the evidence.
- Exact source restoration and resource counts pass for cancel, sustained loss, stale stream, disconnect, disable/re-enable, load-pre hook, viewport loss and Edit Mode interruption. Missed pinch, release gate, shared-data TCP rejection, zero-distance release with no Undo entry, and Undo during an active extrusion are covered.
- Packaged primitive, real-TCP MOVE, ROTATE/SCALE, and original bridge regressions pass. Existing checks now expect EXTRUDE to arm instead of treating it as unsupported.

Commands (run sequentially; every foreground check uses fixed port 8765):

```sh
cd /Users/krishpatel/HackRu
.venv/bin/python -m pytest -q
.venv/bin/python tools/package_addon.py
BLENDER_USER_RESOURCES="$(mktemp -d /tmp/air-geometry.XXXXXX)" \
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python-exit-code 1 --python addon/air_modeler/extrusion_geometry_check.py
BLENDER_USER_RESOURCES="$(mktemp -d /tmp/air-extrude.XXXXXX)" \
  /Applications/Blender.app/Contents/MacOS/Blender --factory-startup \
  --python-exit-code 1 --python addon/air_modeler/extrusion_check.py
```

Other retained checks are `smoke_check.py` (background), `move_check.py`, `transform_check.py`, and `bridge_check.py` (foreground), with the same isolated-resource invocation documented in the prior handoffs.

## Remaining manual/live rehearsal

No new manual Blender click-through, visual confirmation of face-outline rendering, physical hand extrusion, or end-to-end spoken extrusion is claimed. Native foreground checks exercise drawing callbacks and operations but do not substitute for those observations. File-load cleanup was tested through the handler; an actual file-open remains a manual check. Plus teammates' 0.4.0 evidence is separate, and V's live voice result does not prove live geometry integration.

Team sequence: create a cube; type `extrude`; confirm the intended face alone outlines without selection/mutation. Pinch, raise slowly, hold (no topology growth), lower to zero, raise again and release. Rearm EXTRUDE, extend the new cap, then Undo twice. Repeat a prism triangular cap and a rectangular side after rotating/nonuniformly scaling the prism. Try zero release, Escape, `cancel`, brief/long hand loss, companion shutdown, and Undo while held. Confirm baseline restoration and open-hand rearming. Try a shared mesh/modifier target and check readable rejection. Finish by testing a normal MOVE, world rotation, and uniform scale.

Remaining demo work: install 0.5.0 on the demo laptop, verify face-outline readability and gesture sensitivity under actual camera/venue conditions, rehearse physical shortcuts/Preferences/file-open cleanup and the live voice→Blender command path. Confirm sponsor attribution separately with the workspace/sponsor admin. Broader arbitrary geometry, reflected transforms, inward extrusion, multi-face extrusion, and live self-intersection handling are not supported.

Changed P-owned files: `extrusion.py`, `extrusion_geometry_check.py`, `extrusion_check.py`; controller, viewport, operators, panel, registration/version, package allowlist/smoke expectations, existing bridge/transform expectations; P-owned protocol/current-handoff docs and this document. Generated ZIPs, model/environment files, secrets and unrelated `demo.blend` remain excluded from commits.
