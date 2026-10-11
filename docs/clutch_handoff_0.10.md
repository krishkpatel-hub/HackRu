# Air Modeler 0.10.0: visible-face signed extrusion

Branch `feature/blender`; final delivery SHA is reported in chat. Previous release:
`c58cf8bbcbe5839e38cd3da5dd9577c138bd79e9` (0.9.0). Its package is preserved at
`dist/air_modeler-baseline-0.9.0.zip`; [engineering record](clutch_handoff_0.9.md)
and [physical record](physical_acceptance_0.9.md) are archived. All scene files
remain untouched. Main is not merged. Prepared PR: `/tmp/air-modeler-integration-pr.md`;
GitHub permission failure is not retried or treated as a rehearsal blocker.

## What was diagnosed

The user reports selection, MOVE, SCALE and ROTATE now work reasonably well.
Their hand recognition, thresholds, gains, mappings and transaction behavior are
unchanged. Hand/voice teammate modules and shared protocol remain unchanged.
Only the companion's version banner changes. No captured live failure sequence
was supplied, so recognition and comfortable physical travel remain observations
to collect, not diagnosed threshold problems.

The actual 0.9 source admitted hidden faces deliberately, scored only positive
outward alignment, and clamped negative distance to zero. Those were concrete
causes of the mismatch with the requested behavior. Its face-selection travel was
already consumed at lock; the existing pre-close anchor, palm-relative cursor,
frozen opening coordinate and release protection are retained.

At inspection, installed user add-on **on disk** and source both said **0.9.0**.
The running companion command used this checkout, camera 0/mic 0/two-hands/PTT;
its loaded Python modules were not introspected, so exact running-code equality
was not established. That identified process was interrupted cleanly for isolated
TCP tests. The user's Blender session and scene were left open and untouched.
The installed user add-on remains 0.9.0 until the update below is confirmed.

## Gestures and mapping

Left thumb/index pinch selects and holds the object only; Left motion is inert.
Right open-palm translation MOVE, whole-finger SCALE and quaternion ROTATE retain
0.9 controls and sensitivity. Right fresh isolated thumb/index pinch enters
EXTRUDE direction pending. There is no required face click. Release Left or Right
first commits extrusion once; reopen both required hands before rearming.

At Left selection we capture the connected 3D viewport's **WINDOW region**, its
projection/view matrices and dimensions, target transform, mesh identity and
geometry/attribute baseline. At EXTRUDE activation the mapping is resolved **before**
face discovery: AUTO chooses the cardinal XY/XZ/YZ plane with greatest projected
area (canonical order breaks ties), optionally constrained by an explicit world
axis. The two signed plane axes map to screen right/up. This is a deterministic
virtual world mapping, not inferred camera depth or inverse near-zero projection.

Use typed/PTT `extrude plane xy axis x`, `extrude plane xy axis y`, or
`extrude plane xz axis z` while idle when AUTO cannot express the visible normal.
Other compatible XY/XZ/YZ/axis combinations work. The sidebar shows the actual
signed right/up vectors; do not assume screen up always means positive world Z.
Choose an exposed side, or finish ROTATE, reselect, and discover its new faces.
A visible face normal with less than 0.25 projection onto available mapping axes
is unobservable and cannot win; feedback requests a different mapping/view.

Right displacement uses `(du × camera aspect, dv)` in image-height units. At least
0.018 height-equivalent selection travel, absolute normal alignment ≥0.55 and
separation ≥0.12 from materially different normals are required. The current
candidate may retain with ≥0.10 separation. Candidate outline appears after
60 ms; lock requires the same candidate for 100 ms. Ambiguity resets lock timing,
keeps the prior candidate outline at most 150 ms with a pending label, and never
mutates geometry. Parallel normals on different visible patches are ambiguous too, including adjacent
coplanar side quads after a prior extrusion. Only identical geometric patches are
equivalent; smallest face index breaks that tie. Sign never chooses an invisible
opposite face.

Lock captures face identity and outward normal, consumes selection travel by
rebasing the corrected cursor, then highlights for 120 ms before deformation.
Orange outlines the face; the green arrow points outward when its screen projection
is meaningful. When the world-normal arrow has no screen length, a labeled **OUT (virtual drag)**
arrow shows the required screen hand direction from the frozen mapping; the sidebar
also shows the OUT world normal and signed axes. This does not estimate depth.
Subsequent distance is the mapped displacement dotted with the locked outward
normal. Positive extends; negative shortens; reversal never changes faces.

**Gain stays 12 world units per image-height travel**, adjustable in the sidebar
and frozen on selection; vector length is bounded to 4 world units. An aligned
0.05-height drag after lock gives 0.6 units. This is a verified mapping, not live
comfort calibration. No accumulated deltas or frame-rate multiplier. Holding
still holds the result. Inward travel also has the geometry bound below.
`extrude 0.5 units` / `extend 0.5 units` remain positive-only fixed commands using
the same visible-face choice and validated outward geometry. First set a plane/
axis if needed. Numeric arming edits nothing; amount applies after face lock.

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
input age, pinch evidence, arbitration scores/state, candidate visibility reasons,
area/sample count, signed alignment, observability, locked face, signed distance,
active mapping and geometry limit/rejection. This distinguishes recognition,
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
Source and rebuilt ZIP are **0.10.0**, protocol `left_clutch_v3` unchanged.
Installed user version is still **0.9.0 on disk** until confirmed after restart.

