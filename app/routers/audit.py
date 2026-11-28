"""审计日志查询（view_audit 能力，默认 admin / grade_leader）。"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import current_user
from ..db import get_db
from ..permissions import require_capability

router = APIRouter(
    prefix="/api/audit-logs",
    tags=["audit"],
    dependencies=[Depends(current_user)],
    responses={
        401: {"description": "未登录或 token 无效"},
        403: {"description": "无查看审计权限"},
    },
)

_LIST_FIELDS = (
    "id, actor, action, table_name, record_id, old_value, new_value, created_at"
)


@router.get("")
def list_audit_logs(
    action: str | None = None,
    actor: str | None = None,
    table_name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn=Depends(get_db),
    _user=Depends(require_capability("view_audit")),
):
    clauses: list[str] = []
    params: dict = {}
    if action:
        clauses.append("action = %(action)s")
        params["action"] = action
    if actor:
        clauses.append("actor = %(actor)s")
        params["actor"] = actor
    if table_name:
        clauses.append("table_name = %(table_name)s")
        params["table_name"] = table_name
    if date_from:
        clauses.append("created_at >= %(date_from)s")
        params["date_from"] = date_from
    if date_to:
        clauses.append("created_at < (%(date_to)s::date + 1)")
        params["date_to"] = date_to
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    total = conn.execute(
        f"SELECT count(*) AS n FROM audit_logs {where}", params
    ).fetchone()["n"]
    rows = conn.execute(
        f"""
        SELECT {_LIST_FIELDS}
        FROM audit_logs
        {where}
        ORDER BY id DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {**params, "limit": limit, "offset": offset},
    ).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


@router.get("/scores")
def score_history(
    exam_pid: UUID | None = None,
    student_pid: UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn=Depends(get_db),
    _user=Depends(require_capability("view_audit")),
):
    """成绩变更历史（按考试/学生筛选）。"""
    clauses = ["action IN ('score.create', 'score.update')"]
    params: dict = {"limit": limit, "offset": offset}

    if exam_pid:
        exam = conn.execute(
            "SELECT id FROM exams WHERE public_id = %s", (exam_pid,)
        ).fetchone()
        if exam is None:
            raise HTTPException(status_code=404, detail="考试不存在")
        clauses.append(
            "COALESCE((new_value->>'exam_id')::int, (old_value->>'exam_id')::int) = %(exam_id)s"
        )
        params["exam_id"] = exam["id"]
    if student_pid:
        student = conn.execute(
            "SELECT id FROM students WHERE public_id = %s", (student_pid,)
        ).fetchone()
        if student is None:
            raise HTTPException(status_code=404, detail="学生不存在")
        clauses.append(
            "COALESCE((new_value->>'student_id')::int, (old_value->>'student_id')::int) = %(student_id)s"
        )
        params["student_id"] = student["id"]

    where = "WHERE " + " AND ".join(clauses)
    total = conn.execute(
        f"SELECT count(*) AS n FROM audit_logs {where}", params
    ).fetchone()["n"]
    rows = conn.execute(
        f"""
        SELECT {_LIST_FIELDS}
        FROM audit_logs
        {where}
        ORDER BY id DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
    ).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "items": rows}
