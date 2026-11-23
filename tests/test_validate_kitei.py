from pathlib import Path

from app.ingest.kitei_parser import DEFAULT_KITEI_DIR
from scripts.validate_kitei import validate_dir


def test_real_data_has_no_errors() -> None:
    n_docs, n_chunks, errors = validate_dir(DEFAULT_KITEI_DIR)
    assert (n_docs, n_chunks, errors) == (7, 95, [])


def test_reports_structure_and_style_errors_together(tmp_path: Path) -> None:
    # 実データをコピーして壊す（data/ は書き換えない）
    src = (DEFAULT_KITEI_DIR / "kitei-003_weekly-report.md").read_text(encoding="utf-8")
    broken = src.replace("### 第3条", "### 第4条").replace("3営業日", "３営業日")
    broken = broken.replace("午後6時00分まで", "午後６時00分まで", 1)
    (tmp_path / "kitei-003_weekly-report.md").write_text(broken, encoding="utf-8")

    n_docs, _, errors = validate_dir(tmp_path)

    assert n_docs == 0
    assert any("全角の数字" in e for e in errors)
    assert any("条番号が連番ではありません" in e for e in errors)


def test_file_name_must_start_with_doc_id(tmp_path: Path) -> None:
    src = (DEFAULT_KITEI_DIR / "kitei-003_weekly-report.md").read_text(encoding="utf-8")
    (tmp_path / "kitei-099_weekly-report.md").write_text(src, encoding="utf-8")

    _, _, errors = validate_dir(tmp_path)

    assert errors == [
        "kitei-099_weekly-report.md: ファイル名が doc_id（kitei-003）で始まっていません"
    ]
