"""Build the legacy add-on ZIP with an explicit runtime-only allowlist (no bpy)."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = ("__init__.py", "primitives.py", "operators.py", "panel.py", "bridge.py", "viewport.py", "transforms.py", "extrusion.py", "selection.py", "intent.py", "planes.py")


def main():
    source = ROOT / "addon" / "air_modeler"
    contents = {name: (source / name).read_bytes() for name in RUNTIME_FILES}
    contents["_protocol.py"] = (ROOT / "shared" / "protocol.py").read_bytes()
    contents["spatial.py"] = (ROOT / "shared" / "spatial.py").read_bytes()
    destination = ROOT / "dist" / "air_modeler.zip"
    destination.parent.mkdir(exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            archive.writestr(f"air_modeler/{name}", data)
    print(destination)


if __name__ == "__main__":
    main()
