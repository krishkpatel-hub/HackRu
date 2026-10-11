# Air Modeler 0.8.0 — Left clutch, Right whole hand

## Baseline and scope

Branch `feature/blender`, origin `https://github.com/krishkpatel-hub/HackRu.git`.
The fetched, pushed baseline was `a59445232f24704395d3c76563b75ab742cfcfb0` (0.7.0).
Its reported 244 Python tests / 78 subtests / eight Blender scripts are historical,
not evidence for these revised controls. The baseline ZIP is preserved at
`dist/air_modeler-baseline-0.7.0.zip`, SHA-256
`4f41a943139eb05d2c48a2d4e1275467f332d1859cb1f7898e632f3a61519f6e`.

The user's saved rehearsal copy and reported installed/enabled 0.7.0 after a
Blender 5.2.2 restart are preserved in [the 0.7 acceptance record](physical_acceptance_0.7.md)
and commit `4e07d56`. No 0.7 modeling result was reported. The prior full engineering
record is [archived separately](clutch_handoff_0.7.md). `demo.blend`, `demo.blend1`
and `rehearsal_070.blend` remain unrelated untracked scenes and are not changed.
The old identified hands/PTT companion was cleanly signaled to stop for testing;
the user's existing Blender scene was not used for automated checks.

## Revised controls

`--two-hands` uses only this interaction. **Left thumb/index pinch selects and
holds; Left movement never drives geometry. Right alone cannot select or edit.**
The selecting-hand displacement candidate and Right-selection path were removed
from the classifier/controller rather than hidden behind a larger threshold.
No three-finger grip field or aperture authorizes these controls.

| Tool | Right-hand input while Left clutch is valid | Completion |
| --- | --- | --- |
| MOVE | Translate an open palm, all five fingers open, stable shape/orientation | Observed Left release |
| ROTATE | Twist the open whole hand, reasonably stable openness | Observed Left release |
| SCALE | Close the whole hand toward a fist to shrink; reopen to enlarge | Observed Left release |
| EXTRUDE | Fresh isolated thumb/index pinch with at least two of middle/ring/pinky open; drag the corrected pinch cursor | First valid Right-pinch release or Left release |

A fist is valid SCALE input even when thumb and index touch. Right pinch END
while scaling never commits; Left remains the clutch. Static selection, static
Right input and ambiguous motion make no edit. With ambiguous input the sidebar
says: “Move palm, twist hand, close/open hand, or pinch to extrude.”

Left START uses corrected pre-close aim, raycasts once and locks object, gesture
UUID, original transform/mesh, viewport, configuration and any eligible face.
An object without an eligible extrusion face can still be selected for transforms;
face eligibility is reported separately. A miss cannot acquire a later hover.
Neither later Left motion nor another hover changes the target or captured face.

SELECTED_READY compares only Right observations. Activation locks tool,
identities, axis/plane and fresh manipulation references, so threshold crossing
causes no jump. All previews derive from one original transaction baseline.
Changing pose or issuing a mode command cannot switch an active tool.

## Measurements and intent defaults

One mirrored camera capture detects up to two hands. The fixed anatomical labels
come from confidence and spatial continuity, never result-array order. Actual
anatomical labeling still needs the new physical check. Defaults remain confidence
≥0.8, stable acquisition 300 ms, recovery 80 ms, max center step 0.18 and minimum
hand separation 0.12 normalized image units. Right's identity anchor stays
protected throughout Left pinch, including open hand or fist, so uncertain
crossing cannot transfer a transaction to another path.

Palm position uses the existing once-filtered wrist/index-MCP/middle-MCP/pinky-MCP
center. Twist is unwrapped `atan2(wrist_y-middle_MCP_y,
aspect*(middle_MCP_x-wrist_x))`: a **2D image-plane** signal, not full 3D orientation.
Sensitivity is one world radian per measured radian. Rotation defaults to world Z;
explicit X/Y/Z overrides retain the original origin and scale/signs.

Whole-hand openness averages index, middle, ring and pinky, independently of the
three old tips. For each finger:

- Flexion = clamp((min(PIP angle, DIP angle) − 50°) / 110°, 0, 1).
- Reach = clamp((MCP-to-tip distance / palm size − 0.15) / 1.2, 0, 1).
- Finger openness = 0.7 × flexion + 0.3 × reach.

