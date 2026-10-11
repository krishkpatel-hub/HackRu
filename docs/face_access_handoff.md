# Air Modeler 0.16.0 — extrusion face access and normal dragging

Focused continuation of `004ec739a7af9ab90ca02f9a38a23c4d3a95c7d1` (0.15.0),
on `feature/blender`. Scene files and the existing environment are preserved.
The [0.15 Edit Mode handoff](edit_mode_handoff.md) remains historical evidence.
**All 0.16 camera/microphone physical acceptance is NOT RUN.**

## Root causes and scope

The previous AUTO path chose a world plane before choosing a face. Its normal
observability filter could reject a correctly selected face whose normal was
nearly perpendicular to that plane. Thus “face cannot be selected” and “selected
face cannot drag outward” could look the same. Ordinary nearest-surface raycasting
also cannot reach a hidden opposite/bottom face from one fixed view. Separately,
the sidebar showed generic `DRAGGING` while the extrusion stage said `DWELLING`.

The extrusion Right cursor now spans usable viewport pixels, accounting for
overlapping toolbar/sidebar/header regions. Its nearest current-mesh ray hit,
rather than coarse visibility samples or world direction, determines hover.
Unsupported hits report a specific face eligibility reason. The sidebar and
overlay show the extrusion stage consistently: TARGETING, DWELLING, LOCKED or
DRAGGING; completion/cancellation feedback remains explicit.

Changes are confined to extrusion targeting, its controls/overlay, and unconstrained
AUTO distance. Left selection remains stationary; MOVE/ROTATE/SCALE recognition,
thresholds, sensitivity and smoothing are unchanged. Voice CREATE/REMOVE,
typed commands, optional PTT, UUID deduplication, reconnect protection, explicit
plane/axis controls, numeric distance and the shared wire contract remain intact.
No global hand filter, extra microphone stream or speech implementation was added.

## Choosing a face

1. Left pinch selects/holds the object. A fresh deliberate Right extrusion pinch
   enters actual Edit Mode, Face Select, on that object only.
2. **Hover:** put the Right cursor inside a visible eligible face. Cyan identifies
   the complete boundary and shows dwell progress. Hold both pinches and the same
   valid face for two seconds. Orange means its identity is locked.
3. **Expose another side:** before lock, use normal orbit/pan/zoom, standard view
   shortcuts or perspective/orthographic toggle. View changes reset dwell and
   refresh projection/raycast references. Navigation never deforms the object.
4. **Explicit browser:** click **Previous Face / Next Face** in the viewport, or
   press `[` / `]`. The browser enumerates current eligible polygons, including
   eligible caps/side faces from earlier extrusions. Read **Face i of N**, mesh
   index and world OUT normal. Browsing does not lock or deform the face.
5. Browser mode ignores incoming hover choices. An occluded browsed candidate has
   a distinct **dashed magenta** boundary through occluders, alongside the cyan
   candidate/orange locked styling. This is explicit selection, never silent
   through-mesh hover. Press **Enter** or click **Confirm / dwell**, then keep both
   pinches valid for a fresh continuous two seconds. `H` / **Hover targeting**
   returns to ordinary hover. A teammate may operate these keyboard/mouse controls
   while the hand operator keeps both pinches held.

Changing candidates, losing a target, invalid tracking, stale/gapped observations
or view changes reset dwell. Timers alone cannot authorize lock. Tiny boundary
jitter can briefly retain the outline only; it grants no selection or dwell time.
Browsing/hovering adds no geometry or Undo step. At lock, face/operation and a new
manipulation reference are frozen: all targeting movement contributes zero distance.

## Dragging, limits and completion

Unconstrained **AUTO / no axis** maps Right displacement to a signed scalar along
the selected face's transformed outward normal. Drag along the displayed projected
OUT arrow. When the normal projects near zero, the stable displayed fallback is
**upward = outward, downward = inward**. This choice freezes at lock; it never
infers camera depth from hand size or switches direction mid-drag. Rotation,
nonuniform scale and negative scale use the inverse-transpose normal correctly.

