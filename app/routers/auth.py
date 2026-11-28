"""认证路由：登录（失败锁定）、当前用户、修改密码、登出。"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..audit import write_audit
from ..auth import (
    COOKIE_NAME,
    JWT_EXPIRE_MINUTES,
    LOCK_MINUTES,
    MAX_LOGIN_FAILURES,
    create_token,
    current_user,
    hash_password,
    validate_password,
    verify_password,
)
from ..db import get_db
from ..permissions import capabilities_for, load_scope
from ..schemas import ChangePasswordIn, LoginIn

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto == "https"


@router.post("/login")
def login(
    body: LoginIn, request: Request, response: Response, conn=Depends(get_db)
):
    now = dt.datetime.now(dt.timezone.utc)
    ip = _client_ip(request)
    row = conn.execute(
        """
        SELECT id, username, password_hash, role, status, token_version,
               failed_attempts, locked_until, must_change_password
        FROM users WHERE username = %s
        """,
        (body.username,),
    ).fetchone()

    def fail(reason: str):
        write_audit(
            conn,
            actor=body.username,
            action="auth.login.failed",
            table_name="users",
            record_id=body.username,
            new_value={"reason": reason, "ip": ip},
        )
        # 登录失败需要立即提交：失败计数/锁定与审计不能因 401 回滚
        conn.commit()
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if row is None:
        fail("unknown_user")
    if row["status"] != "active":
        fail("disabled")
    if row["locked_until"] and row["locked_until"] > now:
        fail("locked")

    if not verify_password(row["password_hash"], body.password):
        failed = row["failed_attempts"] + 1
        locked_until = (
            now + dt.timedelta(minutes=LOCK_MINUTES)
            if failed >= MAX_LOGIN_FAILURES
            else None
        )
        conn.execute(
            "UPDATE users SET failed_attempts = %s, locked_until = %s WHERE id = %s",
            (failed, locked_until, row["id"]),
        )
        fail("bad_password")

    conn.execute(
        "UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login_at = %s "
        "WHERE id = %s",
        (now, row["id"]),
    )
    write_audit(
        conn,
        actor=row["username"],
        action="auth.login.success",
        table_name="users",
        record_id=str(row["id"]),
        new_value={"ip": ip},
    )
    token = create_token(
        row["id"], row["username"], row["role"], row["token_version"]
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=JWT_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=_is_https(request),
        samesite="lax",
        path="/",
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": row["role"],
        "must_change_password": row["must_change_password"],
    }


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(current_user), conn=Depends(get_db)):
    scope = load_scope(conn, user)
    if not scope["all_classes"]:
        rows = conn.execute(
            "SELECT public_id FROM classes WHERE id = ANY(%s) ORDER BY id",
            (scope["class_ids"],),
        ).fetchall()
        scope = {**scope, "class_public_ids": [r["public_id"] for r in rows]}
    if not scope["all_subjects"]:
        rows = conn.execute(
            "SELECT public_id FROM subjects WHERE id = ANY(%s) ORDER BY sort_order",
            (scope["subject_ids"],),
        ).fetchall()
        scope = {**scope, "subject_public_ids": [r["public_id"] for r in rows]}
    return {
        **user,
        "capabilities": capabilities_for(user),
        "scope": scope,
    }


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn, user=Depends(current_user), conn=Depends(get_db)
):
    row = conn.execute(
        "SELECT password_hash FROM users WHERE id = %s", (user["id"],)
    ).fetchone()
    if not verify_password(row["password_hash"], body.old_password):
        raise HTTPException(status_code=400, detail="原密码错误")
    try:
        validate_password(body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if body.old_password == body.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与原密码相同")

    conn.execute(
        """
        UPDATE users
        SET password_hash = %s, token_version = token_version + 1,
            must_change_password = FALSE
        WHERE id = %s
        """,
        (hash_password(body.new_password), user["id"]),
    )
    write_audit(
        conn,
        actor=user["username"],
        action="user.change_password",
        table_name="users",
        record_id=str(user["id"]),
    )
    return {"ok": True, "message": "密码已修改，请重新登录"}
