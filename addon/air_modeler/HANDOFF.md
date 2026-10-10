# Blender primitive milestone

## Delivered

The Air Modeler sidebar provides Create Cube, Create Sphere, Create Cylinder, and Create Triangular Prism. Each uses the same undoable operator, creates an unparented mesh in the active collection at the scene's 3D cursor, deselects prior view-layer selections, and selects/activates the new object. Blender supplies unique names such as `Air Cube.001`. Object Mode is required and preserved; Edit Mode is never switched silently.

| Identifier | Geometry in Blender units |
| --- | --- |
| `cube` | Side length 2; 8 vertices, 6 faces |
| `sphere` | UV sphere, radius 1; 32 longitudinal / 16 latitude segments; 482 vertices, 512 faces |
| `cylinder` | Radius 1, depth 2 along world Z; 32 sides, two n-gon caps |
| `prism` | Three-sided cylinder, circumradius 1, depth 2 along world Z; 6 vertices, 9 edges, 5 faces (2 triangles and 3 quads) |

Meshes use flat shading, unit scale, and no modifiers. No existing interaction-state infrastructure was present. No competing state manager was added: MOVE reporting will belong to the upcoming shared Blender state/bridge integration. Transport, gestures, speech, transformations, and extrusion are not implemented here.

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
```

Use Blender's **legacy add-on ZIP** route, supported by the installed 5.2.2 installer and the [Blender add-on installation documentation](https://docs.blender.org/manual/en/latest/editors/preferences/addons.html):

1. Open **Edit > Preferences > Add-ons**.
2. Open the top-right drop-down and choose **Install from Disk**.
3. Select `air_modeler.zip` without extracting it, and install.
4. Search for **Air Modeler** and enable its checkbox if not already enabled. Save Preferences if automatic saving is disabled.
5. In the 3D Viewport, enter Object Mode, press **N**, and select the **Air Modeler** sidebar tab.

To disable, clear Air Modeler's checkbox in Preferences > Add-ons. To uninstall, expand its entry and choose **Remove**, then confirm. Disabling/removing the add-on leaves meshes already created in the scene. The validation session did not persistently install or enable the add-on in your user preferences.

## Callable interfaces and undo

```python
from air_modeler.primitives import create_primitive

create_primitive(context: bpy.types.Context, shape: str) -> bpy.types.Object

# Preferred action entry point; True explicitly requests an undo step for Python callers.
bpy.ops.air_modeler.create_primitive("EXEC_DEFAULT", True, shape="cube")
```

The helper accepts only `cube`, `sphere`, `cylinder`, `prism`. It raises `ValueError` for unsupported identifiers and `RuntimeError` for a missing scene/view layer, mismatched scene/view layer, non-Object Mode, noneditable/hidden/unselectable collection context, nonfinite cursor, or off-main-thread execution. Validation precedes mutation; construction failures remove new datablocks and restore selection/active object before propagating the exception.

The helper itself does **not** push undo. The single `air_modeler.create_primitive` operator has `REGISTER` and `UNDO`, delegates to that helper, and returns `{'FINISHED'}` on success. Poll failures disable buttons and supply a readable reason; Python invocation raises a poll `RuntimeError`. The operator reports helper validation/runtime errors and cancels; invalid enum values are rejected by Blender before execution (`TypeError` for Python calls).

The panel only draws controls. There are no nested primitive operators, manual undo pushes, timers, handlers, scene properties, or keymaps. Registration is operator then panel; unregistration reverses that order.

Future command handling must schedule the **operator** on Blender's main thread with a valid window/scene/view-layer context, using `context.temp_override(...)` as appropriate. Use the explicit undo argument shown above for Python dispatch, enable Blender Global Undo, and test timer-driven undo during bridge integration. Do not call the helper directly from a network thread or duplicate mesh construction.

## Validation performed

Run the retained smoke check only in a separate process:

```sh
/Applications/Blender.app/Contents/MacOS/Blender \
  --background --factory-startup --python-exit-code 1 \
  --python /Users/krishpatel/HackRu/addon/air_modeler/smoke_check.py
```

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

Only Object Mode creation is supported. Global Undo must be enabled for undo history. Local View/isolation behavior and timer-driven command dispatch remain unverified. There is no persistent interaction mode/status system yet.

## Integration handoff

Branch: `feature/blender`, based on README baseline `46c25b9` published to `origin/main`. The milestone commit SHA and confirmed push status are reported with the delivery; obtain its full SHA with `git rev-parse feature/blender`.

Changed source/validation/documentation: `addon/air_modeler/{__init__.py,primitives.py,operators.py,panel.py,smoke_check.py,HANDOFF.md}` and `tools/package_addon.py`. Root README and teammates' modules are untouched. The ZIP is a local distribution artifact, excluded from the commit.

Next bounded task: implement the README's local TCP bridge (companion server, Blender client at `127.0.0.1:8765`, versioned newline-delimited JSON) and route validated spawn commands through this existing undoable operator on Blender's main thread.
