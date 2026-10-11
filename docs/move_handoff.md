> Current **0.9.0** stabilization: [handoff](clutch_handoff.md) and [physical checklist](physical_acceptance.md). Material below records earlier versions; 0.9 physical checks are NOT RUN.

> Current 0.8.0 Left-clutch/Right-whole-hand controls: [current handoff](clutch_handoff.md). Material below is historical.

> Historical 0.7.0 controls and verification: [0.7 clutch handoff](clutch_handoff_0.7.md). The material below is historical and does not establish a combined 0.7.0 live pass.

> Current 0.6.0 integration: [two-hand selection and precision](enhancement_handoff.md). The results below are historical.

# Superseded transform support

For version 0.4.0 ROTATE/SCALE support and the generalized commit interface, see [Transform handoff](transform_handoff.md). The following records the 0.3.0 MOVE milestone and its validation.

# MOVE integration handoff (P)

The root README remains the architecture agreement. Add-on **0.3.0** implements a hand cursor, passive hover picking, default viewport-plane MOVE, typed spawning/cancel/undo, and optional hand/microphone workers. Rotation, uniform scaling, and extrusion remain unsupported and visibly rejected.

## Integrated branches

Merged one at a time into `feature/blender`, with no main merge or teammate-module edits:

- Hands: `4af4741f68d5dba6eb8e78b24ca94e1de156893f` (includes the superseded `5ff3460`).
- Voice: current remote tip `e2164c14e63f639609613b9b6901e5c8c8e5466d`, which includes the requested `b1f771da6f110b9fde7792dd0f5d7baaa8ca0c8c`. The newer commit documents physical microphone capture; authenticated recognition remains pending.

The public callback and wire schemas are unchanged. The implementation commit and push status accompany delivery; `git rev-parse feature/blender` identifies it locally.

## Environment verified here

macOS 26.6.2 arm64; external CPython **3.12.15**; Blender **5.2.2 LTS**, bundled Python **3.13.13**. Never install camera/audio dependencies into Blender.

| Package | Verified version |
| --- | --- |
| MediaPipe | 1.1.0 |
| opencv-contrib-python | 4.11.0.86 (`cv2` 4.11.0) |
| NumPy | 1.26.4 |
| ElevenLabs (optional microphone) | 2.71.0 |
| sounddevice | 0.5.6 |
| httpx / websockets | 0.28.1 / 17.2 |
| pytest (development only) | 9.1.1 |

These versions resolved together on Python 3.12; imports, real model construction/close, and dependency consistency passed. Only one OpenCV distribution is installed. An initial MediaPipe 0.10.21 wheel imported but contained x86_64 platform metadata; it was replaced with 1.1.0 and the final dependency check passed. `requirements.txt` owns hands/runtime pins; `requirements-voice.txt` includes V's unchanged audio pins. MediaPipe itself may depend on sounddevice; importing typed input does not require it or open audio.

This checkout already has `.venv/bin/python` backed by an ignored `.runtime/` Python installation. To reproduce with any installed Python 3.12:

```sh
cd /Users/krishpatel/HackRu
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-voice.txt
.venv/bin/python -m pip check
.venv/bin/python -m companion.hands.model
```

The existing environment was provisioned with uv rather than pip. To reproduce that route with uv installed:

```sh
UV_PYTHON_INSTALL_DIR="$PWD/.runtime" uv python install 3.12
UV_PYTHON_INSTALL_DIR="$PWD/.runtime" uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-voice.txt pytest
uv pip check --python .venv/bin/python
```

The downloaded model and generated ZIP are ignored. No keys or camera recordings are stored.

## Camera blocker and launch

**No local camera index has been selected.** Personally ran the documented command:

```sh
cd /Users/krishpatel/HackRu
.venv/bin/python -m companion.hands --list-cameras
```

OpenCV reported `not authorized to capture video (status 0), requesting...` followed by `camera failed to properly initialize!` for every index 0–4. No usable camera was enumerated. This OS permission blocker remains despite running the probe outside the filesystem sandbox. Do not copy the teammate's index 2 blindly.

On the demo laptop, grant Camera access to the launching app in **System Settings > Privacy & Security > Camera**, relaunch that app if needed, and repeat the command from Terminal. Select the actual laptop-camera index using its nonblack/nonvirtual image and reported resolution. If ambiguous, inspect it with the standalone main-thread preview:

```sh
# Replace N with the index discovered above; do not type N literally.
.venv/bin/python -m companion.hands --camera N
# Quit that preview before starting the integrated runner.
.venv/bin/python -m companion.main --camera N
```

Actual integration config: `camera_index=N`, `preview=False`, `pinch_start=0.35`, `pinch_release=0.60`, `loss_cancel_s=0.5`; H's remaining defaults are preserved, including smoothing 0.5, stability 80 ms, 640×480 at requested 30 fps, emit cap 30 Hz. Optional `--model /absolute/path/hand_landmarker.task` overrides the model location. No OpenCV GUI calls run in the worker.