Explicit plane/axis and numeric-distance semantics are unchanged. If a chosen
constraint cannot move along this face normal, feedback says the face was selected
but its constraint blocks travel; cancel and choose AUTO or a compatible constraint.
Numeric distance applies on the next valid observation after the same dwell lock.

Existing geometry checks remain: editable single-user local mesh, closed consistent
outward manifold, flat strictly convex supporting triangle/quad, finite nonsingular
unsheared transform, and supported attributes. Parents, enabled modifiers,
constraints, animation, shape keys and custom normals remain unsupported. The
visibility workflow retains its simple-mesh/scene budgets. Recessed faces are
explicitly rejected: a stepped extrusion can make an older face recessed. A new
cube cap and its four supporting side faces are eligible outward. Inward shortening
remains conservative; coplanar fixed geometry or the next topology event can block
or bound it, with an explicit reason. It is not a cavity/boolean operation.

Outward preview topology is built once and updated from the immutable baseline.
Zero/inward crossings reuse that ownership/cache; edits do not accumulate. Either
valid release order completes once, returns to Object Mode with the target selected,
and requires release/rearm before another gesture. Early/zero release changes no
geometry. One completed extrusion is one native Undo; repeated edits undo separately.
Escape, Cancel, sustained loss, stale input, disconnect and context loss retain
restoration/cleanup protections and the unchanged 0.5-second loss limit. Blender
work stays on its main thread. CREATE/REMOVE reject during active targeting/preview.

## Verification record

**425 Python tests + 78 subtests passed**, `/tmp/air16-python.log`.
**12 isolated native Blender 5.2.2 scripts passed** using the installed ZIP,
with 99 PASS markers (group and completion markers, not 99 independent tests).
Logs are `/tmp/air16-final-<script>.log`:

| Script | PASS markers | Evidence |
| --- | ---: | --- |
| `face_access_check` | 7 | All six faces in PERSP/ORTHO, occluded browse, view navigation, fallback, new cap/side, transformed/negative-scale exact distance, native Undo |
| `browser_controls_check` | 5 | Actual modal keyboard/button dispatch, invalid-hand dwell reset, navigation versus edit shortcuts, sidebar cancellation/no Undo, context loss before TIMER |
| `face_access_geometry_check` | 7 | Current editable faces, all four new supporting sides, signed world displacement, one topology build, exact restoration and specific eligibility reasons |
| `viewport_check` | 4 | Usable viewport/sidebar mapping, native perspective/orthographic rays, legacy mapping, browser hitboxes, actual GPU hidden-face cue/state restoration |
| `clutch_check` | 17 | Left inert, MOVE/ROTATE/SCALE, explicit planes, numeric extrusion, dwell/release gates, losses, cancellation, Undo and lifecycle cleanup |
| `remove_check` | 6 | Selected tagged-object removal, ambiguity rejection, shared-mesh preservation, active-gesture rejection, UUIDs and native Undo |
| `bridge_check` | 16 | Creation, validation/dedup, reconnect/no replay, lifecycle and native Undo |
| `precision_check` | 6 | Typed/sidebar precision, selector, explicit numeric extrusion and independent Undo |
| `visibility_check` | 9 | Nearest visible cube/prism faces, projection/occlusion, transformed normals and view invalidation |
| `overlay_check` | 3 | Native GPU tint, distinct cyan/orange, depth occlusion, no geometry mutation |
| `extrusion_check` | 13 | Legacy cube/prism extrusion, attributes, separate Undo, cancellation/loss/context/edit cleanup |
| `smoke_check` | 6 | Installed runtime allowlist, primitive creation, registration/rejection/lifecycle |

