# Air Modeler 0.7.0 physical acceptance

**Run has not started.** Target branch: `feature/blender`. Record exact
`git rev-parse HEAD` before starting; installed add-on must report **0.7.0**, Blender
**5.2.2 LTS**, camera **0**, microphone **0 (MacBook Air Microphone)**.

| Run identity | Recorded observation |
| --- | --- |
| Tested checkout SHA | NOT RUN — record exact SHA before first physical action |
| Installed add-on version | NOT RUN for 0.7.0 |
| Blender version | User previously reported 5.2.2; reconfirm for this run |
| Camera / microphone | User confirmed 0 / 0; actual connected status pending new run |
| Previous startup evidence | User observed installed 0.6.0, two_hands=True, Scribe ready; startup only |

The baseline is `7631716b4c6f2800983207d8f90595bdb32efc0d` (0.6.0), preserved
independently with its ZIP. Automated synthetic tests, the genuine historical
cursor recording, and standalone voice reports do not fill any row below.
Use PASS / FAIL / NOT RUN, and record observations, exact commit/version and any
recovery. A partial row remains NOT RUN with partial evidence, or FAIL if a stated
requirement fails. Never mark an entire row from process startup alone.

The guide will deliver **one small action at a time**, waiting for the user's
observation. This table is the test record and reference, not simultaneous
instructions. Save work first and use a disposable rehearsal scene. Do not
overwrite `demo.blend` or `demo.blend1`.