1. Save a new `/Users/krishpatel/HackRu/rehearsal_0_10.blend` copy; preserve all older scenes.
2. Stop any companion; Blender Disconnect, disable/remove the old Air Modeler add-on.
3. Fully quit Blender; reopen → Preferences → Add-ons → Install from Disk →
   `/Users/krishpatel/HackRu/dist/air_modeler.zip`; enable and confirm **0.10.0**.
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
N sidebar. Require companion 0.10.0/profile v3, Blender Connected/companion READY,
actual hand observations and **Scribe session ready**. Process startup alone proves
none of those connections. PTT starts muted; keep Terminal typed input available.
`quit`/Ctrl+C shuts down; check camera off and terminal prompt, then
`unset ELEVENLABS_API_KEY`. Launch Blender separately from the key-bearing shell.

## Verification

The verification table below records automated evidence separately from physical observations.
[Physical acceptance](physical_acceptance.md) is **NOT RUN on 0.10.0**. Historical
standalone voice success and synthetic geometry/transport tests do not establish
a combined live pass. Guide each physical observation separately after installation.

### Automated evidence

Existing `.venv`: **290 tests + 78 subtests passed** (`/tmp/air10-python.log`).
No dependencies were installed. This includes existing hands, typed/voice/PTT,
protocol, transport, precision, arbitration and replay regressions. It is separate
from historical 67-test/78-subtest evidence and standalone voice verification.

Blender **5.2.2 LTS** ran with factory startup and isolated user resources; native
TCP scripts ran serially, without a competing companion. Successful checks:

| Script | PASS groups | Coverage |
| --- | ---: | --- |
| `smoke_check.py` | 6 | Installed runtime-only ZIP, primitives/registration |
| `stabilization_check.py` | 4 | Preserved quaternion/TRS and mapping math |
| `extrusion_geometry_check.py` | 27 | Existing outward geometry, attributes, constraints |
| `signed_extrusion_check.py` | 10 | All cube/prism faces under three TRS cases; inward/outward/zero, limits, attributes, no temporary-mesh leak, deterministic preview/commit parity, tapered solid, repeated rings, native Manifold API evaluation |
| `visibility_check.py` | 8 | Actual WINDOW perspective/orthographic projection, all cube/prism faces, signed choice, hidden/full/partial occlusion, rotated/extruded refresh, ambiguity and unobservable mappings |
| `move_check.py` | 7 | Existing MOVE, release/cancel/Undo |
| `transform_check.py` | 13 | Existing world transforms and native Undo |
| `extrusion_check.py` | 13 | Legacy scalar extrusion/TCP and cleanup |
| `bridge_check.py` | 16 | Transport, commands, context/disconnect/file cleanup |
| `precision_check.py` | 6 | Typed numeric edits, staged controls, dedup and Undo |
| `clutch_check.py` | 14 | Working tools preserved; visible six-side mapping; signed reversal; both releases; no-change Undo; repeated caps; inward cancel/loss/stale/view/mesh/attribute recovery; ambiguous direction; reconnect/shutdown |

Logs: `/tmp/air10-final-<script-name>.log`. These are synthetic captures/geometry,
not physical hands or a combined live demo. No recorded user failure was available.

Development failures were retained in the investigation: initialized missing BMesh
lookup tables, fixed the new arrow's missing Vector import, restricted the new
stale-baseline guard to the two-hand path to preserve legacy extrusion, and updated
the precision test's old version assertion. A later release-equality assertion
failed once around a 0.68-second frame gap; its original controller error was not
captured, so attribution is not definitive. Diagnostic reruns passed. An explicit
0.68-second gap test now verifies a stale-input error, exact baseline restoration
and rejection of late completion. No safety timeout was relaxed. Physical timing
and responsiveness still need the acceptance checks.

The final feedback-only adjustment labels the existing 4-unit mapping travel cap;
it does not change geometry, sensitivity or arbitration. Compile checks and
`git diff --check` pass. ZIP inspection confirms **15 runtime-only entries**,
version **0.10.0**, exact source bytes and unchanged packaged protocol/spatial
helpers. ZIP SHA-256:
`19dae540a6d317f1f3efdc6bf8c6a15009f7cce31e74611b9f3d88bd7ffc3315`.

`dist` packages remain generated/ignored, as before; rebuild with
`.venv/bin/python tools/package_addon.py` on another checkout. The preserved 0.9
ZIP checksum is `959a016645b2b9025a6557d8d46e4df35d073b7c6cb186ddc514036eae82d202`.
