# Air Modeler 0.12.0 physical acceptance

**All checks NOT RUN on 0.12.0.** Latest actual user report: closing/opening the
Right hand to SCALE often starts ROTATE, and EXTRUDE chooses an unintended face
and needs clear highlighting. Installed add-on on disk was 0.11.0; loaded-module
identity and a detailed failure capture were not verified. Preserve the report;
do not convert synthetic passes into physical acceptance. Previous records:
[0.11](physical_acceptance_0.11.md), [0.10](physical_acceptance_0.10.md).

Proceed **one small action per reply**. Save a new
`/Users/krishpatel/HackRu/rehearsal_0_12.blend` copy, then follow
[install/restart/launch](clutch_handoff.md#install-and-launch). Confirm installed
0.12.0, exact revision, Blender version, camera 0/mic 0, companion 0.12.0/profile v3,
bridge Connected/READY, actual hand observations and Scribe-ready separately.
The development companion was stopped cleanly; the user's Blender scene was left
open. Never put a private key in this record, chat, arguments or recordings.

| Step | Status | One physical check | Observe and record |
| --- | --- | --- | --- |
| 1 | NOT RUN | With Right open and stationary, Left pinch selects a cube; move Left slightly. | SELECTED_READY; Left inert; no geometry change or Undo entry. |
| 2 | NOT RUN | Without a tool override, close Right gradually into a fist, pause, reopen. | SCALE activates without ROTATE/EXTRUDE or lock jump; stays SCALE through contact/reopening; positive proportional scaling around original origin. |
| 3 | NOT RUN | Release Left, Undo, then repeat closure with a small natural palm wobble. | Still SCALE, one completion/Undo; record wobble, any ambiguity and diagnostic reason. |
| 4 | NOT RUN | Reselect with stable openness, deliberately turn Right palm; release and Undo. | ROTATE activates; free X/Y/Z rotation remains available; no unwanted SCALE/MOVE or lock jump. |
| 5 | NOT RUN | Reselect; Right isolated pinch, deliberately drag toward a visible face, then pause. | Displayed Right cursor, cyan actual candidate, then orange locked polygon/OUT arrow. Highlight remains on that face; no deformation during recognition/highlight. |
| 6 | NOT RUN | Continue outward, hold, reverse to zero and slightly inward. | Continuous signed motion beyond small deadband; same face and highlight follow preview; original topology at zero; bounded clean shortening. |
| 7 | NOT RUN | Release Right then Left, Undo; repeat with Left released first. | Exactly one completion and one Undo per meaningful extrusion; no release jump; overlays clear. |
| 8 | NOT RUN | Reselect and repeat on each accessible cube face, one at a time. | Clear direction wins; tied directions can use displayed Right cursor inside the face; hidden faces never win. Record face/mapping/cursor and chosen result. |
| 9 | NOT RUN | Try an ambiguous diagonal with the Right cursor off the object or on an edge. | Cyan tentative polygon and “Drag more clearly to choose a face”; no geometry. Move clearly toward another face and observe candidate change before lock. |
| 10 | NOT RUN | Rotate the object, finish, reselect, extrude a newly exposed face. | Fresh visible world normals and correct highlighted face; repeat on a new cap where supported. |
| 11 | NOT RUN | Separately Cancel/Escape, brief and >0.5 s hand loss, disconnect/reconnect, and disable during previews. | Brief loss freezes/reanchors; sustained loss/interrupt restores exact baseline; overlays clear and fresh release is required. |
| 12 combined | NOT RUN | PTT `/talk` → “create cube” → `/end`, hands sequence, typed overrides/fallback, individual Undo, clean shutdown. | Actual service-ready states first; commands execute once; workers/camera close and active previews restore without warnings. |

For every action record exact version/revision, starting pose, PASS/FAIL/NOT RUN,
actual observation and recovery. Incomplete groups remain NOT RUN unless a failure
occurs. If SCALE/ROTATE still conflict, use optional 2 Hz diagnostics and the existing
private bounded **world-landmark** capture to inspect the actual shape/orientation
sequence before further tuning. The historical sparse pinch recording cannot
answer that question. PR permissions do not block physical acceptance.
