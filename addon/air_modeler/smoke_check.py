"""Run only in a disposable --background --factory-startup Blender process.

Installs the packaged ZIP into temporary script storage, not user preferences.
"""

from pathlib import Path
import tempfile
from types import SimpleNamespace
from zipfile import ZipFile

import addon_utils
import bmesh
import bpy


def snapshot():
    return (
        set(bpy.data.objects.keys()), set(bpy.data.meshes.keys()),
        {obj.name for obj in bpy.context.selected_objects},
        getattr(bpy.context.view_layer.objects.active, "name", None),
    )


def rejects(call, error):
    before = snapshot()
    try:
        call()
    except error:
        pass
    else:
        raise AssertionError(f"Expected {error.__name__}")
    assert snapshot() == before, "Rejected call changed scene or selection"


def main():
    assert bpy.app.background, "Run in a separate background process, not your current scene"
    root = Path(__file__).resolve().parents[2]
    archive_path = root / "dist" / "air_modeler.zip"
    with tempfile.TemporaryDirectory(prefix="air-modeler-smoke-") as directory:
        with ZipFile(archive_path) as archive:
            assert set(archive.namelist()) == {
                f"air_modeler/{name}" for name in
                ("__init__.py", "primitives.py", "operators.py", "panel.py", "bridge.py", "_protocol.py")
            }
        # Use Blender's actual legacy installer, isolated from the user's add-ons.
        entry = bpy.context.preferences.filepaths.script_directories.new()
        entry.name = "Air Modeler Smoke"
        entry.directory = directory
        result = bpy.ops.preferences.addon_install(
            filepath=str(archive_path), target=entry.name, overwrite=False,
        )
        assert result == {"FINISHED"}
        bpy.utils.refresh_script_paths()
        addon_utils.modules_refresh()
        module = addon_utils.enable("air_modeler", default_set=False)
        assert module is not None
        assert Path(module.__file__).resolve().is_relative_to(Path(directory).resolve())
        addon_utils.disable("air_modeler", default_set=False)
        assert not hasattr(bpy.types, "AIRMODELER_PT_primitives")
        assert addon_utils.enable("air_modeler", default_set=False) is not None
        from air_modeler.primitives import create_primitive

        # An empty scene's root can report is_visible=False even with no restrictions.
        bpy.context.window.scene = bpy.data.scenes.new("Air Modeler Empty Scene Check")
        cursor = (2.5, -3.0, 4.25)
        bpy.context.scene.cursor.location = cursor
        names = []
        for shape in ("cube", "sphere", "cylinder", "prism", "cube"):
            before_count = len(bpy.data.objects)
            result = bpy.ops.air_modeler.create_primitive("EXEC_DEFAULT", shape=shape)
            assert result == {"FINISHED"}
            assert len(bpy.data.objects) == before_count + 1
            obj = bpy.context.view_layer.objects.active
            assert obj.type == "MESH"
            assert tuple(obj.location) == cursor
            assert bpy.context.selected_objects == [obj]
            assert bpy.context.mode == "OBJECT"
            assert obj.name not in names
            names.append(obj.name)
            mesh = bmesh.new()
            mesh.from_mesh(obj.data)
            assert all(edge.is_manifold for edge in mesh.edges)
            assert mesh.calc_volume(signed=True) > 0
            mesh.free()
            if shape == "prism":
                assert len(obj.data.vertices) == 6
                assert len(obj.data.edges) == 9
                assert len(obj.data.polygons) == 5
                assert sorted(len(face.vertices) for face in obj.data.polygons) == [3, 3, 4, 4, 4]
            print(f"PASS {shape}: {obj.name}, vertices={len(obj.data.vertices)}, faces={len(obj.data.polygons)}")

        rejects(lambda: create_primitive(bpy.context, "unsupported"), ValueError)
        rejects(lambda: bpy.ops.air_modeler.create_primitive(shape="unsupported"), TypeError)
        rejects(lambda: create_primitive(SimpleNamespace(scene=None, view_layer=None), "cube"), RuntimeError)
        with bpy.context.temp_override(scene=None, view_layer=None):
            assert not bpy.ops.air_modeler.create_primitive.poll()

        bpy.ops.object.mode_set(mode="EDIT")
        rejects(lambda: create_primitive(bpy.context, "cube"), RuntimeError)
        rejects(lambda: bpy.ops.air_modeler.create_primitive(shape="cube"), RuntimeError)
        assert bpy.context.mode == "EDIT_MESH"
        bpy.ops.object.mode_set(mode="OBJECT")

        collection = bpy.data.collections.new("Smoke unselectable")
        bpy.context.scene.collection.children.link(collection)
        bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[collection.name]
        collection.hide_select = True
        rejects(lambda: create_primitive(bpy.context, "cube"), RuntimeError)
        rejects(lambda: bpy.ops.air_modeler.create_primitive(shape="cube"), RuntimeError)
        bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection

        addon_utils.disable("air_modeler", default_set=False)
        assert not hasattr(bpy.types, "AIRMODELER_PT_primitives")
        bpy.context.preferences.filepaths.script_directories.remove(entry)
        print(f"PASS installed-ZIP lifecycle, selection, naming, topology and rejection checks on Blender {bpy.app.version_string}")
        print("UI panel/button and undo-history checks remain separate; not proven by background execution.")


if __name__ == "__main__":
    main()
