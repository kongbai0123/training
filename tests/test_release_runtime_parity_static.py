from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_r1_incremental_build_overrides_pin_binary_compatibility_boundary():
    overrides = (
        ROOT / "updates" / "baselines" / "runtime-r1-build-overrides.txt"
    ).read_text(encoding="utf-8")
    strategy = (ROOT / "docs" / "release_strategy.md").read_text(encoding="utf-8")

    for requirement in (
        "fastapi==0.135.1",
        "pydantic==2.12.5",
        "pydantic-core==2.41.5",
        "starlette==0.52.1",
        "ultralytics==8.4.22",
        "uvicorn==0.42.0",
    ):
        assert requirement in overrides
    assert "--force-reinstall --no-deps" in strategy
    assert "build_update_package.py" in strategy
    assert "new runtime baseline" in strategy
