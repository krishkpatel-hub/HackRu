# Air Modeler v1 local bridge

The root README contains current setup instructions and the preserved architecture agreement. This document records the current clutch interaction and its legacy compatibility. The single standard-library implementation is `shared/protocol.py`; `tools/package_addon.py` copies its bytes to `air_modeler/_protocol.py` **inside the ZIP only**. Never edit or maintain a second validator source.

## Endpoint and handshake

The companion listens only on `127.0.0.1:8765`, accepts one Blender client (including a client awaiting hello), and closes additional connections. Blender uses a nonblocking socket and a roughly 30 Hz modal timer. No socket thread touches `bpy`.

Every wire message is one UTF-8 JSON object followed by `\n`, with exactly `v`, `type`, `session_id`, `seq`, and `payload`. Blender initiates:

```json
{"v":1,"type":"hello","session_id":null,"seq":1,"payload":{}}
```

The companion assigns a fresh canonical lowercase UUID for every connection and replies:

```json
{"v":1,"type":"hello","session_id":"9a6d7dd7-1ee2-46a4-95cb-cf34d2fb92a6","seq":1,"payload":{}}
```

After hello, each direction uses its own increasing positive integer sequence (first post-hello message is 2), with the assigned session. The receiver accepts strictly increasing values; it does not require contiguous numbers. Unknown fields, repeated JSON keys, non-UTF-8 text, invalid schemas, wrong versions/sessions, and stale sequences are rejected. A bad complete line does not prevent processing the following line. Hello has an empty payload and is accepted only at connection startup. Connection/hello timeout is five seconds.

Companion → Blender: `command`, `hands_frame`; legacy `hand_frame`, `gesture_start`, `gesture_end`, `gesture_cancel`, and deprecated `selector_frame` remain schema-compatible.
Blender → companion: `status`. Both directions send the initial `hello` as described above.

## Payloads

| Type | Required payload fields |
| --- | --- |
| `command` / `spawn` | `id` UUID, `action: "spawn"`, `shape`: `cube`, `sphere`, `cylinder`, `prism` |
| `command` / `set_mode` | `id` UUID, `action: "set_mode"`, `mode`: `MOVE`, `ROTATE`, `SCALE`, `EXTRUDE`; ROTATE optionally accepts `axis` X/Y/Z (default Z); EXTRUDE optionally accepts `plane` AUTO/XY/XZ/YZ (default AUTO) and `axis` NONE/X/Y/Z (default NONE). Explicit axes must belong to explicit planes. |
| `command` / `precision` | `id` UUID, `action: "precision"`, `mode`, finite numeric `value`; `axis` required for MOVE/ROTATE and forbidden for SCALE/EXTRUDE. Bounds and semantics below. |
| `command` / `cancel` or `undo` | `id` UUID, `action`: `cancel` or `undo` |
| `hands_frame` | `frame_id` positive integer, `t` nonnegative finite capture elapsed seconds, `hands` with exactly anatomical `Left` and `Right` observations; exact fields below |
| `hand_frame` | `u`, `v`, `present` boolean, `pinching` boolean |
| `gesture_start`, `gesture_end` | `gesture_id` UUID, `u`, `v` |
| `gesture_cancel` | `gesture_id` UUID, `reason` text |
| `status` | `mode`, `phase`, `selected_object`, `hovered_object`, `tracking`, `last_error` |

Coordinates must be finite numbers in `[0, 1]`; boolean values are not coordinates. Only absent `hand_frame` observations (`present: false`) may use null coordinates, with both `u` and `v` null. Visible/start/end coordinates cannot be null. Text fields allow at most 1024 Unicode characters and must encode as UTF-8. Extra payload fields are rejected.

**Spawn, MOVE, ROTATE, SCALE and single-face EXTRUDE** change the scene. Matching gesture start/end/cancel events control the armed transform; frames only report/update an existing preview. Commands `cancel`, `undo`, and `set_mode: MOVE/ROTATE/SCALE/EXTRUDE` are implemented. See [MOVE handoff](move_handoff.md) for lifecycle, camera setup, and validation.