Distances and angles correct x by camera aspect; palm size is the larger of
wrist–middle MCP and index–pinky MCP distances. Translation, uniform image scale
and in-plane rotation leave these shape measurements unchanged. Edge-on palms,
occlusion and projection changes can degrade the 2D measurements; these are not
camera-depth measurements. Degenerate joints/palm orientation produce explicit
shape-invalid feedback and freeze manipulation, not a fabricated release.

Open-palm recognition requires all four finger values ≥0.72 plus an extended
thumb (IP ≥125°, reach ≥0.65 palm sizes). It stays open down to finger 0.60 and
thumb IP 115°. Extrusion eligibility requires at least two of middle/ring/pinky
≥0.72, retaining eligibility down to 0.60. These HandConfig thresholds provide
pose hysteresis. Thumb/index pinch remains palm-normalized: contact ≤0.35,
release ≥0.60, each stable 80 ms; approach reservation begins at ≤0.75.

| Classifier setting | Default |
| --- | --- |
| Right palm MOVE displacement | 0.035 normalized image units |
| ROTATE twist | 8° |
| SCALE openness difference | 0.15 absolute openness units |
| Shape stability for MOVE/ROTATE | ≤0.08 openness difference |
| MOVE orientation stability | ≤16° from ready reference |
| Intent persistence | 150 ms |
| Dominance | Winner ≥1.35 × runner-up normalized score |
| Candidate hysteresis | Retain existing candidate down to score 0.75; activate only at score ≥1 |
| Missing/invalid/stale required input | Freeze immediately; cancel after 0.5 s |

Movement/twist/openness thresholds, persistence, dominance and intent hysteresis
are sidebar configurable and captured at selection. Pose thresholds use
`companion.hands.config.HandConfig`; other constants use frozen `intent.CONFIG`.
**Live calibration is pending.** Generated skeletons are not physical accuracy
measurements.

An isolated pinch approach reserves intent and pauses other candidates, preventing
incidental closing translation from becoming MOVE. Fist closure has folded
remaining fingers and stays SCALE input. A fresh eligible Right START must persist
for the intent window to activate extrusion. Right already pinched at Left
selection (including simultaneous STARTs) must visibly reopen, then pinch again.
Opening after reserved/held isolated pinch resets ready references; it does not
become an accidental SCALE. Corrected pre-close Right START is captured; the drag
reference is rebased at activation so recognition itself does not displace a cap.

Scale factor = `exp(log(4) * (current_openness - activation_openness))`, clamped
to 0.1–10. There is no division by openness, so near-closed starts remain finite.
Closing shrinks; opening enlarges. Scale preserves original origin, rotation,
component proportions and negative scale signs. Twist/translation do not add to
locked SCALE. A static old three-finger pose provides no activation permission.

## Extrusion, completion and recovery

Signed XY/XZ/YZ mapping, AUTO choice and compatible X/Y/Z axis constraints are
preserved. AUTO includes the dominant world-normal axis and chooses the second
axis by projected area/visibility, then deterministic plane order. Axes are
assigned to screen right/up using viewport alignment; edge-on ties use positive
sign fallbacks. Feedback displays object, captured face, plane, axis, signed
vector and actual screen directions.

For Right **corrected pinch cursor** displacement `(du,dv)` (v increases down),
`world_vector = 4 * (horizontal_axis * du - vertical_axis * dv)`.
Axis constraint suppresses the other component; length clamps to 4 world units.
Opposite movement gives opposite signed vectors. Any ±world axis is available on
a suitable outward face. A nonzero vector must satisfy
`dot(vector, captured_world_normal) > 0.00001`; zero is unchanged, and tangential
or inward motion rejects safely. Invalid motion freezes the last valid mesh;
releasing while invalid cancels instead of committing it.

One cap/side topology is created per preview; only its cap coordinates change
from baseline. The captured inverse object linear transform converts world motion
to mesh local space. Object transforms remain unchanged. Supported geometry is a
local single-user closed manifold mesh with a flat convex triangular/quad
supporting face, positive nonsingular transform, no enabled modifiers, constraints,
parent, animation, shape keys or custom normals. Cube/prism/new caps and rotated,
nonuniform positive scales remain supported. Reflections, arbitrary inward or
recessed/concave/nonplanar faces and general collision detection remain unsupported.

