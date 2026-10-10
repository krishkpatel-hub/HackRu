# Air Modeler 0.9.0 physical acceptance

**NOT RUN on 0.9.0.** No synthetic/native test marks a physical pass. Previous
live findings: MOVE works; SCALE/fist recognition unreliable; apparent single-axis
rotation (reported X); palm turning sometimes triggers SCALE; extrusion weak.
Reported at last release 0.8.0; exact captured failure sequences unavailable.
Preserve [the 0.8 record](physical_acceptance_0.8.md) and all scene files.

Setup first, one action per reply: save `rehearsal_090.blend`; install/restart with
[the exact instructions and launch command](clutch_handoff.md#install-and-launch).
Record delivered SHA, installed version, companion 0.9.0/profile v3, actual Blender
version, anatomical Left/Right, camera 0/microphone 0, actual bridge and voice readiness.
User install remains 0.8.0 until confirmed. No key belongs in chat or diagnostics.

| Group | Status | Starting pose and action | Expected result and required observation |
| --- | --- | --- | --- |
| 1 Selection/MOVE | NOT RUN | Right open, stationary; Left points at cube, pinches and moves while held. Then move Right open palm, hold, release Left. Undo; repeat two edits and Undo separately. | READY without deformation/Undo; Left inert, Right MOVE same sensitivity; no activation/release jump; each edit one Undo. Report phase, smoothness and exact unexpected motion. |
| 2 SCALE | NOT RUN | Select with Left; Right fingers together, extended. Close whole hand to fist, hold 1 s, reopen and hold. Release Left, Undo. Repeat with typed `scale` before selection if recognition fails. | Shrink/enlarge smoothly, steady holds, fist valid, no EXTRUDE, origin/rotation/proportions intact. Report openness range and which fingers/pose fail; capture 20 s if needed. |
| 3 FREE ROTATE | NOT RUN | Select with Left; Right open fingers together. Separately twist, tilt and turn sideways through palm-to-knuckles, then combine motions; hold/release/Undo. Compare `rotate`, then `rotate x/y/z`. | Three independent rotations with no scale change or frame flips. Constrained commands affect only named world axis. Report each physical motion separately with phase/quaternion validity; never mark all three from one motion. |
| 4 EXTRUDE | NOT RUN | Left selects object anywhere. Right fresh isolated pinch; drag a little, hold direction for highlight, then move a comfortable short distance. Try opposite signs, explicit XY/XZ/YZ, hidden face, diagonal ambiguity and repeated cap. | No topology pending/ambiguous; intended outward face highlights/locks; short travel visibly extends; reverse returns toward zero without switching. Report mapping, signed normal, comfortable measured travel/distance and any jump. |
| 5 Completion/recovery/Undo | NOT RUN | Repeat extrusion with Right release first and Left first. Cancel/Escape; briefly hide each hand, then hide >0.5 s; cross/occlude, release during loss, disconnect/reconnect. Undo two completed edits separately; Undo during preview. | Commit only once; observed releases required; brief loss freezes/rebases, sustained loss/cancel exactly restores; no stale release or ownership transfer; correct separate Undo. Report each path separately. |
| 6 Typed/PTT/full demo/shutdown | NOT RUN | IDLE: typed and PTT create cube, numeric move/rotate/scale, fixed extrusion with plane override. Then voice cube → Left clutch/Right MOVE → SCALE → FREE ROTATE → EXTRUDE → individual Undo. Quit/relaunch/quit. | Committed-only voice once each, muted speech inert, typed fallback works, fixed distance exact after automatic face choice. Camera light off/terminal return/reopen; no worker warning. Report service readiness and complete sequence result. |

For every action record PASS/FAIL/NOT RUN, revision/version, starting pose,
actual result, reason/diagnostics and recovery. Partial groups remain NOT RUN unless
a failure occurs. Fix demonstrated failures, rebuild/reinstall and rerun affected
checks before marking ready. Live gain tuning and three-axis visibility limits are
still open acceptance work, not blocked by the draft PR permission issue.
