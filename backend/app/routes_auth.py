"""Auth endpoints: register, login, me, api-key rotation."""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_db
from .models import AuditLog, User
from .schemas import LoginIn, RegisterIn, TokenOut, UserOut
from .security import create_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=TokenOut)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    if not settings.allow_registration:
        raise HTTPException(403, "Registration is disabled")
    if settings.invite_code and body.invite_code != settings.invite_code:
        raise HTTPException(403, "Invalid invite code")

    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Email already registered")

    count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        role="admin" if count == 0 else "user",  # first user becomes admin
    )
    db.add(user)
    db.add(AuditLog(action="register", detail={"email": user.email}))
    await db.commit()
    await db.refresh(user)
    return TokenOut(access_token=create_token(user), role=user.role, email=user.email)


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.email == body.email.lower()))
    user = res.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(403, "Account disabled")
    return TokenOut(access_token=create_token(user), role=user.role, email=user.email)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.get("/api-key")
async def get_api_key(user: User = Depends(get_current_user)):
    return {"api_key": user.api_key}


@router.post("/api-key/rotate")
async def rotate_api_key(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user.api_key = secrets.token_urlsafe(32)
    await db.commit()
    return {"api_key": user.api_key}
