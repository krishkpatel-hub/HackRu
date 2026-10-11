> Current release **0.16.0** adds [all-face access and AUTO normal dragging](face_access_handoff.md).
> [Automatic CREATE/REMOVE voice](voice_auto_handoff.md) is preserved.
> The 0.13 dwell/observation implementation below is preserved. Its automated numbers
> are the historical baseline; current results are in the face-access handoff. All current
> physical checks remain NOT RUN. No main merge or scene edits.

# Air Modeler 0.13.0: two-second face hover and smoother observations

Branch `feature/blender`; release commit is reported in chat and available with
`git log -1 --format=%H`. Baseline `eab6d178a01843bfdb51ca23f2400c2bba5dc078`
(0.12.0) is preserved in `dist/air_modeler-baseline-0.12.0.zip`,
[engineering record](clutch_handoff_0.12.md) and [physical record](physical_acceptance_0.12.md).
No main merge or scene edits. Known PR permissions remain blocked; prepared
review description: `/tmp/air-modeler-integration-pr.md`.

## Changed files

- Runtime workflow/UI/version: `addon/air_modeler/bridge.py`, `extrusion_input.py`,
  `visibility.py`, `viewport.py`, `panel.py`, `__init__.py`; `companion/main.py`.
- Observation measurements/filter: `companion/hands/articulation.py`, `config.py`,
  `observations.py`, new `feature_filter.py`.
- Focused checks: `tests/test_extrusion_input.py`, new `test_feature_filter.py`;
  `addon/air_modeler/clutch_check.py`, `extrusion_check.py`, `visibility_check.py`,
  `precision_check.py`.
- Documentation: `README.md`, `docs/protocol.md`, `hands_handoff.md`, `clutch_handoff.md`,
  `demo_handoff.md`, `physical_acceptance.md`; archived `clutch_handoff_0.12.md`,
  `physical_acceptance_0.12.md`, `demo_handoff_0.5.md`.

Geometry generation, intent thresholds, shared schema/validator, voice/PTT modules,
working cursor engine and dependencies are unchanged. Generated ZIPs are local
ignored artifacts, not committed. Scene files are excluded from staging.

## Unchanged hand contract

Left thumb/index pinch selects and holds the object only; Left movement is inert.
Right open-palm translation is MOVE; coherent closing to a fist and reopening is
SCALE; palm orientation is ROTATE with FREE three-axis motion or explicit X/Y/Z
constraints; isolated Right thumb/index pinch starts EXTRUDE targeting. No new
fingers, role swap, mandatory voice or confirmation gesture. Other gestures,
MOVE cursor correction/mapping/sensitivity, transform baselines and native Undo
remain. Active tools do not compete or switch until completion/cancellation.

## Hover workflow and timing

1. Left-pinch and hold an eligible object with Right open. This selects the object,
   not a face. A Right pinch already held at selection must open and pinch freshly.
2. A fresh isolated Right pinch reserves EXTRUDE. Hold both pinches, keeping other
   Right fingers substantially extended. **TARGETING:** “Hover the right cursor over
   a face.” Corrected palm-relative Right cursor remains movable while pinched.
3. Move the displayed Right cursor inside the desired eligible visible polygon.
   **DWELLING:** cyan polygon plus “Hold on this face: 1.2 / 2.0 s.” Moving anywhere
   inside that same polygon keeps progress; crossing its triangulation seam does
   not create another face identity. No geometry or Undo is created.
4. After two seconds of fresh valid same-face observations, **LOCKED:** orange face
   and “Face locked — drag to extrude.” Capture a new current Right drag reference,
   face identity, baseline normal and mapping. All targeting motion is consumed.
   Ordinary extrusion is exactly zero at lock; no extra pause or gesture is required.
5. Subsequent drag deforms only that locked face, even off the face or across others.
   **DRAGGING:** signed distance, OUT arrow, active plane/axis and limit feedback.
   Holding still holds the result. Reverse through zero into supported inward motion.
6. Matching Right release with valid Left, or matching Left release with valid Right,
   completes a meaningful edit once. The other release only rearms. Either release
   before lock ends with no edit/Undo; mismatched/stale IDs cannot complete it.

