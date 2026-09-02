from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_xgboost_baseline_note_is_visible_only_for_tree_models():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "pages" / "training_modes.js").read_text(encoding="utf-8")

    assert 'id="rnn-xgboost-baseline-note"' in html
    assert 'qs("#rnn-xgboost-baseline-note")?.classList.toggle("hidden", !isTreeModel)' in script


def test_xgboost_baseline_copy_explains_flattening_and_leakage_boundaries():
    zh = (ROOT / "static" / "state" / "i18n" / "zh-TW.js").read_text(encoding="utf-8")
    en = (ROOT / "static" / "state" / "i18n" / "en.js").read_text(encoding="utf-8")

    for catalog in (zh, en):
        assert "rnn.training.xgboostBaselineTitle" in catalog
        assert "rnn.training.xgboostBaselineHelp" in catalog
        assert "sequence_id" in catalog
        assert "split" in catalog
