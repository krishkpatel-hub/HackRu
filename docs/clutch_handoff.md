# Air Modeler 0.12.0: SCALE arbitration and visible face intent

Branch `feature/blender`; final commit SHA is reported in chat. Previous release
`1b389b37a997e9c104881c4b9f77d24f9d3cdd7e` (0.11.0) is preserved in
`dist/air_modeler-baseline-0.11.0.zip`, [engineering record](clutch_handoff_0.11.md)
and [physical record](physical_acceptance_0.11.md). All scenes, including
`rehearsal_0_11.blend`, are preserved. No merge into main. Prepared PR description:
`/tmp/air-modeler-integration-pr.md`; the known GitHub permission blocker is not retried.

## Observations and reproduced causes

The user reports two real interaction failures: closing/opening to SCALE often
starts ROTATE, and EXTRUDE chooses an unintended face without clear highlighting.
At inspection, the installed add-on **on disk** is 0.11.0. Loaded-module equality
was not introspected. The identified camera 0/mic 0/two-hands/PTT companion was
stopped with SIGINT for isolated tests; the user's Blender session was untouched.

The observation path already separates image-space corrected palm translation,
normalized metric finger flexion, and orientation from wrist 0 / MCPs 5, 9, 17.
Fingertips do not define the orientation frame. Degenerate palm frames and
implausible orientation jumps already reject; hand identities, timestamps and
loss guards are preserved. World landmarks never supply absolute camera depth.

Two regressions fail on 0.11 before the fix (`/tmp/air12-reproduction.log`):

- Gradual openness 0.98 → 0.94 → 0.925 with 0.25-radian MCP-frame wobble locks
  ROTATE at 0.26 s, before stronger finger closure can win.
- Sustained closure to 0.6 openness with 14° wobble never qualifies as SCALE.

The controller admitted early angular evidence while openness was still within
its stable band, then disqualified SCALE above 8° of orientation difference.
A disqualified angular score could also block otherwise useful shape evidence.
These are reproduced controller defects, not proof that a particular user's MCP
estimate followed the synthetic trace. The only checked-in real recording is
`real_still_pinch.json`: 259 sparse image-landmark frames, two pinch/open cycles,
no world landmarks/full finger pose. Its unchanged replay passes; it cannot
establish the exact orientation drift in the new physical report.

For extrusion, 0.11 already normalizes projected normals and uses stable direction
evidence, but lacked a secondary Right-cursor cue. Its polygon outline was drawn
in POST_PIXEL with no depth testing and used one color for tentative/locked faces.
The displayed cursor also remained at Left selection during Right extrusion.
Those concrete selection/feedback gaps are addressed here.

## Controls and temporal arbitration

Left pinch selects/holds the OBJECT; Left movement is inert. Right open-palm
translation MOVE, whole-finger closing/reopening SCALE, deliberate palm orientation
ROTATE (FREE or explicit world X/Y/Z), isolated thumb/index pinch EXTRUDE. An active
operation remains locked until completion/cancel; pose changes cannot switch it.

The controller now compares a bounded **200 ms** window of shape and angular
measurements. Median openness/finger changes and angular magnitudes reduce single
spikes. Current evidence must still support the candidate, so a lone spike cannot
lock after the hand returns to baseline. Early coherent change in at least three
fingers reserves shape intent at **0.04**, before the unchanged **0.15** SCALE
activation threshold. While shape changes substantially, automatic ROTATE and
incidental MOVE are suppressed. Minor shape adjustments may settle for 200 ms,
then deliberate rotation with reasonably stable openness works again.

SCALE allows incidental orientation differences up to **25°**; larger simultaneous
shape/rotation stays SELECTED_READY. Deliberate rotation with stable openness
retains the **8°** activation threshold and all three/free axes. Normalized scores,
**150 ms persistence**, **1.35 dominance**, **0.75 candidate hysteresis**, and the
existing MOVE threshold remain. Settings live in `IntentConfig`; they are explicit
engineering choices verified against regressions, not a completed live calibration.
Explicit typed/voice overrides select the intended evidence without changing
required-hand validity or transaction rules. Early whole-finger contact is not
an isolated extrusion pinch. SCALE remains active through a fist and reopening.

Producer measurements, filtering, corrected pre-close/opening anchors, shared
protocol and voice/PTT modules are unchanged. No extra producer filter was added.
Scale uses its existing positive bounded baseline factor `exp(log(4) × openness
change)` after rebasing at intent lock. Origin, proportions, rotation and scale
signs are preserved; camera-distance changes do not create shape scale evidence.

## Extrusion direction, cursor and highlighting