`DwellConfig.duration = 2.0` is the single configuration value for the dwell duration
in `addon/air_modeler/extrusion_input.py`. `DwellConfig.max_gap = 0.20` seconds bounds
both capture and receiver gaps. Effective progress is the minimum of elapsed
monotonic capture time and local receipt time. Delivery age must be within ±200 ms
of the session's established clock offset. No frame count, timer callback, duplicate,
compressed replay or queued gap can establish continued hover. Existing session,
sequence, frame-ID, timestamp and gesture UUID protection remains unchanged.

A different face restarts at zero. Empty space, 3-pixel boundary margin, occluded or
unsupported hit, incompatible mapping, invalid/missing required hand, stale input
or gap over 200 ms clears progress and cyan highlight. The timer can clear stale
progress but never authorize lock. Sustained 0.5 s loss still cancels. A brief loss
after lock freezes/reanchors deformation without a jump; tracking loss is not release.
Projection/navigation changes during targeting reset and reevaluate current screen
coordinates. After lock, view/context changes follow existing safe cancellation.

Typed `extrude` uses this same sequence. `extrude 0.5 units` or `extend .5 units`
also waits for the full dwell; the fixed amount applies on the **next valid observation**
after lock, independent of targeting travel, without an extra drag. It remains a
preview until valid release; Cancel restores exactly. The feedback distinguishes
fixed amount from ordinary zero-at-lock extrusion.

## Cursor, visibility, mapping and geometry

The exact corrected Right `u/v` used to draw the cursor feeds the ray in the connected
Blender WINDOW region. Mirroring/top-origin conversion happens once. Perspective and
orthographic viewport rays use cached evaluated scene BVHs; hits resolve to the
selected baseline polygon, never another object or an occluded/opposite face.
Enabled modifiers and unsupported original/evaluated topology remain rejected.
Directional scoring and tie-breaking have been removed from this selection path.

The existing AUTO/XY/XZ/YZ plane and optional world axis map **post-lock** displacement
to signed distance along the locked world normal. Normal projection below 0.25
cannot support that mapping: cancel, choose a compatible plane/axis and retry. No
other face is silently substituted. Existing gain is 12 world units per image-height,
symmetric deadband 0.003 image-height, mapped travel bound 4 units. An aligned raw
0.05-height motion gives 0.564 units after the 0.036-unit deadband. Holding does not
accumulate; continuous reversal restores the original mesh datablock at zero.

Eligible faces must satisfy existing supported geometry rules, front-facing dot≥0.04,
projected area≥16 pixels², and an unoccluded in-window sample. Inverse-transpose world
normals handle supported rotated/nonuniform/reflected transforms. The ray under the
cursor must independently hit that eligible selected polygon first. A three-pixel
interior margin rejects ambiguous shared boundaries. No boundary hysteresis carries
progress onto another face. Solid shading/X-Ray off is the supported demo setup.

Candidate discovery samples triangle interiors, centers and near corners. Tiny
visible slivers between samples can be missed conservatively. Limits remain 256
target vertices/faces, 128 evaluated objects and 100,000 evaluated vertices/polygons;
instanced occluders reject. Occluder stamps are checked at 4 Hz and forced at lock
and completion. Changes before lock refresh/reset; changes afterward cancel.
Target geometry/attribute or transform changes always cancel. Temporary stale cyan
feedback may exist until the next stamp check, but forced revalidation prevents
locking through changed geometry. New transactions use current mesh/transforms.

Tint/outline remains POST_VIEW, LESS_EQUAL depth-tested with no depth writes and
restored GPU state. Cyan is candidate, orange locked; the actual polygon/preview
outline and OUT arrow follow geometry. No material/object edits support the overlay.
Release, cancellation, disconnect, context/file loss, disable and shutdown clear it.
All Blender/mesh work remains on the main thread. Topology generation was not rewritten.

## Recognition evidence

Existing measurements were already separated: image palm translation, wrist/MCP
rigid orientation, normalized PIP/DIP and chain geometry for four-finger flexion,
thumb/index contact with other-finger eligibility, identity/validity/freshness.
Fingers together remain open; reliable full fists remain valid. Thumb/fingertips
never define orientation. World landmarks are hand-relative, not absolute depth.
No per-joint confidence is available or assumed.

This release changes only the observation path in two bounded ways:

