# Air Modeler 0.11.0: stable face choice and signed dragging

Branch `feature/blender`; final delivery SHA is reported in chat. Previous release:
`8132c0adff11ad0d559df4617a9bff2e6e3da11b` (0.10.0). Its package is preserved at
`dist/air_modeler-baseline-0.10.0.zip`; [engineering record](clutch_handoff_0.10.md)
and [physical record](physical_acceptance_0.10.md) are archived. All scenes are
preserved. Main is not merged. Prepared PR: `/tmp/air-modeler-integration-pr.md`;
the existing GitHub permission failure is not retried and does not block rehearsal.

## What was diagnosed

**Actual user observation on installed 0.10.0:** “EXTRUDE arms, but face choice or
dragging is unpredictable.” This establishes successful arming and a physical
usability failure; it does not identify a particular face, input trace, or timing
fault. Earlier selection/MOVE/SCALE/ROTATE success remains a separate report.

Source inspection found two concrete controller problems addressed here:

- Full-world normal scores favored a larger in-plane projection even when two
  normals projected to the same direction. For XY, normals `(0.6,0,0.8)` and
  `(1,0,0)` scored 0.6 and 1 for the same horizontal intent. Both now score 1 and
  remain ambiguous. A tentative outline explains the pending choice without edits.
- Although face lock rebased the cursor, the following 120 ms highlight pause
  accumulated movement. Its first deformation could jump to that accumulated
  distance. The pause now continuously rebases and its final sample is zero.

Face recognition used individual frame directions. It now uses a bounded 120 ms
median displacement window, at least three observations spanning 80 ms, with
75% within 15 degrees of the median direction, before allowing a stable winner.
This filters recognition only. Continuous deformation keeps the existing single
palm filter and gains a continuous symmetric deadband, without another EMA.

The genuine historical `real_still_pinch.json` recording contains 259 observations
and two pinch/open cycles. Replaying the unchanged producer gives two START/END
pairs; held corrected frame motion has median 0.00103, p90 0.00262 and maximum
0.01792 image-height units. It contains only sparse image landmarks, no world
landmarks/full finger pose, and cannot calibrate current isolated-pinch versus
fist recognition. The 0.003-height deformation deadband is provisional for live
comfort, not a claim that this recording proves steady geometry or current-user
calibration. Gesture thresholds, pre-close anchors, opening freeze, producer
smoothing, hand/voice modules, geometry helpers and shared protocol are unchanged.
The companion only changes its version banner.

Installed user add-on **on disk** was verified as **0.10.0**; loaded module equality
was not introspected. The positively identified companion using camera 0/mic 0,
two-hands/PTT was stopped with SIGINT for isolated TCP tests. The user's Blender
session and scenes were left open and untouched. Installation of 0.11.0 is pending.

## Gestures and mapping

Left thumb/index pinch selects and holds the object only; Left motion is inert.
Right open-palm translation MOVE, whole-finger SCALE and quaternion ROTATE retain
existing controls and sensitivity. Right fresh isolated thumb/index pinch enters
visible EXTRUDE ARMED. There is no required face click. Release Left or Right
first commits extrusion once; reopen both required hands before rearming.

At Left selection we capture the connected 3D viewport's **WINDOW region**, its
projection/view matrices and dimensions, target transform, mesh identity and
geometry/attribute baseline. At EXTRUDE activation the mapping is resolved **before**
face ranking: AUTO chooses the cardinal XY/XZ/YZ plane with greatest projected
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
0.018 height-equivalent selection travel, absolute normalized projected-normal alignment ≥0.55 and
separation ≥0.12 from materially different normals are required. The current
candidate may retain with ≥0.10 separation. Candidate outline appears after
60 ms; lock requires the same candidate for 100 ms plus the stable direction
window described above. Both motion and inverse-transpose world normals are
projected into the frozen mapping axes and normalized there. Ambiguity resets
lock timing, shows a labeled tentative outline with 0.12 retention hysteresis,
and never mutates geometry. The tentative face has no lock authority. Parallel normals on different visible patches are ambiguous too, including adjacent
coplanar side quads after a prior extrusion. Only identical geometric patches are
equivalent; smallest face index breaks that tie. Sign never chooses an invisible
opposite face.

Lock captures face identity and outward normal, consumes selection travel by
rebasing the corrected cursor, then highlights for 120 ms while continuously rebasing. The last highlight
sample becomes the manipulation reference; motion during recognition or the
pause is consumed. Feedback progresses EXTRUDE ARMED → candidate/ambiguous →
EXTRUDE FACE LOCKED → EXTRUDE DRAGGING.
Orange outlines the face; the green arrow points outward when its screen projection
is meaningful. When the world-normal arrow has no screen length, a labeled **OUT (virtual drag)**
arrow shows the required screen hand direction from the frozen mapping; the sidebar
also shows the OUT world normal and signed axes. This does not estimate depth.
Subsequent distance is the mapped displacement dotted with the locked outward
normal, followed by a symmetric continuous deadband: signed amount =
`sign(raw) * max(abs(raw) - band, 0)`, where band is 0.003 × gain × normal
observability. Positive extends; negative shortens; reversal never changes faces.