Example status (at most 4 Hz while idle, also after received actions/errors):

```json
{"v":1,"type":"status","session_id":"9a6d7dd7-1ee2-46a4-95cb-cf34d2fb92a6","seq":2,"payload":{"mode":"MOVE","phase":"IDLE","selected_object":"Air Cube","hovered_object":null,"tracking":false,"last_error":null}}
```

`mode` is the armed MOVE, ROTATE, SCALE or EXTRUDE; `phase` is the actual IDLE, SELECTED_READY, DRAGGING, or NEEDS_RELEASE state. `selected_object` is the selected active object's name or null. `hovered_object` is the nearest eligible mesh under the cursor or null; passive hover never selects. `tracking` requires a present observation within 0.5 seconds. `last_error` is a readable rejection/recovery diagnostic, cleared by a successful command or gesture. Status is state reporting, not a per-command acknowledgement. SELECTED_READY locks a target and baseline but does not deform it.

In the **legacy single-cursor stream**, a start uses its own coordinates and locks a target, original transform, mode, axis, sensitivity and fixed view mapping. Frames preview from the original transform only; matching end honors final coordinates and creates one undoable transform, then returns to MOVE. Absent frames freeze immediately; 0.5 seconds without a present observation cancels, including stopped streams. Interruptions restore baseline and require a fresh present, non-pinching frame before another start. H independently enforces physical release; its `pinching` flag means gesture-active, never permission to start editing. Duplicate starts are remembered per session (4096 limit); mismatched ends/cancels are ignored. Spawn and mode changes during drag are rejected. The coherent two-hand stream instead follows the clutch lifecycle below.

## Teammate callback

```python
server = BridgeServer()  # from companion.transport.server
server.start()
emit = server.emit
# run_hand_tracker(emit, stop_event, config)
# run_voice(emit, stop_event, config)

accepted = emit({
    "type": "command",
    "payload": {
        "id": "875905d1-9dad-46bd-9ef6-439da23920ef",
        "action": "spawn",
        "shape": "cube",
    },
})
```

`BridgeServer.emit(event: dict) -> bool` is thread-safe and nonblocking with respect to network I/O and queue space. It validates and snapshots the event under short memory-only synchronization. H/V supply **only** `type` and `payload`, including their own command/gesture UUIDs. One transport thread assigns all outgoing envelope sequence numbers and writes bytes. H/V must not create sockets, add envelope fields, manage Blender modes, or retry discarded input after reconnect. Their existing service signatures and independent print-JSON harnesses remain unchanged.

`True` means queued in the current ready session, not confirmed scene execution. `False` means invalid input, no ready connection, a session change during the call, or queue overflow; `server.last_error` explains. The callback captures its initial session so an in-flight call cannot cross reconnect. Preserve ordered boundary events. Only a trailing legacy `hand_frame` may be replaced by another consecutive legacy `hand_frame`; never coalesce across a command or gesture boundary. **`hands_frame` events are never coalesced**, because each coherent capture can contain either hand's START/END/CANCEL boundary. The callback queue holds at most 256 events. Overflow faults the connection and discards pending input rather than silently losing boundaries.

## Limits, failure and reconnect behavior