Camera-free typed demo:

```sh
cd /Users/krishpatel/HackRu
.venv/bin/python -m companion.main
```

After Blender connects, type one phrase per line:

```text
create cube
create sphere
create cylinder
create triangular prism
move
undo
cancel
status
quit
```

`spawn cube` and the other original strict shape aliases remain supported. V's parser and UUID emitter handle accepted phrases; there is no additional natural-language parser. `QUEUED` means callback acceptance, not execution acknowledgment; inspect Blender and `STATUS`. Optional `--mic --device N` uses V's microphone config; keys stay in the shell environment. Missing key/dependency or worker failure leaves typed input and the other worker running. No authenticated live speech test was performed.

## Blender update and connection

1. Save user work. Disconnect, disable, and remove the old add-on in Preferences. Quit and restart Blender to clear old cached modules.
2. Build with `.venv/bin/python tools/package_addon.py` and install `/Users/krishpatel/HackRu/dist/air_modeler.zip` through **Edit > Preferences > Add-ons > Install from Disk**. Enable Air Modeler, version **0.3.0**. Do not import the ZIP in a live console.
3. Use a disposable scene in a single ordinary 3D Viewport, **Object Mode**, with Global Undo enabled. Open **N > Air Modeler**.
4. Start the companion using one launch command above. Click **Connect** in the intended viewport and wait for **Connected** / `READY`.
5. Type `create cube`, then hold an open hand in view. A white cursor means no eligible hit; green means hover; orange means an active MOVE. Hover alone leaves selection and geometry unchanged.
6. Pinch over the cube, move slowly, and open fingers to commit. Escape or typed `cancel` restores the preview. Open the hand visibly after any interruption before trying again. Typed `undo` or the platform Undo shortcut reverses the last completed edit; during a drag it cancels that preview first.
7. Type `quit` to stop workers/server, or disconnect in Blender. Reconnect explicitly after file/editor/scene changes. Update the installed ZIP only through Preferences, not the user's live Python console.

The ZIP contains `__init__.py`, `primitives.py`, `operators.py`, `panel.py`, `bridge.py`, `viewport.py`, and a byte-for-byte generated `_protocol.py` from `shared/protocol.py`. Test scripts and device packages are excluded.

## Controller behavior and interfaces

`BridgeServer.emit(event) -> bool` remains the single thread-safe/nonblocking integration callback. H receives `run_hand_tracker(server.emit, stop_event, config)` and V receives `run_voice(server.emit, stop_event, {"device": ...})` in guarded workers. Shutdown sets the shared stop event, closes transport immediately to restore Blender previews, and joins workers. A native driver stuck beyond six seconds is diagnosed; process exit releases remaining native resources. A failed/stalled hand worker is covered by Blender's independent 0.5-second stale-input watchdog.

An immediate reconnect now reaps a closed old peer before enforcing the single-client rule, avoiding rejection when accept races the old EOF. Live second clients remain rejected.

One Blender modal controller owns the socket, timer, gesture state, and draw-handler token. `viewport.py` only supplies passive drawing and ray math. The controller still throttles TIMER events with monotonic time; it never accesses `event.timer`.

- Cursor mapping is `(u * width, (1-v) * height)` in the captured drawable WINDOW region. There is no second mirror, smoothing filter, or pinch detector.
- Only a fresh `gesture_start` can select/lock a hit object. Gesture UUIDs are remembered for the session (4096 cap). Frames cannot start an edit; mismatched/duplicate terminal events cannot commit another gesture. A missed start enters `NEEDS_RELEASE`.
- The original world matrix, hit/grab point, viewport matrices, region dimensions, and viewport-facing plane are frozen at start. Every preview is the original translation plus ray-plane displacement; rotation/scale and grab offset are preserved. Nearly parallel/invalid intersections and extreme deltas are skipped.
- `present=false` hides the cursor and freezes immediately without reading null coordinates, even when `pinching=true`. A brief dropout can resume the same active gesture. Sustained loss or stopped input cancels after 0.5 seconds. Only a fresh present `pinching=false` frame releases Blender's interruption gate; H additionally enforces its own physical-release hysteresis. `pinching` never authorizes starting an edit.
- Matching end coordinates supply the final position. The controller restores baseline then executes `air_modeler.commit_move` with an explicit Undo step. Preview, cancel, and unchanged release add no modeling Undo step.
- Cancel, Escape, disconnect, target invalidation, Object Mode exit, captured-context loss, disable, or load-pre restore the baseline if the locked object still exists. Undo cancels before invoking Blender Undo and reacquires references. Spawn/mode changes are rejected during dragging; sidebar spawn polling is disabled. Navigation/edit shortcuts are consumed during a drag and pass through while idle.

## Validation personally performed

