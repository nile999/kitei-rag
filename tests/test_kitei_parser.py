from datetime import date

import pytest

from app.ingest.kitei_parser import (
    KiteiDocument,
    KiteiFormatError,
    find_style_issues,
    load_kitei_dir,
    parse_kitei,
)

FRONT_MATTER = """---
doc_id: kitei-999
title: テスト規程
version: "1.0"
effective_date: 2026-04-01
allowed_roles: [full_time, contract]
---
"""

BODY = """
# 株式会社サンプルテック テスト規程

## 第1章 総則

### 第1条（目的）

1. 本規程は、テストのために定める。

## 第2章 手続

### 第2条（申請）
<!-- allowed_roles: [manager, hr] -->

1. 申請は、3営業日前までに行う。
2. 承認は、所属長が行う。

## 附則

1. 本規程は、2026年4月1日から施行する。
"""


def make(body: str = BODY, front_matter: str = FRONT_MATTER) -> str:
    return front_matter + body


@pytest.fixture
def doc() -> KiteiDocument:
    return parse_kitei(make())


# ---- 正しい書式を読めること ----


def test_reads_front_matter(doc: KiteiDocument) -> None:
    fm = doc.front_matter
    assert fm.doc_id == "kitei-999"
    assert fm.version == "1.0"
    assert fm.effective_date == date(2026, 4, 1)


def test_one_chunk_per_article_plus_supplementary(doc: KiteiDocument) -> None:
    # 2条＋附則＝3チャンク（D-003、D-005）
    assert [c.chunk_id for c in doc.chunks] == [
        "kitei-999#art1",
        "kitei-999#art2",
        "kitei-999#suppl",
    ]


def test_chunk_keeps_chapter_and_body(doc: KiteiDocument) -> None:
    art2 = doc.chunks[1]
    assert art2.chapter == "第2章 手続"
    assert art2.article_no == 2
    assert art2.article_title == "申請"
    assert art2.body == "1. 申請は、3営業日前までに行う。\n2. 承認は、所属長が行う。"


def test_text_has_doc_title_and_chapter_prefix(doc: KiteiDocument) -> None:
    assert doc.chunks[1].text.startswith("テスト規程 第2章 手続 第2条（申請）\n1. 申請は")


def test_citation(doc: KiteiDocument) -> None:
    assert doc.chunks[0].citation == "テスト規程 第1条（目的）"
    assert doc.chunks[2].citation == "テスト規程 附則"


def test_supplementary_has_no_chapter_or_article_no(doc: KiteiDocument) -> None:
    suppl = doc.chunks[2]
    assert suppl.chapter is None
    assert suppl.article_no is None
    assert suppl.body == "1. 本規程は、2026年4月1日から施行する。"


def test_article_comment_overrides_roles(doc: KiteiDocument) -> None:
    # 第1条は規程の権限、第2条は見出し直下のコメントで上書き（D-004）
    assert doc.chunks[0].allowed_roles == ["full_time", "contract"]
    assert doc.chunks[1].allowed_roles == ["manager", "hr"]
    assert doc.chunks[2].allowed_roles == ["full_time", "contract"]


# ---- 書式違反を見つけられること ----


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("### 第2条（申請）", "### 第3条（申請）", "条番号が連番ではありません"),
        ("## 第2章 手続", "## 第3章 手続", "章番号が連番ではありません"),
        ("### 第2条（申請）", "### 第2条(申請)", "見出しの書式が決まりと違います"),
        ("## 附則\n", "", "最後に「## 附則」がありません"),
        ("1. 本規程は、テストのために定める。", "", "第1条 の本文が空です"),
        ("[manager, hr]", "[manager, boss]", "未知の権限があります"),
        (
            "2. 承認は",
            "<!-- allowed_roles: [manager, hr] -->\n2. 承認は",
            "権限のコメントは条の見出しの直下に置きます",
        ),
        (
            "<!-- allowed_roles: [manager, hr] -->",
            "<!-- allowed_role: [manager, hr] -->",
            "コメントの書式が決まりと違います",
        ),
    ],
)
def test_detects_body_errors(old: str, new: str, message: str) -> None:
    body = BODY.replace(old, new, 1)
    assert body != BODY, "置き換え対象が見つからない（テストの書き間違い）"
    with pytest.raises(KiteiFormatError, match=message):
        parse_kitei(make(body))


def test_detects_heading_after_supplementary() -> None:
    body = BODY + "\n### 第3条（追加）\n\n1. 追加する。\n"
    with pytest.raises(KiteiFormatError, match="附則の後に見出しがあります"):
        parse_kitei(make(body))


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('version: "1.0"', "version: 1.0", "引用符で囲んでください"),
        ("allowed_roles: [full_time, contract]", "allowed_roles: [part_time]", "未知の権限"),
        ("doc_id: kitei-999\n", "", "doc_id"),
    ],
)
def test_detects_front_matter_errors(old: str, new: str, message: str) -> None:
    front_matter = FRONT_MATTER.replace(old, new, 1)
    assert front_matter != FRONT_MATTER
    with pytest.raises(KiteiFormatError, match=message):
        parse_kitei(make(front_matter=front_matter))


def test_requires_front_matter() -> None:
    with pytest.raises(KiteiFormatError, match="front matter"):
        parse_kitei(BODY)


def test_style_issues() -> None:
    body = BODY.replace("3営業日前", "３営業日前").replace("所属長が行う", "所属長(部長)が行う")
    issues = find_style_issues(make(body))
    assert len(issues) == 2
    assert "全角の数字" in issues[0]
    assert "半角の括弧" in issues[1]
    assert find_style_issues(make()) == []


# ---- 実際の規程データ（data/kitei）----


def test_real_kitei_files() -> None:
    docs = load_kitei_dir()
    assert len(docs) == 7
    assert sum(len(d.chunks) for d in docs) == 95  # 88条＋附則7


def test_real_article_level_role() -> None:
    chunks = {c.chunk_id: c for d in load_kitei_dir() for c in d.chunks}
    assert chunks["kitei-006#art10"].allowed_roles == ["manager", "hr"]
    assert "contractor" in chunks["kitei-006#art9"].allowed_roles
