> Current 0.7.0 controls and verification: [clutch handoff](clutch_handoff.md). The material below is historical and does not establish a combined 0.7.0 live pass.

# Two-hand selection and precision handoff — 0.6.0

Cursor-fixed baseline was committed/pushed before enhancements: `9fc3907` (integration merge `2e18ae8cfd93bfd8a7fe321caed0f9473ccb09d2`), incorporating reviewed H implementation `b6d3d56` and handoff `d3ced04`. Baseline: 71 Python tests + 78 subtests, package 0.5.0. The baseline ZIP is preserved locally at `/tmp/air-modeler-cursor-baseline-0.5.0.zip`. Final enhancement commit is the commit containing this file (`git log -1 --format=%H -- docs/enhancement_handoff.md`). Package **0.6.0**, minimum Blender **5.2**, tested runtime **5.2.2 LTS**. No dependencies changed.

The user's updated instructions authorize implementation across all project modules; Plus teammates now assist testing. No other branch implementation beyond the reviewed hands tip was merged. `demo.blend` and `demo.blend1` are unrelated and preserved. No main merge or PR permission retry.

## Installation and runtime identity

Build: `/Users/krishpatel/HackRu/.venv/bin/python /Users/krishpatel/HackRu/tools/package_addon.py`.
ZIP: `/Users/krishpatel/HackRu/dist/air_modeler.zip`. It contains ten runtime files: the prior eight, new `selection.py`, and generated `_protocol.py` identical to `shared/protocol.py`.

Save user work under the user's chosen name; do not overwrite demo files automatically. Disconnect, disable/remove the old add-on in Preferences, quit Blender, restart **5.2.2**, install the ZIP through Preferences → Add-ons → Install from Disk, enable Air Modeler, and confirm **0.6.0**. Use Object Mode, Global Undo, one ordinary viewport and a separate rehearsal scene.

Before live acceptance, verify the running module, not just the ZIP label. After that restart, in Blender's Python Console this read-only check compares installed source bytes to the package:

```python
import air_modeler, bpy, pathlib, zipfile
print(bpy.app.version_string, air_modeler.bl_info['version'], air_modeler.__file__)
z = zipfile.ZipFile('/Users/krishpatel/HackRu/dist/air_modeler.zip'); root = pathlib.Path(air_modeler.__file__).parent
print('PACKAGE MATCH', all((root / pathlib.Path(n).name).read_bytes() == z.read(n) for n in z.namelist())); z.close()
```

Expected: Blender 5.2.2, add-on (0, 6, 0), PACKAGE MATCH True. Restarting first is necessary because file bytes alone do not prove already-imported modules refreshed. Return to the viewport before Connect. This identity check remains NOT RUN in the user's live session; disposable native tests install the actual ZIP and verify isolated runtime paths.

## Launch and role check

The user confirmed camera **0** and microphone **0: MacBook Air Microphone**. Re-run the existing discovery commands if devices change:

```sh
cd /Users/krishpatel/HackRu
/Users/krishpatel/HackRu/.venv/bin/python -m companion.hands --list-cameras
/Users/krishpatel/HackRu/.venv/bin/python -m companion.voice --list-devices
```

Privately enter the authorized replacement key in this companion terminal using the hidden zsh prompt in README. The voice module reads `ELEVENLABS_API_KEY`. Never print/share/commit it or pass it to Blender. The exposed prior key needs revocation by its owner; revocation is not verified here.

Single-hand cursor-fixed fallback, typed commands always available:

```sh
cd /Users/krishpatel/HackRu
/Users/krishpatel/HackRu/.venv/bin/python -m companion.main --camera 0 --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --mic --device 0 --push-to-talk
```

Two-hand automatic selection:

```sh
cd /Users/krishpatel/HackRu
/Users/krishpatel/HackRu/.venv/bin/python -m companion.main --camera 0 --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --mic --device 0 --push-to-talk --two-hands --manipulator-hand Right
```