**Gain stays 12 world units per image-height travel**, adjustable in the sidebar
and frozen on selection; vector length is bounded to 4 world units. An aligned
0.05-height drag after the highlight gives 0.564 units after the 0.036-unit
deadband (raw distance 0.6). This is a verified mapping, not live
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
Source and rebuilt ZIP are **0.11.0**, protocol `left_clutch_v3` unchanged.
Installed user version is still **0.10.0 on disk** until confirmed after restart.

1. Save a new `/Users/krishpatel/HackRu/rehearsal_0_11.blend` copy; preserve all older scenes.
2. Stop any companion; Blender Disconnect, disable/remove the old Air Modeler add-on.
3. Fully quit Blender; reopen → Preferences → Add-ons → Install from Disk →
   `/Users/krishpatel/HackRu/dist/air_modeler.zip`; enable and confirm **0.11.0**.
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
N sidebar. Require companion 0.11.0/profile v3, Blender Connected/companion READY,
actual hand observations and **Scribe session ready**. Process startup alone proves
none of those connections. PTT starts muted; keep Terminal typed input available.
`quit`/Ctrl+C shuts down; check camera off and terminal prompt, then
`unset ELEVENLABS_API_KEY`. Launch Blender separately from the key-bearing shell.

## Verification

Automated results are recorded below. All physical checks
are **NOT RUN on 0.11.0**. The user's 0.10 report is a partial real observation of
arming plus unpredictable face choice/dragging, not a combined live pass.
Historical standalone voice and 67-test/78-subtest evidence remain historical.

Existing `.venv`: **300 tests + 78 subtests passed** (`/tmp/air11-python.log`).
Coverage includes the existing historical real-pinch replay, closing/opening
anchors, pinch/fist discrimination, slow-pinch suppression and timeout/rearm,
voice/PTT, protocol and transport. New pure checks cover stable/spiky/ambiguous
recognition evidence at 24/30/60/120 Hz, reversal, stale/nonfinite evidence and
continuous stateless signed deadband. The first sandboxed run could not bind
localhost; the final run with localhost permission passed.

Blender **5.2.2 LTS**, isolated factory-startup profiles, sequential TCP scripts:

| Script | PASS groups | Coverage |
| --- | ---: | --- |
| `smoke_check.py` | 6 | Installed runtime-only ZIP and primitives |
| `stabilization_check.py` | 4 | Preserved quaternion/TRS and mapping |
| `extrusion_geometry_check.py` | 27 | Existing outward geometry/attributes/bounds |
| `signed_extrusion_check.py` | 10 | Supported inward/outward/zero, transformed cube/prism, limits, parity, repeated rings, native Manifold evaluation |
| `visibility_check.py` | 10 | Actual WINDOW projection/occlusion, transformed inverse-transpose normals, normalized projected ties, clear/degenerate directions and tentative outline authority |
| `move_check.py` | 7 | MOVE, cancel/release/Undo |
| `transform_check.py` | 13 | World transforms and native Undo |
| `extrusion_check.py` | 13 | Legacy extrusion/TCP/cleanup |
| `bridge_check.py` | 16 | Commands, context/file/disconnect cleanup |
| `precision_check.py` | 6 | Numeric edits, staging/dedup/Undo |
| `clutch_check.py` | 15 | Existing tools; six signed face directions; recognition/highlight no-jump; raw deadband/gain/hold; fixed face through reversal; both release orders and one native Undo; zero-noUndo; inward cancel/loss/stale/edit invalidation; tentative ambiguity; reconnect/shutdown |

All 11 scripts exited successfully, **127 PASS groups**. Logs:
`/tmp/air11-final-<script-name>.log`. These are synthetic inputs and geometry,
not live hands. The new raw-input controller regression moves during the highlight,
then holds still: no geometry is created. Afterward a raw 0.6-unit movement gives
0.564, repeated holds do not accumulate, reversal stays on the same face, and
cancel restores the exact baseline. The visibility regression rejects the false
winner in the `(0.6,0,0.8)` versus `(1,0,0)` example above.

Compile checks and `git diff --check` pass. ZIP verification confirms **16 runtime
entries**, **0.11.0**, exact source bytes and unchanged packaged protocol/spatial
helpers. ZIP SHA-256: `254ea875ecef8da43a593b8667ab750d17b0b4fc0dc657ff26d1422aeb5c2a51`.


The 0.10 engineering archive retains its development failures, including the
unattributed release-equality failure near a 0.68-second frame gap. The explicit
stale-completion regression is retained; no safety timeout has been relaxed.
Current synthetic coverage cannot establish real camera timing or comfortable
travel. Follow [physical acceptance](physical_acceptance.md) one action at a time:
each accessible cube face, rotate/finish/reselect a newly exposed face, reversal,
both release orders and individual Undo, then interruption and combined services.

`dist` packages remain generated/ignored; rebuild with
`.venv/bin/python tools/package_addon.py` on another checkout. Preserve the 0.10
baseline ZIP and all `.blend`/backup files. No dependencies were installed.