The final review found and fixed an event-order cleanup gap: context loss followed
by a browser click before TIMER now disconnects and restores the baseline safely.
The added modal regression, legacy extrusion and install smoke scripts passed
again on the final ZIP. No tracking/geometry safeguards were loosened.

All **18 runtime ZIP entries** match source byte-for-byte, including the unchanged
shared protocol and spatial copies; no tests, credentials or scene files are packaged.
ZIP: `/Users/krishpatel/HackRu/dist/air_modeler.zip`, version **0.16.0**, SHA-256
`3aac4f21540eaf046ead7f258cbd6c712e0cb7c19b49fb631d4ed1feb3a571b2`.
The ZIP is a local ignored artifact; build it from the release checkout with
`.venv/bin/python tools/package_addon.py`. Run the Python suite with
`.venv/bin/python -m pytest -q`. Native scripts live in `addon/air_modeler/`; use
disposable factory-startup Blender sessions with isolated `BLENDER_USER_RESOURCES`,
the rebuilt ZIP and port 8765 free. They must run sequentially when using TCP.

Generated observations, native geometry/operators/Undo, mocked audio and transport
tests are automated evidence only. The original 67-test/78-subtest baseline and
standalone voice results are historical; none proves a combined physical demo.
Baseline ZIP `dist/air_modeler-baseline-0.15.0.zip` is retained with SHA-256
`61a8711471e8def291d910d13b66ea913c0c6208dc87756f5fc807598aa82991`.
Known GitHub draft-PR permissions remain separate from build/rehearsal; prepared
description `/tmp/air-modeler-integration-pr.md` is retained without repeated retries.

## Install, restart and launch

1. Save your scene separately. Stop the companion, Disconnect, and disable/remove
   the old add-on. Fully quit Blender.
2. Reopen Blender → Preferences → Add-ons → Install from Disk →
   `/Users/krishpatel/HackRu/dist/air_modeler.zip`. Enable and confirm **0.16.0**.
3. Fully quit/reopen Blender again. Open your rehearsal scene in Object Mode,
   Global Undo enabled, Solid shading and X-Ray off. Use one intended viewport.
4. In the Terminal shell where the replacement key is privately exported:

```sh
cd /Users/krishpatel/HackRu && /Users/krishpatel/HackRu/.venv/bin/python -m companion.main --camera 0 --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --two-hands --device 0
```

Camera 0 and microphone 0 (MacBook Air Microphone) are user-confirmed. If needed,
enter the replacement key with hidden zsh input; never put it in chat, arguments,
a file or a commit:

```zsh
set +x
read -rs 'ELEVENLABS_API_KEY?ElevenLabs API key (hidden): '
export ELEVENLABS_API_KEY
printf '\n'
```

Connect from that viewport's Air Modeler sidebar. Require Connected/READY, fresh
Left/Right tracking and **VOICE LISTENING — CREATE/REMOVE ONLY** separately.
No `/talk` is required. Typed input stays available; `--no-mic` disables audio and
`--push-to-talk` opts into PTT. The hand worker retains `preview=False`.

## Short physical acceptance — NOT RUN

Say **create cube**, wait for selection. For each world normal ±X, ±Y and ±Z,
Left-clutch → fresh Right pinch → browse to the indicated normal → Enter → hold
two seconds → drag along OUT (or upward fallback) → release → verify Object Mode
→ Undo once. Open both hands between trials. Also expose an opposite/bottom face
with viewport navigation and hover it; verify navigation resets dwell.

Next keep one completed outward extrusion. Start again and choose its new cap,
then a new supporting side face; complete and Undo each edit separately. Verify
no lock jump, no face switch after lock, both release orders, early release,
Escape/loss restoration, and unchanged MOVE/ROTATE/SCALE and CREATE/REMOVE. Record
observed results; do not infer them from automated passes. Finish with `quit` or
Ctrl+C, verify camera off/prompt returned, then `unset ELEVENLABS_API_KEY`.