Only a coherent matching valid boundary completes. MOVE/ROTATE/SCALE use Left END
and current valid Right input. EXTRUDE accepts matching Right END with frozen
final Right coordinates or Left END with latest valid Right coordinates. First
completion clears the transaction; later releases cannot make a second edit.
After Right-first completion, Left must release; after Left-first completion,
Right pinch must release. Completed extrusion stays inactive while Left remains
held. Both gates can be satisfied in one frame or by separately observed releases.
Unchanged/zero-distance completion restores temporary state and creates no Undo.

Both Left and Right are required for these gesture transactions. Missing identity,
invalid required pose or invalid whole-hand measurement freezes immediately.
After 0.5 seconds cancel once, restore exact baseline and require observed release
of both hands. Brief recovery rebases manipulation references to the frozen result
without jumping. A completion in the same frame as recovery from required-hand
loss cancels rather than committing stale geometry. Tracking loss never creates END.

Escape, typed/sidebar cancel, stale input, context/target loss, file load,
disconnect, add-on disable and shutdown restore and free resources. Undo during a
preview cancels it before undoing the previous completed edit. Editing shortcuts
are blocked while selected; sidebar clicks first restore/cancel before native UI
receives them. Idle Cancel/disconnect does not manufacture a release gate, so
numeric typed-only controls remain usable after idle reconnect.

## Voice, sidebar, compatibility and launch

Bare `move`, `rotate [x|y|z]`, `scale`, `extrude`/`extend` override only the next
classifier tool. Required Left clutch, Right gesture, threshold/persistence and
target lock still apply; pending isolated pinch cannot be mistaken for MOVE even
under an override. Modes cannot change or queue during selection/preview. Complete
or cancel clears overrides; a missed Left pinch retains the armed mode for retry.

Precise `rotate x 45 degrees`, `move x -2 units`, `scale by 1.5` apply once to the
selected eligible object while IDLE, without a held clutch. Limits remain ±360°,
±100 units and factor 0.1–10. `extrude 0.5 units` / `extend .5 units` arms the next
explicit Left face selection plus fresh Right pinch. It previews exactly that
outward-normal distance, with no additional drag distance and no hover mutation.
Whole phrases `extrude plane xy`, `extrude plane xz axis z`, `extrude plane yz axis y`,
`extrude plane auto`, `extend axis x` work; incompatible pairs reject. Fixed numeric
extrusion is normal-based and ignores plane mapping.

Sidebar values are staging only. Apply commits numeric transforms or arms fixed
extrusion; Arm Next Gesture arms mode/axis/plane. Cancel Values discards staging.
Feedback includes selected object/face eligibility, Left clutch validity, Right
recognition/openness, pending/blocking reason, locked value and release gate.

Protocol envelope remains v1, with strict new `hands_frame.profile` =
`left_clutch_v2` and whole-hand fields documented in [protocol](protocol.md).
Old 0.7 coherent observations fail validation; never pair a 0.7 companion with this
ZIP. UUID dedup, transport cleanup, main-thread bpy and PTT are preserved.

Primary command (existing `.venv`, confirmed camera **0**, microphone **0**):

```sh
cd /Users/krishpatel/HackRu && /Users/krishpatel/HackRu/.venv/bin/python -m companion.main --camera 0 --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --two-hands --mic --device 0 --push-to-talk
```

Typed commands remain available. Hands worker always uses `preview=False` and
one capture. The private replacement key belongs only in the launching terminal's
`ELEVENLABS_API_KEY`; never in chat, arguments, files or commits. Its owner still
needs to revoke the previously exposed key. No key was requested/read. Sponsor
attribution remains unconfirmed.

Explicit legacy fallback (single detected hand, pinch cursor and bare typed modes):

```sh
cd /Users/krishpatel/HackRu && /Users/krishpatel/HackRu/.venv/bin/python -m companion.main --camera 0 --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --legacy-hands --mic --device 0 --push-to-talk
```