Use `--manipulator-hand Left` to swap both roles. `--two-hands` requires `--camera`. Both modes use one capture stream and worker `preview=False`. No extra Blender smoothing was added. The standalone hands CLI also accepts these role flags; its optional preview runs on its main thread and uses the same capture stream.

Wait for **READY** (Blender handshake) and **Scribe session ready** (voice connection), then verify `tracking: true` with an open manipulation hand. A process/worker starting is not proof of connected services. PTT starts muted; `/talk`, one phrase, `/end`, then wait for committed feedback and visible result. Muted audio is replaced with silence; microphone remains open. Do not reconnect while provider speech is still pending; restart companion first if recognition stalls.

First physical identity check: with only your anatomical right hand open in view, the cursor should appear in the default two-hand setup after stable acquisition. Remove it and show only your left hand: no manipulation cursor should appear. Then show both separated; left changes modes, right alone pinches/drags/releases. This is NOT RUN here. The existing pipeline mirrors once before inference. [MediaPipe's handedness convention](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/hands.md) assumes mirrored/selfie input; physical verification on the installed Tasks model remains required. Never infer roles from detection-array order or screen side.

## Selector observations and identity

Default right manipulator / left selector, configurable as above. Handedness confidence ≥0.8, unique label, finite landmarks and spatial continuity are required. Palm-center separation <0.12 normalized image distance, >0.18 per-frame jumps, or a candidate closer to the previous opposite identity cause rejection. Labels and spatial continuity both matter. After 600 ms without a recovered idle identity, old spatial anchors may expire; a new identity still requires 300 ms stable acquisition plus the engine's open-hand gate.

Any manipulating-hand uncertainty during a pinch quarantines that role until cancellation; frames report absent and the existing 0.5 s loss path cancels once. This intentionally prefers a cancelled gesture over transfer to the other hand. Even brief two-hand identity uncertainty may therefore lead to cancellation rather than resuming; ordinary single-hand short-loss behavior is unchanged. Crossing/occlusion limits are conservative and need physical rehearsal; this is not biometric identity tracking.

Selector classifications inspect four non-thumb fingers. PIP and DIP angles ≥160° plus tip distance from wrist ≥1.15×PIP distance mean extended. PIP angle ≤110° and tip distance ≤1.1×PIP distance mean folded. Geometry is aspect-corrected 2D. Thumb is ignored by selector classification and remains used by manipulation pinch detection.

| Pose | Armed tool |
| --- | --- |
| Four folded fingers (fist) | MOVE |
| Index + middle extended; ring + pinky folded | ROTATE, world Z |
| Index + middle + ring extended; pinky folded | SCALE |
| All four extended (open palm; thumb ignored) | EXTRUDE |
| Absent/ambiguous | Retain confirmed tool briefly, then MOVE |

A new pose needs 300 ms stable classification **while idle**. Ambiguous/absent/unconfirmed-flickering poses retain the old confirmed mode for at most 600 ms; stale observations also fall back. No selector gesture/cursor is emitted. Protocol fields, strict validation and compatibility are in [protocol.md](protocol.md#060-optional-two-hand-and-precision-extension-v1-envelope).

Blender captures mode, axis, target/face, baseline and start coordinates at gesture_start. Selector changes cannot modify the preview. Only the manipulating hand moves/releases. The sidebar/cursor labels show armed mode, world rotation axis and source (`automatic selector`, `voice override`, `sidebar override`, or `single-hand/manual`). A bare voice mode or fixed extrusion distance overrides selection for one operation; completion/cancel clears it. A still-confirmed selector can arm the next idle operation. Single-hand completion returns MOVE; interrupted gestures still require open-hand rearming.

## Numeric voice/typed commands and sidebar

Whole phrases only, optional trailing punctuation, decimal digits and signed values. No natural-language/LLM parser. Spoken number words, compound instructions and units such as meters are unsupported. If speech transcribes a number as words, use the typed fallback. Existing UUID/timestamp deduplication and committed-only speech execution remain unchanged.

| Phrase | Meaning / accepted bound |
| --- | --- |
| `rotate x 45 degrees` | Relative world X/Y/Z rotation through object origin; −360..360° |
| `move x -2 units` | Relative world X/Y/Z translation; −100..100 Blender world units |
| `scale by 1.5` | Multiply original signed scale components uniformly; 0.1..10 |
| `extrude 0.5 units` or `extend 0.5 units` | Arm outward world distance >0.00001 and ≤4 for next valid face pinch |
| `extend` | Alias for bare EXTRUDE mode |

Object commands operate once while IDLE on the active **selected eligible mesh**; missing/unselected/unsupported targets and Edit Mode fail without mutation. Rotation preserves origin/scale, movement preserves basis, uniform scale preserves origin/orientation/proportions. Invalid axes, nonfinite values, booleans, malformed/out-of-range numbers and nonpositive scale are rejected. Zero movement/rotation is a no-op without a modeling Undo step. Positive scale 1 is similarly unchanged.

Numeric extrusion never edits incidental hover. Its visible fixed distance overrides automatic selection. Pinch locks an eligible face and immediately previews exactly that amount; subsequent movement does not add distance. Release uses the existing geometry Undo operator once; cancel/loss restores the exact source mesh and frees preview topology. Existing cube/prism/new-cap eligibility, world-normal distance, attribute preservation and manifold validation remain unchanged. Inward/multi-face, reflected/singular/shared/modified/animated targets and recessed/nonconvex/nonplanar faces remain unsupported.

Sidebar Precision: select operation, set rotation axis/angle, move axis/distance, scale factor or extrusion distance. Sliders only stage values. **Apply to Selected Object** snapshots the target and calls the same commit helper as voice. **Cancel Values** resets unapplied values without editing geometry. **Arm Next Face Pinch** arms extrusion instead of immediately editing a face. Typed/voice `cancel` or Escape cancels a preview; Cancel Values is not a geometry cancel. During preview conflicting controls are disabled and conflicting commands immediately rejected, never deferred.

Native Undo detail: voice calls the shared UNDO transform operator directly. Sidebar Apply is an outer UNDO operator calling that same helper; Blender suppresses nested pushes, so only the outer action contributes a step. This was tested with one Undo restoring one sidebar edit. No second transaction manager was added.

## Verification and remaining work

See [physical acceptance log](physical_acceptance.md). Every physical row is currently NOT RUN locally: installed runtime identity, actual mirrored roles/pose comfort, combined voice/hands, face readability, separate Undo, cancellation/loss, reconnect, file-open cleanup, camera light and reopen. No API key or camera recording is stored. Do not present automated or teammate observations as this combined live pass.

The baseline's 5.2.2 transform rechecks did not reproduce the reported 5.1.1 native segfault. They did expose fixed-delay test races (a mode/Undo not yet delivered within 120 ms) and one stale-stream cancellation during a delayed synthetic sequence. Transform assertions now use bounded observation waits instead of treating 120 ms as a delivery guarantee; production loss timeout was not relaxed. Final regression outcomes are recorded below after execution.

Prepared integration PR description remains `/tmp/air-modeler-integration-pr.md`. GitHub's prior 403 and sponsor attribution are separate blockers and do not block engineering. Keep the PR draft, do not merge main. Sponsor admin must confirm attribution; prior key owner must revoke the exposed credential.

### Final automated results

- Full sequential Python suite: **109 passed, 78 subtests passed**. Includes legacy cursor fix, real tracker loop with one mocked capture stream/two detector hands, role-order changes/crossing/occlusion/low confidence, idle reacquisition, selector debounce/absence/flicker, numeric parsing/bounds, committed transcript dedup/repeats, real runner/PTT/config routing and transport checks.
- Blender **5.2.2 LTS**: installed-package smoke and geometry checks passed; foreground real-TCP MOVE, ROTATE/SCALE, EXTRUDE, original bridge and new precision/selector checks passed. These use fresh isolated user resources and disposable scenes, not the user's live add-on.
- New native coverage: numeric world X/Y/Z rotations, signed world movement, scale up/down on a rotated nonuniform target, per-edit Undo, command UUID dedup and intentional repeats, missing selection/Edit Mode rejection, sidebar staged values/reset/one-step Apply Undo, all selector mappings, voice override/locked drag, conflicting-command rejection, sustained loss/rearming, no immediate hovered extrusion mutation, fixed-distance preview, exact cancellation and geometry Undo.
- Legacy native coverage retains cube/prism/new-cap extrusion, topology/attributes/resources, reflected transform sign handling, cancellation/loss/disconnect/context/load-handler cleanup and malformed/stale protocol input. Actual file opening, mouse UI actions and camera/microphone behavior are still physical NOT RUN.
- Intermediate runs exposed fixed-delay test assertions and a stale synthetic stream; no 5.2.2 segfault occurred. The final precision run passed after a prior run cancelled a delayed synthetic preview. Production 0.5-second cancellation remains intact; timing under actual venue load still needs physical observation. A mistakenly concurrent Python/native run failed six fixed-port tests with Address already in use; rerunning sequentially produced the passing count above. Do not run these suites alongside a live companion or each other.
- Rebuilt ZIP: ten allowlisted runtime files, version 0.6.0, exact source bytes and generated shared validator. No model, tests, environment, demo scene or secret included. Existing dependencies reused; no installs performed.

Reproduce Python checks with `.venv/bin/python -m pytest -q`. Native scripts live in `addon/air_modeler/`: `smoke_check.py` and `extrusion_geometry_check.py` use `--background --factory-startup`; `move_check.py`, `transform_check.py`, `extrusion_check.py`, `bridge_check.py`, `precision_check.py` use foreground `--factory-startup`. For every invocation set a fresh `BLENDER_USER_RESOURCES="$(mktemp -d /tmp/air-check.XXXXXX)"` and `--python-exit-code 1`. Run serially. Keep Undo checks in the foreground.

### Enhancement changed files

- `README.md`
- `addon/air_modeler/HANDOFF.md`
- `addon/air_modeler/__init__.py`
- `addon/air_modeler/bridge.py`
- `addon/air_modeler/extrusion_check.py`
- `addon/air_modeler/operators.py`
- `addon/air_modeler/panel.py`
- `addon/air_modeler/precision_check.py`
- `addon/air_modeler/selection.py`
- `addon/air_modeler/smoke_check.py`
- `addon/air_modeler/transform_check.py`
- `addon/air_modeler/transforms.py`
- `companion/hands/__main__.py`
- `companion/hands/config.py`
- `companion/hands/roles.py`
- `companion/hands/tracker.py`
- `companion/main.py`
- `companion/voice/parser.py`
- `docs/demo_handoff.md`
- `docs/enhancement_handoff.md`
- `docs/extrusion_handoff.md`
- `docs/hands_handoff.md`
- `docs/move_handoff.md`
- `docs/physical_acceptance.md`
- `docs/protocol.md`
- `docs/transform_handoff.md`
- `docs/voice_handoff.md`
- `shared/protocol.py`
- `tests/test_hands_tracker.py`
- `tests/test_two_hands_precision.py`
- `tools/package_addon.py`

Additional final checks: 42 focused hands/selector/precision tests passed after rejecting degenerate selector joints as UNKNOWN. The installed real MediaPipe Tasks model constructed with `num_hands=2`, inferred an empty result on a blank synthetic image, and closed cleanly. This verifies API/configuration compatibility only, not physical handedness or camera input.