| # | Status | Exact action (perform sequentially with guide) | Expected visible result | Failure signs and recovery |
| --- | --- | --- | --- | --- |
| 1 | NOT RUN | Save work; disconnect/disable/remove old add-on, quit; install rebuilt ZIP, enable, verify 0.7.0 and restart. Launch current hands+PTT command, Connect in N sidebar, enable Global Undo. Raise Left alone, then Right alone, then both open. | Installed 0.7.0 / Blender 5.2.2, bridge Connected/READY, Scribe ready, PTT MUTED. Sidebar labels actual anatomical hands correctly; cursor tracks. | Old version/missing labels/worker error is not success. Restart with matching ZIP; recheck device/permission, model or private key. Incorrect anatomical labels stop the gesture test and require diagnosis. |
| 2 | NOT RUN | Type `create cube`. Keep Right out of view. Aim Left at cube, pinch, move slowly past threshold, continue, hold, release; type `undo`. | SELECTED_READY first, then MOVE; no threshold jump, palm-relative motion, frozen release. One Undo restores cube transform, cube remains. | Miss/drift/steal/jump or Undo removes wrong edit: cancel, open Left, record UI/status and repeat only after diagnosis. |
| 3 | NOT RUN | Repeat aim/pinch/MOVE/release/Undo with Right alone and Left absent. | Same result and one Undo; no missing-Left cancellation. | A demand for Left or no MOVE is a failure; cancel/open Right, capture status. |
| 4 | NOT RUN | Create a separate sentinel cube. Left-select it and hold still ≥1 s with Right absent; release without motion, then Undo once. | No deformation or modeling Undo entry from selection. One Undo removes the sentinel cube creation, proving stationary selection added no step. | Any stationary transform or extra Undo: cancel/open, retain observations for diagnosis. |
| 5 | NOT RUN | Left selects and holds. Present Right thumb/index/middle extended, ring/pinky folded; hold neutral, twist >8° for >150 ms, then twist farther, hold, release Left. Undo. Repeat with `rotate x` and `rotate y` overrides. | ROTATE locks with zero recognition jump; further 2D twist rotates only world axis, origin/scale unchanged; each release one Undo. | SCALE, translation, wrong axis, pose flicker or release jump: cancel/open both, inspect threshold/identity feedback; tune only after recording failure. |
| 6 | NOT RUN | Same left clutch/right three-finger grip. Keep palm orientation steady, spread >12% for >150 ms; spread farther then narrow, release Left; Undo. | SCALE locks with no initial jump; positive uniform factor, no twist, origin and proportions preserved. Right thumb/index opening does not commit. | Rotation, early release, nonuniform/negative factor or pose-loss: cancel/open, record grip status and adjust pose/calibration deliberately. |
| 7 | NOT RUN | With left clutch, simultaneously twist/spread near equal normalized thresholds; then make one clearly dominant. During active operation deliberately try the other motion and a typed mode command. | Ambiguous stays READY with prompt; one dominant tool locks. Tool never switches; conflicting command rejects immediately without later execution. | Jump/tool switch/queued command: cancel, open both; record exact sequence and message. |
| 8 | NOT RUN | During each active ROTATE, SCALE and EXTRUDE preview, hold Right still and move Left sideways/up/down while maintaining pinch; then cancel. | Target/cap stays fixed while Left moves; Left acts only as clutch. Cancel restores exact baseline. | Left translates/deforms target or cancellation leaves data: stop, cancel, record operation and status. |
| 9 | NOT RUN | On a cube, aim Left at an eligible visible face, pinch and inspect locked outline; Right open palm initiates outward extrusion, release Left. Repeat on new cap, then Undo twice. Repeat on triangular-prism cap and side. | Outline stays on captured face even if cursor crosses another face; connected cap/sides, unchanged object transform, each edit separately reversible. | Wrong face, cracks/internal caps, changing topology count per frame, unsupported face with no explanation: cancel; use clear supported face, record shape/face. |
| 10 | NOT RUN | Use `extrude plane xy axis x` on suitable +X and −X outward faces; `extrude plane xy axis y` on ±Y; `extrude plane xz axis z` on ±Z; additionally exercise free XZ and YZ mappings. Follow displayed screen-right/up signs, reverse movement, Undo each. | XY/XZ/YZ lock visibly; all ±world axes reachable with outward faces; signed feedback matches cap. Opposite movement reverses vector; inward/tangent input rejects safely. | Wrong sign/plane, depth claims, inward corruption or jump: cancel/open, inspect face normal/constraint; choose outward-compatible face and record failure. |
| 11 | NOT RUN | On selected cube, issue `rotate x 45 degrees`, `move x -2 units`, `scale by 1.5`, undo each; repeat with sidebar Apply. Change sliders then Cancel Values. Arm `extend 0.5 units`, explicitly Left-select a face, use Right open-palm intent, move farther, release, Undo. | Exact bounded values; separate Undo; sliders alone never edit. Fixed cap offset remains 0.5 outward-normal units regardless of further hand movement, never incidental hover. | Value ignored/accumulated/wrong target, staging edit or extra Undo: cancel, verify IDLE/selection and messages, record phrase/settings. |
| 12 | NOT RUN | `/talk`, say “create cube”, `/end`, wait committed+visible result; repeat intentionally. Speak same phrase while muted, then type `undo`. | Two intentional voice turns create two cubes; muted conversation creates none; no partner-transcript duplicates. Typed fallback works. | Missing readiness/duplicate/unintended command: mute, stop speech, inspect sanitized status; restart voice after account/device issue. Never share keys. |
| 13 | NOT RUN | During previews test Escape, typed cancel and Undo. Hide required hand briefly (<0.5 s), return; hide >0.5 s; open to rearm. Hide unrelated hand during each one-hand MOVE. Cross/occlude hands while selected. | Brief required loss freezes/reanchors; sustained loss restores once and gates. Unrelated loss leaves MOVE active. Crossing cannot transfer ownership; uncertain identity freezes/cancels. Undo cancels preview before previous edit. | Drift/jump/transfer, fabricated release, stuck or missing gate: cancel/open required hands; record timings and hand-status labels. |
| 14 | NOT RUN | During unfinished preview Disconnect, reconnect explicitly/open hands. Repeat cleanup via opening a separate saved rehearsal file, disable/re-enable, and companion `quit`; then reconnect after restart. | Original transform/topology restored, no leftover preview meshes/timers/cursors, new session no replay, UI usable. | Surviving deformation/worker, queued command after reconnect, locked UI or join warning: stop/restart companion and Blender after preserving work; report exact exit path. |
| 15 | NOT RUN | After `/end` and completed feedback, `quit` or Ctrl+C; confirm camera indicator off and terminal returns. Relaunch same command, reconnect/open hands, verify cursor, then quit again. | Server stopped, camera light off, microphone/camera released, subsequent camera open succeeds. | Indicator stays on, blocked exit/reopen or worker join warning: identify remaining process/competing capture app; do not call shutdown passed. |

## Observations

No 0.7.0 physical actions have been performed or reported yet. The complete
implementation and automated evidence are in [clutch handoff](clutch_handoff.md).
When a row fails, record its exact action, selected object/face, mode/phase, error,
required hand states and timing. Fix demonstrated failures, rebuild/reinstall if
necessary, record the new commit/version and rerun affected physical checks.