Right isolated pinch shows EXTRUDE ARMED. Left selection never picks the final face.
The existing frozen AUTO/XY/XZ/YZ plane and optional world-axis mapping express
hand displacement and inverse-transpose world normals in the same coordinates.
Both projected directions are normalized; absolute alignment selects a normal
axis while the signed dot determines outward/inward movement. Normals with less
than 0.25 projection are rejected. No inferred absolute hand depth is used.

Retained direction requirements: 0.018 image-height-equivalent travel, alignment
≥0.55, separation ≥0.12 (0.10 for the retained candidate), 120 ms median direction
window spanning at least 80 ms with three samples and 75% directional coherence.
A candidate must persist for 100 ms. It is highlighted immediately in **cyan**;
changing the candidate updates the actual polygon and restarts lock persistence.

Clear direction always wins. If scores are tied within the margin, a ray under
the **displayed corrected Right cursor** may select a tied eligible face. Cached
evaluated scene BVHs choose the nearest surface, so an occluder, hidden face,
unsupported face or unobservable normal cannot win this tie-breaker. A three-pixel
interior margin excludes shared polygon edges. The cue cannot override a clear
directional winner or use the original Left selection. Cursor changes must survive
the same candidate persistence before lock. No mouse click or extra selection
workflow is required. Without a unique cue, show a cyan tentative face plus
**“Drag more clearly to choose a face”** and do not create geometry.

On lock the face becomes **orange** and its identity/normal stay fixed. During the
120 ms lock highlight, movement is continuously rebased; geometry starts from zero.
Further corrected palm displacement is dotted with that locked normal, using the
retained continuous symmetric 0.003-image-height deadband. Gain is 12 world units
per image-height and mapped vector travel is bounded to 4 units. An aligned raw
0.05-height motion yields 0.564 units after the 0.036-unit deadband. Reversal
reduces outward travel, crosses exact original topology at zero, then shortens
supported geometry inward on the SAME face. Fixed numeric extrusion remains.

Polygon tint and outline render in **POST_VIEW with LESS_EQUAL depth testing**,
no depth-buffer writes, and restored blend/depth state. Shader-controlled line
width avoids leaking Retina line state. Geometry in front occludes the highlight.
The outline follows the actual disposable preview face, not its old coordinates.
The existing OUT arrow labels face index, current OUT/IN direction and distance.
These overlays create no materials, mesh edits, objects or Undo entries. Completion,
cancel, file load, disconnect, disable and shutdown clear them and remove callbacks.

## Visibility and stale state

Candidates must pass existing supported-face rules, face the viewer with dot≥0.04,
project to ≥16 square pixels and have an unoccluded in-window sample. Perspective
uses eye-to-face direction; orthographic uses captured view direction. World normals
use inverse transpose, including reflected nonsingular TRS. Clipped/behind-view
faces are conservatively rejected. Solid shading with X-Ray off is required.

A bounded triangle-fan grid plus center and near-corner samples (25 per quad,
14 per triangle) tests world-space BVHs of visible evaluated meshes, curves,
surfaces, text and metaballs, including target self-occlusion. A blocked face
center does not discard visible corners/edges. Tiny slivers between samples can
be conservatively missed; this is bounded visibility sampling, not pixel-perfect
rasterization. Instanced occluders reject clearly. Budgets: 256 target polygons,
128 evaluated objects, 100,000 evaluated vertices/polygons; isolate demo objects if exceeded.
Transparent material alpha, render-camera visibility and arbitrary concave editing
are not used to broaden the supported solid viewport demo.

Candidate/BVH discovery occurs once per EXTRUDE selection, not each hand frame.
Exact target geometry/attribute stamps protect original face indices; evaluated
occluder state is checked at 4 Hz and completion. Target edits, transform changes,
viewport navigation/resizing/shading changes, disappearing context, or occluder
changes cancel and require release/reselection. Mapping never changes mid-operation.
External edits to an untouched original baseline remain external work; cancelling
only discards our disposable preview. Other tools retain their existing policy.

## Clean inward scope and geometric limit

