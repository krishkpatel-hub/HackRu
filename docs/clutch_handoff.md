# Air Modeler 0.9.0 stabilization handoff

Current release on `feature/blender`; the final delivery commit is reported in chat.
Recoverable prior release: `a8e63b554785eabc828212e7e30e224bce478ca4`, version 0.8.0;
`dist/air_modeler-baseline-0.8.0.zip` preserves its package. See
[0.8 engineering evidence](clutch_handoff_0.8.md) and [0.8 acceptance record](physical_acceptance_0.8.md).
All scene files are preserved. Main is not merged. The prepared PR description is
`/tmp/air-modeler-integration-pr.md`; the existing GitHub permission failure is not retried.

## Findings and changes

The user reported working MOVE, unreliable fist SCALE, apparent single-axis
rotation (reported X), orientation sometimes activating SCALE, weak extrusion
and a desire to choose faces by drag direction. These are live observations of
the previous workflow, not established causes or 0.9 acceptance.

Source inspection found: 0.8 discarded metric/world landmarks; openness used
projected 2D bending/reach and rotation used only a 2D wrist/MCP angle. Default
rotation was **world Z**, not X; a prior override or view can change its appearance.
The installed 0.8 package and protocol matched the 0.8 checkout on disk. Its
running Python companion command used camera 0/microphone 0/two-hands/PTT, but
loaded modules in that process were not introspected. It was cleanly interrupted
for isolated testing; the user's Blender session was left alone.

These source limitations explain possible failure mechanisms, but no captured
live sequence establishes each root cause. Version 0.9 separates metric finger
articulation from a rigid palm frame; uses real quaternion rotation; and replaces
Left face picking with direction-based face selection. MOVE's cursor filter,
0.035 threshold, plane mapping and sensitivity remain unchanged. Extrusion's
old 4-unit gain becomes a separately adjustable 12-unit gain. All physical
usability and gain tuning remain pending, not inferred from synthetic tests.

## Contract and measurements

Left thumb/index pinch picks only the object and enters SELECTED_READY. No face
is raycast for coherent extrusion. Left movement never supplies geometry input.
Right alone cannot select. Right chooses one operation, which remains locked:
open-palm translation MOVE, coherent finger articulation SCALE, palm orientation
ROTATE, isolated thumb/index pinch then directional drag EXTRUDE.

The camera flips once before inference. Anatomical labels use confidence and
spatial continuity, never detection-array order. Hand identity gates and cursor
lookback, palm-relative pinch displacement, frozen release coordinates and UUID
lifecycles are unchanged. Confirm anatomical labels physically after installation.

