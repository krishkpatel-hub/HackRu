> Focused voice acceptance is **NOT RUN**: after 0.16 installation and LISTENING
> status, say “create cube”, wait for the selected cube; say “remove cube”, wait for
> its removal; use Blender Undo to restore it. Perform one action per reply.
> See [setup and evidence](face_access_handoff.md). Spoken Undo/transforms are ignored.

# Air Modeler 0.16.0 physical acceptance

**All checks NOT RUN on 0.16.0.** Prior real reports: Right closing/opening sometimes
activates ROTATE, and extrusion face choice/dragging is unpredictable. Those reports
remain failures to address physically; generated tests do not turn them into passes.
Installed add-on **on disk** was 0.12.0 at the prior 0.13 inspection; loaded modules were not
introspected. Previous records: [0.12](physical_acceptance_0.12.md),
[0.11](physical_acceptance_0.11.md), [0.10](physical_acceptance_0.10.md).

Proceed **one small action per reply**, recording actual observations before advancing.
First save a new `/Users/krishpatel/HackRu/rehearsal_0_16.blend` copy; preserve every
older scene. Then follow [install/restart/launch](face_access_handoff.md#installation-and-launch).
Current automated tests run in separate factory-startup Blender processes. Do not
paste keys or key-bearing terminal output into this record or chat.

| Step | Status | Starting pose and exact action | Expected result / observation needed |
| --- | --- | --- | --- |
| 1a | NOT RUN | Hands relaxed; install/restart the rebuilt ZIP and launch the companion. | Installed and companion **0.16.0**, Blender version and git revision; Connected/READY and VOICE LISTENING — CREATE/REMOVE ONLY separately. Report exact non-secret errors. |
| 1b | NOT RUN | Show open Left alone, then Right alone, then both separated and still. | Correct anatomical labels and actual fresh hand observations; no role swaps. |
| 2 | NOT RUN | Right open and still; aim Left cursor at a cube, pinch Left and hold. | SELECTED_READY, unchanged cube. Small Left movement remains inert. |
| 3 | NOT RUN | Keep Left held; pinch only Right thumb/index, other fingers extended. Move Right cursor inside a visible face. | Actual Edit Mode on target only, Face Select, prior component selection cleared; TARGETING then cyan selected polygon and “Hold: … / 2.0 s”; no geometry. |
| 4 | NOT RUN | During cyan countdown, move the still-pinched Right cursor to another eligible visible face. | Right can choose a different face from the Left hit; actual face selection/candidate changes to that polygon; countdown restarts at zero. Empty area/edge clears progress. |
| 5 | NOT RUN | Both pinches held; hover inside one eligible face continuously for 2 seconds. | Orange lock with no ordinary deformation/jump. Small movement inside the face may retain countdown. |
| 5b | NOT RUN | Before lock, orbit/pan or use unmodified numpad views to expose each side/bottom. | View changes reset dwell, geometry unchanged; nearest eligible visible face follows the cursor in PERSP and ORTHO. |
| 5c | NOT RUN | With both pinches held, use viewport Previous/Next Face or [ / ]; inspect Face i of N and normal. Then Enter / Confirm / dwell. | Explicit browser retains its candidate despite hover motion; occluded face has dashed magenta outline. No lock until confirmed fresh two-second dwell. H returns to hover. |
| 5d | NOT RUN | Choose a face nearly facing the viewer; after lock follow the displayed upward fallback. | Upward outward / downward inward; no zero-normal stall or lock jump. |
| 6a | NOT RUN | After orange lock, move Right slowly outward, hold, reverse through zero and slightly inward. | Same locked face, steady held result, continuous signed motion and bounded clean shortening. Report mapping and any limit. |
| 6b | NOT RUN | Release Right then Left, then issue `undo`. On a separate edit reverse release order. | First release commits once without jump and returns to Object Mode with object selected; second only rearms; one native Undo restores that edit. |
| 6c | NOT RUN | Repeat for all six cube faces, with one Undo after each. Leave one extrusion committed and choose a new cap, then a new eligible side. | All eligible normals and new mesh face indices accessible; each edit independently undoable. Test rotation, nonuniform and negative scale separately. |
| 7a | NOT RUN | Start fresh targeting; release either pinch before lock in separate trials. | Object Mode restored, no mesh change, overlay cleared, no extra Undo entry. |
| 7b | NOT RUN | During countdown briefly hide a required hand, then recover; separately interrupt during deformation. | Countdown resets. Deformation freezes/reanchors without jump; >0.5 s loss restores baseline. Loss never commits. |
| 7c | NOT RUN | During a separate preview press Escape or type `cancel`; then test disconnect/reconnect after speech finishes. | Exact restoration and Object Mode when context exists, no stale highlight/input replay; fresh observed release needed to rearm. |
| 7d | NOT RUN | During cyan targeting navigate the viewport; in a separate locked preview navigate again. | Before lock reset/re-evaluate; a view change after lock safely cancels. Hover never targets through occluders; explicit browsing clearly identifies an occluded candidate. |
| 8a | NOT RUN | Fresh Left selection, Right open with fingers together; translate palm, then release Left. | MOVE with unchanged mapping/sensitivity and no SCALE/ROTATE. |
| 8b | NOT RUN | Fresh Left selection, Right closes to a fist, holds and reopens, allowing small natural wobble. | SCALE only; positive proportional shrink/enlarge, stable hold, original origin/rotation/signs; no EXTRUDE. |
| 8c | NOT RUN | Fresh Left selection, steady finger shape; twist/tilt/turn Right palm sideways through three axes. | ROTATE only; no SCALE, flips or false activation. Finger flexion alone must not create rotation. |
| 9 | NOT RUN | Rehearse [spawning → MOVE → ROTATE → SCALE → hover/dwell EXTRUDE → individual Undo](demo_handoff.md), with automatic CREATE/REMOVE speech and typed fallback. | Every actual scene result once; record failures separately from voice-ready/hand-ready states. |
| 10 | NOT RUN | Wait last commit, `quit`/Ctrl+C; then unset private key. Optional PTT: `/end` first. | Camera off, prompt returned, workers/bridge stopped, preview restored, no shutdown warning. |

For every action record version/revision, PASS/FAIL/NOT RUN, pose, actual behavior
and recovery. Test supported rotated/nonuniform cubes and prism faces after the
basic sequence. Typed numeric `extrude 0.5 units` must wait for the same dwell; its amount
appears on the next valid observation after lock without a drag. Unsupported or
mapping-incompatible faces must give readable feedback and no edit.

If confusion persists, use optional 2 Hz diagnostics and an opt-in bounded private
world-landmark recording of the exact failure before tuning further. There is no
current full-pose recording of the reported physical defect. PR permissions do not
block rehearsal, and physical results must not be inferred from automated checks.
