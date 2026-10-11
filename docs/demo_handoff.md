> Current **0.11.0** stable face choice and signed dragging: [handoff](clutch_handoff.md) and [physical checklist](physical_acceptance.md). Installed add-on was 0.10.0 on disk; user reports EXTRUDE arms but face choice/dragging is unpredictable. Installation and all 0.11 physical checks remain pending. Material below records historical versions.

> Historical **0.9.0** stabilization: [handoff](clutch_handoff_0.9.md) and [physical checklist](physical_acceptance_0.9.md). Material below records earlier versions; 0.9 physical checks are NOT RUN.

> Historical 0.8.0 Left-clutch/Right-whole-hand controls: [handoff](clutch_handoff_0.8.md). Material below is historical.

> Historical 0.7.0 controls and verification: [0.7 clutch handoff](clutch_handoff_0.7.md). The material below is historical and does not establish a combined 0.7.0 live pass.

> Current 0.6.0 integration: [two-hand selection and precision handoff](enhancement_handoff.md). The dated results below are historical evidence, not a combined 0.6.0 live pass.

# Demo readiness handoff — P

Add-on **0.5.0** is unchanged from geometry baseline `8eda4fe0d3ba0ed93c08185a6a84835f9dfacea6`. The companion revision is the commit containing this handoff (`git log -1 --format=%H -- companion/main.py`). This milestone adds integrated PTT, console checks and reproducible instructions; it does not claim a complete live demo pass.

## Available evidence, inspected 2026-10-10

`git fetch origin` succeeded. Both teammate tips are already ancestors of feature/blender; there were no new commits/docs to merge. No teammate implementation was changed.

| Evidence | Exact source / tested version | Result and limits |
| --- | --- | --- |
| H handoff | `4af4741f68d5dba6eb8e78b24ca94e1de156893f`, `docs/hands_handoff.md`; standalone tracker, validator checked against `b2de11b` (add-on 0.2.0 milestone) | Controlled holds/releases/loss recovery and clean shutdown reported; 4,267 live events validated. No live Blender gesture consumer tested. Not a 0.5.0 combined report. |
| V handoff | `104924d9c38be26dc8459346be08645a62a17b3e`, `docs/voice_handoff.md`; documentation-only follow-up to voice production tip `e2164c14e63f639609613b9b6901e5c8c8e5466d` | Standalone live 11-command sequence, intentional repeats, replay dedup, venue-noise PTT, typed fallback and clean shutdown reported. No Blender version/commit tested in this report; not integrated 0.5.0 evidence. Already merged via `e40e1dc5a771e5084354e49bf108f53d644e762b`. |
| P Python | This companion revision, Python 3.12.15 | 67 tests + 78 subtests passed. Protocol/transport, hands/voice unit checks, real runner/VoiceConfig/parser routing with substituted devices/socket boundary. No live audio or hands in these tests. |
| P Blender | `8eda4fe0d3ba0ed93c08185a6a84835f9dfacea6`, add-on 0.5.0, Blender 5.2.2 LTS | Previously passed packaged smoke, bridge, MOVE, world rotations/scale, geometry and TCP EXTRUDE regressions, including Undo/cancel/loss/reconnect. Synthetic events/disposable scenes. No Blender changes this milestone, so native tests were not rerun. |
| P local devices now | macOS arm64, current companion environment | Camera discovery now opens indices 0 and 1, 1920×1080, mean brightness 101/114. Earlier authorization failure no longer reproduced. Input enumeration: AirPods 0, MacBook Air microphone 2, iPhone microphone 4. These are observations, not portable defaults or selection/recording tests. |
| Complete live 0.5.0 demo | No received report identifies this exact add-on baseline as a completed combined test | Pending hands + live voice + Blender, face-outline readability, sensitivity, interference, physical recovery and shutdown. No confirmed P-owned modeling failure reported. |