Blender 5.2.2 exposes `bpy.ops.mesh.extrude_manifold` with
`MESH_OT_extrude_region.use_dissolve_ortho_edges`. We evaluated this actual API:
cube faces and prism caps shorten cleanly; prism sides can retain edge-manifold
but non-convex/overlapping geometry, with negative volume on larger inward travel.
The [native tool documentation](https://docs.blender.org/manual/en/5.2/modeling/meshes/tools/extrude_manifold.html)
describes orthogonal-edge dissolution; it is not a general safety guarantee.
The regression probe is in `addon/air_modeler/signed_extrusion_check.py`.

Our inward path therefore moves the **entire original convex face plane** and its
vertices along intersections with their baseline incident side planes. It does
not extrude a cap backward, create an inset/cavity, or perform a through-cut.
Topology stays original. Supported: small connected closed consistently outward
convex cube/prism-like solids with planar strictly convex triangle/quad faces and
solvable incident side planes, including tested tapered cubes, rotations,
nonuniform/reflected TRS and repeated outer cap rings. ≤256 faces/vertices.
Shared/linked/fake-user meshes, shape keys, custom normals, enabled modifiers,
parents, shear/singular transforms and unsupported attributes remain rejected.
Concavity, coplanar fixed vertices on the selected face plane, incompatible
non-simple vertices and unverifiable inward paths reject clearly.

Compute first positive event from (1) moving face plane reaching any fixed
vertex/edge and (2) moving vertices reaching another baseline face plane. Keep
`max(1% of event travel, 0.0001 world units)` clearance and cap at 4 units. This is
not a bounding-box estimate. A 2-unit cube permits 1.98 inward units; the unit-radius
2-high triangular prism sides permit about 1.485, caps 1.98. A fresh 0.5 outer ring
permits 0.495 inward travel before reaching that ring. Different transforms/tapers
recompute world-space bounds. The sidebar reports signed clamped amount and reason.

Endpoint and every inward preview validate connected closed topology, winding,
positive volume, nondegenerate strict convex faces, globally supporting planes,
and no duplicate face geometry. These conservative convex constraints rule out
internal/crossing surfaces in supported solids; edge-manifold counts alone are
not treated as proof. Each result must have lower volume than the baseline.

Outward uses the existing cap/side-wall implementation. Inward uses a disposable
baseline copy with unchanged topology/attributes. Crossing zero restores the
**original mesh datablock**, with no residual cap; sign transitions rebuild only
the needed representation. Every update uses original coordinates. Preview and
undoable commit share the same signed geometry implementation and verified amount.

## Recovery, diagnostics, voice

Selection-only, pending or zero-change release creates no Undo entry. Both release
orders commit once; native Undo removes completed edits individually. Brief hand
loss freezes/reanchors, sustained 0.5 s loss cancels; absence is not release.
Escape, typed cancel, disconnect, file/context loss, disable and shutdown restore
unfinished geometry and free previews. All bpy work remains on the main thread.

Sidebar **Diagnostics (2 Hz console)** reports version, identity/confidence,
input age, pinch evidence, shape-change reservation, normalized arbitration scores/state,
Right cursor/raycast face, candidate visibility reasons,
area/sample count, signed alignment, observability, locked face, signed distance,
active mapping and geometry limit/rejection. New fields include EXTRUDE stage,
pinch event/validity, observed release, recognition feedback, filtered direction
and coherence, raw signed distance and deadband. This distinguishes recognition,
stale context, occlusion, ambiguity, mapping and topology rejection. It never
prints a key. Existing [private bounded landmark recording/replay](clutch_handoff_0.9.md#transactions-diagnostics-and-replay)
is unchanged; use only if an observed recognition failure needs a capture.

PTT and typed fallback are unchanged. `/talk` arms audio; speak one command;
`/end` mutes and requests completion. Wait for committed text and Blender's actual
result before the next turn. `/end` is not Cancel. Realtime access works per the
teammate's report; sponsor attribution remains unconfirmed. The owner must revoke
the previously exposed key; never paste a replacement into chat or a command.

## Install and launch

Existing environment is reused: Python 3.12.15, Blender 5.2.2 LTS/Python 3.13.13.
Source and rebuilt ZIP are **0.12.0**, protocol `left_clutch_v3` unchanged.
Installed user version is still **0.11.0 on disk** until confirmed after restart.

1. Save a new `/Users/krishpatel/HackRu/rehearsal_0_12.blend` copy; preserve all older scenes.
2. Stop any companion; Blender Disconnect, disable/remove the old Air Modeler add-on.
3. Fully quit Blender; reopen → Preferences → Add-ons → Install from Disk →
   `/Users/krishpatel/HackRu/dist/air_modeler.zip`; enable and confirm **0.12.0**.
4. Fully quit/reopen again; open the new rehearsal scene, Object Mode, Global Undo on,
   Solid shading, X-Ray off. Use a single connected 3D viewport.
5. In Terminal, privately enter the replacement key if needed, then launch:

```zsh
set +x
read -rs 'ELEVENLABS_API_KEY?ElevenLabs API key (hidden): '
export ELEVENLABS_API_KEY
printf '\n'
```

```sh
cd /Users/krishpatel/HackRu && /Users/krishpatel/HackRu/.venv/bin/python -m companion.main --camera 0 --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --two-hands --mic --device 0 --push-to-talk
```

Camera 0 and mic 0 (MacBook Air Microphone) were user-confirmed; worker `preview=False`
remains. Do not reinstall working dependencies. Connect from intended viewport's
N sidebar. Require companion 0.12.0/profile v3, Blender Connected/companion READY,
actual hand observations and **Scribe session ready**. Process startup alone proves
none of those connections. PTT starts muted; keep Terminal typed input available.
`quit`/Ctrl+C shuts down; check camera off and terminal prompt, then
`unset ELEVENLABS_API_KEY`. Launch Blender separately from the key-bearing shell.

## Verification

Existing `.venv`: **310 tests + 78 subtests passed** (`/tmp/air12-python.log`).
This includes pre-fix failing closure/wobble reproductions, angular/shape spikes,
early fist contact, closure/reopening, large mixed ambiguity, explicit overrides,
minor shape settling followed by rotation, fixed wrist/MCP orientation under
finger flexion, camera-distance invariance, existing real-pinch replay, voice/PTT,
protocol, transport and lifecycle tests. No dependencies were installed.

Blender **5.2.2 LTS** ran with isolated factory-startup profiles and serial TCP tests.
All **12 scripts passed, 132 PASS groups**:

| Script | PASS groups | Coverage |
| --- | ---: | --- |
| `smoke_check.py` | 6 | Final runtime ZIP installation/registration/primitives |
| `stabilization_check.py` | 4 | Preserved transform/mapping math |
| `extrusion_geometry_check.py` | 27 | Existing outward geometry, attributes and bounds |
| `signed_extrusion_check.py` | 10 | Validated signed geometry, transformed solids, limits, parity, repeated rings |
| `visibility_check.py` | 11 | Perspective/orthographic visibility; rotated/nonuniform cube/prism and reflected cube normals; right-ray hits; occluded cursor rejection; tied/clear/degenerate directions; tentative retention/change |
| `overlay_check.py` | 3 | Actual GPU pixel readback: cyan/orange differ, foreground geometry occludes highlights, clearing restores pixels; GPU state and mesh/material data unchanged |
| `move_check.py` | 7 | Existing MOVE/release/cancel/Undo |
| `transform_check.py` | 13 | Existing rotation/scale transforms and Undo |
| `extrusion_check.py` | 13 | Legacy extrusion/TCP/cleanup |
| `bridge_check.py` | 16 | Commands/context/file/disconnect cleanup |
| `precision_check.py` | 6 | Numeric commands/staging/dedup/Undo |
| `clutch_check.py` | 16 | Gradual closure with wobble → SCALE without premature ROTATE; fist/reopen and FREE XYZ rotation; six-face signed extrusion; no-jump/deadband; right-cursor tie choice independent of Left; actual face/preview outline parity; locked reversal; both release orders; one native Undo; exact cancellation; stale/loss/edit/reconnect/disable/shutdown cleanup |

Logs: `/tmp/air12-final-<script-name>.log`. Inputs are synthetic; the GPU checks
verify actual rendered pixels, not actual hands. Meaningful implementation failures
were resolved during development: direct triangle intersection missed a reflected
quad's internal triangulation seam, so the cursor now uses the same robust cached
scene BVHs; Retina line-width restoration changed GPU state, so overlay thickness
now uses the polyline shader's width uniform. Both regressions pass afterward.
The previous release's historical stale-frame investigation remains archived;
its explicit 0.68-second stale-completion regression is retained, with no relaxed
loss timeout.

The final **0.12.0** ZIP contains **16 runtime entries**, exactly matching source
and unchanged shared protocol/spatial bytes. Compile checks and `git diff --check`
pass. ZIP SHA-256: `55ed037b766b77486241a33e7228fd5ed3cc7d2d954a233ffab9b69f7c00eb4a`.


All **0.12 physical checks remain NOT RUN**. User observations above are recorded
separately from synthetic tests and the sparse historical replay. Standalone voice
success and the historical 67-test/78-subtest baseline do not establish a combined
live demo. Next: install/restart, confirm connections, test automatic closing/fist/
reopening, deliberate rotation, then each accessible extrusion face and a newly
exposed face after rotation. Follow [physical acceptance](physical_acceptance.md)
one small action per reply. No private API key belongs in chat, arguments or logs.

Generated ZIPs remain ignored; rebuild with `.venv/bin/python tools/package_addon.py`.
No dependencies were installed. Scenes are excluded from the implementation commit.
