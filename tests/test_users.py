import pytest
from pydantic import ValidationError

from app.auth.users import User, UserDirectory, load_users

EVERYONE = ["full_time", "contract", "contractor", "manager", "hr"]
EMPLOYEES = ["full_time", "contract", "manager", "hr"]
MANAGEMENT = ["manager", "hr"]


@pytest.fixture(scope="module")
def directory() -> UserDirectory:
    return load_users()


def test_loads_five_users(directory: UserDirectory) -> None:
    assert len(directory.users) == 5


@pytest.mark.parametrize(
    ("user_id", "allowed_roles", "expected"),
    [
        ("u001", EMPLOYEES, True),  # 正社員は就業規則を見られる
        ("u003", EMPLOYEES, False),  # 業務委託は就業規則の対象外
        ("u003", EVERYONE, True),  # 週報ルールは業務委託も見られる
        ("u001", MANAGEMENT, False),  # 一般社員は評価規程を見られない
        ("u004", MANAGEMENT, True),  # 管理職は見られる
        ("u005", MANAGEMENT, True),  # 人事も見られる
    ],
)
def test_can_access(
    directory: UserDirectory, user_id: str, allowed_roles: list[str], expected: bool
) -> None:
    user = directory.get(user_id)
    assert user is not None
    assert user.can_access(allowed_roles) is expected


def test_unknown_employment_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        User(id="x", name="テスト", employment_type="part_time", role="member")
