"""角色、能力与数据范围。

- 角色 = 命名权限模板（roles 表），用户可拥有多个角色，权限取并集
- 用户可单独覆盖权限（users.permissions）
- rank 是排名总开关：rank_grade/rank_class 仅在 rank 开启时有效
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from .auth import current_user
from .db import get_db

ROLES = ("admin", "grade_leader", "head_teacher", "teacher", "viewer")

ROLE_LABELS = {
    "admin": "管理员",
    "grade_leader": "年级组长",
    "head_teacher": "班主任",
    "teacher": "科任老师",
    "viewer": "只读",
}

CAPABILITY_LABELS = {
    "report_grade": "查看年级报告",
    "report_class": "查看班级报告",
    "rank": "排名总开关",
    "rank_grade": "查看年排",
    "rank_class": "查看班排",
    "view_total": "查看总分",
    "view_subject": "查看单科",
    "view_stats": "查看汇总指标",
    "enter_scores": "录入/修改成绩",
    "export": "导出",
    "view_audit": "查看审计日志",
    "manage_users": "用户管理",
    "manage_roles": "角色管理",
    "manage_config": "配置管理",
    "create_exam": "创建考试",
}

# 兼容旧数据/角色表缺失时的兜底默认
ROLE_CAPABILITIES: dict[str, set[str]] = {
    "admin": set(CAPABILITY_LABELS),
    "grade_leader": {
        "report_grade",
        "report_class",
        "rank",
        "rank_grade",
        "rank_class",
        "view_total",
        "view_subject",
        "view_stats",
        "enter_scores",
        "export",
        "view_audit",
    },
    "head_teacher": {
        "report_class",
        "rank",
        "rank_grade",
        "rank_class",
        "view_total",
        "view_subject",
        "view_stats",
        "enter_scores",
        "export",
    },
    "teacher": {
        "report_class",
        "rank",
        "rank_class",
        "view_subject",
        "view_stats",
        "enter_scores",
        "export",
    },
    "viewer": {
        "report_class",
        "rank",
        "rank_class",
        "view_total",
        "view_subject",
        "view_stats",
        "export",
    },
}


def normalize_permissions(permissions: dict[str, bool]) -> dict[str, bool]:
    """写入前规范化权限：排名总开关关闭时，年排/班排强制关闭。"""
    result = {k: bool(v) for k, v in (permissions or {}).items()}
    if not result.get("rank"):
        result["rank_grade"] = False
        result["rank_class"] = False
    return result


def capabilities_for(user: dict) -> dict[str, bool]:
    """解析用户能力：角色并集 + 用户覆盖 + rank 门控派生。"""
    base = {name: False for name in CAPABILITY_LABELS}

    role_permissions = user.get("role_permissions") or {}
    for key, value in role_permissions.items():
        if key in base and isinstance(value, bool) and value:
            base[key] = True

    if not role_permissions and not (user.get("role_codes") or user.get("roles")):
        for name in ROLE_CAPABILITIES.get(user.get("role") or "", set()):
            base[name] = True

    for key, value in (user.get("permissions") or {}).items():
        if key in base and isinstance(value, bool):
            base[key] = value

    # 派生（读接口用）
    base["can_rank_grade"] = base["rank"] and base["rank_grade"]
    base["can_rank_class"] = base["rank"] and base["rank_class"]
    base["can_rank"] = base["rank"] and (base["rank_grade"] or base["rank_class"])
    base["can_report_grade"] = base["report_grade"]
    base["can_report_class"] = base["report_grade"] or base["report_class"]
    return base


def load_scope(conn, user: dict) -> dict:
    """加载数据范围（班级/科目）。多角色按最宽范围合并。"""
    role_codes = set(user.get("role_codes") or [])
    if not role_codes and user.get("role"):
        role_codes = {user["role"]}
    if role_codes & {"admin", "grade_leader"}:
        return {
            "all_classes": True,
            "class_ids": [],
            "all_subjects": True,
            "subject_ids": [],
        }
    class_ids = [
        r["class_id"]
        for r in conn.execute(
            "SELECT class_id FROM user_classes WHERE user_id = %s", (user["id"],)
        ).fetchall()
    ]
    if role_codes & {"head_teacher", "viewer"}:
        return {
            "all_classes": False,
            "class_ids": class_ids,
            "all_subjects": True,
            "subject_ids": [],
        }
    subject_ids = [
        r["subject_id"]
        for r in conn.execute(
            "SELECT subject_id FROM user_subjects WHERE user_id = %s", (user["id"],)
        ).fetchall()
    ]
    return {
        "all_classes": False,
        "class_ids": class_ids,
        "all_subjects": False,
        "subject_ids": subject_ids,
    }


def get_user_scope(conn=Depends(get_db), user=Depends(current_user)) -> dict:
    """FastAPI 依赖：当前用户的班级/科目范围。"""
    return load_scope(conn, user)


def assert_class_allowed(scope: dict, class_id: int) -> None:
    if scope["all_classes"]:
        return
    if class_id not in scope["class_ids"]:
        raise HTTPException(status_code=403, detail="无权访问该班级")


def assert_subject_allowed(scope: dict, subject_id: int) -> None:
    if scope["all_subjects"]:
        return
    if subject_id not in scope["subject_ids"]:
        raise HTTPException(status_code=403, detail="无权访问该科目")


def require_capability(name: str):
    """FastAPI 依赖工厂：要求某项能力（可传派生键 can_rank_grade 等）。"""

    def dependency(user: dict = Depends(current_user)) -> dict:
        if not capabilities_for(user).get(name):
            label = CAPABILITY_LABELS.get(name, name)
            raise HTTPException(status_code=403, detail=f"无权限：{label}")
        return user

    return dependency
