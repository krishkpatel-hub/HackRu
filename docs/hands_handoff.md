# Hands handoff (H, `feature/hands`)

Standalone one-hand tracker. Implements `run_hand_tracker(emit, stop_event, config) -> None` from the README
(`companion/hands/tracker.py`). No sockets, no Blender code.

## Setup (macOS / Linux / Windows; Python 3.9–3.12 per MediaPipe wheels)

```bash
python3 -m venv .venv-hands && source .venv-hands/bin/activate     # outside git or ignored; I did not touch .gitignore
pip install mediapipe opencv-python numpy          # pytest too, to run the tests
python -m companion.hands.model                    # downloads companion/hands/models/hand_landmarker.task (7.8 MB, git-ignored)
```

Model: `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task`
(sha256 `fbc2a300…cde1` for the file I tested). Override the location with config `model_path` or `$HAND_LANDMARKER_MODEL`.
The downloader uses `certifi` if present and falls back to `curl` (python.org builds on macOS ship without CA certs).

`pip install mediapipe` also pulls in `opencv-contrib-python`; installing `opencv-python` beside it works (both
imported fine) but if you want one OpenCV only, `opencv-contrib-python` alone is enough.

## Launch

Run from the repo root (`companion/` has no `__init__.py`; it works as a namespace package).

```bash
python -m companion.hands                     # preview window + JSON events on stdout
python -m companion.hands --list-cameras      # find the laptop webcam index (0 may be a phone/OBS!)
python -m companion.hands --no-preview        # headless
python -m companion.hands --no-frames         # print only gesture_* events
python -m companion.hands --camera 1 --smoothing 0.7 --pinch-start 0.30 --pinch-release 0.55 --stable-ms 100
```
`q`/Esc/closing the window/Ctrl-C all stop it cleanly (exit 0). Setup errors (camera, model, bad config) print
`error: …` and exit 1. Tests (no webcam needed): `python -m pytest -q tests/test_hands_*.py`.
Replay a fixture: `python -m companion.hands.replay tests/test_hands_fixtures/long_loss_recovery.json`.

## Integration (P)

```python
from companion.hands.tracker import run_hand_tracker
threading.Thread(target=run_hand_tracker, args=(emit, stop_event, {"preview": False}), daemon=True).start()
```
- `emit(event)` is called synchronously from the tracker thread with `{"type","payload"}` only. Keep it non-blocking.
- **Preview/GUI:** `preview` defaults to **False** in the function (the CLI turns it on). On macOS `cv2.imshow` must run on the
  main thread: if `preview=True` is requested off the main thread, preview is disabled with a stderr warning. To show a preview
  while integrating on macOS, run `run_hand_tracker` on the main thread and the rest in other threads.
- **Camera permission (macOS):** the process (your terminal/IDE) needs Camera access. Without it startup raises
  `RuntimeError("cannot open camera 0 …")` *before* any event is emitted. On the dev laptop index 0 was the iPhone (Continuity Camera, 1080p, black), 1 was OBS and the FaceTime camera was **2**.
  Indices differ per machine and change when a phone connects: run `--list-cameras` and set `camera_index`.
- `run_hand_tracker` raises `RuntimeError`/`FileNotFoundError`/`ValueError` for setup problems, and `RuntimeError` if the camera
  stops delivering frames for `camera_fail_timeout_s` (3 s). On every exit path it releases the camera, closes the landmarker,
  and, if a gesture is active, emits one `gesture_cancel` with `reason: "shutdown"` first.
- Unknown config keys raise `ValueError` (typo protection). `config=None` uses defaults.

## Event behavior

| Situation | Events |
| --- | --- |
| steady state | `hand_frame` ≈30 Hz (`emit_hz`, capped even from a 60 fps camera); state changes are emitted immediately |
| hand visible | `u`,`v` smoothed index-tip cursor, finite, clamped to [0,1]; `u` ↑ left→right, `v` ↑ top→bottom, in the **mirrored** image |
| pinch (ratio ≤ start for ≥ stable window) | `gesture_start` {uuid, u, v}, then `hand_frame` with `pinching:true` |
| release (ratio ≥ release for ≥ stable window) | `gesture_end` same id, then `pinching:false` |
| tracking lost | `hand_frame` `present:false`, `u`/`v` `null` on the very first lost frame |
| lost ≥ `loss_cancel_s` (0.5 s) | one `gesture_cancel` `reason:"tracking_lost"` (if a gesture was active); a visibly open hand is then required |
| lost < 0.5 s while pinching | same gesture continues if still pinched on return (end/cancel logic unchanged) |

Choices to know about (all within the README contract, but not spelled out in it):
- **`pinching` means "gesture active", not "fingers touching right now".** During a <0.5 s dropout mid-pinch the frames read
  `present:false, pinching:true, u/v:null` (= frozen). Blender should key off `gesture_*` events, not `pinching`.
- `gesture_start` coordinates are the cursor position when the pinch *began* (start of the stability window), and `gesture_end`
  coordinates are the position when the release *began*. This avoids the cursor drifting as the fingers close/open.
