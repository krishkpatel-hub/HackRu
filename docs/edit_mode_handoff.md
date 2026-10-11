> Historical 0.15 implementation and evidence. Current release **0.16.0** adds
> [face browsing and face-normal AUTO mapping](face_access_handoff.md).
> Use that handoff for the current ZIP, controls, installation and live checks.

# Air Modeler 0.15.0 — editable face targeting and extrusion

Continue from `fc8f94306815739f5832d97cab320a037d7e4395` (0.14.0), on
`feature/blender`. No reset, main merge, dependency installation, hand/voice module
rewrite or scene modification. Camera 0 and microphone 0 (MacBook Air Microphone)
remain user-confirmed. **All 0.15 physical acceptance is NOT RUN.** Prior reports of
unpredictable extrusion and SCALE/ROTATE confusion remain physical acceptance items.

## Workflow and boundaries

Left pinch selects/holds the object; Left movement never edits it. With a valid
Left clutch, a fresh deliberate Right extrusion pinch enters actual Blender Edit
Mode on that object only, enables Face Select and clears previous components.
An already-held Right pinch still requires release/rearm. MOVE, ROTATE and SCALE
retain their existing recognition and Object Mode transaction behavior.

Right's displayed cursor raycasts the current editable mesh. It can choose a
different visible face from Left's selection hit. The face under that cursor is
actually selected, with cyan candidate outline/countdown. Continuous hover on one
eligible polygon for two seconds turns it orange and locks its identity, normal
and a fresh drag reference. Ordinary lock creates no geometry or visible jump.
Changing faces, empty/occluded/edge hits, missing/invalid required tracking, or
capture/receipt gaps over 200 ms reset dwell; invalid time never contributes.
Timers alone cannot authorize lock. No through-object or fallback face selection.

Post-lock Right displacement drives the existing signed plane/axis mapping and
deadband. Outward extrusion adds a cap; inward shortening remains limited to the
supported convex solid and safe distance (not a cavity/boolean tool). Face and
operation remain fixed. Numeric extrusion applies its explicit distance on the
next valid observation after the same lock, without adding hand-travel distance.

The first valid Right-pinch or Left-clutch release commits a meaningful edit once
and returns to Object Mode with the target selected. The second release only
rearms. Release during targeting or at zero distance returns to Object Mode with
no geometry edit or extra Undo entry. Missing landmarks never synthesize release.

Escape, typed Cancel, required-hand uncertainty/loss, stale input, disconnect,
disable, file load and shutdown retain the existing freeze/cancel protections.
The **0.5-second loss timeout is unchanged**. Short recovery rebases; sustained
loss restores baseline. Undo during preview cancels it before undoing the previous
completed operation. Each completed extrusion has one native Undo; temporary mode
transitions and hover selections add none. CREATE/REMOVE and tool changes reject
during selection/targeting/preview, without queued execution. Normal commands work
after completion. Hands-free voice, typed input, optional PTT, UUID deduplication
and session/reconnect behavior are preserved; wire v1/left_clutch_v3 are unchanged.

## Geometry and resource ownership

`edit_extrusion.py` owns a transaction by object/Mesh/scene IDs. The original Mesh
is immutable while a temporary copy hosts Edit Mode. All Blender work stays on the
main thread. `from_edit_mesh` supplies the actual wrapped BMesh: its Python wrapper
is held for the transaction lifetime, synchronized through `update_edit_mesh`,
and **never freed by us**. Only independent BMesh copies are freed.

Face indices and BVHs come from that editable mesh, with existing eligibility,
visibility, occlusion, view and external-change checks. Mesh RNA hides custom-data
collections in Edit Mode, so attribute validation snapshots an owned BMesh copy;
all snapshot values are detached before freeing it. Selection flags are excluded
from geometry stamps. UVs, custom attributes and baseline topology are preserved.

Outward topology is constructed once. Dragging updates the same cap from baseline
coordinates. Crossing zero/inward restores baseline topology; later outward motion
reuses a cached topology copy instead of extruding another cap. Commit leaves Edit
Mode with Undo disabled for that temporary transition, restores baseline data, then
adopts the prepared result in the existing undoable main-thread operator. No second
extrusion is built at commit. Pending results and caches are discarded on failure.