- One elapsed-time filter follows **raw** geometry validation and orientation-jump
  rejection. `HandConfig.feature_smoothing_s = 0.05` seconds; coefficient
  `1 - exp(-dt/tau)`. Shortest-arc quaternion interpolation smooths orientation;
  per-finger EMA smooths articulation, with openness still the exact four-value mean.
  Raw hysteretic pose gates are retained so a fist cannot inherit a filtered old
  extrusion permission. Missing/invalid data or `feature_max_gap_s = 0.20` resets
  filter state; recovery starts from raw data and the controller rebases safely.
  Cursor and palm translation use their unchanged existing filter only.
- Unused thumb joints 1–3 no longer invalidate otherwise valid measurements.
  Wrist, thumb tip and required palm/finger geometry still must be valid; no guessed
  joints or invented confidence. A partial-landmark regression verifies both paths.

The 0.12 controller arbitration is preserved: 200 ms median evidence window, coherent
≥3-finger change reserves SCALE at 0.04 before 0.15 activation; stable-openness band
0.08; 25° scale wobble allowance; 8° rotation threshold; 150 ms persistence, dominance
1.35, candidate hysteresis 0.75. Large mixed intent stays ready, minor shape changes
can settle, and isolated pinch has its existing bounded entry reservation. No new
universal delay and no threshold changes. Once active, previews still use the
original baseline. Scale remains positive/bounded `exp(log(4) × openness change)`,
preserving proportions, origin, rotation and original scale signs.

Measured deterministic **generated** noisy 3D geometry, 30 Hz, seed 13, 0.002-coordinate
Gaussian landmark noise, 360 frames with the first 30 excluded:

| Measurement | Unfiltered | 50 ms filter |
| --- | ---: | ---: |
| Stationary palm angular RMS from baseline | 1.3302° | 0.7670° |
| Stationary openness standard deviation | 0.002988 | 0.001659 |
| SCALE activation after deliberate motion onset (separate seed 42 trace) | 0.500 s | 0.533 s |
| ROTATE activation after deliberate motion onset (separate seed 42 trace) | 0.400 s | 0.433 s |
| Stationary false tool activation in that 4-second trace | none | none |

Recognition traces use constant bone lengths, coherent closure with small palm wobble,
and a separate rotation trace, with 0.0015-coordinate noise. They remain distinct.
Step response is 98.17% after 200 ms at 15/30/60/120 Hz; held poses converge without
accumulation. These justify the small filter's smoothing/latency tradeoff, not a
physical error-rate claim. Cursor/identity outputs compare exactly with filtering
on/off. Existing jump rejection and corrected cursor/release/loss tests still pass.

The only checked-in real pinch recording contains 259 sparse image-landmark frames,
two pinch cycles and no full world/finger pose. Its unchanged replay passes, but it
cannot quantify this user's SCALE/ROTATE defect. Full current physical results are
**NOT RUN**; capture an actual failure privately before further threshold tuning.
Logs: `/tmp/air13-features.log`. Tests: `tests/test_feature_filter.py`.

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

## Recovery, voice and installation

Unchanged native transactions restore exact baseline geometry/attributes on Cancel,
Escape, disconnect, file/context loss, disable or shutdown. One meaningful completed
edit creates one Undo step; targeting/unchanged release creates none. Both release
orders are retained. Required releases must be observed before rearming. Invalid
completion cancels; all scene edits remain on Blender's main thread.

PTT and typed numeric commands remain. Microphone speech is now CREATE/REMOVE only;
REMOVE and status feedback extend the shared schema as documented in the voice handoff. `/talk` arms audio; `/end` mutes/commits; wait for the
actual committed phrase and visible result. `/end` is not Cancel. Typed commands
stay available. The teammate's standalone report is not this combined demo. Realtime
access works per that report; sponsor attribution remains unconfirmed. The owner
must revoke the previously exposed credential; replacements enter privately only.

## Install and launch

For current installation and evidence, use the [0.16 face-access handoff](face_access_handoff.md).

Existing environment: Python 3.12.15, Blender 5.2.2 LTS/Python 3.13.13. No dependencies
reinstalled. Rebuilt ZIP and source are **0.16.0**; the `left_clutch_v3` hand schema is unchanged.
The prior 0.13 inspection found installed **0.12.0 on disk**; the loaded version
has not been verified for this release. The prior companion was stopped for those
tests. Current checks use separate factory-startup processes; the user's Blender
session and all scene files remain untouched.

1. Save a NEW `/Users/krishpatel/HackRu/rehearsal_0_16.blend` copy. Preserve every older scene.
2. Stop any companion; Blender Disconnect, disable/remove the old Air Modeler add-on.
3. Fully quit/reopen Blender. Preferences → Add-ons → Install from Disk →
   `/Users/krishpatel/HackRu/dist/air_modeler.zip`. Enable and confirm **0.16.0**.