- Maximum encoded line: 8192 bytes excluding newline. Overlong lines are discarded through the next newline, then normal decoding resumes. Each socket read takes at most 8192 bytes; complete buffered lines drain before another read. Partial-line storage is bounded to 8192 bytes.
- Blender decodes/dispatches at most four lines per timer tick and uses nonblocking writes with retained partial-write offsets. The server accepts at most one connection, processes at most 16 incoming lines and queues at most four callback events per iteration. Outgoing bytes are capped at 64 KiB; backpressure overflow disconnects instead of blocking.
- Command IDs are deduplicated in Blender for the entire session, including failed/unsupported commands. A duplicate with a newer sequence is consumed without a second action. At 4096 distinct command IDs, close the session rather than evict IDs and risk replay. Reconnect explicitly to continue.
- Clean EOF, server shutdown, connection failure, disable, file load, or invalid captured viewport context restores any active preview, closes the socket, and removes the modal timer and cursor draw handler. Reconnect is a user action; there is no automatic reconnect or spawn retry.
- Disconnect destroys session sequence/dedup state, partial receive data, pending writes, and queued callback input. The server rejects input while offline. Fresh sessions never replay prior pending events. TCP cannot retract an action already executed before a disconnect; inspect the scene/status if delivery was interrupted.
- Session state is runtime-only. Blender captures the initiating window/viewport/region and scene/view-layer names, re-resolves them after Undo, and uses an explicit context override for the existing undoable spawn operator. Changing/closing that viewport or switching its scene/view layer stops the connection. Edit Mode rejects spawn without switching modes or creating geometry.

## Development runner

From `/Users/krishpatel/HackRu`:

```sh
.venv/bin/python -m companion.main
```

Connect from Blender's Air Modeler panel and wait for `READY`. Then enter:

```text
spawn cube
spawn sphere
spawn cylinder
spawn prism
status
quit
```

Typed input now reuses V's parser and UUID emitter: `create cube`, `create sphere`, `create cylinder`, `create triangular prism`, `rotate`, `rotate x/y/z`, `scale`, `extrude`, `move`, `cancel`, and `undo`. Strict `spawn <shape>` aliases are translated to V's create phrase. `quit`, EOF, or Ctrl-C stops workers and transport; no stale replay occurs. `QUEUED` is not an acknowledgement. No camera/audio packages or keys are needed for typed/synthetic operation. Optional `--camera N`, `--mic`, and `--synthetic` are documented in [MOVE handoff](move_handoff.md); discover N through the hands module before selecting it.

In the legacy single-cursor fallback, ROTATE uses horizontal displacement around a world axis; SCALE uses upward vertical displacement to enlarge. The new clutch stream uses measured right-grip twist and aperture. Axis/angle/factor appear locally in the sidebar/cursor text.

EXTRUDE uses an isolated geometry preview and separate geometry Undo operator. Face index, plane mapping and displacement remain Blender-owned transaction details; the tracker supplies observations, never geometry decisions. The legacy stream's outward vertical-distance mapping is distinct from the new signed plane mapping.

The integrated runner also supports `--mic --push-to-talk`: local `/talk` and `/end` controls share VoiceConfig’s gate and never enter the wire protocol. See [README](../README.md) and [demo handoff](demo_handoff.md) for audio gating, launch and rehearsal details.

## Coherent clutch observations (0.7.0, v1 envelope)

The `--two-hands` producer uses one camera capture, detects up to two anatomical hands, and emits one `hands_frame` per processed capture through the existing `emit` callback. It does not emit competing legacy cursor streams or selector-pose commands. Each observation comes from the same capture and timestamp. Result-array order has no semantic meaning. `frame_id` is an increasing integer in `[1, 2^53−1]`; `t` is increasing elapsed seconds from the producer's monotonic clock origin. Blender rejects stale frame IDs/timestamps within a connection. These fields are distinct from the transport's session/sequence numbers.

The payload has exactly `frame_id`, `t`, and `hands`. `hands` has exactly `Left` and `Right`, including an explicit invalid observation for an absent or uncertain identity. Each hand has exactly:

