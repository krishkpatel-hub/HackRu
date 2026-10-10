# Air Modeler v1 local bridge

The root README remains the architecture agreement. This document records its executable details for the connection/status/spawn and MOVE milestones. The single standard-library implementation is `shared/protocol.py`; `tools/package_addon.py` copies its bytes to `air_modeler/_protocol.py` **inside the ZIP only**. Never edit or maintain a second validator source.

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

Companion → Blender: `command`, `hand_frame`, `gesture_start`, `gesture_end`, `gesture_cancel`.
Blender → companion: `status`. Both directions send the initial `hello` as described above.

## Payloads

| Type | Required payload fields |
| --- | --- |
| `command` / `spawn` | `id` UUID, `action: "spawn"`, `shape`: `cube`, `sphere`, `cylinder`, `prism` |
| `command` / `set_mode` | `id` UUID, `action: "set_mode"`, `mode`: `MOVE`, `ROTATE`, `SCALE`, `EXTRUDE`; optional `axis` only for ROTATE, `X`/`Y`/`Z`, default Z |
| `command` / `cancel` or `undo` | `id` UUID, `action`: `cancel` or `undo` |
| `hand_frame` | `u`, `v`, `present` boolean, `pinching` boolean |
| `gesture_start`, `gesture_end` | `gesture_id` UUID, `u`, `v` |
| `gesture_cancel` | `gesture_id` UUID, `reason` text |
| `status` | `mode`, `phase`, `selected_object`, `hovered_object`, `tracking`, `last_error` |

Coordinates must be finite numbers in `[0, 1]`; boolean values are not coordinates. Only absent `hand_frame` observations (`present: false`) may use null coordinates, with both `u` and `v` null. Visible/start/end coordinates cannot be null. Text fields allow at most 1024 Unicode characters and must encode as UTF-8. Extra payload fields are rejected.

**Spawn, MOVE, ROTATE and SCALE** change the scene. Matching gesture start/end/cancel events control the armed transform; frames only report/update an existing preview. Commands `cancel`, `undo`, and `set_mode: MOVE/ROTATE/SCALE` are implemented. EXTRUDE remains visibly unsupported. See [MOVE handoff](move_handoff.md) for lifecycle, camera setup, and validation.

Example status (at most 4 Hz while idle, also after received actions/errors):

```json
{"v":1,"type":"status","session_id":"9a6d7dd7-1ee2-46a4-95cb-cf34d2fb92a6","seq":2,"payload":{"mode":"MOVE","phase":"IDLE","selected_object":"Air Cube","hovered_object":null,"tracking":false,"last_error":null}}
```

`mode` is the armed MOVE, ROTATE or SCALE; `phase` is the actual IDLE, DRAGGING, or NEEDS_RELEASE state. `selected_object` is the selected active object's name or null. `hovered_object` is the nearest eligible mesh under the cursor or null; passive hover never selects. `tracking` requires a present observation within 0.5 seconds. `last_error` is a readable rejection/recovery diagnostic, cleared by a successful command or gesture. Status is state reporting, not a per-command acknowledgement.

A start uses its own coordinates and locks a target, original transform, mode, axis, sensitivity and fixed view mapping. Frames preview from the original transform only; matching end honors final coordinates and creates one undoable transform, then returns to MOVE. Absent frames freeze immediately; 0.5 seconds without a present observation cancels, including stopped streams. Interruptions restore baseline and require a fresh present, non-pinching frame before another start. H independently enforces physical release; its `pinching` flag means gesture-active, never permission to start editing. Duplicate starts are remembered per session (4096 limit); mismatched ends/cancels are ignored. Spawn and mode changes during drag are rejected. Cancel/Undo/Escape and cleanup behavior are detailed in the handoff.

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

`True` means queued in the current ready session, not confirmed scene execution. `False` means invalid input, no ready connection, a session change during the call, or queue overflow; `server.last_error` explains. The callback captures its initial session so an in-flight call cannot cross reconnect. Preserve ordered boundary events. Only a trailing `hand_frame` may be replaced by another consecutive `hand_frame`; never coalesce across a command or gesture boundary. The callback queue holds at most 256 events. Overflow faults the connection and discards pending input rather than silently losing boundaries.

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

Typed input now reuses V's parser and UUID emitter: `create cube`, `create sphere`, `create cylinder`, `create triangular prism`, `rotate`, `rotate x/y/z`, `scale`, `move`, `cancel`, and `undo`. Strict `spawn <shape>` aliases are translated to V's create phrase. `quit`, EOF, or Ctrl-C stops workers and transport; no stale replay occurs. `QUEUED` is not an acknowledgement. No camera/audio packages or keys are needed for typed/synthetic operation. Optional `--camera N`, `--mic`, and `--synthetic` are documented in [MOVE handoff](move_handoff.md); discover N through the hands module before selecting it.

ROTATE uses horizontal displacement around a world axis; SCALE intentionally uses upward vertical displacement to enlarge. Numeric mappings, mode reset, local angle/factor display and generalized commit details are in [Transform handoff](transform_handoff.md). The status schema is unchanged; axis/angle/factor appear locally in the sidebar/cursor text.
