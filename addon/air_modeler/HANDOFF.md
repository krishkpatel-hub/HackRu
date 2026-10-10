> Current 0.7.0 controls, launch and verification: [clutch handoff](../../docs/clutch_handoff.md). Historical milestones follow.

> Current 0.6.0 integration: [two-hand selection and precision handoff](../../docs/enhancement_handoff.md). The dated results below are historical evidence, not a combined 0.6.0 live pass.

# Current milestone: single-face EXTRUDE (0.5.0)

See [Extrusion handoff](../../docs/extrusion_handoff.md) for supported faces, resource/Undo ownership, installation, checks and live rehearsal. Prior milestone records below are historical.

# Current milestone: ROTATE and SCALE (0.4.0)

See [Transform handoff](../../docs/transform_handoff.md) for the current mappings, package/update steps, interfaces and validation. Prior milestone records below are historical.

# Current milestone: MOVE (0.3.0)

See [P’s MOVE integration handoff](../../docs/move_handoff.md) for the current package, environment, camera permission blocker, launch steps, callback/config, checks and limitations. The primitive/bridge record below is retained as historical evidence for 0.1/0.2; its unsupported-feature statements and version-specific instructions are superseded by that handoff.

# Blender primitive and local bridge milestones

## Delivered

The Air Modeler sidebar provides Create Cube, Create Sphere, Create Cylinder, and Create Triangular Prism. Each uses the same undoable operator, creates an unparented mesh in the active collection at the scene's 3D cursor, deselects prior view-layer selections, and selects/activates the new object. Blender supplies unique names such as `Air Cube.001`. Object Mode is required and preserved; Edit Mode is never switched silently.

| Identifier | Geometry in Blender units |
| --- | --- |
| `cube` | Side length 2; 8 vertices, 6 faces |
| `sphere` | UV sphere, radius 1; 32 longitudinal / 16 latitude segments; 482 vertices, 512 faces |
| `cylinder` | Radius 1, depth 2 along world Z; 32 sides, two n-gon caps |
| `prism` | Three-sided cylinder, circumradius 1, depth 2 along world Z; 6 vertices, 9 edges, 5 faces (2 triangles and 3 quads) |

Meshes use flat shading, unit scale, and no modifiers. The sidebar now also has Connect, Disconnect, connection state, and latest status/error. The device-free companion is a local TCP server; Blender is its client. Accepted external spawn commands use the existing undoable primitive operator. Status reports the reserved default MOVE/IDLE state; movement, picking, gestures, speech, rotation/scaling, and extrusion are not implemented.

## Package and install

Verified executable: `/Applications/Blender.app/Contents/MacOS/Blender`.
Verified version: **Blender 5.2.2 LTS**, build `d13f752e3b9c`; bundled Python **3.13.13**. Metadata targets Blender 5.2 or later; other versions/platforms are unverified. No external runtime dependencies are required.

From the repository root:

```sh
python3 tools/package_addon.py
```

Or from any working directory:

```sh
python3 /Users/krishpatel/HackRu/tools/package_addon.py
```

Output: `/Users/krishpatel/HackRu/dist/air_modeler.zip` (generated, not committed). The helper uses Python's standard library and never imports `bpy`. Its explicit allowlist includes exactly:

```text
air_modeler/__init__.py
air_modeler/primitives.py
air_modeler/operators.py
air_modeler/panel.py
air_modeler/bridge.py
air_modeler/_protocol.py
```

Use Blender's **legacy add-on ZIP** route, supported by the installed 5.2.2 installer and the [Blender add-on installation documentation](https://docs.blender.org/manual/en/latest/editors/preferences/addons.html):

1. Open **Edit > Preferences > Add-ons**.
2. Open the top-right drop-down and choose **Install from Disk**.
3. Select `air_modeler.zip` without extracting it, and install.
4. Search for **Air Modeler** and enable its checkbox if not already enabled. Save Preferences if automatic saving is disabled.
5. In the 3D Viewport, enter Object Mode, press **N**, and select the **Air Modeler** sidebar tab.

To disable, clear Air Modeler's checkbox in Preferences > Add-ons. To uninstall, expand its entry and choose **Remove**, then confirm. Disable removes the connection, timer, and load handler; existing meshes remain. Validation installs into isolated user-resource directories and does not update your live installed add-on.

### Update the previously installed version

1. Save any user work you want to keep. In the old Air Modeler add-on, disconnect if available, then disable and remove it from Preferences > Add-ons.
2. **Quit and restart Blender before installing the new ZIP.** This clears cached modules and the distribution-ZIP import path left by the earlier console test. Do not import the ZIP in the live console or add it to `sys.path`.
3. Install the rebuilt ZIP through **Install from Disk** and enable **Air Modeler**. The expanded add-on information should show version **0.2.0**; the panel should include Connect and Disconnect.
4. In a terminal, run `cd /Users/krishpatel/HackRu` and `python3 -m companion.main`.
5. In the intended 3D Viewport/scene, open **N > Air Modeler**, click **Connect**, and wait for **Connected** / companion `READY`.
6. In the companion terminal, enter `spawn cube`, `spawn sphere`, `spawn cylinder`, or `spawn prism`. `status` prints the last received Blender state. Disconnect in Blender or enter `quit` in the companion to stop.