4. Fully quit/reopen again to clear cached modules. Open the new rehearsal scene,
   Object Mode, Global Undo on, Solid shading and X-Ray off. Use one connected viewport.
5. In Terminal, if needed, enter the replacement key with hidden input:

```zsh
set +x
read -rs 'ELEVENLABS_API_KEY?ElevenLabs API key (hidden): '
export ELEVENLABS_API_KEY
printf '\n'
```

Then this CLI-verified command (typed fallback remains active):

```sh
cd /Users/krishpatel/HackRu && /Users/krishpatel/HackRu/.venv/bin/python -m companion.main --camera 0 --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --two-hands --device 0
```

Camera **0**, microphone **0 MacBook Air Microphone** were user-confirmed. Integrated
hands worker keeps `preview=False`. Launch Blender separately from the key-bearing
shell. Connect in intended viewport's N sidebar. Confirm companion **0.16.0**, profile
v3, Connected/READY, actual hand observations with correct anatomical identities,
and **VOICE LISTENING — CREATE/REMOVE ONLY** separately. Process started is not services connected.
`status`/`help` remain available; hands-free listening is automatic. Optional PTT starts muted. `quit`/Ctrl+C stops workers;
check camera off and prompt returned, then `unset ELEVENLABS_API_KEY`.

## Historical 0.13 verification

Python: **334 tests + 78 subtests passed** (`/tmp/air13-python.log`). Coverage includes
dwell at 10/15/24/30/60/120 Hz, same-face identity, resets, stale/duplicate/queued input,
no timer lock, noisy/partial observations, raw jump guards, rate-independent filtering,
MOVE cursor parity, identity/order, retained gesture separation, real sparse-pinch
replay, protocol, voice/PTT, transport and lifecycle. No test substitutes for real
camera/audio acceptance. Original 67-test/78-subtest evidence remains historical.

Blender **5.2.2 LTS**, isolated factory-startup profiles, serial localhost checks:
all **12 scripts passed, 131 PASS groups**.

| Script | PASS groups |
| --- | ---: |
| `smoke_check.py` | 6 |
| `stabilization_check.py` | 4 |
| `extrusion_geometry_check.py` | 27 |
| `signed_extrusion_check.py` | 10 |
| `visibility_check.py` | 9 |
| `overlay_check.py` | 3 |
| `move_check.py` | 7 |
| `transform_check.py` | 13 |
| `extrusion_check.py` | 13 |
| `bridge_check.py` | 16 |
| `precision_check.py` | 6 |
| `clutch_check.py` | 17 |

The full two-hand controller check includes six-face extrusion, real two-second
dwell, no early geometry/Undo, same-face travel/rebase, face/empty/invalid/gap/navigation
resets, decoder-error reset, cyan/orange polygon parity, fixed distance, locked-face
reversal, both release orders, separate native Undo, recovery and lifecycle cleanup.
Visibility covers perspective/orthographic cursor rays, polygon triangulation seams,
occluders, rotated/nonuniform/reflected objects and mapping incompatibility. GPU
checks use actual rendered pixels/depth. Legacy extrusion remains covered separately.
Logs: `/tmp/air13-final-<script-name>.log`. Inputs are generated, not physical hands.

Development checks found a legacy modal guard accessing two-hand-only fields; the
guard now explicitly requires dwell state, with a decoder-error legacy regression.
One controller run had a measured 575 ms capture gap and correctly cancelled stale
input (`/tmp/air13-clutch-attempt1.log`). The full reruns passed, including the explicit
0.68-second stale-cancellation test. Neither freshness nor loss timeouts were relaxed.


Historical 0.13 package inspection: 16 runtime entries, byte-identical to source and unchanged
shared protocol/spatial copies; actual version 0.13.0. Compile and diff checks pass.
ZIP SHA-256: 581b03aed347be4d893689c12a1e1502731cc04365a5a2c8bb8e8f3144e05c1d.

[Physical acceptance](physical_acceptance.md): **all NOT RUN for 0.13.0**. Follow it
one action per reply; begin with scene preservation, installation/version/connection
and anatomical hand identity confirmation. The user-reported defects remain physical
acceptance work, not verified successes. [Combined rehearsal](demo_handoff.md).
