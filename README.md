# Handmade

**Build in Blender with your hands and voice.**

Handmade is a HackRU project that turns webcam hand tracking and spoken commands into Blender modeling actions. Create a shape, hold it with one hand, and use the other to move, rotate, resize, or extrude it.

We wanted a way to start making shapes using the movements you already use to describe them. Blender handles the geometry and viewport; Handmade supplies the controls.

> **Hackathon prototype:** the implementation currently lives on [`feature/blender`](https://github.com/krishkpatel-hub/HackRu/tree/feature/blender). The inspected add-on is **0.12.0** and still appears as **Air Modeler** in Blender. Gesture reliability is being refined; the latest combined physical acceptance checks remain unperformed.

[![Watch the video]([https://youtube.com](https://www.youtube.com/watch?v=iJkz58EZ7BM))]([https://youtu.be](https://www.youtube.com/watch?v=iJkz58EZ7BM))
## What it can do

- Create cubes, UV spheres, cylinders, and triangular prisms through sidebar buttons, typed commands, or voice.
- Move, rotate, and uniformly scale objects with two-hand controls.
- Extrude one eligible face at a time, with face highlighting and a live preview.
- Undo completed edits individually or cancel an unfinished preview.
- Use typed input when microphone recognition is unavailable.
- Use push-to-talk for voice commands in noisy environments.
- Enter supported numeric commands for precise transforms.

The current extrusion implementation uses drag-direction alignment and a right-cursor tie-breaker. The **right-cursor-only, two-second hover selection** and **point-and-dwell creation buttons** are in progress, not completed features of 0.12.0.

## Controls

In two-hand mode, **left pinch selects and holds the object**. Moving the left hand does not transform it. The right hand supplies the modeling action.

| Action | Right-hand control while left pinch is held |
| --- | --- |
| Move | Translate an open palm |
| Scale | Close the whole hand to shrink; reopen it to enlarge |
| Rotate | Turn the palm; free rotation and explicit world-axis overrides are available |
| Extrude, current 0.12.0 | Isolated thumb/index pinch, then deliberate drag to identify and manipulate a face |

Tools lock once an operation begins. For MOVE, SCALE, and ROTATE, left release commits the edit. In 0.12.0, either valid release order can complete an extrusion. Tracking loss freezes a preview; sustained loss cancels it. Release visibly before starting again after cancellation.

**Upcoming extrusion workflow:** hold the object with left pinch, hold right pinch, and hover the right cursor over one visible face for two continuous seconds. A progress indicator runs while geometry stays unchanged. The selected face turns orange; only subsequent right-hand movement extrudes it. Right release commits while left remains held, then left release resets. This replaces direction-based face selection when implemented.

## Tech stack

| Component | Technology |
| --- | --- |
| Modeling and viewport | Blender, `bpy`, `bmesh`, `mathutils` |
| Webcam capture | OpenCV |
| Hand tracking | MediaPipe Tasks Hand Landmarker |
| Speech recognition | ElevenLabs Scribe v2 Realtime |
| Microphone input | `sounddevice` |
| Companion application | Python |
| Local connection | TCP with newline-delimited JSON |

Camera and audio dependencies run in the external companion, outside Blender. Typed commands use the same deterministic command parser as voice.

## Requirements

- **Blender 5.2 or later**, as declared by the add-on; **5.2.2** is the tested version.
- **Python 3.12** for the companion; the development environment used 3.12.15.
- A webcam for gestures and an optional microphone for voice.
- An ElevenLabs API key with realtime speech-to-text access for live voice. Typed input does not need a key.

The reported development setup is macOS on Apple Silicon. The runner has macOS/Linux console paths, but Linux has not been physically validated. Windows console input is not implemented. Compatibility with other Blender versions remains unverified.

## Quick start

### 1. Get the implementation and prepare Python

```bash
git clone --branch feature/blender https://github.com/krishkpatel-hub/HackRu.git
cd HackRu
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m companion.hands.model
```

For optional live voice:

```bash
.venv/bin/python -m pip install -r requirements-voice.txt
```

Reuse an existing working environment rather than recreating it. Install dependencies into the companion environment, not Blender. The project uses `opencv-contrib-python`; do not install a second OpenCV distribution alongside it.

### 2. Build and install the Blender add-on

```bash
.venv/bin/python tools/package_addon.py
```

This creates `dist/air_modeler.zip`.

1. In Blender, open **Edit → Preferences → Add-ons → Install from Disk** and choose the ZIP.
2. Enable **Air Modeler**.
3. Use **Object Mode**, **Solid** viewport shading, and **X-Ray off**. Enable Global Undo.
4. In the 3D Viewport, press **N** and open the **Air Modeler** tab.

When updating an older installation, disconnect, disable/remove it, and fully restart Blender before installing the rebuilt ZIP. Use matching companion and add-on revisions.

### 3. Find your devices

```bash
.venv/bin/python -m companion.hands --list-cameras
```

If using voice:

```bash
.venv/bin/python -m companion.voice --list-devices
```

Grant Camera and Microphone access to the Terminal or IDE launching the companion. Restart that application if needed. Device indices vary across machines and attached devices.

### 4. Start hands and typed commands

Set the camera index to the working index from discovery; `0` below is an example.

```bash
CAMERA_INDEX=0
.venv/bin/python -m companion.main --camera "$CAMERA_INDEX" --model companion/hands/models/hand_landmarker.task --two-hands
```

In Blender, click **Air Modeler → Connect**. Wait for **Connected / READY** before issuing commands.

Try typing in the companion terminal:

```text
create cube
create sphere
create cylinder
create triangular prism
rotate x
scale
extrude
move
cancel
undo
status
help
```

Bare tool commands choose a gesture tool; they do not transform geometry by themselves. Supported numeric examples include `rotate x 45 degrees`, `scale by 1.5`, `move x 2 units`, and `extrude 0.5 units`. Inspect Blender's status and use `help` for available controls.

### 5. Optional voice with push-to-talk

In the companion terminal, load your key privately. The following hidden-input commands work in macOS zsh and Bash:

```bash
set +x
printf 'ElevenLabs API key: '
read -rs ELEVENLABS_API_KEY
export ELEVENLABS_API_KEY
printf '\n'
```

Keep the key out of source code, screenshots, chat, and diagnostic output. Launch Blender separately from this key-bearing terminal.

Stop any existing companion before starting the voice-enabled version. Set the microphone index from device discovery; `0` is an example.

```bash
MIC_INDEX=0
.venv/bin/python -m companion.main --camera "$CAMERA_INDEX" --model companion/hands/models/hand_landmarker.task --two-hands --mic --device "$MIC_INDEX" --push-to-talk
```

Connect Blender again. Wait for **READY**, **Scribe session ready**, and **PTT MUTED**.

1. Enter `/talk` to arm voice input.
2. Speak one supported command, such as “create cube.”
3. Enter `/end` to mute and request completion of that utterance.
4. Wait for the committed transcript and Blender's result before the next command.

Typed commands remain available. `/end` does not cancel an already spoken command. PTT gates recognition audio; the microphone remains open until shutdown. Speech already captured can finish processing after muting.

For hands-free voice, omit `--push-to-talk`.

### 6. Shut down

Enter `quit` or press **Ctrl-C** in the companion terminal. Unfinished previews should restore and device workers should close. After using voice:

```bash
unset ELEVENLABS_API_KEY
```

For a camera-free starting point, run `.venv/bin/python -m companion.main`, connect Blender, and use typed commands or sidebar controls. An explicit single-hand fallback is available with `--legacy-hands` instead of `--two-hands`.

## How it works

The companion captures webcam frames, tracks hand landmarks, recognizes supported speech commands, and sends structured events to Blender over `127.0.0.1:8765`.

The Blender add-on owns selection, gesture interpretation, previews, and mesh edits. All Blender scene changes happen on its main thread. Each preview is calculated from an original baseline so cancellation can restore it and a completed edit can create one Undo step.

| Path | Purpose |
| --- | --- |
| `addon/air_modeler/` | Blender add-on, controls, overlays, transforms, and extrusion |
| `companion/hands/` | Hand tracking and observations |
| `companion/voice/` | Speech recognition and command parsing |
| `companion/transport/` | Local bridge server |
| `companion/main.py` | Runner, device workers, typed input, and PTT |
| `shared/` | Protocol validation and shared spatial helpers |
| `tools/package_addon.py` | Add-on ZIP builder |
| `tests/` | Python regression checks |
| `docs/` | Setup details, engineering handoffs, and acceptance records |

## Current limits

- Automatic gesture recognition is still being tuned. Users have reported SCALE/ROTATE confusion and unintended extrusion face choices; 0.12.0 includes fixes that still need combined live acceptance.
- Extrusion supports a restricted set of eligible faces and meshes, starting with convex cube/prism geometry. Inward editing performs bounded shortening, not arbitrary cavity creation or through-cuts.
- The integrated tracker runs without a separate camera preview window.
- The bridge supports one Blender client and requires explicit reconnect.
- Queued commands are not proof of scene execution; check the viewport or `status`.
- This prototype does not reconstruct arbitrary air-drawn meshes or provide a physics engine.

## Verification and further development

The [0.12.0 engineering handoff](docs/clutch_handoff.md) reports **310 Python tests plus 78 subtests** and **12 Blender regression scripts** passing. These automated results do not establish a successful combined live-hand/voice session on this version.

Use the [physical acceptance checklist](docs/physical_acceptance.md) for live verification and the [protocol documentation](docs/protocol.md) for integration details.

Next priorities are exact right-pointer face selection with the two-second dwell, point-and-dwell creation controls, more reliable gesture separation, and user calibration.

Built by a four-person team at HackRU.