Realtime access is confirmed by V. Sponsor attribution is **unconfirmed**: workspace/sponsor admin must verify workspace and grant. Local live credential/account access and physical microphone capture remain unverified here. Do not share keys in reports.

## Setup and controls

Follow [README setup and all three launch configurations](../README.md#reproducible-companion-setup). Select local devices, download/check the model, enter the ElevenLabs key privately in the companion terminal, build/install the ZIP, restart Blender and enable Global Undo. Use a separate rehearsal scene; preserve the user's working scene and `demo.blend`.

Start one companion with hands and `--mic --device "$MIC_INDEX" --push-to-talk`. Wait for the Scribe-ready message, connect from the 3D viewport N sidebar, and wait for `READY`. `status` prints session, Blender mode/phase/error and the PTT gate. `help` lists phrases; `quit`/Ctrl+C shuts down. Keep the companion console accessible to a second teammate for PTT/typed controls while the demonstrator keeps their hand in view. Avoid switching/closing the captured Blender viewport during an operation.

PTT begins `PTT MUTED`. `/talk` sets the one shared event and prints `PTT ARMED`; `/end` clears it and prints `PTT MUTED`. Repetition is harmless. Controls never become wire messages. Without PTT, `/talk` and `/end` explain the required flags; ordinary typed commands still use V's parser and the same Blender operators.

The existing voice service keeps its microphone open, samples 100 ms blocks and substitutes silence while muted. After a captured active→inactive transition, it sends a manual commit. Buffered active audio and its intended committed result may finish after `/end`. Only timestamped committed events execute, with deduplication by text/audio span; partial/plain feedback does not execute. This milestone tests late committed routing and duplicate suppression using the real TranscriptHandler, not a live provider. Existing voice tests exercise PCM gating and one release commit with fake audio/API. The standalone live report supplies separate real-provider evidence.

Wait for `Committed with timestamps:` and the visible Blender result before another turn or disconnect. `/end` does not retract speech already submitted; do not use it as Cancel. Do not immediately quit after speaking, because shutdown stops rather than drains recognition. Do not rapidly toggle below one capture block or issue empty turns; provider commit throttling is possible. A delayed provider transcript is not tied to the Blender session in the current voice interface, so do not reconnect with speech still pending: stop/restart the companion first if recognition is stalled. Transport discards already queued/offline input, but cannot cancel speech still at the provider. This is a documented boundary, not a new replay guarantee.

## Roughly two-minute rehearsal

Prepare the separate scene and installed add-on before timing. Keep a cube-sized target visible near the center and leave space for movement. Use one complete phrase per turn, with no narrated command phrases while armed. Keep spoken feedback/other speakers away from the microphone; feedback is text, not speech playback. A helper should enter controls silently.

| Time | Action / PTT voice turn | Typed fallback | Expected visible result |
| --- | --- | --- | --- |
| 0–20 s | Start companion; Connect Blender; wait READY and Scribe ready; show an open hand | `status` | MOVE / IDLE, live cursor. PTT MUTED until explicitly armed. |
| 20–35 s | `/talk`, say “create cube”, `/end`; wait committed result | `create cube` | One cube at the spawn location, selected; no duplicate cube from transcript partners. |
| 35–50 s | Point at cube with open hand; pinch, move slowly sideways, release | `move` arms default mode; mouse manipulation is the fallback if camera fails | Cube follows viewport plane without jumping; release commits once and returns MOVE. |
| 50–70 s | `/talk`, say “rotate z”, `/end`; wait; point/pinch and move horizontally, release | `rotate z` | Cube rotates around **world Z**, keeping its origin. About 1/8 viewport width is 45°. Release returns MOVE. |
| 70–85 s | `/talk`, say “scale”, `/end`; wait; pinch target, raise hand a little, release | `scale` | Uniform enlargement about origin; upward 0.1 normalized height ≈1.26×. Release returns MOVE. |
| 85–110 s | `/talk`, say “extrude”, `/end`; wait; open hand and target a clear supported face; confirm outline, pinch and raise slowly, release | `extrude` | One yellow target face outline; its cap extends outward along its normal (0.1 height = 0.4 world units). Side walls remain closed; release returns MOVE. |
| 110–120 s | `/talk`, say “undo”, `/end`; wait for result | `undo` | Only completed extrusion disappears; previous move/rotation/scale remain. |

Typed phrases select modes/create/undo through exactly the voice parser/geometry paths. They do not synthesize a hand movement; if the camera fails, finish with typed spawn/Undo and normal Blender mouse modeling, explicitly describing the live-hand limitation.

EXTRUDE: use a cube quad or triangular-prism cap/side, with an outward supporting face. Target the visible face itself, not an edge/empty area. Confirm the outline and sidebar face index before pinch; a rejection must leave geometry unchanged. Closed local single-user geometry, no enabled modifiers/constraints/parent/animation/shape keys/custom normals, positive nonsingular transform, planar convex tri/quad face required. Downward movement clamps to zero (no inward extrusion). Zero-distance release adds no undo step. New eligible caps can be extruded again; do not demonstrate arbitrary recessed/concave geometry.

## Recovery rehearsal before presenting

- **Cancel:** during a preview, enter typed `cancel` or press Escape in Blender. Original transform/topology returns. Mode returns MOVE and phase NEEDS_RELEASE. Show a visibly open hand, then pinch again. For voice Cancel, allow for recognition delay.
- **Tracking loss:** briefly leave camera view while pinching: preview freezes. Sustained loss around 0.5 s restores baseline. Return with an open hand before a fresh pinch. A missed-target pinch also requires release; do not drag into a target while held.
- **Undo during drag:** cancels the uncommitted preview, then undoes the previous completed action. Use the final table step only after release if demonstrating a single extrusion Undo.
- **Disconnect/reconnect:** finish any speech commit first; disconnect mid-preview to check restoration. Input issued while offline is discarded. Reconnect explicitly, wait READY, show an open hand, deliberately issue a new command. No transport queue replay. If a speech response is stalled, restart the companion before reconnecting as described above.
- **Shutdown:** `/end`, wait committed/visible result, then `quit` or Ctrl+C. Check `Server stopped`, restored preview if interrupted, no surviving worker/camera capture. A native-driver join warning is a failure to report, not a clean shutdown pass.

## Validation and presentation gate

Commands run for this milestone:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m companion.main --help
.venv/bin/python -m companion.hands --help
.venv/bin/python -m companion.voice --help
.venv/bin/python -m companion.hands --list-cameras
.venv/bin/python -m companion.voice --list-devices
.venv/bin/python tools/package_addon.py
```

PTT runner checks cover initial mute, same VoiceConfig event, repeated controls, no control wire messages, ordinary typed routing, hands-free behavior, unavailable controls, missing credentials, and clearing/joining workers at shutdown. Existing failed-device subprocess covers hands/voice failure isolation. New tests use fake device boundaries and are not physical capture verification. ZIP verification requires exactly the eight runtime modules plus byte-identical shared `_protocol.py`, version 0.5.0, and no tests/dependencies/secrets.

Before presenting:

- [ ] Record `git rev-parse HEAD`, installed add-on 0.5.0 and Blender version on each test laptop.
- [ ] Select/check camera and microphone in the actual room; verify model checksum and local API access.
- [ ] Complete the two-minute combined PTT sequence; verify each result and typed fallback, repeated command, muted speech, and no voice/hands interference.
- [ ] Verify face outline readability, gesture sensitivity, Cancel, loss/open-hand rearming, Undo, reconnect and clean shutdown physically.
- [ ] Have H/V report the exact tested commit/version, command and reproduction for any failure; P owns runner/Blender fixes, H tracking, V audio/transcripts. No new defect requiring teammate code changes was confirmed this run.
- [ ] Confirm sponsor attribution with the admin before making a sponsor claim. Keep the integration PR draft until missing live checks are resolved.