| Field | Wire meaning and validation |
| --- | --- |
| `valid` | Boolean: a confidently assigned visible anatomical identity. Invalid does not mean released. |
| `confidence` | Finite number in `[0,1]`; exactly zero when invalid. |
| `u`, `v` | Corrected selection cursor in `[0,1]`: closing aim hold, palm-relative held motion, frozen coordinates on opening. Both null when invalid. |
| `palm_u`, `palm_v` | Once-filtered normalized image palm center in `[0,1]` for manipulation translation; both null when invalid. |
| `pinching` | Boolean: this identity's thumb/index gesture is active. False when invalid; never by itself creates a transaction. |
| `open` | Boolean: observed stable thumb/index release/rearm state. False while pinching or invalid. A manipulation grip's aperture may grow without committing the left clutch. |
| `gesture_id` | Canonical lowercase UUID on START/END/CANCEL or active pinching observations; null for inactive NONE observations. |
| `event` | Exactly NONE, START, END or CANCEL. START requires valid+pinching; END requires valid+open+not-pinching; CANCEL requires an ID and not-pinching, and can accompany an invalid observation. |
| `grip` | Boolean: valid right-manipulation thumb/index/middle grip, mutually exclusive with `open_palm`. False when invalid. |
| `angle` | Finite measured image-plane radians in `[-π,π]` only when grip is true, otherwise null. This is not measured 3D orientation. |
| `aperture` | Finite thumb/index/middle spread normalized by palm size, between 0.03 and 10, only when grip is true; otherwise null. |
| `open_palm` | Boolean: deliberate open-palm manipulation pose. False when invalid. |

All flags must be JSON booleans, not 0/1. All four invalid coordinates must be null; invalid observations also have false pose flags and null grip metrics. Unknown keys and partially valid observations are rejected. Anatomical labels come from handedness confidence plus spatial continuity on the mirrored input; the physical acceptance checklist must confirm the labels on the actual camera pipeline. Synthetic correctness does not establish that physical result.

Blender owns arbitration and transaction state: IDLE → SELECTED_READY → DRAGGING → NEEDS_RELEASE → IDLE. A START uses corrected pre-close coordinates to capture the target, selecting identity/UUID, original transform and eligible face without deforming. Simultaneous valid selection attempts have deterministic Left-before-Right ownership. Misses remain release-gated; a held miss cannot acquire a later hover target. Either selecting hand's deliberate movement can activate MOVE. Right selection has no two-hand operation. With a left clutch, deliberate right thumb/index/middle twist or aperture motion can activate ROTATE/SCALE; right open-palm motion can activate EXTRUDE. The former FIST/TWO/THREE/OPEN selector menu is not used.

Mode, hand identities, selected object/face, reference measurements, axis/plane and the restorable baseline lock when intent activates. Competing intent uses normalized thresholds and persistence; ambiguous intent stays SELECTED_READY. Manipulation references are captured at activation to avoid a threshold jump. During a right-hand operation, left motion is ignored except for clutch validity/release. Every preview is calculated from the original baseline, never accumulated deltas.

Only the matching selecting-hand END commits an active valid preview: MOVE uses the final corrected selecting cursor; right-hand operations use the latest valid manipulation observation. An END from the other hand, mismatched UUID, repeated START or completed transaction ID cannot commit another edit. A valid selecting END itself satisfies the successful release gate, so that hand need not remain visible for a later other-hand selection. Cancellation still needs a subsequent observed open state. Releasing SELECTED_READY leaves selection with no edit/Undo entry; unchanged active operations likewise create no Undo entry. Gesture IDs retain session-scoped dedup semantics; command UUID dedup remains in `Session`.

Missing or uncertain required identity/pose freezes immediately and cancels after approximately 0.5 seconds without recovery. MOVE requires only its owner; unrelated-hand loss does not interrupt it. ROTATE/SCALE/EXTRUDE require the left clutch and valid right manipulation pose. Short-loss recovery rebases manipulation measurements to avoid a jump. Cancellation restores the original baseline and requires observed open-hand rearming; loss never fabricates END. Crossing must not transfer ownership. Escape, cancel, stale input, disconnect, context invalidation, file load, disable and shutdown follow the same restoration path. Undo first cancels any held selection/preview, then undoes the prior completed edit.

## Precision and one-operation overrides

