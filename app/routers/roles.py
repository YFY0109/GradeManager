"""角色管理路由（角色 = 可命名的权限模板）。"""

import json

from fastapi import APIRouter, Depends, HTTPException

from ..audit import write_audit
from ..auth import current_user
from ..db import get_db
from ..permissions import (
    CAPABILITY_LABELS,
    capabilities_for,
    normalize_permissions,
    require_capability,
)
from ..schemas import RoleCreate, RoleUpdate

router = APIRouter(
    prefix="/api/roles",
    tags=["roles"],
    dependencies=[Depends(current_user)],
    responses={
        400: {"description": "请求参数或业务校验错误"},
        401: {"description": "未登录或 token 无效"},
        403: {"description": "需要角色管理权限"},
        404: {"description": "角色不存在"},
    },
)


def _validate_permissions(permissions: dict[str, bool]) -> dict[str, bool]:
    invalid = [key for key in permissions if key not in CAPABILITY_LABELS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"未知能力项: {', '.join(invalid)}",
        )
    return normalize_permissions(permissions)


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


def _normalize_role(row: dict) -> dict:
    if row is not None:
        row["permissions"] = normalize_permissions(row.get("permissions") or {})
    return row


def _role_detail(conn, code: str) -> dict:
    return _normalize_role(
        conn.execute(
            """
            SELECT r.code, r.name, r.permissions, r.is_system,
                   (SELECT count(*) FROM user_roles ur WHERE ur.role_id = r.id) AS user_count
            FROM roles r WHERE r.code = %s
            """,
            (code,),
        ).fetchone()
    )


@router.get("")
def list_roles(conn=Depends(get_db), user=Depends(current_user)):
    caps = capabilities_for(user)
    if not (caps["manage_users"] or caps["manage_roles"]):
        raise HTTPException(status_code=403, detail="无权限查看角色列表")
    rows = conn.execute(
        """
        SELECT r.code, r.name, r.permissions, r.is_system,
               (SELECT count(*) FROM user_roles ur WHERE ur.role_id = r.id) AS user_count
        FROM roles r
        ORDER BY r.id
        """
    ).fetchall()
    return [_normalize_role(row) for row in rows]


@router.post("")
def create_role(
    body: RoleCreate,
    conn=Depends(get_db),
    actor=Depends(require_capability("manage_roles")),
):
    if conn.execute("SELECT 1 FROM roles WHERE code = %s", (body.code,)).fetchone():
        raise HTTPException(status_code=400, detail="角色代码已存在")
    permissions = _validate_permissions(body.permissions)
    _assert_can_grant(actor, permissions)
    conn.execute(
        """
        INSERT INTO roles (code, name, permissions)
        VALUES (%s, %s, %s::jsonb)
        """,
        (body.code, body.name, json.dumps(permissions, ensure_ascii=False)),
    )
    write_audit(
        conn,
        actor=actor["username"],
        action="role.create",
        table_name="roles",
        record_id=body.code,
        new_value={"code": body.code, "name": body.name, "permissions": permissions},
    )
    return _role_detail(conn, body.code)


@router.patch("/{code}")
def update_role(
    code: str,
    body: RoleUpdate,
    conn=Depends(get_db),
    actor=Depends(require_capability("manage_roles")),
):
    target = conn.execute(
        "SELECT id, code, is_system FROM roles WHERE code = %s", (code,)
    ).fetchone()
    if target is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    if not _is_admin(actor) and target["is_system"]:
        raise HTTPException(status_code=403, detail="只有管理员可以修改系统角色")

    updates: list[str] = []
    params: list = []
    if body.name is not None:
        updates.append("name = %s")
        params.append(body.name)
    if body.permissions is not None:
        permissions = _validate_permissions(body.permissions)
        _assert_can_grant(actor, permissions)
        updates.append("permissions = %s::jsonb")
        params.append(json.dumps(permissions, ensure_ascii=False))
    if updates:
        conn.execute(
            f"UPDATE roles SET {', '.join(updates)} WHERE id = %s",
            (*params, target["id"]),
        )
    write_audit(
        conn,
        actor=actor["username"],
        action="role.update",
        table_name="roles",
        record_id=code,
        new_value=body.model_dump(exclude_none=True),
    )
    return _role_detail(conn, code)


@router.delete("/{code}")
def delete_role(
    code: str,
    conn=Depends(get_db),
    actor=Depends(require_capability("manage_roles")),
):
    target = conn.execute(
        """
        SELECT r.id, r.code, r.is_system,
               (SELECT count(*) FROM user_roles ur WHERE ur.role_id = r.id) AS user_count
        FROM roles r WHERE r.code = %s
        """,
        (code,),
    ).fetchone()
    if target is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    if target["is_system"]:
        raise HTTPException(status_code=400, detail="系统角色不可删除")
    if target["user_count"]:
        raise HTTPException(
            status_code=400,
            detail=f"仍有 {target['user_count']} 个用户使用该角色，请先调整用户",
        )
    conn.execute("DELETE FROM roles WHERE id = %s", (target["id"],))
    write_audit(
        conn,
        actor=actor["username"],
        action="role.delete",
        table_name="roles",
        record_id=code,
    )
    return {"ok": True}
