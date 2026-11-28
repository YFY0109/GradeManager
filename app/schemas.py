"""请求/响应模型。"""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class LoginIn(BaseModel):
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str
    display_name: str | None = None
    role_codes: list[str] = Field(default_factory=list)
    class_public_ids: list[UUID] = Field(default_factory=list)
    subject_public_ids: list[UUID] = Field(default_factory=list)
    permissions: dict[str, bool] = Field(default_factory=dict)

    @field_validator("password")
    @classmethod
    def _password_length(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("密码至少 8 位")
        return value


class UserUpdate(BaseModel):
    display_name: str | None = None
    role_codes: list[str] | None = None
    status: Literal["active", "disabled"] | None = None
    password: str | None = None
    class_public_ids: list[UUID] | None = None
    subject_public_ids: list[UUID] | None = None
    permissions: dict[str, bool] | None = None
    must_change_password: bool | None = None

    @field_validator("password")
    @classmethod
    def _password_length(cls, value: str | None) -> str | None:
        if value is not None and len(value) < 8:
            raise ValueError("密码至少 8 位")
        return value


class RoleCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=32)
    permissions: dict[str, bool] = Field(default_factory=dict)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=32)
    permissions: dict[str, bool] | None = None


class SubjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    full_score: float = Field(gt=0, le=999.9)
    sort_order: int = Field(default=0, ge=0, le=9999)


class SubjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=32)
    full_score: float | None = Field(default=None, gt=0, le=999.9)
    sort_order: int | None = Field(default=None, ge=0, le=9999)


class ExamCreate(BaseModel):
    name: str
    exam_type: Literal["weekly", "monthly", "midterm", "final"] = "monthly"
    exam_date: date | None = None
    # 仅 weekly（周考/大练考，单科）需要
    subject_public_id: UUID | None = None


class ScoreItem(BaseModel):
    student_public_id: UUID
    subject_public_id: UUID
    score: float | None = None


class ScoreBatch(BaseModel):
    items: list[ScoreItem]
