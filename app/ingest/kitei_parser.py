"""規程（Markdown）を読み、検索用のチャンクに分ける。

- 1条＝1チャンク（D-003）。附則も1チャンクにする（D-005）
- 権限は front matter の allowed_roles を基本とし、条の見出し直下の
  `<!-- allowed_roles: [...] -->` があればその条だけ上書きする（D-004）
"""

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError, field_validator

from app.auth.users import EmploymentType, Role

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KITEI_DIR = REPO_ROOT / "data" / "kitei"

# allowed_roles に書いてよい値。member は「権限を増やさない」役割なので書かない
VALID_ROLES: frozenset[str] = frozenset(
    {e.value for e in EmploymentType} | {Role.MANAGER.value, Role.HR.value}
)

SUPPLEMENTARY = "附則"

_CHAPTER_RE = re.compile(r"^## 第(\d+)章 (.+)$")
_ARTICLE_RE = re.compile(r"^### 第(\d+)条（(.+)）$")
_SUPPLEMENTARY_RE = re.compile(r"^## 附則$")
_ROLE_COMMENT_RE = re.compile(r"^<!--\s*allowed_roles:\s*(\[.*\])\s*-->$")


class KiteiFormatError(ValueError):
    """規程の書式が決まりに合わないときに投げる。"""


class FrontMatter(BaseModel):
    """規程の先頭にある YAML。Javaでいえば record＋Bean Validation に近い。"""

    doc_id: str
    title: str
    version: str
    effective_date: date
    allowed_roles: list[str]

    @field_validator("version", mode="before")
    @classmethod
    def version_must_be_quoted(cls, value: object) -> object:
        # version: 1.0 と引用符なしで書くと YAML では小数になり、"1.10" と "1.1" が区別できない
        if not isinstance(value, str):
            raise ValueError('version は引用符で囲んでください（例：version: "1.0"）')
        return value

    @field_validator("allowed_roles")
    @classmethod
    def roles_must_be_known(cls, value: list[str]) -> list[str]:
        return _check_roles(value)


class Chunk(BaseModel):
    """検索の単位。1つの条、または附則。"""

    chunk_id: str  # 例：kitei-001#art20、kitei-004#suppl
    doc_id: str
    doc_title: str
    version: str
    effective_date: date
    chapter: str | None  # 例：第4章 休暇等。附則は None
    article_no: int | None  # 附則は None
    article_title: str  # 例：年次有給休暇。附則は「附則」
    allowed_roles: list[str]
    body: str  # 項の本文（見出しを除く）

    @property
    def citation(self) -> str:
        """回答に示す出典。例：就業規則 第20条（年次有給休暇）"""
        if self.article_no is None:
            return f"{self.doc_title} {SUPPLEMENTARY}"
        return f"{self.doc_title} 第{self.article_no}条（{self.article_title}）"

    @property
    def text(self) -> str:
        """埋め込み・検索に使う文字列。規程名と章名を先頭に付ける（D-003）。"""
        heading = " ".join(
            part for part in (self.doc_title, self.chapter, self._article_heading()) if part
        )
        return f"{heading}\n{self.body}"

    def _article_heading(self) -> str:
        if self.article_no is None:
            return SUPPLEMENTARY
        return f"第{self.article_no}条（{self.article_title}）"


class KiteiDocument(BaseModel):
    front_matter: FrontMatter
    chunks: list[Chunk]


def _check_roles(roles: object) -> list[str]:
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise ValueError("allowed_roles は文字列のリストで書いてください（例：[manager, hr]）")
    unknown = set(roles) - VALID_ROLES
    if unknown:
        raise ValueError(f"未知の権限があります: {sorted(unknown)}")
    if not roles:
        raise ValueError("allowed_roles が空です")
    return roles