Camera runs require exactly one of `--two-hands` or `--legacy-hands`. Omission is
an error, never silent legacy behavior. Standalone camera diagnostics use the
same explicit flags. Typed-only fallback:
`/Users/krishpatel/HackRu/.venv/bin/python -m companion.main` from the project folder.
No microphone/key is needed if `--mic --device 0 --push-to-talk` is omitted.
Implemented runner flags: `--camera`, `--model`, `--two-hands`, `--legacy-hands`,
`--manipulator-hand` (Right only with two hands), `--mic`, `--device`,
`--push-to-talk`, `--synthetic`; `--help` lists them.

PTT starts muted: `/talk`, speak one full command, `/end`, wait for committed
feedback and Blender's result. `/end` mutes/commits buffered authorized audio; it
is not Cancel. Only timestamped committed recognition executes, with provider
and command UUID dedup retained. Wait for **Scribe session ready**, actual hand
observations and bridge **Connected/READY**; a started process or PTT gate alone
is not proof of service health. `quit`/Ctrl+C should stop workers, release camera
and microphone and discard pending transport input; inspect any join warning.

## Install and physical acceptance

ZIP `/Users/krishpatel/HackRu/dist/air_modeler.zip`, add-on **0.8.0**. Build with
`/Users/krishpatel/HackRu/.venv/bin/python tools/package_addon.py`. Only allowlisted
runtime modules and the byte-identical shared validator belong in the ZIP.

Save work into a separate rehearsal copy. Stop the old companion. In Blender,
Disconnect, then Preferences → Add-ons → disable/remove Air Modeler. Quit Blender
fully. Reopen Blender 5.2.2, Preferences → Add-ons → Install from Disk, choose the
new ZIP, enable it and confirm **0.8.0**. Quit and reopen Blender once more to clear
cached modules. Enable Global Undo and open the separate rehearsal scene. Launch
one companion and Connect from the intended 3D viewport's Air Modeler N sidebar.

The [new physical checklist](physical_acceptance.md) has nine ordered groups,
all NOT RUN until user observations. Guide one small action at a time. Historical
0.7 installation, recorded cursor fixtures, standalone voice reports and synthetic
native tests do not fill these rows. PR permissions do not block this work; keep
`/tmp/air-modeler-integration-pr.md` available, without repeating the failed request.


## Verified build and engineering results

Final runtime/feedback commit: `07d77cb3e03033c150da69be7996a71d26d57334`. The core control implementation
is `8181ed5d27d0ffeb3b5663fc45a930191d7136f6`. Separate reviewable commits preserve
0.7 user observations (`4e07d56`) and correct native Undo context lifetime
(`623f12f`). The following documentation commit records delivery; use its final
checkout SHA when starting the physical run. Main was not merged or modified.

**Actual revised Python result: 260 passed, 78 subtests passed** using
`/Users/krishpatel/HackRu/.venv/bin/python -m pytest -q` for the revised gesture, protocol and runner logic.
These include generated whole-finger skeletons, preserved recorded cursor fixture,
identity/crossing/rearming, new strict schema/round trips, classifier hysteresis,
fist/pinch separation and explicit legacy flag selection. Working dependencies
were reused, with no installation or environment replacement.

**Eight Blender 5.2.2 regression scripts passed**, each with exit code 0 in isolated
factory-startup resources. Native modal/Undo scripts ran foreground with the actual
synthetic TCP companion. Smoke/geometry alone ran background.

| Script | Evidence / coverage | Local log |
| --- | --- | --- |
| `smoke_check.py` | Installed ZIP registration, primitives, lifecycle, rejection | `/tmp/air-08-smoke_check.log` |
| `extrusion_geometry_check.py` | Signed planes/axes, transformed geometry, topology/attributes, restore/resources | `/tmp/air-08-extrusion_geometry_check.log` |
| `move_check.py` | Explicit legacy MOVE, final cursor, separate Undo and cleanup | `/tmp/air-08-final-move_check.log` |
| `transform_check.py` | Legacy world XYZ/scale/signs, consecutive Undo, loss/cancel | `/tmp/air-08-final-transform_check.log` |
| `extrusion_check.py` | Cube/prism/new cap, final coordinates, exact restore, Undo and interruption paths | `/tmp/air-08-final-extrusion_check.log` |
| `bridge_check.py` | Real TCP, UUIDs, reconnect, modal Undo, load and disable | `/tmp/air-08-final-bridge_check.log` |
| `precision_check.py` | Numeric/UI/typed-only reconnect, fixed-distance and legacy compatibility | `/tmp/air-08-final-precision_check.log` |
| `clutch_check.py` | New whole-hand controls and completion/recovery, ten assertion groups below | `/tmp/air-08-final-clutch_check.log` |

