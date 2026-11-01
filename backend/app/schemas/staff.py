from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models import StaffUser

RoleName = Literal["owner", "admin", "operator", "finance"]


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class StaffOut(BaseModel):
    id: int
    login: str
    display_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    permissions: list[str] = []

    @classmethod
    def from_model(cls, staff: StaffUser, permissions: list[str] | None = None) -> "StaffOut":
        return cls(
            id=staff.id,
            login=staff.login,
            display_name=staff.display_name,
            role=staff.role,
            is_active=staff.is_active,
            last_login_at=staff.last_login_at,
            created_at=staff.created_at,
            permissions=permissions or [],
        )


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    staff: StaffOut


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class CreateStaffRequest(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=100)
    role: RoleName
    password: str = Field(min_length=1, max_length=256)


class UpdateStaffRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: RoleName | None = None
    is_active: bool | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=1, max_length=256)