Cancellation restores the original data and Object Mode when the original context
is still valid. IDs are re-resolved after deletion/Undo; stale RNA is never reused.
If another object/scene has taken the edit context, baseline geometry is restored
in the owned editable mesh without switching the new active object's mode. The
unused baseline/caches are retired; the restored mesh may remain in Edit Mode until
the user returns to that context. Viewport disappearance alone can still return the
original active target to Object Mode. This conservative context-loss behavior is
intentional. Actual file loading runs the existing pre-load cleanup first.

## Installation and launch

Final ZIP: `/Users/krishpatel/HackRu/dist/air_modeler.zip`.
Version **0.15.0**, matching the companion. Do not install a baseline ZIP.

1. Save current work under a new rehearsal filename (for example
   `/Users/krishpatel/HackRu/rehearsal_0_15.blend`); preserve all older scenes.
2. Stop the companion. In Blender, Disconnect, then disable/remove the old Air
   Modeler add-on. Fully quit Blender.
3. Reopen Blender → Preferences → Add-ons → Install from Disk → select the final
   ZIP. Enable Air Modeler and confirm **0.15.0**.
4. Fully quit/reopen Blender again to clear cached Python modules. Open the new
   rehearsal scene manually, start in Object Mode, enable Global Undo, use Solid
   shading with X-Ray off. Keep one intended connected viewport.
5. In the Terminal shell with the private replacement key, run:

```sh
cd /Users/krishpatel/HackRu && /Users/krishpatel/HackRu/.venv/bin/python -m companion.main --camera 0 --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --two-hands --device 0
```

If needed, first enter the key with hidden zsh input (never paste it in chat,
arguments, a file or a commit):

```zsh
set +x
read -rs 'ELEVENLABS_API_KEY?ElevenLabs API key (hidden): '
export ELEVENLABS_API_KEY
printf '\n'
```

The normal command has **no PTT flag**: CREATE/REMOVE listening is automatic.
Typed commands remain available. `--no-mic` disables audio; `--push-to-talk` is
optional. The hand worker retains `preview=False`. Launch Blender independently
of the key-bearing shell. Connect in N sidebar → Air Modeler from the intended
viewport. Require **Connected/READY**, actual fresh Left/Right observations, and
**VOICE LISTENING — CREATE/REMOVE ONLY** separately; a started process is not proof
of service readiness. After the last command, `quit`/Ctrl+C, check camera off and
prompt returned, then `unset ELEVENLABS_API_KEY`.

The prior companion on port 8765 was stopped cleanly for these automated checks.
The user's Blender session was not updated or introspected; install/restart is
still required. The exposed key's revocation and sponsor attribution remain
unconfirmed. No credentials were printed, stored or committed.

## Verification record

Automated checks use the existing Python environment and isolated factory-startup
Blender **5.2.2 LTS**, installing the ZIP. Generated hand observations, mocked audio,
native TCP/operators and Undo are separate from physical camera/microphone evidence.
**369 Python tests + 78 subtests passed** (`/tmp/air15-python.log`, 4.51 s).
Coverage retains voice allowlisting/committed-only execution, duplicate versus
intentional repeated commands, default microphone startup, PTT/typed compatibility,
voice-failure isolation, transport/session validation, hand arbitration and dwell.

**12 native scripts passed, 118 PASS groups**, all on the installed final runtime:

| Check | PASS groups | Evidence |
| --- | ---: | --- |
| `edit_geometry_check.py` | 1 | Actual Edit Mode/Face Select, immutable original, UV/custom data, signed topology built once/reused, one native Undo and no temporary Undo |
| `edit_context_check.py` | 6 | Editable attribute guards; viewport/mode/scene/active-object changes and deletion; baseline/cache/wrapper cleanup |
| `edit_load_check.py` | 1 | Actual factory file load during an owned edit preview; pre-load controller/socket/timer/draw cleanup |
| `clutch_check.py` | 17 | MOVE/ROTATE/fist SCALE; different Right face from Left hit; selection/dwell/reset/no jump; all six extrusion directions, both release orders, fixed/zero amounts, separate Undo, preview Undo, cancel/loss/reconnect/active-preview shutdown |
| `remove_check.py` | 6 | All tagged shapes, selection rejection, shared meshes, one-step Undo, duplicate/repeated UUIDs and active-operation rejection |
| `bridge_check.py` | 16 | TCP spawn/validation/dedup, native Undo, fresh reconnect/no replay and lifecycle |
| `precision_check.py` | 6 | Typed numeric/plane/axis controls and native Undo |
| `visibility_check.py` | 9 | Projection, occlusion, face eligibility and mapping rejection |
| `signed_extrusion_check.py` | 10 | Signed inward/outward bounds, reversals and mesh validation |
| `extrusion_geometry_check.py` | 27 | Signed world mappings, scaled/rotated objects, manifold topology and custom data |
| `extrusion_check.py` | 13 | Legacy one-hand extrusion, native Undo and cancellation/lifecycle regression |
| `smoke_check.py` | 6 | Final ZIP allowlist/installation/enable lifecycle and primitive topology |

