# Air Modeler 0.8.0 physical acceptance

**New controls: NOT RUN.** Branch `feature/blender`; record exact delivered commit
before the first physical test. Required installed version is **0.8.0**, Blender
**5.2.2**, camera **0**, microphone **0 (MacBook Air Microphone)**.

The user's 0.7 installation/restart and saved rehearsal copy remain in
[the versioned 0.7 record](physical_acceptance_0.7.md). They do not verify 0.8.
The reported 0.7 automated baseline also does not fill this checklist. Preserve
`demo.blend`, `demo.blend1` and `rehearsal_070.blend`; use a separate copy for 0.8.

| Run identity | Observation |
| --- | --- |
| Delivered/tested revision | NOT RUN — record exact commit before physical testing |
| Installed/running version | NOT RUN for 0.8.0 |
| Blender | Previously user-confirmed 5.2.2; reconfirm new run |
| Camera / microphone | User-confirmed indices 0 / 0; fresh observations pending |
| Anatomical labeling | NOT RUN — check actual Left and Right in the mirrored pipeline |

Guide **one small action at a time**, wait for the user's observation and update
this record. Mark PASS / FAIL / NOT RUN only against the exact code and installed
version. Partial groups stay NOT RUN with partial observations unless a failure
has occurred. Process startup, historical voice reports, synthetic landmarks and
native geometry checks do not establish a combined live pass.

| # | Status | Sequential actions | Expected visible result | Failure signs / recovery |
| --- | --- | --- | --- | --- |
| 1 | NOT RUN | Save separate copy; stop old companion. Disconnect, disable/remove old add-on, quit Blender. Reopen, install new ZIP, enable and confirm 0.8.0; fully quit/reopen again. Enable Global Undo. Launch the exact hands/PTT command from current handoff; Connect. Show Left alone, Right alone, then both. | Running 0.8.0 and Blender 5.2.2; bridge Connected/READY, Scribe ready, PTT MUTED, fresh correctly labeled observations. Right alone never selects. | Old version, wrong labels, static/error status, missing audio/camera is not a pass. Stop before modeling, check matching ZIP, permissions, device/model path or private credential; never share keys. |
| 2 | NOT RUN | Type `create cube`; with Right visible and stationary, aim Left, pinch and hold. Move Left substantially in every screen direction without releasing; release. Repeat with a missed Left pinch. Use a separately created sentinel cube to verify stationary selection adds no Undo. | SELECTED_READY, fixed object/face, zero deformation from Left; no retarget while held, miss stays missed. One Undo after stationary selection removes the sentinel creation. | Left-driven MOVE/deformation or extra Undo fails. Cancel/open both, record exact phase/recognition and selected object before diagnosis. |
| 3 | NOT RUN | Left selects/holds. Show Right open palm, move past threshold, then farther; move Left while holding Right still. Release Left, then Undo. Complete two different moves and Undo separately. Try Right alone. | Right-only palm motion drives MOVE after no-jump activation; Left inert; release commits once; each Undo restores its own edit. Right alone never selects/edits. | Closing motion drives MOVE, jump, Left influence or wrong Undo: cancel, open both, record shapes and state. |
| 4 | NOT RUN | Left selects. Twist Right open hand with stable openness past threshold, then farther. Move Left without moving Right. Release Left and Undo. Repeat with `rotate x` and `rotate y`. | ROTATE world Z/default or explicit axis; original origin and scale retained, no Left motion or shape-driven scale, one Undo. | Wrong tool/axis, drift or unintended scale: cancel/open, record measured recognition and exact override. |
| 5 | NOT RUN | Left selects. Close Right whole hand past threshold, then all the way to a visible fist including thumb/index contact; reopen. Translate/twist Right during locked SCALE, move Left, then release Left and Undo. Repeat starting nearly closed. | SCALE shrinks/closes and enlarges/reopens smoothly; fist stays valid, no EXTRUDE or premature commit; translation/twist/Left motion don't add edits. No near-zero division jump. | Fist labeled lost, extrusion, nonuniform/negative factor or jump fails. Cancel/open, record openness/pose feedback and calibrate only after diagnosis. |
| 6 | NOT RUN | Left captures eligible cube face. Right approaches isolated pinch with at least two of middle/ring/pinky open, then pinches and drags. Test Right release first with Left held; then Left release first with Right pinched. Try already-held Right pinch before selecting: reopen/re-pinch. Repeat on prism/new cap; exercise XY/XZ/YZ and ±world axes on suitable outward faces. Undo each edit. | Approach doesn't steal MOVE; fresh pinch locks original face with zero activation jump. Corrected palm-relative drag and frozen opening coordinates. First valid release commits once, other release is inert; gating prevents editing while Left remains held. Fixed topology count per preview, each edit separately undoable. | Wrong face, Left influence, double commit, opening jump, lost mesh attributes, cracks or inward corruption: cancel/open, record face/plane/vector; use eligible outward face. |
| 7 | NOT RUN | Try static input and balanced translation/twist; then deliberate dominant intent. During active tool try another motion and a conflicting command. Test Escape, cancel, Undo, brief/sustained loss of each required hand, crossing/occlusion and simultaneous release/loss; reopen to rearm. | Ambiguous remains READY with prompt; active tool never switches/queues. Brief loss freezes/rebases; sustained loss restores once. Crossing never transfers ownership. Release/loss race cancels, no stale commit. Undo cancels preview before prior completed edit. | Unexpected switch, fabricated release, drift/transfer, stuck or missing gate fails. Stop/cancel, open both, record timing/identity/pose and error before retry. |
| 8 | NOT RUN | While IDLE on selected cube, `/talk`, say `rotate x 45 degrees`, `/end`; inspect then Undo. Repeat `move x -2 units`, `scale by 1.5`, and sidebar Apply. Stage sliders/Cancel Values. Arm `extend 0.5 units`, Left-select face, Right-pinch, drag farther and release; Undo. Speak commands while muted, intentionally repeat a voice turn, then type commands. | Exact selected-object edits don't need clutch; one Undo each. Sliders alone don't mutate. Fixed extrusion waits for Left face plus fresh Right pinch, stays 0.5 outward units. Muted speech edits nothing; intentional repeats execute once each; typed fallback works. | Unintended/duplicate/missing command or wrong precision value fails. Mute, cancel if active, inspect sanitized committed feedback and state; never paste a key. |
| 9 | NOT RUN | During previews, test disconnect/reconnect, opening a separate saved rehearsal file, disable/re-enable, and companion quit. Reopen/release hands after reconnect. Quit again; confirm camera light off and terminal returns. Relaunch, verify fresh capture, quit again. Also idle-reconnect typed-only precision. | Exact baseline restoration, freed temporary meshes/timers/socket, no stale replay, fresh capture after reopen, clean camera/mic shutdown. Idle typed-only precision remains usable without hand observation. | Surviving deformation/worker/light, blocked camera reopen, join warning or replay fails. Preserve scene, stop identified companion and restart matching services; report specific path. |

## Observations

No 0.8 physical result has been reported. Defaults and 2D recognition need live
calibration. Record each action, observed version/commit, phase, Left clutch state,
Right recognition/openness, object/face, error and any recovery. Fix demonstrated
failures, rebuild/reinstall as needed, record the new revision and rerun affected
checks. See [the current handoff](clutch_handoff.md) for exact setup and evidence.
