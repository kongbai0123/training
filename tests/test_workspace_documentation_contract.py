import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_uses_data_first_public_workspace_names():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "整合影像訓練、序列訓練、表格資料預測" in readme
    assert "| 階段 | 影像訓練 | 序列訓練 | 表格資料預測 |" in readme
    assert "XGBoost 是目前可選模型" not in readme or "表格資料預測" in readme
    assert "### Tabular 表格工作流程" not in readme


def test_workspace_document_links_resolve_locally():
    files = [
        ROOT / "README.md",
        ROOT / "docs" / "USER_GUIDE.md",
        ROOT / "docs" / "MODEL_SUPPORT.md",
        ROOT / "docs" / "ARCHITECTURE.md",
        ROOT / "docs" / "WORKSPACE_INFORMATION_ARCHITECTURE.md",
        ROOT / "docs" / "WORKSPACE_COMPATIBILITY.md",
    ]
    link_pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
    missing = []
    for source in files:
        for target in link_pattern.findall(source.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#")):
                continue
            path_text = target.split("#", 1)[0]
            resolved = (source.parent / path_text).resolve()
            if not resolved.exists():
                missing.append(f"{source.relative_to(ROOT)} -> {target}")
    assert not missing, "Missing local documentation links:\n" + "\n".join(missing)


def test_current_overview_screenshot_exists_and_is_not_placeholder_sized():
    screenshot = ROOT / "docs" / "assets" / "app-overview.png"

    assert screenshot.exists()
    assert screenshot.stat().st_size > 50_000