Passing logs: `/tmp/air15-final-<script>.log`. The package smoke fixture was updated
from the old 16-entry list to the new **17 runtime entries**. Final ZIP contents are
byte-identical to runtime source and the unchanged shared protocol/spatial copies;
actual version **0.15.0**. Compile and diff checks pass.
ZIP SHA-256: `61a8711471e8def291d910d13b66ea913c0c6208dc87756f5fc807598aa82991`.

No automated submission blocker remains. The direct scripted-deletion context probe
emits a Blender exit-time unfreed-memory diagnostic, despite passing explicit
mesh/cache/controller ownership assertions. Direct deletion of an Edit Mode object
also reproduces an allocator diagnostic in **stock Blender without the add-on**
(`/tmp/air15-stock-deletion.log`). Normal competing delete shortcuts are blocked
while the controller owns a preview. This is recorded separately from the tests'
passing assertions; it is not evidence of physical or whole-process leak freedom.

Development found two product issues and one harness issue: the wrapped BMesh
Python handle must outlive its vertex/face handles; Mesh-stamp vector values must
be copied before freeing snapshot data; and the test's attribute snapshots must
read BMesh rather than hidden Edit Mode RNA collections. These are fixed and have
native regressions. No production timing thresholds were weakened. Development
snapshot failure evidence: `/tmp/air15-stamp-failure.log`.

Baseline ZIP preserved locally: `dist/air_modeler-baseline-0.14.0.zip`, SHA-256
`6a027f94eb5701368473ab094940adb26979a89cf9eb7b4606cec59d39ea3bf7`.
Historical 0.14 automated evidence remains in [voice handoff](voice_auto_handoff.md).
The original 67-test/78-subtest result and standalone 11-command voice verification
are historical; neither establishes a successful combined live demo for 0.15.
Prepared draft PR text: `/tmp/air-modeler-integration-pr.md`. Known GitHub PR
permission failure is not retried and does not block build/rehearsal.

## Short live sequence — NOT RUN

Perform one action at a time and record the result before advancing:

1. Hands open: say **“create cube”**, wait for one new selected cube.
2. Left pinch holds it; move the open Right palm, then release Left to commit MOVE.
3. Reselect with Left, fresh isolated Right pinch: verify actual Edit Mode / Face
   Select. Hover Right over a different visible eligible face. Wait for cyan →
   orange after two seconds with no jump, then drag a small extrusion.
4. Release either pinch: verify Object Mode and selected object. Open both; the
   second release must create no edit. Use Blender Undo once to restore extrusion.
5. Hands open: say **“remove cube”**; only that selected tagged cube disappears.
   Use Blender Undo once to restore it. Spoken Undo is intentionally ignored.

Then use [physical acceptance](physical_acceptance.md) for rotation/fist scale,
cancellation, brief/sustained loss, reconnect and shutdown. All remain **NOT RUN**
until observed. Report actual failures without inferring a pass from these tests.

To reproduce a native check, use a disposable profile, never the open user scene:

```sh
BLENDER_USER_RESOURCES="$(mktemp -d /tmp/air15-check.XXXXXX)" /Applications/Blender.app/Contents/MacOS/Blender --factory-startup --python-exit-code 1 --window-geometry 0 0 1000 720 --python /Users/krishpatel/HackRu/addon/air_modeler/clutch_check.py
```

Run one native/TCP suite at a time with port 8765 free. Replace the script name for
other foreground checks. Geometry/smoke background checks can replace the window
geometry flags with `--background`. The Python regression suite is
`.venv/bin/python -m pytest -q` from the project folder.
