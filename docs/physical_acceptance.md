# Air Modeler 0.11.0 physical acceptance

**All checks NOT RUN on 0.11.0.** On installed 0.10.0 the user reports:
“EXTRUDE arms, but face choice or dragging is unpredictable.” Arming is observed;
face selection/dragging failed the usability expectation. No detailed capture
or complete combined pass is available. Keep this observation separate.
 User reports selection, MOVE, SCALE and ROTATE
now work reasonably well. Preserve that report and [0.9 history](physical_acceptance_0.9.md);
do not reinterpret synthetic passes as live acceptance. Extrusion is this milestone's focus.

Setup proceeds **one small action per reply**. First save a new
`/Users/krishpatel/HackRu/rehearsal_0_11.blend` copy. Follow
[installation/restart/launch](clutch_handoff.md#install-and-launch), then confirm
installed version **0.11.0**, exact `git rev-parse HEAD`, Blender version,
companion 0.11.0/profile v3, camera 0/mic 0, bridge READY and Scribe-ready separately.
At development inspection the installed add-on was 0.10.0 on disk; running loaded
module equality was not verified. The old companion was stopped cleanly for tests.
No private key belongs in this record, chat, command arguments or recordings.

| Step | Status | One physical check | Observe and record |
| --- | --- | --- | --- |
| 1 | NOT RUN | With Right open and stationary, Left pinch selects a cube. Hold, then move Left slightly while held. | SELECTED_READY, no deformation, Left movement inert, no Undo entry. |
| 2 | NOT RUN | Still holding Left, Right isolated thumb/index pinch, short deliberate drag toward one visible side, then pause. | EXTRUDE ARMED → labeled candidate → locked orange face/OUT arrow. Move during the brief lock highlight, then hold: no accumulated-motion jump. Record face, signed axes/mapping and any rejection. |
| 3 | NOT RUN | Move Right a comfortable short distance outward, hold, reverse through baseline, then inward toward the limit. | Small deadband at baseline, continuous signed distance beyond it; same face throughout; clean shortening without internal cap/overlap; zero returns original topology; limit clamps with readable reason. Record travel comfort and direction. |
| 4 | NOT RUN | Release Right, then Left; Undo. Repeat with Left release first. | One edit per completion, no release jump or second commit; one Undo restores each exact baseline. |
| 5 | NOT RUN | Reselect and repeat on each accessible visible cube side, using a documented explicit plane/axis if needed. | Hidden opposite face never selected; every visible cube side reachable through suitable mapping, no excessive travel or unexplained sign. |
| 6 | NOT RUN | Rotate the object, finish, reselect, and extrude a newly exposed face. Also repeat on a resulting cap. | Fresh visible faces/normals; stable mapping; repeated cap bound shown; separate Undo for every completed edit. |
| 7 | NOT RUN | Separately test a diagonal ambiguous drag; typed Cancel; Escape; brief and >0.5 s loss of each hand; navigation; disconnect/reconnect. | Ambiguity shows a tentative face and changes no topology; temporary loss freezes/reanchors; sustained loss/cancel/navigation/disconnect restore baseline, require fresh observed release. No stale frame or identity transfer. |
| 8 | NOT RUN | Retest selection/MOVE, SCALE through fist/reopen, and independent three-axis ROTATE; release/Undo each. | Existing controls, gain, smoothness and transaction behavior unchanged. Record each tool separately. |
| 9 combined services | NOT RUN | PTT `/talk` → “create cube” → `/end`; complete hands sequence, typed fallback, fixed numeric extrusion, individual Undo; clean shutdown. | Scribe-ready and bridge-ready before commands; each committed command once; typed input available; shutdown restores active preview, releases camera, returns prompt without worker warning. |

For each action record exact revision/installed version, starting pose, PASS/FAIL/
NOT RUN, actual result and recovery. An incomplete group stays NOT RUN unless a
failure occurs. If recognition fails, inspect 2 Hz diagnostics and optionally use
the existing private bounded landmark recording/replay. Do not globally relax
working arbitration thresholds. Fix demonstrated owned-code defects only, rebuild,
reinstall/restart and rerun affected checks. PR permissions do not block rehearsal.
