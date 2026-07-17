"""Pydantic request/response schemas."""
from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    invite_code: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    email: str


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


class DriveIn(BaseModel):
    name: str
    folder_id: str
    default_agency: str = ""


class DriveOut(DriveIn):
    id: int
    is_active: bool
    last_synced: str | None = None

    class Config:
        from_attributes = True


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    session_id: int | None = None
    mode: str = "auto"          # auto | docs | web
    model: str = "auto"         # "auto" or "provider/model_id"
    agency: str = ""            # optional metadata filter
    top_k: int = 0              # 0 = use server default


class ModelToggleIn(BaseModel):
    is_active: bool


class UserUpdateIn(BaseModel):
    role: str | None = None
    is_active: bool | None = None