- **63 tests / 78 subtests passed** under Python 3.12 with the final dependency versions, including H's 21 tests, V's 28, bridge/protocol tests, typed parsing/UUID integration, and failed-worker isolation.
- Dependency consistency passed; actual MediaPipe model opened and closed; hands/voice imports succeeded.
- Rebuilt ZIP installed/enabled in isolated Blender user resources; background primitive regressions passed.
- Original foreground bridge check passed: real TCP/timer spawning, malformed traffic recovery, command deduplication, reconnect, independent spawn Undo, invalid viewport, load handler, disable/re-enable, server shutdown, absent server.
- New **foreground TCP MOVE check** uses the actual `companion.main --synthetic` process and real modal events, not direct handler calls for gesture delivery. It verifies cursor mapping/hover without movement; start without a jump; no held-frame acquisition; no drift; final end coordinates; duplicate/mismatched IDs; two separate Undo steps; missed pinch; locked target across another object; brief loss; sustained loss, stale input, explicit gesture/typed cancellation and disconnect; release gating; typed spawn and mode rejection during drag; sidebar poll rejection; Undo during drag; rotated/nonuniformly scaled target in perspective and orthographic views.
- Additional lifecycle checks exercise unchanged/cancelled gestures without Undo entries, active-preview load-pre callback, viewport loss, Object Mode exit, disable/re-enable, and timer/socket/draw-handler cleanup.
- Tests use disposable scenes/processes and isolated add-on installs. `demo.blend`, user preferences, and the user's installed add-on are not overwritten.

Reproduce (each Blender command opens its own process):

```sh
cd /Users/krishpatel/HackRu
.venv/bin/python -m pytest -q
.venv/bin/python tools/package_addon.py
BLENDER_USER_RESOURCES="$(mktemp -d /tmp/air-smoke.XXXXXX)" \
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python-exit-code 1 --python addon/air_modeler/smoke_check.py
BLENDER_USER_RESOURCES="$(mktemp -d /tmp/air-bridge.XXXXXX)" \
  /Applications/Blender.app/Contents/MacOS/Blender --factory-startup \
  --python-exit-code 1 --python addon/air_modeler/bridge_check.py
BLENDER_USER_RESOURCES="$(mktemp -d /tmp/air-move.XXXXXX)" \
  /Applications/Blender.app/Contents/MacOS/Blender --factory-startup \
  --python-exit-code 1 --python addon/air_modeler/move_check.py
```

Do not run the foreground checks concurrently: all use fixed port 8765. `--synthetic` accepts complete raw type/payload JSON lines alongside typed commands for camera/key-free gesture testing. `move_check.py` is the reproducible full sequence.

## Evidence still pending / limits

H's controlled live session and **4,267 validator-compatible events** are teammate-reported evidence, not this integration's live validation. V's microphone-capture results are likewise teammate evidence; live authenticated speech is pending.

**Live camera → Blender picking/MOVE has not been verified here because camera access is denied.** After fixing permission, H can run this short rehearsal: open hand/hover without selection changes; pinch cube/move/open; repeat and Undo twice; pinch empty space then cross cube (no acquisition); drag across another object (target stays locked); briefly leave view (<0.5s) then return pinched (freeze/resume); leave >0.5s (restore, no restart until open); Escape; typed `cancel`; quit companion during drag; reconnect; disable/re-enable. Repeat a rotated/scaled target and perspective/orthographic views. Report camera index, lighting, cursor/drag feel, unexpected cancels and exact commands/status. This also checks physical Escape/Undo shortcuts, actual visual cursor rendering, and Preferences clicks; automated API checks do not prove those manual actions. Actual file-open remains pending; the load-pre handler was invoked directly.

Only visible editable unparented meshes without enabled modifiers, constraints, or animation are eligible (conservative beyond topology-changing modifiers). No rotation/scaling/extrusion tools, depth inference, multi-hand input, automatic reconnect, Windows typed console, Quad View, or large-scene performance guarantee. Local View is checked by visibility but not manually rehearsed. Navigation is blocked during drag; resize/other UI behavior is not a separate supported manipulation path. Live smoothing/threshold feel and venue lighting remain to be assessed. One client, fixed loopback port, and existing transport size/dedup limits still apply.

P-owned changes: `companion/main.py`, `companion/transport/server.py`, `requirements*.txt`, `.gitignore`; add-on `bridge.py`, `viewport.py`, `operators.py`, `panel.py`, `__init__.py`, `move_check.py`, package smoke expectations; `tests/test_runner.py`, `tests/test_transport.py`; `tools/package_addon.py`; P-owned protocol/handoff docs. Root README and teammate source/handoff files remain unchanged by integration.

**Next bounded task:** rotation and uniform scaling through the same start/preview/end/cancel/Undo lifecycle, retaining the cursor/picking and loss-recovery behavior. Extrusion and live speech completion follow separately.