The revised clutch check proves with synthetic input: Right alone cannot select;
large Left movement in READY and all operations is inert; Right open-palm MOVE;
whole-hand rotation on world XYZ; SCALE through fist/contact/reopening and near-zero
starts; static/ambiguous intent; zero-jump locks; required-hand loss/recovery and
release races; original face plus all six signed extrusion directions; both release
orders with exactly one geometry Undo; final frozen Right release coordinate;
pinch approach priority/held-pinch rearm; fixed distance/repeated cap; exact cancel,
preview Undo, sidebar isolation, disconnect/disable/reconnect and clean shutdown.
Legacy and geometry checks also exercise file/context loss and resource cleanup.

Intermediate results are not hidden or counted as passes. A runner help-text
indentation error was corrected before the final suite. The first new clutch run
had an incorrect test expectation that releases must be simultaneous; production
correctly accepts separately observed releases, and the test now checks the hand
still missing. Another synthetic run had a measured 1.202-second timer gap and
correctly triggered the unchanged 0.5-second stale safeguard. A smaller isolated
window completed the revised test. No production timeout or assertion tolerance
was loosened.

A later legacy consecutive-Undo run crashed inside Blender's scene dependency
update. Unlike the earlier 0.7 hypothesis that only forced test evaluation caused
it, this run had no such forced update. The command handler now overrides only
stable window/area/region context rather than retaining replaceable Scene/ViewLayer
RNA across native Undo. All six foreground scripts, including both legacy and new
consecutive Undo, then passed against the corrected final ZIP. This fixes the
identified context-lifetime hazard; real session stability still needs observation.

Final ZIP: `/Users/krishpatel/HackRu/dist/air_modeler.zip`, version **0.8.0**.
SHA-256: `e4803f25351d86e0368d0b211302b4b06e0578540ce52f4ec0c4ecffc22321cc`.
All **12** allowlisted entries were checked byte-for-byte against runtime source,
including the generated validator. No tests, model, scenes, environment or
credentials are packaged. Pure geometry passed before the narrow command-context correction; all six
foreground scripts passed after it. Sidebar wording/face-feedback changes
were followed by another installed-ZIP smoke and revised clutch run. The final
idle source-label correction was smoke-checked; it changes no modeling logic. Rebuilding
may change ZIP timestamps/hash and should be reinspected.

All **nine 0.8 physical acceptance groups remain NOT RUN**. Installation, actual
anatomical identity, shape calibration, combined camera/PTT modeling, release races
and camera light/reopen must be observed. The prior 0.7 installation does not verify
these controls. The GitHub PR permission issue was not retried; prepared description
remains `/tmp/air-modeler-integration-pr.md` and does not block the rehearsal.

### Changed files relative to the pushed 0.7 baseline

30 project files; unrelated untracked scene files are excluded. Build ZIPs are
ignored local artifacts. Versioned archives retain the previous contract and user
observations instead of relabeling them as 0.8 evidence.

```text
README.md
addon/air_modeler/HANDOFF.md
addon/air_modeler/__init__.py
addon/air_modeler/bridge.py
addon/air_modeler/clutch_check.py
addon/air_modeler/intent.py
addon/air_modeler/operators.py
addon/air_modeler/panel.py
addon/air_modeler/precision_check.py
companion/hands/__main__.py
companion/hands/config.py
companion/hands/observations.py
companion/main.py
docs/clutch_handoff.md
docs/clutch_handoff_0.7.md
docs/demo_handoff.md
docs/enhancement_handoff.md
docs/extrusion_handoff.md
docs/hands_handoff.md
docs/move_handoff.md
docs/physical_acceptance.md
docs/physical_acceptance_0.7.md
docs/protocol.md
docs/transform_handoff.md
docs/voice_handoff.md
shared/protocol.py
tests/test_clutch_protocol.py
tests/test_hand_observations.py
tests/test_intent.py
tests/test_runner.py
```
