import json
import os
import sys
from pathlib import Path

from labelme.__main__ import main


def _run_component_smoke(root_value: str) -> None:
    from PIL import Image, ImageDraw
    from labelme import LabelFile
    from labelme import __appname__
    from labelme.app import MainWindow
    from PyQt5 import QtWidgets

    root = Path(root_value).expanduser().resolve()
    image_dir = root / "dataset" / "images" / "raw"
    label_dir = root / "annotations" / "current" / "labelme"
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    image_path = image_dir / "offline_sample.png"
    label_path = label_dir / "offline_sample.json"
    image = Image.new("RGB", (640, 480), (30, 42, 58))
    draw = ImageDraw.Draw(image)
    draw.rectangle((150, 110, 490, 370), fill=(45, 125, 210), outline=(255, 255, 255), width=4)
    image.save(image_path)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([__appname__])
    window = MainWindow(
        config_file=None,
        config_overrides={},
        file_or_dir=str(image_path),
        output_dir=str(label_dir),
    )
    window.show()
    app.processEvents()
    window.close()
    app.processEvents()

    relative_image_path = os.path.relpath(image_path, label_dir)
    shapes = [{
        "label": "smoke_object",
        "points": [[150.0, 110.0], [490.0, 110.0], [490.0, 370.0], [150.0, 370.0]],
        "group_id": None,
        "shape_type": "polygon",
        "flags": {},
    }]
    LabelFile().save(
        str(label_path),
        shapes=shapes,
        image_path=relative_image_path,
        image_height=480,
        image_width=640,
        image_data=None,
    )
    loaded = LabelFile(str(label_path))
    if len(loaded.shapes) != 1 or loaded.shapes[0].get("label") != "smoke_object":
        raise RuntimeError("Managed LabelMe failed to save and reload the smoke annotation.")

    print(json.dumps({
        "status": "pass",
        "image": image_path.as_posix(),
        "label": label_path.as_posix(),
        "shapes": len(loaded.shapes),
    }))


if __name__ == "__main__":
    # An explicit empty mapping keeps defaults and makes the managed component
    # independent from stale or empty machine-level LabelMe configuration.
    if "--component-smoke" in sys.argv:
        smoke_index = sys.argv.index("--component-smoke")
        if smoke_index + 1 >= len(sys.argv):
            raise SystemExit("--component-smoke requires a working directory")
        smoke_root = sys.argv[smoke_index + 1]
        del sys.argv[smoke_index:smoke_index + 2]
        _run_component_smoke(smoke_root)
        raise SystemExit(0)
    if "--config" not in sys.argv:
        sys.argv.extend(["--config", "{}"])
    main()