The packager copies `shared/protocol.py` unchanged into the ZIP as `_protocol.py`; there is no separately edited add-on validator. See `docs/protocol.md` for schemas, limits, callback behavior, and reconnect rules.

## Callable interfaces and undo

```python
from air_modeler.primitives import create_primitive

create_primitive(context: bpy.types.Context, shape: str) -> bpy.types.Object

# Preferred action entry point; True explicitly requests an undo step for Python callers.
bpy.ops.air_modeler.create_primitive("EXEC_DEFAULT", True, shape="cube")
```

The helper accepts only `cube`, `sphere`, `cylinder`, `prism`. It raises `ValueError` for unsupported identifiers and `RuntimeError` for a missing scene/view layer, mismatched scene/view layer, non-Object Mode, noneditable/hidden/unselectable collection context, nonfinite cursor, or off-main-thread execution. Validation precedes mutation; construction failures remove new datablocks and restore selection/active object before propagating the exception.

The helper itself does **not** push undo. The single `air_modeler.create_primitive` operator has `REGISTER` and `UNDO`, delegates to that helper, and returns `{'FINISHED'}` on success. Poll failures disable buttons and supply a readable reason; Python invocation raises a poll `RuntimeError`. The operator reports helper validation/runtime errors and cancels; invalid enum values are rejected by Blender before execution (`TypeError` for Python calls).

The panel only draws controls. There are no nested primitive operators or manual undo pushes. Registration orders the primitive operator, connection operators, and panel; unregistration reverses that order after closing the runtime. One modal event timer is owned by the connection; a persistent `load_pre` handler closes it on file load. No scene properties or keymaps are added.

The modal bridge invokes the **operator** on Blender's main thread with a captured, revalidated viewport/scene/view-layer context via `context.temp_override(...)`, using the explicit undo argument above. Enable Blender Global Undo. Timer-driven network spawning and separate Undo steps have now passed in a disposable foreground process. The indefinitely running controller has no UNDO flag; each spawn owns its own undo action. The geometry helper is unchanged from the primitive milestone.

Additional operator interfaces: `bpy.ops.air_modeler.connect()` from a VIEW_3D context, and `bpy.ops.air_modeler.disconnect()`. H/V use `BridgeServer.emit(event) -> bool` from `companion.transport.server`; `True` means queued, not execution acknowledged. For example:

```python
emit({"type": "command", "payload": {
    "id": "875905d1-9dad-46bd-9ef6-439da23920ef",
    "action": "spawn", "shape": "cube",
}})
```

The callback is thread-safe, does not wait for socket I/O or queue capacity, and never needs camera/audio modules. H/V continue supplying only type/payload and their own IDs; P's writer adds the session envelope.

## Validation performed

Run the retained smoke check only in a separate process:

```sh
/Applications/Blender.app/Contents/MacOS/Blender \
  --background --factory-startup --python-exit-code 1 \
  --python /Users/krishpatel/HackRu/addon/air_modeler/smoke_check.py
```

For the current bridge package, prefix Blender checks with a fresh `BLENDER_USER_RESOURCES` directory as shown below so a previously installed add-on cannot shadow the test package. Run each check in a **separate process**; do not combine the two Python scripts in one Blender invocation because the first removes its temporary installed files while Python retains imports.

Passed on Blender 5.2.2 LTS:

- Exact ZIP contents; Blender's actual legacy installer targeting a temporary script directory; imports from the installed package without the repository on `sys.path`.
- Enable, disable, enable, then disable through `addon_utils`; class removal verified.
- All four shapes through the actual operator, including an initially empty scene/root collection and cursor `(2.5, -3.0, 4.25)`.
- Correct mesh types, selection/active object, Object Mode, repeated unique names, closed manifold geometry, and positive volume; exact prism topology/caps.
- Unsupported helper/operator shapes, missing context, actual missing-scene operator poll, Edit Mode, and unselectable collection reject without partial creation or selection changes.

Live UI checks used the packaged Python modules in a disposable scene:

- Visually inspected the Air Modeler panel and all four button labels.
- Invoked the shared operator for cube, sphere, cylinder, prism from Blender's console with explicit undo enabled.
- Used macOS **Command-Z** in the viewport: one step removed only the prism, the next only the cylinder, and two further steps removed the sphere and cube. The disposable scene was then empty.
- Unregister/register in the live session removed/restored the panel class without duplicates.
- Removed the disposable scene, unregistered the temporary add-on, and restored the original scene; no `.blend` files or preferences were saved.

The first sandboxed Blender startup crashed; running the installed executable with sandbox permission succeeded. An early test exposed unsafe missing-scene access and another exposed `is_visible=False` on an unrestricted empty root collection; both are fixed and covered by the final passing smoke run.

## Remaining manual checks and limitations

Mouse automation returned `noWindowsAvailable` even while screenshots/keyboard control worked. **Direct sidebar button clicks, Preferences checkbox toggling, and uninstall via Preferences have not been performed.** Background checks do not prove these UI actions. After installation, in a disposable scene:

1. Click each of the four buttons; verify the named mesh appears at a nonzero cursor location and is the sole selected/active object.
2. Undo four times; confirm one creation disappears per step. Repeat creation of one shape and check the `.001` name.
3. Enter Edit Mode: buttons must be disabled with the Object Mode explanation and no edits. Return to Object Mode.
4. Disable/re-enable through Preferences, confirm exactly one panel returns, and create again. Remove the add-on if desired and verify its panel disappears while existing meshes remain.

Only Object Mode creation is supported. Global Undo must be enabled for undo history. Local View/isolation behavior remains unverified. Runtime status exists, but interaction tools beyond spawn remain unimplemented.

## Integration handoff

Branch: `feature/blender`, based on README baseline `46c25b9` published to `origin/main`. The milestone commit SHA and confirmed push status are reported with the delivery; obtain its full SHA with `git rev-parse feature/blender`.

The primitive milestone changed `addon/air_modeler/{__init__.py,primitives.py,operators.py,panel.py,smoke_check.py,HANDOFF.md}` and `tools/package_addon.py`. Root README and teammates' modules remain untouched. The ZIP is a local distribution artifact, excluded from commits.

## Bridge validation and current handoff

The baseline commit `954bb19` is retained on `feature/blender`. The next commit adds the standard-library protocol/server/runner, modal bridge, package inclusion, protocol documentation, and focused checks. No teammate modules or root README changes are needed. `demo.blend` is unrelated pre-existing work and remains untracked; generated ZIPs and Python caches are excluded from commits.

Changed files in this bridge milestone:

- `.gitignore`, `shared/protocol.py`, `docs/protocol.md`.
- `companion/main.py`, `companion/transport/server.py`.
- `addon/air_modeler/__init__.py`, `bridge.py`, `bridge_check.py`, `panel.py`, `smoke_check.py`, `HANDOFF.md`.
- `tests/test_protocol.py`, `tests/test_transport.py`, `tests/bridge_driver.py`.
- `tools/package_addon.py`.

Commands used from the repository root (system Python verified as **3.14.7**):

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tools/package_addon.py

BLENDER_USER_RESOURCES="$(mktemp -d /tmp/air-modeler-regression.XXXXXX)" \
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python-exit-code 1 --python addon/air_modeler/smoke_check.py

BLENDER_USER_RESOURCES="$(mktemp -d /tmp/air-modeler-modal.XXXXXX)" \
  /Applications/Blender.app/Contents/MacOS/Blender --factory-startup \
  --python-exit-code 1 --python addon/air_modeler/bridge_check.py
```

Do not run the modal bridge check with `--background`: Blender 5.2's redo HUD crashed under a headless viewport context. The foreground check opens its **own disposable Blender process**, installs the ZIP through Blender's installer in isolated user resources, launches `tests/bridge_driver.py` as an external companion process, runs real timer events, and exits. It does not import the ZIP into your live console or load/overwrite `demo.blend`. The temporary resource directories can be removed after testing.

Verified for the bridge milestone:

- Eleven standard-library protocol/loopback tests pass: split/combined lines, malformed and oversized recovery, shape/version/session validation, partial writes/backpressure bounds, deduplication, fresh sessions, callback ordering/coalescing/concurrency/overflow, rejection of in-flight callbacks crossing reconnect, disconnect cleanup, single-client behavior, and startup through `python3 -m companion.main` without device dependencies.
- Background Blender primitive/package checks still pass, including enable/disable/enable and all original geometry/selection/rejection checks.
- Automated **foreground Blender** check passes with the real modal timer and external process: hello handshake, each shape, duplicate-ID suppression, malformed JSON plus invalid version/session/shape followed by valid input, readable Edit Mode rejection, explicit reconnect with a fresh session and no replay, two separate network-spawn Undo steps, repeated disable/enable with timer/socket/handler cleanup, file-load cleanup handler, lost viewport context, unsupported-action reporting, server shutdown, and absent-server failure.
- Packaged `_protocol.py` matches `shared/protocol.py` byte for byte; installation/import uses isolated extracted add-on files.

The foreground check is automated API/event-loop validation, **not a manual click-through or visual inspection of the new connection controls**. Remaining manual checks: update via Preferences and restart as above; click Connect/Disconnect; type all four commands in the companion; Undo each spawn; disconnect/reconnect while changing editors; actually load another disposable `.blend` and confirm it disconnects. The load handler was exercised directly, not through an actual file-open operation. The previous primitive panel was visually inspected and the user confirmed creation Undo; those observations do not stand in for these new checks.

Known limits: one client on the fixed localhost port; explicit reconnect only; no command acknowledgements/retries; at most 4096 distinct command IDs per session; changing the captured viewport/scene/view layer disconnects; only spawn acts on the scene. Unsupported mode/cancel/undo commands and hand events produce status errors. No camera/audio access, models, credentials, or live device integration are required.

Next bounded milestone: synthetic cursor, object picking, and default pinch-and-drag movement.