def _split_front_matter(text: str) -> tuple[str, list[str], int]:
    """(front matter の文字列, 本文の行, 本文の1行目がファイルの何行目か) を返す。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise KiteiFormatError("先頭に YAML front matter（--- で囲む）がありません")
    try:
        end = lines.index("---", 1)
    except ValueError as e:
        raise KiteiFormatError("front matter の終わりの --- がありません") from e
    return "\n".join(lines[1:end]), lines[end + 1 :], end + 2


def _parse_front_matter(raw: str) -> FrontMatter:
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise KiteiFormatError("front matter が YAML の key: value 形式ではありません")
    try:
        return FrontMatter.model_validate(data)
    except ValidationError as e:
        messages = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
        raise KiteiFormatError("front matter が不正です: " + " / ".join(messages)) from e


@dataclass
class _Draft:
    """作成中のチャンク。見出しを読んだら作り、次の見出しが来たら Chunk に変える。"""

    article_no: int | None  # 附則は None
    title: str
    chapter: str | None
    roles: list[str]
    lines: list[str] = field(default_factory=list)

    @property
    def is_supplementary(self) -> bool:
        return self.article_no is None

    @property
    def label(self) -> str:
        return SUPPLEMENTARY if self.article_no is None else f"第{self.article_no}条"

    def has_body(self) -> bool:
        return any(line.strip() for line in self.lines)

    def to_chunk(self, fm: FrontMatter) -> Chunk:
        body = "\n".join(self.lines).strip()
        if not body:
            raise KiteiFormatError(f"{self.label} の本文が空です")
        suffix = "suppl" if self.article_no is None else f"art{self.article_no}"
        return Chunk(
            chunk_id=f"{fm.doc_id}#{suffix}",
            doc_id=fm.doc_id,
            doc_title=fm.title,
            version=fm.version,
            effective_date=fm.effective_date,
            chapter=self.chapter,
            article_no=self.article_no,
            article_title=self.title,
            allowed_roles=self.roles,
            body=body,
        )


def parse_kitei(text: str) -> KiteiDocument:
    """規程1本分の Markdown を読み、チャンクの一覧を返す。書式違反は KiteiFormatError。"""
    raw_front_matter, lines, first_line_no = _split_front_matter(text)
    fm = _parse_front_matter(raw_front_matter)

    chunks: list[Chunk] = []
    chapter: str | None = None
    next_chapter = 1
    draft: _Draft | None = None

    for line_no, line in enumerate(lines, start=first_line_no):
        stripped = line.strip()
        where = f"{line_no}行目"

        if draft is not None and draft.is_supplementary and stripped.startswith("##"):
            raise KiteiFormatError(f"{where}：附則の後に見出しがあります：{stripped}")

        if m := _CHAPTER_RE.match(stripped):
            number = int(m.group(1))
            if number != next_chapter:
                raise KiteiFormatError(f"{where}：章番号が連番ではありません（第{number}章）")
            next_chapter += 1
            chapter = f"第{number}章 {m.group(2)}"
            continue

        if m := _ARTICLE_RE.match(stripped):
            number = int(m.group(1))
            if chapter is None:
                raise KiteiFormatError(f"{where}：第{number}条 が章の外にあります")
            if draft is not None:
                chunks.append(draft.to_chunk(fm))
            expected = len(chunks) + 1
            if number != expected:
                raise KiteiFormatError(
                    f"{where}：条番号が連番ではありません（第{expected}条のはずが第{number}条）"
                )
            draft = _Draft(number, m.group(2), chapter, list(fm.allowed_roles))
            continue

        if _SUPPLEMENTARY_RE.match(stripped):
            if draft is not None:
                chunks.append(draft.to_chunk(fm))
            draft = _Draft(None, SUPPLEMENTARY, None, list(fm.allowed_roles))
            continue

        if stripped.startswith("#") and not stripped.startswith("# "):
            raise KiteiFormatError(f"{where}：見出しの書式が決まりと違います：{stripped}")

        if m := _ROLE_COMMENT_RE.match(stripped):
            # 条の見出しの直下（まだ本文がない）でだけ使える
            if draft is None or draft.is_supplementary or draft.has_body():
                raise KiteiFormatError(f"{where}：権限のコメントは条の見出しの直下に置きます")
            try:
                draft.roles = _check_roles(yaml.safe_load(m.group(1)))
            except ValueError as e:
                raise KiteiFormatError(f"{where}：{draft.label}の権限：{e}") from e
            continue

        if stripped.startswith("<!--"):
            # 書き間違えたコメントを本文として黙って取り込まないようにする
            raise KiteiFormatError(f"{where}：コメントの書式が決まりと違います：{stripped}")

        if draft is None:
            # 最初の条より前に書いてよいのは、空行と「# 規程名」の行だけ
            if stripped and not stripped.startswith("# "):
                raise KiteiFormatError(f"{where}：最初の条より前に本文があります")
            continue

        draft.lines.append(line)

    if draft is None or not draft.is_supplementary:
        raise KiteiFormatError("最後に「## 附則」がありません")
    chunks.append(draft.to_chunk(fm))
    return KiteiDocument(front_matter=fm, chunks=chunks)


# 書式の決まり「数字は半角、括弧は全角」に反する文字
_FULL_WIDTH_DIGIT_RE = re.compile(r"[０-９]")
_HALF_WIDTH_PAREN_RE = re.compile(r"[()]")


def find_style_issues(text: str) -> list[str]:
    """数字と括弧の表記の乱れを探す。front matter（YAML）は対象外。"""
    _, lines, first_line_no = _split_front_matter(text)
    issues: list[str] = []
    for line_no, line in enumerate(lines, start=first_line_no):
        if _FULL_WIDTH_DIGIT_RE.search(line):
            issues.append(f"{line_no}行目：全角の数字があります：{line.strip()}")
        if _HALF_WIDTH_PAREN_RE.search(line):
            issues.append(f"{line_no}行目：半角の括弧があります：{line.strip()}")
    return issues


def load_kitei_dir(directory: Path = DEFAULT_KITEI_DIR) -> list[KiteiDocument]:
    """フォルダ内の規程（kitei-*.md）をすべて読む。doc_id の重複は許さない。"""
    documents = [
        parse_kitei(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("kitei-*.md"))
    ]
    doc_ids = [d.front_matter.doc_id for d in documents]
    duplicated = {d for d in doc_ids if doc_ids.count(d) > 1}
    if duplicated:
        raise KiteiFormatError(f"doc_id が重複しています: {sorted(duplicated)}")
    return documents