Command action `precision` requires `id`, `action`, `mode`, `value`, plus `axis` only for MOVE/ROTATE. Values must be finite JSON numbers (not bool): rotation ±360 degrees, movement ±100 world units, scale 0.1–10 inclusive, extrusion >0.00001 and ≤4 world units. Axes are X/Y/Z. Exact object commands apply once to the currently selected eligible object while IDLE. EXTRUDE arms outward-normal distance for the next explicit face-selection operation: no hover edit and no additional hand displacement. Invalid/conflicting commands during SELECTED_READY or DRAGGING are rejected, never queued. Session/UUID dedup and typed/committed-only speech remain unchanged.

Whole phrases include `rotate x 45 degrees`, `move z -2 units`, `scale by 1.5`, `extrude 0.5 units`, and `extend .5 units`. Bare `rotate [x|y|z]`, `scale`, `move`, `extrude` and `extend` arm one operation subject to the same target/identity locks and required gestures. Mode/plane commands do not immediately alter geometry. Completion/cancellation clears the override.

Plane phrases exactly match the controls: `extrude plane xy`, `extrude plane xz axis z`, `extrude plane yz axis y`, `extrude plane auto`, or `extrude axis x`. `extend` is accepted in place of `extrude`. Optional axes are X/Y/Z/NONE; omitted plane is AUTO and omitted axis is NONE. AUTO with an explicit axis chooses a compatible mapping plane. Explicit plane/axis incompatibility (such as XY with Z) is rejected. Numeric extrusion accepts distance only and keeps its separate outward-normal semantics. Conversational prefixes/suffixes and combined multi-action phrases are rejected.

## Deprecated 0.6.0 selector compatibility

Legacy events retain their exact payloads. Deprecated `selector_frame` has exactly `pose` (FIST, TWO, THREE, OPEN, UNKNOWN or ABSENT), `manipulator` (Right/Left) and `selector` (the opposite role). Its validator remains for compatibility; it is not emitted or used as the selector-pose menu in the new clutch interaction. The following describes the historical 0.6.0 producer/consumer, not the current two-hand controls. Older add-ons reject `hands_frame`; install the matching current ZIP and companion together.

Blender confirms FIST→MOVE, TWO→ROTATE world Z, THREE→SCALE, OPEN→EXTRUDE after 300 ms continuously observed while idle. UNKNOWN/ABSENT retains the last confirmed pose for 600 ms, then MOVE. A stale selector stream also falls back after 600 ms. Changes never alter a drag's captured mode/axis/target/start/baseline. Bare mode commands override automatic selection for one operation; fixed-distance extrusion also overrides. Completion/cancellation clears the override. Single-hand completes to MOVE; two-hand can rearm the still-confirmed selector while idle after release gating.

Two-hand identity uses MediaPipe handedness on the already mirrored input (selfie convention; anatomical labels must be physically verified), confidence ≥0.8, unique labels and spatial continuity of palm centers. Centers within 0.12 normalized image distance are ambiguous; displacement >0.18 per frame is rejected. Uncertain manipulating-hand identity during a pinch is quarantined until the existing loss cancellation; no hand substitution is permitted. After 600 ms without a recovered idle identity, old spatial anchors may expire. Reacquisition requires 300 ms stable identity and the existing open-hand gate. Selector never generates manipulation events.

Pose classification uses index/middle/ring/pinky MCP/PIP/DIP/tip points in aspect-corrected image coordinates. Extended: PIP and DIP joint angles ≥160° and tip-wrist distance ≥1.15×PIP-wrist distance. Folded: PIP angle ≤110° and tip-wrist distance ≤1.1×PIP-wrist distance. Other shapes are UNKNOWN. Fist requires all four folded; TWO requires only index/middle extended; THREE adds ring; OPEN requires all four extended. Thumb is ignored for selection (it remains part of manipulation pinch detection). This is conservative 2D classification; edge-on/occluded hands may be UNKNOWN.