- The first pinch after startup, after loss ≥ 0.5 s, and after a cancel all require a visibly open hand (ratio ≥ release for the stability window).
- Smoothing is reset when the hand is re-acquired (no sliding in from the old position).

## Calibration (config keys / CLI flags)

| Key | Default | Meaning |
| --- | --- | --- |
| `smoothing` | 0.5 | 0 = off … 0.9 = heavy; weight kept from previous cursor per 1/30 s (frame-rate independent). More = steadier but laggier |
| `pinch_start` | 0.35 | thumb-tip↔index-tip distance / palm size at or below which a pinch starts |
| `pinch_release` | 0.60 | ratio at or above which it releases; must be > `pinch_start` (the gap is the hysteresis dead band) |
| `pinch_stable_ms` | 80 | how long a condition must hold (≈3 frames at 30 fps) |
| `loss_cancel_s` | 0.5 | sustained loss before cancel |
| `emit_hz`, `camera_index`, `width`/`height`/`camera_fps` (640×480@30), `min_*_confidence` (0.5) | | |

Palm size = max(wrist→middle-MCP, index-MCP→pinky-MCP) in image-height units, so the ratio is independent of hand distance.
**The thresholds are starting values, not tuned on a live hand** (see below): the preview prints `ratio=` live, so hold a
pinch and an open hand, read the numbers, and set `pinch_start` a bit above your pinch ratio and `pinch_release` well below your open ratio.

## Tested (2026-10-10)

Environment: macOS 26.5.2 arm64 (M1), Python 3.12.8, mediapipe 1.1.0, opencv-python 5.0.0.93, numpy 2.5.3, pytest 9.1.1.

Actually performed:
- `pytest tests/test_hands_*.py`: 21 passed. Covers normal pinch, held pinch, release, short loss (continues), long loss (one cancel,
  no restart while still pinched, restart only after open hand), immediate `present:false`/null coordinates, ~0.5 s cancel timing,
  hysteresis dead band, 2-frame flicker rejection, cursor direction (right→u↑, down→v↑) and clamping, smoothing, ≈30 Hz cap from
  60 fps input, palm-size normalization (half-scale hand gives same ratio), shutdown cancel, config validation, the four JSON replay
  fixtures, and the tracker loop with a fake camera/landmarker (stop_event releases camera + landmarker, camera failure raises and cleans up,
  missing model fails before opening the camera, preview dropped off the main thread on macOS).
- Real MediaPipe model on a real hand photo: detects a hand; the same image mirrored gives u(raw)+u(mirrored) = 0.99 (≈1), i.e.
  the mirror convention holds with the real model.
- Preview overlay rendered to an image with real landmarks and checked visually (skeleton, cursor ring, status, u/v, ratio, fps).
- Model download via `python -m companion.hands.model`, including the curl fallback, sha256 matches.
- CLI `--help`, and camera-denied path (clean error, exit 1).

- Live laptop camera (index 2, headless, run in a thread): ~29 Hz `hand_frame`, hand detected in some frames, `stop_event` ends the thread and releases the camera. (Index 0 was a phone feed at 1080p: ~24 Hz and black.) Camera access had to be granted to the host terminal first.

- Live hand session, laptop camera index 2, preview window, CLI (`--camera 2`), ~2.3 min, 4,087 `hand_frame`s: the tester ran open hand, pinch/hold, move+release, and out-of-view/return, and reported all behaved correctly with the lowest pinch ratio seen = **0.12** (default `pinch_start` 0.35 leaves ample margin). Log: 11 gestures = 4 clean start/end pairs and 7 `tracking_lost` cancels (each exactly once; none restarted while still pinched). Cursor u/v stayed in 0.05–0.97 / 0.13–0.94. Whether individual cancels were deliberate hand-outs or MediaPipe dropouts was not recorded.
- Three loss gaps of 0.34 s, 0.48 s and 0.59 s occurred mid-pinch: the first two were absorbed (same gesture), the third cancelled. These sit near `loss_cancel_s` (0.5), so if real pinches get cancelled by brief dropouts, raise `loss_cancel_s` (e.g. 0.8) at the cost of slower cancel.

**Not verified:**
- The *open-hand* ratio value on a live hand (not logged), and whether the cancels were all intentional.
- Windows/Linux (code has no platform-specific paths besides the macOS main-thread rule).
- Tuning of the thresholds/smoothing on real hand motion; dropout behavior of MediaPipe when fingers overlap in a pinch.

## Known limitations

- One hand only (`num_hands=1`); it picks whichever hand MediaPipe reports first.
- 2D only: a hand pointing straight at the camera shrinks palm size and makes the ratio less reliable.
- Cursor is the index fingertip, which moves slightly while pinching; mitigated by the start/end position rule above, not eliminated.
- Camera frame timing drives everything: if the camera stalls the loop emits nothing until frames resume or the 3 s fail timeout raises.
- MediaPipe VIDEO mode runs inference synchronously on the tracker thread (CPU delegate, XNNPACK); frame rate depends on the machine.
- Model "latest" URL can change upstream; sha256 above is the tested file.
