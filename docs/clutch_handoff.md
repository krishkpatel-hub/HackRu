# Clutch interaction implementation log

## Preserved baseline

Branch `feature/blender`, origin `https://github.com/krishkpatel-hub/HackRu.git`.
Committed and pushed baseline: `7631716b4c6f2800983207d8f90595bdb32efc0d`, add-on 0.6.0.
Fetch confirmed `d3ced04` / cursor implementation `b6d3d56` already integrated;
no newer origin/feature/hands commits existed. No repeat merge or main change.

Baseline ZIP preserved at `dist/air_modeler-baseline-0.6.0.zip` (ignored build output)
and `/tmp/air-modeler-baseline-0.6.0.zip`.
SHA-256: `9feb436461f8b5f790d080708445eca4cfb2ffd64a8c74208b12315b29e626e7`.

Rechecked before implementation: **109 Python tests + 78 subtests passed**;
Blender **5.2.2 LTS** installed-ZIP smoke and foreground transform/consecutive
Undo regression passed in isolated resources. Initial Python run had six
port-bind failures because the user's 0.6 companion was still listening;
a clean SIGINT stopped that identified companion, then the full suite passed.
The user's Blender process and untracked `demo.blend` / `demo.blend1` were preserved.

User reported installed 0.6.0 in Blender 5.2.2, companion `two_hands=True`, and
Scribe ready. This is startup evidence only. It is not a successful modeling or
combined live acceptance result. New physical checks will follow implementation.

## 0.7.0 interaction and launch

`--two-hands` now means the anatomical clutch interaction, replacing the 0.6 pose
menu. It uses one capture and at most two detector hands. Either hand can MOVE
alone. Two-hand ROTATE/SCALE/EXTRUDE always use Left selection and Right
manipulation; `--manipulator-hand Right` is accepted for old launch compatibility,
while `Left` is rejected in this mode. Omit `--two-hands` for the documented legacy
single-cursor fallback. No working dependencies were reinstalled.

Confirmed devices for this laptop: camera **0**, microphone **0 (MacBook Air
Microphone)**. Keep the private replacement credential in the launching terminal
as `ELEVENLABS_API_KEY`; never put its value in commands, files, chat or logs. The
previous exposed credential still needs revocation by its owner. No new key was
requested or inspected during implementation. Sponsorship attribution remains
unconfirmed; prior Scribe-ready observations establish API startup only.

Hands + push-to-talk + typed fallback:

```sh
cd /Users/krishpatel/HackRu
/Users/krishpatel/HackRu/.venv/bin/python -m companion.main --camera 0 --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --two-hands --mic --device 0 --push-to-talk
```

Hands + typed, no microphone/API required:

```sh
cd /Users/krishpatel/HackRu
/Users/krishpatel/HackRu/.venv/bin/python -m companion.main --camera 0 --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --two-hands
```

Legacy single-hand + PTT fallback (one detected hand; keep the other out of view):

```sh
cd /Users/krishpatel/HackRu
/Users/krishpatel/HackRu/.venv/bin/python -m companion.main --camera 0 --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --mic --device 0 --push-to-talk
```

Typed-only recovery: `/Users/krishpatel/HackRu/.venv/bin/python -m companion.main`.
The runner's real flags are `--camera`, `--model`, `--two-hands`,
`--manipulator-hand`, `--mic`, `--device`, `--push-to-talk`, `--synthetic`.
The integrated worker always uses `preview=False`; camera GUI belongs only on a
main thread. Typed input remains available if camera or voice setup fails.

## Selection, intent and recovery

IDLE → SELECTED_READY → DRAGGING → NEEDS_RELEASE → IDLE. A fresh selecting pinch
uses its independent corrected pre-close aim point. It selects and locks the
object, anatomical owner, UUID, original matrix, original mesh, eligible face,
viewport and configuration without deforming. Left wins simultaneous STARTs in
one coherent frame. Other STARTs are consumed, never queued. A miss requires that
owner visibly open before another attempt; it cannot acquire a later hover.