MediaPipe returns both image and hand-relative metric landmarks; the latter are
used for articulation/orientation only, **never absolute camera translation**.
See the [official output definitions](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python#handle_and_display_results).
Each of index/middle/ring/pinky contributes 65% weighted PIP/DIP joint extension,
20% fingertip reach divided by its own three-bone chain, and 15% proximal alignment
with the palm's wrist-to-middle-MCP axis. Joint extension maps 55–170 degrees to
0–1; reach maps 0.25–0.95 chain length to 0–1. Aggregate is the four-finger mean.
No finger-spread, image width, tip overlap, knuckle appearance or thumb position
enters openness. An extended fingers-together hand is open; a full fist stays valid.
Palm length normalizes bone plausibility (each segment 0.035–0.9 palm lengths).

A rigid frame uses wrist, index, middle and pinky MCPs. Along = normalized
wrist→middle MCP; across = pinky→index MCP; normal = across×along; orthogonal
across = along×normal. Degenerate frames, palm width/length outside 0.2–2.5,
near-collinear axes and malformed bones invalidate input with readable feedback.
Mirrored-camera metric (x-right,y-down,z-away) maps to view (x-right,y-up,z-toward)
by `(x,-y,-z)`, a proper rotation. Left/Right identities never share references.
Quaternion signs are kept continuous. A step exceeding min(55°,12°+900°/s×dt)
within 0.5 s is rejected against the last accepted orientation. This rejects
isolated flips rather than inventing a smooth hand; prolonged uncertain input
cancels through the existing watchdog. These are model plausibility checks, not
per-landmark visibility confidence; monocular occlusion still needs live testing.
No second smoothing layer touches the working cursor.

Open palm uses all four fingers with 0.72 enter/0.60 retain thresholds; no thumb
spread requirement. Isolated pinch needs at least two of middle/ring/pinky open,
with the metric thumb/index approach ratio ≤0.75; existing debounced 2D cursor
contact still supplies START/END. Blender additionally requires at least two
remaining fingers stable within 0.12 of selection reference. Coherent closure
of three fingers by ≥0.08 cannot become EXTRUDE, even if contact happens early.

## Intent, defaults and constraints

READY scores normalize Right palm travel by 0.035 image units, relative quaternion
angle by 8°, and openness difference by 0.15. Persistence is 150 ms; dominance
1.35×; candidate retention 0.75. Translation requires stable openness (≤0.08)
and orientation (≤16°); automatic SCALE requires ≥3 coherent fingers and palm
angle ≤8°; ROTATE requires stable articulation. Static/ambiguous stays READY.
Pinch approach reserves up to 600 ms to establish contact; an uncompleted or already-held pinch must reopen. Expiry stays READY with an instruction, never falls through into incidental MOVE.
Activation captures fresh references, so the threshold does not jump the object.
Explicit `move`, `scale`, `rotate`, `rotate x/y/z`, `extrude` overrides remove
competition while retaining valid deliberate evidence and the same preview/commit
implementation. An active operation cannot switch when pose changes.

SCALE factor = clamp(exp(gain × (openness−activation_openness)),0.1,10), default
gain ln(4)=1.386294. A 0.5 openness change gives 2× or 0.5×; reference near zero
is safe. Original origin, rotation, signed scale proportions are preserved.
These ranges are mathematically verified; actual camera openness ranges must be
measured during rehearsal. There is no required calibration ritual.

Free ROTATE is default, including bare typed/voice `rotate`. Let Q be palm frame,
Q0 captured at activation, V captured viewport orientation. World delta is
`V × (Q × inverse(Q0)) × inverse(V)`, premultiplied onto the original object
matrix with original translation restored. Palm tilt, sideways turn and wrist
twist supply independent axes. No Euler angles or accumulated frame deltas.
Explicit world constraints extract quaternion twist around X/Y/Z. Default gain
1 and 2° deadband; radial angle outside deadband maps continuously from 0 to π:
`a=(angle−deadband)×π/(π−deadband)`, output `2 atan(gain tan(a/2))`, with π fixed.
This keeps rotation continuous at the 180° quaternion branch even with non-unit
gain. Short loss captures a fresh Q0 plus the already-applied delta, without jump.
TRS transforms including reflection/nonuniform scale are supported; parent,
constraint, animation, singular or sheared transforms reject before mutation.
Numeric `rotate x 45 degrees` remains an exact independent precision command.

Sidebar tuning exposes scale log gain, rotation gain, extrusion gain and intent
thresholds; values freeze at Left selection. MOVE defaults have not been lowered.

## Automatic extrusion and gain

Right fresh isolated pinch locks EXTRUDE **direction pending**, object/baseline
and mapping, with no topology. Mapping is resolved from viewport or explicit
XY/XZ/YZ plane/axis BEFORE evaluating faces. AUTO chooses the cardinal plane with
largest projected area, restricted to any requested world axis; canonical order
breaks ties. Within the plane, screen right/up get the best projected signed axes.
Edge-on components use that fixed, labeled **virtual world mapping**, never division
by a tiny projection. This is not camera depth estimation. A single view's AUTO
plane cannot offer all six signed axes equally: use explicit XY/XZ/YZ/axis controls.
The sidebar prints plane, signed horizontal/vertical vectors and locked normal.

Corrected Right pinch `(du,dv)` becomes `(du×capture_aspect,dv)` in image-height
units. Direction needs ≥0.018 height-equivalent travel and 100 ms of the same
face candidate. These gates are independent of extrusion gain. Candidate normals
are transformed from untouched mesh with inverse-transpose; this correctly
preserves outward directions under reflected TRS (no extra determinant sign flip).
All supported eligible faces, including hidden faces, participate. Best positive
alignment must be ≥0.55 and beat any distinct-normal direction by ≥0.12. Otherwise:
“Drag more clearly toward one direction.” Equivalent parallel normals use the
outermost center along drag, then smallest face index. No hand raycast chooses it.

Once chosen, lock face/normal and rebase corrected cursor. Draw its orange outline
in screen space, including hidden faces, and wait ≥120 ms before deformation.
Subsequent normal component produces distance:
`clamp(dot(mapping(du×aspect,dv),locked_normal),0,4)` with **12 world units per
image height** default. A 0.05 height-equivalent drag after lock produces 0.6 units
when aligned: clearly visible relative to a 2-unit default cube in synthetic
geometry. No live travel measurement has yet tuned this default. Frame rate and
resolution do not change the formula. Reverse travel returns to zero; face never
switches and inward geometry is not created. Topology is allocated once, only
when distance becomes meaningful, and its vertices update from baseline.

`extrude plane xz axis z` then `extrude 0.5 units` retains that mapping for automatic
face selection. The armed amount supplies exactly 0.5 outward units after the
highlight interval, never adds drag distance. Sidebar Arm Fixed Extrusion uses
its staged plane/axis. Numeric arming alone edits nothing.

Supported: single-user local closed outward manifold meshes, flat strictly convex
supporting triangles/quads, including repeated outer caps, rotated/nonuniform and
reflected nonsingular TRS. Existing restrictions remain: no recessed/non-supporting
faces, arbitrary multi-face operation, shared/linked/fake-user mesh data, shape
keys, enabled modifiers, custom normals, unsupported attributes, parents/shear.
Normals use the same validated cap/side-wall geometry path and native commit.

## Transactions, diagnostics and replay

MOVE/ROTATE/SCALE finish once on observed Left release. EXTRUDE accepts observed
Right release or Left release first, once, followed by existing release gates.
Absence is never release. Required invalid input freezes; sustained 0.5 s loss or
release racing loss restores baseline. Selection-only, pending direction, zero
movement or reversed-to-zero creates no Undo entry. Cancel/Escape, disconnect,
file/context loss, disable and shutdown restore unfinished previews. Undo during
preview cancels first then undoes the previous completed edit. bpy stays on main
thread. PTT, committed-only recognition, typed fallback and UUID dedup remain.

Enable sidebar **Diagnostics (2 Hz console)** before selecting. `AIR_DIAG` prints
identity/confidence, age, phase, clutch, per-finger openness, aggregate, isolated
pinch, orientation validity/quaternion/angle, normalized scores, candidate duration,
rejection/target feedback, applied amount, mapping, candidate alignments and face.
Compare automatic and an explicit tool override: stable measurements but no winner
suggest arbitration; wrong pose/invalid quaternion suggests observations; correct
winner with bad displacement suggests mapping/geometry. Connection errors/age
point to transport. Ordinary sidebar remains object/tool/tracking/reason focused.

Opt-in private capture: append `--record-landmarks /tmp/air-modeler-capture.jsonl
--record-seconds 20` to the launch command below. Choose a new filename; existing
files are never overwritten. Capture stores only bounded landmark arrays, times,
aspect, non-secret tracker settings and emitted hand events (0600 permissions, max 60 seconds/3600 frames).
No audio, pixels, commands or credentials. It starts when camera processing starts;
prepare the scene first and connect promptly. Recording is off by default.

Replay in a disposable scene with matching starting object/view and the intended
typed override, if any. Quit the live companion first:

```sh
cd /Users/krishpatel/HackRu && /Users/krishpatel/HackRu/.venv/bin/python -m companion.main --replay-landmarks /tmp/air-modeler-capture.jsonl
```

Replay waits for Blender connection, recomputes identity/cursor/articulation through
TwoHandObservations with original times, then uses real strict transport/controller.
It uses deterministic synthetic UUIDs and the recorded tracker control settings. It
stops sending at EOF/disconnect; no camera, microphone or recorded voice commands.
Identical landmark files produce identical measurements/events; Blender wall-clock
load and scene/view state still affect stale-input rejection and selection.
No user failure capture is available yet; synthetic tests cannot certify usability.

## Install and launch

Verified executable versions: external Python 3.12.15; Blender 5.2.2 LTS, its Python
3.13.13. Existing dependencies/model reused, no installation. Source/package version
0.9.0; coherent protocol `left_clutch_v3`. The installed user add-on remains 0.8.0
until the user follows this update. Cached running modules require a full restart.

1. Save a separate `rehearsal_090.blend`; keep previous scenes untouched.
2. Stop old companion. Blender Disconnect; disable/remove Air Modeler in Preferences.
3. Fully quit Blender. Reopen → Preferences → Add-ons → Install from Disk →
   `/Users/krishpatel/HackRu/dist/air_modeler.zip`; enable and confirm **0.9.0**.
4. Fully quit/reopen again; open the separate scene, Object Mode, Global Undo enabled.
5. Privately enter the replacement key in launching Terminal using README's hidden
   zsh prompt, then run the exact command below. Do not send/read/log/store the key.
6. Connect from intended 3D viewport. Check actual Left/Right observations, bridge
   Connected/READY and **Scribe session ready**, not merely process startup.

```sh
cd /Users/krishpatel/HackRu && /Users/krishpatel/HackRu/.venv/bin/python -m companion.main --camera 0 --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --two-hands --mic --device 0 --push-to-talk
```

Confirmed devices: camera 0, microphone 0 MacBook Air Microphone. Hands worker
still `preview=False`. PTT starts muted; `/talk`, speak one command, `/end`, wait
for committed text and Blender result. Typed input stays available. `/end` is not
Cancel. `quit`/Ctrl+C shuts down. Check camera light off and terminal prompt return.

Explicit legacy fallback replaces `--two-hands` with `--legacy-hands`; legacy
single-cursor rotation retains world-Z default for bare rotate. Typed-only removes
camera/model/two-hands/mic/device/PTT flags. Keep matching source and ZIP. Sponsor
attribution unconfirmed; the exposed old key still requires its owner's revocation.

## Verification and physical status

Final automated results, package hash and changes are recorded below after final
checks. They remain separate from [physical acceptance](physical_acceptance.md).
The user's working MOVE report applies to the old workflow; new SCALE, three-axis
physical rotation including palm-to-knuckles, gain comfort, labels and combined
PTT demo require actual observations. Rehearsal proceeds one small action at a time.

### Final automated evidence

**290 Python tests passed, 78 subtests passed** using existing `.venv`;
`/tmp/air09-final-python.log`. Full suite ran after Blender TCP checks finished,
with no competing port listener. This includes unchanged voice/PTT/transport
regressions and new metric-pose, quaternion, protocol, deterministic recording and
session-boundary replay tests. Compile and `git diff --check` also pass.

Nine isolated Blender 5.2.2 scripts exited **0**:

| Script | PASS groups | Log |
| --- | ---: | --- |
| smoke_check | 6 | `/tmp/air09-final-smoke_check.log` |
| stabilization_check | 4 | `/tmp/air09-final-stabilization_check.log` |
| extrusion_geometry_check | 27 | `/tmp/air09-final-extrusion_geometry_check.log` |
| move_check | 7 | `/tmp/air09-final-move_check.log` |
| transform_check | 13 | `/tmp/air09-final-transform_check.log` |
| extrusion_check | 13 | `/tmp/air09-final-extrusion_check.log` |
| bridge_check | 16 | `/tmp/air09-final-bridge_check.log` |
| precision_check | 6 | `/tmp/air09-final-precision_check.log` |
| clutch_check | 11 | `/tmp/air09-final-clutch_check.log` |

The new spatial check exercises free quaternion XYZ with a nonidentity view,
rotated/nonuniform/reflected object, explicit world constraints, sign equivalence
and continuous 180° crossing, all signed face directions, ambiguity/parallel ties,
repeated caps and unsupported shear. The revised real-TCP clutch script verifies
free XYZ with native Undo and short-loss recovery, fist contact/reopening,
Left-only selection/inert movement, unchanged MOVE, hidden-face selection (Left
is deliberately aimed at the opposite face), six signed extrusion directions,
face-lock zero mutation, exact fixed distance, reversed-to-zero/no-edit Undo,
both completion orders, release gates and interruption cleanup.

The last package-only intent refinements (bounded pinch entry and allowing valid
closed-hand orientation) were followed by the complete clutch/precision checks
and final Python suite; earlier legacy/geometry checks cover unchanged paths.
These results validate implementation, **not physical hand accuracy or a live demo**.

Intermediate failures: old schema/test fixtures were updated to v3; package smoke
needed its allowlist updated for the new shared quaternion module; a continuity
assertion compared quaternion signs instead of equivalent rotations, corrected to
matrix comparison; an old test assumed face-dependent AUTO mapping, replaced with
the explicit-plane fixed-distance workflow; bare-rotate/default-axis and release
version assertions were updated. An overlapping Python/Blender run conflicted on
8765 and interrupted a legacy preview; those suites were rerun sequentially and
passed. No production watchdog or geometric assertion tolerance was weakened.

Final ZIP `/Users/krishpatel/HackRu/dist/air_modeler.zip`, **0.9.0**,
SHA-256 `959a016645b2b9025a6557d8d46e4df35d073b7c6cb186ddc514036eae82d202`.
All **13 runtime-only entries** match source byte-for-byte; `_protocol.py` matches
shared/protocol.py and spatial.py matches shared/spatial.py. No tests, scenes,
model, environment, recording or credentials are packaged. Model checksum remains
`fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`.
Existing dependency versions were read and reused: MediaPipe 1.1.0, OpenCV contrib
4.11.0.86, NumPy 1.26.4, ElevenLabs 2.71.0, sounddevice 0.5.6, websockets 17.2.

Preserved 0.8 baseline ZIP SHA-256:
`e4803f25351d86e0368d0b211302b4b06e0578540ce52f4ec0c4ecffc22321cc`.
All six new physical groups are **NOT RUN**. First user action: save a separate
`rehearsal_090.blend`; then guide installation and each observed test one at a time.
