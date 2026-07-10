from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WARNING_FILE = ROOT / "build" / "vision_training_studio" / "warn-vision_training_studio.txt"

BLOCKER_PATTERNS = [
    r"missing module named ['\"]?src(\.|['\"]|\s)",
    r"missing module named ['\"]?launcher(['\"]|\s)",
    r"missing module named ['\"]?app(['\"]|\s)",
    r"missing module named ['\"]?fastapi(['\"]|\s)",
    r"missing module named ['\"]?starlette(['\"]|\s)",
    r"missing module named ['\"]?uvicorn(['\"]|\s)",
    r"missing module named ['\"]?torch(['\"]|\s)",
    r"missing module named ['\"]?torchvision(['\"]|\s)",
    r"missing module named ['\"]?ultralytics(['\"]|\s)",
]

WATCH_PATTERNS = [
    r"pycparser\.(lex|yac)tab",
    r"scipy\.special\._cdflib",
    r"missing module named sip",
    r"torch\.utils\.tensorboard",
]

EXPECTED_PATTERNS = [
    r"\((?:[^)]*,\s*)?(optional|conditional|delayed)(?:,\s*[^)]*)?\)",
    r"missing module named (pwd|grp|fcntl|termios|resource|posix|_posix|_scproxy)\b",
    r"missing module named ['\"]?(org\.python|java|vms_lib|_winreg)",
    r"missing module named ['\"]?.*\.tests?['\"]?",
    r"missing module named ['\"]?(pytest|_pytest|mypy|toml|tomli|email_validator|fastapi_cli|orjson|ujson)\b",
    r"missing module named ['\"]?(trio|curio|wsproto|gunicorn|werkzeug|python_socks|a2wsgi|uvloop|h2|OpenSSL|watchfiles)(\.|['\"]|\s)",
    r"missing module named ['\"]?(android|jnius|objc|WebKit|Foundation|AppKit|qtpy|cefpython3|PyObjCTools|System|Microsoft|WebBrowserInterop|gi\.repository)\b",
    r"missing module named ['\"]?(System\.|Microsoft\.Web)\b",
    r"missing module named ['\"]?(wandb|ray|neptune|mlflow|dvclive|comet_ml|clearml|roboflow|streamlit|flask)\b",
    r"missing module named ['\"]?(pyspark|dask|xgboost\.spark|xgboost\.dask)\b",
    r"missing module named ['\"]?(tensorrt|openvino|tensorflowjs|onnx2tf|rknn|ncnn|MNN|paddle|executorch|coremltools)\b",
    r"missing module named ['\"]?(awscrt\.|rsa|requests\.packages\.urllib3)\b",
    r"missing module named ['\"]?(Cheetah|mako|aiohttp_wsgi|bjoern|diesel|twisted|fapws|meinheld|paste|waitress|cheroot|cherrypy|flup|eventlet)\b",
    r"missing module named (urllib\.|urlparse|StringIO|ConfigParser|cPickle|Cookie|httplib|collections\.)",
    r"missing module named ['\"]?multiprocessing\.",
    r"missing module named ['\"]?(pkg_resources|setuptools)\.extern\.",
    r"missing module named ['\"]?(railroad|_curses|macholib|macholib\.|win32ctypes\.core\.|code_generators|code_generators\.numpy_api|olefile)\b",
    r"missing module named ['\"]?(scipy\.special\.|scipy\.linalg\.|scipy\.sparse\.|scipy\._lib\.array_api_compat)",
    r"missing module named ['\"]?(torch\.|cupy|pyodide|html5lib|six\.moves|dateutil\.tz\.tzfile|pyglet|optree|onnx|onnx_model|onnx_ir|onnxscript|fusion_utils|ml_dtypes|py3nvml|cpuinfo)\b",
    r"missing module named ['\"]?(pydantic\.PydanticUserError|pygments\.lexers\.PrologLexer|itsdangerous|itsdangerous\.exc|outcome)\b",
    r"missing module named ['\"]?(smbprotocol|smbclient|paramiko|libarchive|pygit2|distributed|panel|fuse|pytorch_lightning)\b",
    r"excluded module named ",
    r"libgomp\.so\.1",
]


def matches_any(line: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in patterns)


def classify_lines(lines: list[str]) -> dict[str, list[str]]:
    result = {"blocker": [], "watch": [], "expected": [], "unclassified": []}
    for line in lines:
        if "missing module named" not in line and "excluded module named" not in line and "Hidden import" not in line and "Ignoring " not in line:
            continue
        if matches_any(line, BLOCKER_PATTERNS):
            result["blocker"].append(line)
        elif matches_any(line, WATCH_PATTERNS):
            result["watch"].append(line)
        elif matches_any(line, EXPECTED_PATTERNS):
            result["expected"].append(line)
        else:
            result["unclassified"].append(line)
    return result


def main() -> int:
    warning_file = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_WARNING_FILE
    if not warning_file.exists():
        print(f"[ERROR] PyInstaller warning file not found: {warning_file}")
        return 1

    lines = warning_file.read_text(encoding="utf-8", errors="replace").splitlines()
    classified = classify_lines(lines)

    print(f"PyInstaller warning audit: {warning_file}")
    for key in ["blocker", "watch", "expected", "unclassified"]:
        print(f"{key}: {len(classified[key])}")

    for key in ["blocker", "unclassified", "watch"]:
        if classified[key]:
            print(f"\n[{key}]")
            for line in classified[key][:40]:
                print(f"- {line}")
            if len(classified[key]) > 40:
                print(f"- ... {len(classified[key]) - 40} more")

    if classified["blocker"] or classified["unclassified"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
