from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import threading
from typing import Iterator


_LOCK = threading.RLock()
_ROOT_COUNTS: dict[Path, int] = {}
_ORIGINAL_SAVEFIG = None


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _savefig_with_vector_copy(figure, filename, *args, **kwargs):
    original = _ORIGINAL_SAVEFIG
    if original is None:
        raise RuntimeError("Vector plot capture is not initialized")
    result = original(figure, filename, *args, **kwargs)
    try:
        output_path = Path(filename).expanduser().resolve()
    except (TypeError, ValueError, OSError):
        return result
    if output_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        return result
    with _LOCK:
        roots = tuple(_ROOT_COUNTS)
    if not any(_is_inside(output_path, root) for root in roots):
        return result

    vector_kwargs = dict(kwargs)
    for key in ("dpi", "pil_kwargs", "quality", "optimize", "progressive"):
        vector_kwargs.pop(key, None)
    vector_kwargs["format"] = "svg"
    try:
        original(figure, output_path.with_suffix(".svg"), *args, **vector_kwargs)
    except Exception as exc:
        print(f"[VectorPlotCapture] SVG export failed for {output_path.name}: {exc}")
    return result


@contextmanager
def capture_vector_plots(output_root: Path) -> Iterator[None]:
    """Save a true SVG sibling whenever Matplotlib writes a raster plot under output_root."""
    global _ORIGINAL_SAVEFIG
    root = Path(output_root).expanduser().resolve()
    with _LOCK:
        from matplotlib.figure import Figure

        if _ORIGINAL_SAVEFIG is None:
            _ORIGINAL_SAVEFIG = Figure.savefig
            Figure.savefig = _savefig_with_vector_copy
        _ROOT_COUNTS[root] = _ROOT_COUNTS.get(root, 0) + 1
    try:
        yield
    finally:
        with _LOCK:
            count = _ROOT_COUNTS.get(root, 0) - 1
            if count > 0:
                _ROOT_COUNTS[root] = count
            else:
                _ROOT_COUNTS.pop(root, None)
            if not _ROOT_COUNTS and _ORIGINAL_SAVEFIG is not None:
                from matplotlib.figure import Figure

                Figure.savefig = _ORIGINAL_SAVEFIG
                _ORIGINAL_SAVEFIG = None
