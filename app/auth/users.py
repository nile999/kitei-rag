from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel

# app/auth/users.py から2つ上がリポジトリ直下。実行する場所に左右されないようにする
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_USERS_PATH = REPO_ROOT / "data" / "users.yaml"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    CONTRACT = "contract"
    CONTRACTOR = "contractor"


class Role(StrEnum):
    MEMBER = "member"
    MANAGER = "manager"
    HR = "hr"


class User(BaseModel):
    id: str
    name: str
    employment_type: EmploymentType
    role: Role

    @property
    def access_groups(self) -> set[str]:
        """規程の allowed_roles と突き合わせる値。member は権限を増やさない。"""
        groups = {self.employment_type.value}
        if self.role is not Role.MEMBER:
            groups.add(self.role.value)
        return groups

    def can_access(self, allowed_roles: list[str]) -> bool:
        """どれか1つでも一致すれば閲覧できる。"""
        return bool(self.access_groups & set(allowed_roles))


class UserDirectory(BaseModel):
    users: list[User]

    def get(self, user_id: str) -> User | None:
        return next((u for u in self.users if u.id == user_id), None)


def load_users(path: Path = DEFAULT_USERS_PATH) -> UserDirectory:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return UserDirectory.model_validate(data)