While SELECTED_READY, owner cursor motion can start MOVE. With a left clutch,
right thumb/index/**middle** grip motion can start rotation or uniform scale;
right open-palm translation can start extrusion. Ring and pinky are folded for
the grip, all fingers including thumb extended for open palm. No index/middle/ring
menu is used in this stream. Static selection or static grip does not edit.

Default normalized intent thresholds:

| Signal | Threshold / behavior |
| --- | --- |
| Selecting cursor displacement | 0.025 of normalized image coordinates |
| Right palm displacement | 0.035 of normalized image coordinates |
| Right grip twist | 8 degrees |
| Right grip aperture change | 12% relative to its ready reference |
| Persistence | Same dominant candidate for 150 ms |
| Dominance | Largest normalized score ≥1 and ≥1.35× runner-up |
| Required loss / pose invalid / stale stream | Freeze immediately, cancel after 0.5 s |

MOVE, twist, aperture and persistence are configurable in sidebar Intent
thresholds; values are captured at selection. The remaining defaults are in the
frozen `intent.IntentConfig` and plane mapping helper (edit/rebuild to tune).
These are starting values requiring physical calibration. Competing intent stays
ready and displays “Twist to rotate or spread fingers to scale.”

At intent lock, capture fresh manipulation references: crossing the threshold
causes no visible jump. MOVE similarly starts its displacement at recognition.
Mode never switches mid-preview. Left movement has no geometric effect during
right-hand operations. Every preview derives from the original object baseline.
Only the matching selecting-hand END commits: corrected frozen final cursor for
MOVE; latest valid right observation for right operations. Right grip aperture
can cross its own thumb/index release threshold without releasing the left
clutch. A ready release or unchanged preview creates no edit or Undo entry. The observed
END itself satisfies the successful release gate; the completed owner may leave
view before the other hand independently selects. Cancellation still needs a
subsequent observed open state.

MOVE needs only its owner; loss of an unrelated hand is harmless. Right operations
need Left plus valid Right grip/open palm. Brief loss freezes and rebases recovery
to retain the last displayed result without jumping. Sustained loss cancels once
and requires observed open state for the operation's required hands. Releasing
Left while Right pose/identity is invalid cancels instead of committing stale
geometry. Invalid/tangent/inward extrusion freezes the last valid cap and an
invalid release restores baseline. Tracking loss never manufactures END.

Confident identity plus continuity, not detector result order, determines roles.
Confidence ≥0.8; initial stable acquisition 300 ms, stable reacquisition 80 ms;
palm jump >0.18 or two palms closer than 0.12 are ambiguous. Active owner anchors
stay protected; Right's anchor also stays protected while Left pinches, even
when wide grip aperture has ended Right's own pinch. Mirrored anatomical identity
must still be confirmed with actual hands on this laptop. Safe cancellation is
preferred when crossing/occlusion cannot establish continuity.

Escape, typed/voice/sidebar cancel, stale stream, unsupported context or target,
source-mesh replacement, disconnect, load-pre, disable and shutdown restore the
one original baseline and free preview resources. Undo during selection/preview
cancels it before undoing the prior completed edit. Sidebar Cancel/Undo remain
available. Clicking/scrolling the sidebar during selection first cancels and
restores the preview before handing the event to Blender, so native Item fields
cannot edit an unfinished preview. Editing keyboard shortcuts remain blocked.
Competing commands are disabled/rejected, never queued.

Idle Cancel or disconnect does not create a new release gate: typed-only
precision commands still work after idle reconnect without a camera. An actual
selection, failed pinch or existing release gate still requires observed opening.

## Twist, scale and signed plane mapping

Grip twist is the unwrapped aspect-correct **2D wrist→middle-MCP direction**:
`atan2(wrist_y - middle_mcp_y, aspect * (middle_mcp_x - wrist_x))`.
The right thumb/index/middle pose authorizes that measurement. Sensitivity is one
world radian per measured radian; default world Z, explicit X/Y/Z override
supported. This is not a measured 3D hand orientation. Rotation keeps original
origin and scale, including component signs.

Aperture is the mean pairwise distance among thumb/index/middle tips (4/8/12),
divided by palm size `max(wrist→middle MCP, index MCP→pinky MCP)`, with x scaled by
camera aspect. Scale is positive current/captured aperture, clamped to 0.1–10.
It preserves origin, rotation, component proportions and negative scale signs;
it never applies twist simultaneously. Degenerate grip measurements are invalid.

EXTRUDE captures the eligible face at Left selection and outlines it before
mutation; held selection never retargets. XY/XZ/YZ are world planes; optional
X/Y/Z must belong to the chosen plane. AUTO includes the dominant world face
normal axis and chooses the second axis using projected viewport area, then
visibility, then deterministic XY/XZ/YZ tie order. Explicit AUTO+axis includes
that axis. The two plane axes are assigned to screen-right/screen-up by strongest
viewport alignment, with deterministic positive sign fallbacks for edge-on views.
Sidebar feedback names the actual locked directions, plane, axis and signed
world displacement.

For normalized right-palm displacement `(du,dv)` (v grows down):
`world_vector = 4 * (horizontal_world_axis * du - vertical_world_axis * dv)`.
Axis constraint suppresses the other component; vector length clamps to **4
world units**. Opposite movement gives opposite signed displacement. Virtual
references after short-loss recovery may lie outside the image; the final vector
is still finite and bounded. No landmark z or camera-depth inference is used.

The vector must be zero (unchanged preview) or point outward with
`dot(vector, captured_world_normal) > 0.00001`. Negative world components can be
outward. Tangent/inward/collapsing results are rejected, not clamped into another
direction. An axis tangent to the selected face cannot produce a valid edit;
choose a suitable outward face or another plane. This is not general collision
or inward-extrusion support.

The captured inverse object linear transform converts the world vector into
mesh-local displacement. One cap/side topology is created per preview; frames
move the same cap vertices from baseline. Object matrices stay unchanged.
Existing eligible closed manifold cube/prism/new-cap restrictions remain:
local single-user mesh, positive nonsingular transform, no enabled modifiers,
constraints, parent, animation, shape keys or custom normals; a planar convex
tri/quad supporting face. Rotation and positive-determinant nonuniform scaling
are supported. Reflections, concave/recessed or nonplanar faces and arbitrary
inward/multi-face extrusion remain unsupported. Exact cancellation reattaches the
untouched original mesh (including attributes); commit validates manifold,
orientation, positive volume and uses the existing geometry Undo operator.

## Precision, overrides and sidebar

Whole phrases retain `rotate x 45 degrees` (±360), `move x -2 units` (±100),
`scale by 1.5` (0.1–10), `extrude 0.5 units` / `extend .5 units` (>0.00001–4).
Object edits need an active selected eligible object, Object Mode and IDLE;
apply once with one native Undo, and no-op values add no edit. Numeric extrusion
arms fixed outward-normal distance, never a hover target. In clutch mode, Left
still selects the face and deliberate Right open-palm motion still activates
EXTRUDE; then exactly the armed distance previews, with no hand-distance addition.
In legacy fallback, the explicit face pinch directly previews the fixed distance.

Bare `move`, `rotate [x|y|z]`, `scale`, `extrude` / `extend` override classification
for one operation: only that tool's own motion score must persist. Required
identities/poses, target lock and thresholds still apply. Right-owned selection
cannot execute ROTATE/SCALE/EXTRUDE; release and select with Left. Completion or
cancellation clears mode, axis, plane and fixed distance; a missed pinch preserves
the armed override for an explicit retry after opening.

Whole plane phrases: `extrude plane xy`, `extrude plane xz axis z`,
`extrude plane yz axis y`, `extrude plane auto`, `extrude axis x` (AUTO), and the
same with `extend`. `axis none` clears the constraint. Incompatible explicit
pairs fail closed. Numeric fixed-distance extrusion is normal-based and ignores
plane mapping; the sidebar labels this distinction.

Sidebar Precision stages values only. Apply edits the selected object; for
extrusion **Arm Next Face Pinch** arms fixed distance. **Arm Next Gesture** uses
the staged mode/rotation axis/plane constraint without applying numeric values.
**Cancel Values** discards staging, not geometry or already armed overrides.
Use Cancel Selection / Preview to clear those. During ready/active selection,
conflicting spawn, modes, precision and staging actions reject immediately.

PTT starts muted: `/talk` arms; speak one complete command; `/end` mutes and
requests commit; wait for timestamped committed feedback and Blender result.
Buffered authorized speech may complete after `/end`; it is not Cancel.
`PTT ARMED` is a gate state, not proof of microphone connection. Wait for
**Scribe session ready**, **Connected/READY**, and actual hand status/cursor.
Typed commands use the same parser and remain available. `quit`/Ctrl+C stops
workers, clears the PTT gate and closes transport; inspect any join warning.

## Package and physical session

Build `/Users/krishpatel/HackRu/dist/air_modeler.zip` using
`/Users/krishpatel/HackRu/.venv/bin/python tools/package_addon.py`. Version **0.7.0**.
The allowlist contains eleven runtime modules and byte-identical generated
`_protocol.py`; no model, tests, environment, scene or credential is included.

Save open Blender work to an intentional location; preserve existing demo files.
Disconnect the old add-on, disable/remove Air Modeler in Preferences, quit Blender,
then reopen Blender 5.2.2. Preferences → Add-ons → Install from Disk → select the
rebuilt ZIP → enable Air Modeler. Confirm **0.7.0**, then restart Blender once to
clear cached modules. Enable Global Undo and use a separate disposable rehearsal
scene. Start one companion, connect from the intended VIEW_3D N sidebar and wait
for actual bridge/hand/voice readiness.

[Physical acceptance](physical_acceptance.md) contains the complete ordered
checklist. Run it one action at a time after automated verification, recording
actual observations against the exact checkout SHA and installed version. All new
physical rows remain NOT RUN until the user supplies observations. Tests using
synthetic observations or geometry do not prove a successful combined live demo.
Prepared PR text remains `/tmp/air-modeler-integration-pr.md`; the earlier GitHub
403 was not retried and does not block rehearsal. Main is untouched.


## Final automated evidence and revisions

Runtime implementation revision: `bc321d48afb97d2cee78e4a52232a5c400c2d11e`. The following documentation-only
commit records this evidence and the physical checklist; obtain the final checkout
revision with `git rev-parse HEAD` before physical testing. The source and package
were verified before committing; no runtime changes followed these final checks.

Preserved baseline: `7631716b4c6f2800983207d8f90595bdb32efc0d` (0.6.0).
Reviewable implementation commits before the runtime integration:
`eb71ca1` baseline record, `9448da5` signed-vector geometry/planes,
`f9451af` bounded recovery mapping, `18e5fd5` normalized persistent intent.
The coherent producer, shared validator, consumer, voice/UI and package changed
together in the runtime integration commit so their wire contract stays aligned.

Final Python suite: **244 passed, 78 subtests passed** using the existing `.venv`.
The existing genuine recorded cursor fixture was retained; new landmark sequences
and coherent TCP observations are synthetic. Dependency compatibility check passed
for 46 installed packages; no dependencies were installed or replaced.

Blender **5.2.2 LTS** checks each passed in a separate factory-startup process
with isolated user resources. Foreground modal/Undo checks used the actual local
TCP companion; background was limited to smoke and pure geometry checks.

| Regression script | Final result | Local evidence |
| --- | --- | --- |
| `smoke_check.py` | PASS — installed ZIP, registration, primitives, rejection, lifecycle | `/tmp/air-07-verified-smoke_check.log` |
| `extrusion_geometry_check.py` | PASS — all plane/axis signs, rotated/nonuniform transforms, topology, attributes, restoration and resources | `/tmp/air-07-verified-extrusion_geometry_check.log` |
| `move_check.py` | PASS — perspective/orthographic MOVE, final coordinates, separate Undo, cancellation/loss/context cleanup | `/tmp/air-07-final-move_check.log` |
| `transform_check.py` | PASS — world XYZ rotation, scale/signs, final values, consecutive Undo and interruption paths | `/tmp/air-07-transform-ready.log` |
| `extrusion_check.py` | PASS — cube/prism/new cap, separate Undo, cancellation and every supported interruption | `/tmp/air-07-final-extrusion_check.log` |
| `bridge_check.py` | PASS — real TCP, UUID dedup, session/reconnect, modal Undo and lifecycle | `/tmp/air-07-final-bridge_check.log` |
| `precision_check.py` | PASS — numeric/UI/legacy compatibility plus typed-only idle cancel and reconnect with no hand observations | `/tmp/air-07-precision-complete.log` |
| `clutch_check.py` | PASS — coherent either-hand ownership, stationary selection, twist/scale ambiguity, no-jump lock/recovery, unrelated loss, six signed directions, fixed/repeated cap, Undo, sidebar isolation and shutdown | `/tmp/air-07-clutch-natural.log` |

The final narrow idle-cancel/reconnect correction was exercised by the last two
checks against the rebuilt final ZIP. Both completed with exit code 0. Earlier
regressions cover the unchanged geometry, transport and legacy paths.

Intermediate failures were investigated, not counted as passes: fixed short
sleeps read commands before delivery or matrices before Blender completed Undo
evaluation; a delayed synthetic timer correctly hit the production 0.5-second
stale-input safeguard. Harnesses now keep coherent heartbeats and wait for exact
observable results. An attempted forced dependency-graph update caused a native
Blender crash during consecutive Undo; that test intervention was removed. The
final clutch check waits for exact matrices/meshes to remain stable over natural
timer cycles and completed all ten assertion groups. Production timeouts and
matrix tolerances were not loosened. Final review also fixed a genuine idle
reconnect gate bug and added its regression. Physical stability still requires
the real session below; these automated passes do not establish a live demo.

Final package: `/Users/krishpatel/HackRu/dist/air_modeler.zip`, add-on **0.7.0**.
SHA-256: `4f41a943139eb05d2c48a2d4e1275467f332d1859cb1f7898e632f3a61519f6e`.
All **12** allowlisted entries match current runtime source byte-for-byte,
including the generated shared validator. ZIP contents exclude tests, scenes,
model, environment and credentials. Rebuilding can change ZIP metadata/hash;
reinspect if rebuilt. The preserved baseline ZIP hash remains unchanged.

All **15 physical acceptance rows remain NOT RUN**. Actual anatomical labels,
gesture calibration, combined camera/PTT behavior, model edits and camera release
must be observed on this laptop. Keep the earlier standalone voice report and
0.6 startup observations separate. The PR permission blocker remains; the prepared
description is available locally and no repeated PR request was made.

### Changed files relative to the preserved baseline

The following 39 project files comprise this change. Untracked `demo.blend`
and `demo.blend1` are unrelated and excluded from commits. Build ZIPs are ignored.

```text
README.md
addon/air_modeler/HANDOFF.md
addon/air_modeler/__init__.py
addon/air_modeler/bridge.py
addon/air_modeler/clutch_check.py
addon/air_modeler/extrusion.py
addon/air_modeler/extrusion_geometry_check.py
addon/air_modeler/intent.py
addon/air_modeler/operators.py
addon/air_modeler/panel.py
addon/air_modeler/planes.py
addon/air_modeler/precision_check.py
addon/air_modeler/smoke_check.py
addon/air_modeler/transform_check.py
addon/air_modeler/transforms.py
companion/hands/__main__.py
companion/hands/config.py
companion/hands/engine.py
companion/hands/observations.py
companion/hands/tracker.py
companion/main.py
companion/voice/parser.py
docs/clutch_handoff.md
docs/demo_handoff.md
docs/enhancement_handoff.md
docs/extrusion_handoff.md
docs/hands_handoff.md
docs/move_handoff.md
docs/physical_acceptance.md
docs/protocol.md
docs/transform_handoff.md
docs/voice_handoff.md
shared/protocol.py
tests/test_clutch_protocol.py
tests/test_hand_observations.py
tests/test_hands_tracker.py
tests/test_intent.py
tests/test_planes.py
tools/package_addon.py
```
