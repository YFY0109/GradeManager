"""用户管理路由（多角色 + 用户级权限覆盖）。"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..audit import write_audit
from ..auth import current_user, hash_password
from ..db import get_db
from ..permissions import (
    CAPABILITY_LABELS,
    capabilities_for,
    get_user_scope,
    normalize_permissions,
    require_capability,
)
from ..schemas import UserCreate, UserUpdate

router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    dependencies=[Depends(current_user)],
    responses={
        400: {"description": "请求参数或业务校验错误"},
        401: {"description": "未登录或 token 无效"},
        403: {"description": "需要管理员权限"},
        404: {"description": "用户不存在"},
        422: {"description": "请求体校验错误"},
    },
)


def _resolve_ids(conn, table: str, public_ids: list[UUID]) -> list[int]:
    ids: list[int] = []
    for pid in dict.fromkeys(public_ids):
        row = conn.execute(
            f"SELECT id FROM {table} WHERE public_id = %s", (pid,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=400, detail=f"{table} 中存在无效 ID: {pid}")
        ids.append(row["id"])
    return ids


def _validate_permissions(permissions: dict[str, bool]) -> dict[str, bool]:
    invalid = [key for key in permissions if key not in CAPABILITY_LABELS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"未知能力项: {', '.join(invalid)}",
        )
    return normalize_permissions(permissions)


def _normalize_user_row(row: dict) -> dict:
    if row is not None:
        row["permissions"] = normalize_permissions(row.get("permissions") or {})
    return row


def _resolve_roles(conn, codes: list[str]) -> list[dict]:
    roles = []
    for code in dict.fromkeys(codes):
        row = conn.execute(
            "SELECT id, code, name, permissions FROM roles WHERE code = %s", (code,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=400, detail=f"角色不存在: {code}")
        roles.append(row)
    return roles


def _is_admin(user: dict) -> bool:
    return "admin" in (user.get("role_codes") or []) or user.get("role") == "admin"


def _grantable_caps(user: dict) -> set[str]:
    caps = capabilities_for(user)
    return {key for key in CAPABILITY_LABELS if caps.get(key)}


def _assert_can_grant(actor: dict, permissions: dict[str, bool]) -> None:
    if _is_admin(actor):
        return
    allowed = _grantable_caps(actor)
    extra = [key for key, value in permissions.items() if value and key not in allowed]
    if extra:
        raise HTTPException(
            status_code=403,
            detail=f"不能授予超出自身权限的能力: {', '.join(extra)}",
        )


def _assert_roles_grantable(actor: dict, roles: list[dict]) -> None:
    if _is_admin(actor):
        return
    allowed = _grantable_caps(actor)
    for role in roles:
        for key, value in (role.get("permissions") or {}).items():
            if value and key not in allowed:
                raise HTTPException(
                    status_code=403,
                    detail=f"不能授予超出自身权限的角色: {role['code']}",
                )


def _assert_scope_grantable(
    actor_scope: dict, class_ids: list[int], subject_ids: list[int]
) -> None:
    if not actor_scope["all_classes"]:
        extra = set(class_ids) - set(actor_scope["class_ids"])
        if extra:
            raise HTTPException(status_code=403, detail="不能授予超出自身的班级范围")
    if not actor_scope["all_subjects"]:
        extra = set(subject_ids) - set(actor_scope["subject_ids"])
        if extra:
            raise HTTPException(status_code=403, detail="不能授予超出自身的科目范围")


def _user_is_admin(conn, user_id: int) -> bool:
    return conn.execute(
        """
        SELECT 1 FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        WHERE ur.user_id = %s AND r.code = 'admin'
        """,
        (user_id,),
    ).fetchone() is not None


def _target_exceeds_actor(conn, target: dict, actor: dict) -> bool:
    if _is_admin(actor):
        return False
    allowed = _grantable_caps(actor)
    target_caps = {
        key for key, value in (target.get("permissions") or {}).items() if value
    }
    for row in conn.execute(
        """
        SELECT r.permissions FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        WHERE ur.user_id = %s
        """,
        (target["id"],),
    ).fetchall():
        for key, value in (row["permissions"] or {}).items():
            if value:
                target_caps.add(key)
    return bool(target_caps - allowed)


def _set_roles(conn, user_id: int, roles: list[dict]) -> None:
    conn.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
    for role in roles:
        conn.execute(
            "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
            (user_id, role["id"]),
        )
    primary = roles[0]["code"] if roles else None
    conn.execute("UPDATE users SET role = %s WHERE id = %s", (primary, user_id))


def _user_detail(conn, user_id: int) -> dict:
    row = conn.execute(
        """
        SELECT u.public_id, u.username, u.display_name, u.role, u.status,
               u.permissions, u.must_change_password, u.created_at, u.last_login_at,
               COALESCE((
                   SELECT json_agg(json_build_object('code', r.code, 'name', r.name)
                                   ORDER BY r.id)
                   FROM user_roles ur JOIN roles r ON r.id = ur.role_id
                   WHERE ur.user_id = u.id
               ), '[]'::json) AS roles,
               COALESCE((
                   SELECT json_agg(json_build_object('public_id', c.public_id, 'name', c.name)
                                   ORDER BY c.id)
                   FROM user_classes uc JOIN classes c ON c.id = uc.class_id
                   WHERE uc.user_id = u.id
               ), '[]'::json) AS classes,
               COALESCE((
                   SELECT json_agg(json_build_object('public_id', s.public_id, 'name', s.name)
                                   ORDER BY s.sort_order)
                   FROM user_subjects us JOIN subjects s ON s.id = us.subject_id
                   WHERE us.user_id = u.id
               ), '[]'::json) AS subjects
        FROM users u WHERE u.id = %s
        """,
        (user_id,),
    ).fetchone()
    return _normalize_user_row(row)


@router.get("")
def list_users(
    conn=Depends(get_db), _user=Depends(require_capability("manage_users"))
):
    rows = conn.execute(
        """
        SELECT u.id, u.public_id, u.username, u.display_name, u.role, u.status,
               u.permissions, u.must_change_password, u.created_at, u.last_login_at,
               COALESCE((
                   SELECT json_agg(json_build_object('code', r.code, 'name', r.name)
                                   ORDER BY r.id)
                   FROM user_roles ur JOIN roles r ON r.id = ur.role_id
                   WHERE ur.user_id = u.id
               ), '[]'::json) AS roles,
               COALESCE((
                   SELECT json_agg(json_build_object('public_id', c.public_id, 'name', c.name)
                                   ORDER BY c.id)
                   FROM user_classes uc JOIN classes c ON c.id = uc.class_id
                   WHERE uc.user_id = u.id
               ), '[]'::json) AS classes,
               COALESCE((
                   SELECT json_agg(json_build_object('public_id', s.public_id, 'name', s.name)
                                   ORDER BY s.sort_order)
                   FROM user_subjects us JOIN subjects s ON s.id = us.subject_id
                   WHERE us.user_id = u.id
               ), '[]'::json) AS subjects
        FROM users u
        ORDER BY u.id
        """
    ).fetchall()
    for row in rows:
        row.pop("id", None)
        _normalize_user_row(row)
    return rows


@router.post("")
def create_user(
    body: UserCreate,
    conn=Depends(get_db),
    actor=Depends(require_capability("manage_users")),
    actor_scope=Depends(get_user_scope),
):
    if conn.execute("SELECT 1 FROM users WHERE username = %s", (body.username,)).fetchone():
        raise HTTPException(status_code=400, detail="用户名已存在")

    permissions = _validate_permissions(body.permissions)
    roles = _resolve_roles(conn, body.role_codes)
    class_ids = _resolve_ids(conn, "classes", body.class_public_ids)
    subject_ids = _resolve_ids(conn, "subjects", body.subject_public_ids)
    _assert_can_grant(actor, permissions)
    _assert_roles_grantable(actor, roles)
    _assert_scope_grantable(actor_scope, class_ids, subject_ids)

    row = conn.execute(
        """
        INSERT INTO users (username, password_hash, display_name, role, permissions)
        VALUES (%s, %s, %s, %s, %s::jsonb)
        RETURNING id
        """,
        (
            body.username,
            hash_password(body.password),
            body.display_name,
            roles[0]["code"] if roles else None,
            json.dumps(permissions, ensure_ascii=False),
        ),
    ).fetchone()
    _set_roles(conn, row["id"], roles)
    _set_scope(conn, row["id"], class_ids, subject_ids)
    write_audit(
        conn,
        actor=actor["username"],
        action="user.create",
        table_name="users",
        record_id=str(row["id"]),
        new_value={
            "username": body.username,
            "role_codes": [r["code"] for r in roles],
            "class_ids": class_ids,
            "subject_ids": subject_ids,
            "permissions": permissions,
        },
    )
    return _user_detail(conn, row["id"])


@router.patch("/{user_pid}")
def update_user(
    user_pid: UUID,
    body: UserUpdate,
    conn=Depends(get_db),
    actor=Depends(require_capability("manage_users")),
    actor_scope=Depends(get_user_scope),
):
    target = conn.execute(
        "SELECT id, username, role, status, token_version, permissions "
        "FROM users WHERE public_id = %s",
        (user_pid,),
    ).fetchone()
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    if _user_is_admin(conn, target["id"]) and not _is_admin(actor):
        raise HTTPException(status_code=403, detail="不能修改管理员账号")
    if target["id"] != actor["id"] and _target_exceeds_actor(conn, target, actor):
        raise HTTPException(status_code=403, detail="不能修改权限高于自己的用户")

    if target["id"] == actor["id"]:
        if (
            body.role_codes is not None
            or body.permissions is not None
            or body.class_public_ids is not None
            or body.subject_public_ids is not None
        ):
            raise HTTPException(status_code=400, detail="不能修改自己的角色、权限或数据范围")
        if body.status == "disabled":
            raise HTTPException(status_code=400, detail="不能禁用自己的账号")

    updates: list[str] = []
    params: list = []
    token_bump = False

    if body.display_name is not None:
        updates.append("display_name = %s")
        params.append(body.display_name)
    if body.role_codes is not None:
        roles = _resolve_roles(conn, body.role_codes)
        _assert_roles_grantable(actor, roles)
        _set_roles(conn, target["id"], roles)
        token_bump = True
    if body.status is not None:
        updates.append("status = %s")
        params.append(body.status)
        token_bump = True
    if body.permissions is not None:
        permissions = _validate_permissions(body.permissions)
        _assert_can_grant(actor, permissions)
        updates.append("permissions = %s::jsonb")
        params.append(json.dumps(permissions, ensure_ascii=False))
        token_bump = True
    if body.must_change_password is not None:
        updates.append("must_change_password = %s")
        params.append(body.must_change_password)
    if body.password is not None:
        updates.append("password_hash = %s")
        params.append(hash_password(body.password))
        token_bump = True

    if body.class_public_ids is not None:
        class_ids = _resolve_ids(conn, "classes", body.class_public_ids)
        _assert_scope_grantable(actor_scope, class_ids, [])
        conn.execute("DELETE FROM user_classes WHERE user_id = %s", (target["id"],))
        for class_id in class_ids:
            conn.execute(
                "INSERT INTO user_classes (user_id, class_id) VALUES (%s, %s)",
                (target["id"], class_id),
            )
        token_bump = True
    if body.subject_public_ids is not None:
        subject_ids = _resolve_ids(conn, "subjects", body.subject_public_ids)
        _assert_scope_grantable(actor_scope, [], subject_ids)
        conn.execute("DELETE FROM user_subjects WHERE user_id = %s", (target["id"],))
        for subject_id in subject_ids:
            conn.execute(
                "INSERT INTO user_subjects (user_id, subject_id) VALUES (%s, %s)",
                (target["id"], subject_id),
            )
        token_bump = True

    if token_bump:
        updates.append("token_version = token_version + 1")
    if updates:
        conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = %s",
            (*params, target["id"]),
        )

    write_audit(
        conn,
        actor=actor["username"],
        action="user.update",
        table_name="users",
        record_id=str(target["id"]),
        new_value=body.model_dump(exclude_none=True, exclude={"password"}),
    )
    return _user_detail(conn, target["id"])


@router.delete("/{user_pid}")
def disable_user(
    user_pid: UUID,
    conn=Depends(get_db),
    actor=Depends(require_capability("manage_users")),
):
    target = conn.execute(
        "SELECT id, username, permissions FROM users WHERE public_id = %s", (user_pid,)
    ).fetchone()
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target["id"] == actor["id"]:
        raise HTTPException(status_code=400, detail="不能禁用自己的账号")
    if _user_is_admin(conn, target["id"]) and not _is_admin(actor):
        raise HTTPException(status_code=403, detail="不能禁用管理员账号")
    if _target_exceeds_actor(conn, target, actor):
        raise HTTPException(status_code=403, detail="不能禁用权限高于自己的用户")

    conn.execute(
        "UPDATE users SET status = 'disabled', token_version = token_version + 1 WHERE id = %s",
        (target["id"],),
    )
    write_audit(
        conn,
        actor=actor["username"],
        action="user.disable",
        table_name="users",
        record_id=str(target["id"]),
        new_value={"username": target["username"], "status": "disabled"},
    )
    return {"ok": True, "message": "用户已禁用"}


def _set_scope(conn, user_id: int, class_ids: list[int], subject_ids: list[int]) -> None:
    conn.execute("DELETE FROM user_classes WHERE user_id = %s", (user_id,))
    conn.execute("DELETE FROM user_subjects WHERE user_id = %s", (user_id,))
    for class_id in class_ids:
        conn.execute(
            "INSERT INTO user_classes (user_id, class_id) VALUES (%s, %s)",
            (user_id, class_id),
        )
    for subject_id in subject_ids:
        conn.execute(
            "INSERT INTO user_subjects (user_id, subject_id) VALUES (%s, %s)",
            (user_id, subject_id),
        )
