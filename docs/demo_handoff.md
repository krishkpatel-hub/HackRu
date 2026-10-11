# Air Modeler 0.14.0 combined demo handoff

Install/restart and private key handling: [current engineering handoff](clutch_handoff.md#install-and-launch).
One-action acceptance record: [physical checklist](physical_acceptance.md).
All current physical results are **NOT RUN**. Complete readiness and safety checks
before rehearsing this sequence. No automated or standalone voice result establishes
a combined live pass.

Camera 0; microphone 0 (MacBook Air Microphone); existing `.venv`; worker
`preview=False`. Source and packaged add-on 0.14.0 must match. From the intended
3D viewport, Connect and require Blender Connected, companion READY, actual Left
and Right observations, and **VOICE LISTENING — CREATE/REMOVE ONLY** separately. A listening process
or PTT ARMED alone proves neither tracking nor voice readiness.

## Rehearsal sequence

Keep Terminal available to a helper, with normal hands-free listening active. For each voice turn, say one supported
CREATE/REMOVE phrase, pause, then wait for committed text and the visible result.
In optional PTT mode, `/end` is not Cancel and does not retract buffered speech. Do not start another turn
or reconnect with recognition still pending. Typed phrases use the same parser and
remain available throughout. Reconnect closes the old audio session and discards its delayed transcripts before
a fresh session starts; do not repeat a command until READY/LISTENING returns.

1. Voice “create cube” (typed `create cube`): one new cube, no duplicate.
2. With Right open and still, Left pinch the cube and hold. Move Right palm to MOVE;
   release Left to commit. Left motion must remain inert.
3. Reselect, turn the Right palm to ROTATE through the intended three axes, then
   release Left. If needed, typed `rotate x`, `rotate y`, or `rotate z` constrains
   the next operation; the physical gesture stays palm orientation.
4. Reselect, close Right fingers toward a fist to shrink, hold, reopen to enlarge;
   release Left. SCALE must not turn into ROTATE or EXTRUDE.
5. Reselect with Right open, then isolate Right thumb/index pinch. While both pinches
   remain held, move the displayed Right cursor inside the desired eligible face.
   Cyan countdown must remain on that polygon for 2.0 seconds, then turn orange
   with zero ordinary deformation. Move only after lock: outward, hold, reverse
   through zero, then a small bounded inward shortening. Release either pinch to
   commit once, then open both to rearm. For a mapping rejection, cancel and choose
   a compatible plane/axis before retrying; never force an unsupported face.
6. Typed `undo` or Blender Undo once per completed edit, waiting each time: extrusion, scale,
   rotation, then movement. Leave the spawned cube selected for the removal test.
   Each completed edit has its own native Undo.
7. With both hands released, say “remove cube” to remove only the selected tagged
   cube; use Blender Undo to restore it.
8. In separate transactions test Cancel, brief and sustained loss, disconnect/reconnect,
   typed fallback and clean shutdown. Pending hover creates no geometry or Undo.

## Recovery and shutdown

- Escape/typed `cancel` restores an unfinished preview and clears the overlay. Open
  both required hands to rearm. Spoken Cancel is ignored; use typed Cancel or Escape.
- Missing/invalid tracking immediately clears an unfinished dwell. A >200 ms capture
  gap resets it; cached timers never lock. During deformation brief loss freezes
  and recovery rebases; sustained 0.5 s loss cancels. Loss is not release.
- Navigation before lock resets/re-evaluates hover; navigation after lock cancels.
- Finish speech first, disconnect during a separate preview, verify restoration;
  reconnect explicitly, wait READY, open both hands and issue new commands. Offline
  commands are discarded, not replayed.
- Wait for the last committed result, then `quit` or Ctrl+C (optional PTT: `/end` first). Check restored
  preview, camera off, terminal prompt and no worker warning. Finally
  `unset ELEVENLABS_API_KEY`. Never print or record the value.

## Evidence boundaries

Current automated results/limits are in the [voice handoff](voice_auto_handoff.md). The original
67-test/78-subtest baseline and older live reports are preserved in the
[historical demo handoff](demo_handoff_0.5.md). Teammate V's report at
`104924d9c38be26dc8459346be08645a62a17b3e` covers standalone 11-command speech,
intentional repetitions, deduplication, venue-noise PTT, typed fallback and shutdown.
It does not test this two-hand Blender release. Realtime API access works according
to that report; sponsor attribution is unconfirmed. The key owner must revoke the
previously exposed credential and supply a replacement privately.

Draft PR permissions remain blocked; prepared description is
`/tmp/air-modeler-integration-pr.md`. This does not block rehearsal. Do not merge main.
