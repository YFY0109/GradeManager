"""认证：密码哈希 + JWT + 会话校验。"""

import datetime as dt

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import JWT_ALG, JWT_EXPIRE_MINUTES, JWT_SECRET
from .db import get_db

_ph = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)

COOKIE_NAME = "gm_token"
MAX_LOGIN_FAILURES = 5
LOCK_MINUTES = 15
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"密码至少 {MIN_PASSWORD_LENGTH} 位")


def create_token(user_id: int, username: str, role: str, token_version: int) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": username,
        "uid": user_id,
        "role": role,
        "ver": token_version,
        "iat": now,
        "exp": now + dt.timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def current_user(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    conn=Depends(get_db),
) -> dict:
    """解析 token（优先 Authorization Bearer，其次 HttpOnly Cookie），并实时校验账号状态。"""
    token = cred.credentials if cred else request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="登录已过期或 token 无效")

    uid = payload.get("uid")
    if uid is None:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")

    row = conn.execute(
        """
        SELECT id, username, role, display_name, status, token_version,
               permissions, must_change_password
        FROM users WHERE id = %s
        """,
        (uid,),
    ).fetchone()
    if row is None or row["status"] != "active":
        raise HTTPException(status_code=401, detail="账号不存在或已被禁用")
    if payload.get("ver") != row["token_version"]:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")

    role_rows = conn.execute(
        """
        SELECT r.code, r.name, r.permissions
        FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        WHERE ur.user_id = %s
        ORDER BY r.id
        """,
        (row["id"],),
    ).fetchall()
    if not role_rows and row["role"]:
        role_rows = conn.execute(
            "SELECT code, name, permissions FROM roles WHERE code = %s",
            (row["role"],),
        ).fetchall()

    role_codes = [r["code"] for r in role_rows]
    role_permissions: dict[str, bool] = {}
    for role in role_rows:
        for key, value in (role["permissions"] or {}).items():
            if value is True:
                role_permissions[key] = True

    return {
        "id": row["id"],
        "username": row["username"],
        "role": role_codes[0] if role_codes else row["role"],
        "role_codes": role_codes,
        "roles": [{"code": r["code"], "name": r["name"]} for r in role_rows],
        "role_permissions": role_permissions,
        "display_name": row["display_name"],
        "permissions": row["permissions"] or {},
        "must_change_password": row["must_change_password"],
    }


def admin_user(user: dict = Depends(current_user)) -> dict:
    """仅管理员可访问（保留兼容；新代码建议用 require_capability）。"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
