"""data/kitei の規程が書式の決まりに合っているかを確かめる。

実行（リポジトリ直下で）：
    uv run python -m scripts.validate_kitei

すべて問題なければ終了コード0、1件でも問題があれば1を返す（CIでも使える）。
"""

import sys
from pathlib import Path

from app.ingest.kitei_parser import (
    DEFAULT_KITEI_DIR,
    KiteiFormatError,
    find_style_issues,
    parse_kitei,
)


def validate_dir(directory: Path) -> tuple[int, int, list[str]]:
    """(規程の本数, チャンク数, エラーの一覧) を返す。"""
    errors: list[str] = []
    n_docs = 0
    n_chunks = 0
    seen_doc_ids: dict[str, str] = {}

    for path in sorted(directory.glob("kitei-*.md")):
        text = path.read_text(encoding="utf-8")
        file_errors: list[str] = []
        try:
            # 構造のエラーがあっても、表記の問題はまとめて報告する
            file_errors.extend(find_style_issues(text))
            doc = parse_kitei(text)
        except KiteiFormatError as e:
            errors.extend(f"{path.name}: {msg}" for msg in [*file_errors, str(e)])
            continue

        doc_id = doc.front_matter.doc_id
        if doc_id in seen_doc_ids:
            file_errors.append(f"doc_id {doc_id} が {seen_doc_ids[doc_id]} と重複")
        seen_doc_ids[doc_id] = path.name
        if not path.name.startswith(f"{doc_id}_"):
            file_errors.append(f"ファイル名が doc_id（{doc_id}）で始まっていません")

        n_docs += 1
        n_chunks += len(doc.chunks)
        if file_errors:
            errors.extend(f"{path.name}: {msg}" for msg in file_errors)
            continue
        n_articles = sum(1 for c in doc.chunks if c.article_no is not None)
        print(f"  OK  {path.name}: {doc.front_matter.title}（{n_articles}条＋附則）")

    return n_docs, n_chunks, errors


def main() -> int:
    n_docs, n_chunks, errors = validate_dir(DEFAULT_KITEI_DIR)
    for error in errors:
        print(f"  NG  {error}")
    print(f"{n_docs}本・{n_chunks}チャンク・エラー{len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
