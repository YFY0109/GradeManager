"""学科管理路由（新增/编辑/删除科目）。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..audit import write_audit
from ..auth import current_user
from ..db import get_db
from ..permissions import require_capability
from ..schemas import SubjectCreate, SubjectUpdate

router = APIRouter(
    prefix="/api/subjects",
    tags=["subjects"],
    dependencies=[Depends(current_user)],
    responses={
        400: {"description": "请求参数或业务校验错误"},
        401: {"description": "未登录或 token 无效"},
        403: {"description": "需要配置管理权限"},
        404: {"description": "科目不存在"},
    },
)

# 月考固定五科；这五科改名会导致新建月考失败，因此禁止改名/删除
MONTHLY_SUBJECTS = {"语文", "数学", "英语", "物理", "化学"}


def _subject_detail(conn, subject_id: int) -> dict:
    return conn.execute(
        """
        SELECT s.public_id, s.name, s.full_score, s.sort_order,
               (SELECT count(*) FROM exam_subjects es WHERE es.subject_id = s.id)
                   AS exam_count,
               (SELECT count(*) FROM scores sc WHERE sc.subject_id = s.id)
                   AS score_count,
               (SELECT count(*) FROM user_subjects us WHERE us.subject_id = s.id)
                   AS user_count
        FROM subjects s WHERE s.id = %s
        """,
        (subject_id,),
    ).fetchone()


@router.get("/manage")
def manage_subjects(
    conn=Depends(get_db),
    _user=Depends(require_capability("manage_config")),
):
    """配置管理用：全部科目 + 引用计数。"""
    return conn.execute(
        """
        SELECT s.public_id, s.name, s.full_score, s.sort_order,
               (SELECT count(*) FROM exam_subjects es WHERE es.subject_id = s.id)
                   AS exam_count,
               (SELECT count(*) FROM scores sc WHERE sc.subject_id = s.id)
                   AS score_count,
               (SELECT count(*) FROM user_subjects us WHERE us.subject_id = s.id)
                   AS user_count
        FROM subjects s
        ORDER BY s.sort_order, s.id
        """
    ).fetchall()


@router.post("")
def create_subject(
    body: SubjectCreate,
    conn=Depends(get_db),
    actor=Depends(require_capability("manage_config")),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="科目名称不能为空")
    if conn.execute("SELECT 1 FROM subjects WHERE name = %s", (name,)).fetchone():
        raise HTTPException(status_code=400, detail="科目名称已存在")

    row = conn.execute(
        """
        INSERT INTO subjects (name, full_score, sort_order)
        VALUES (%s, %s, %s)
        RETURNING id, public_id
        """,
        (name, body.full_score, body.sort_order),
    ).fetchone()
    write_audit(
        conn,
        actor=actor["username"],
        action="subject.create",
        table_name="subjects",
        record_id=str(row["id"]),
        new_value={
            "public_id": str(row["public_id"]),
            "name": name,
            "full_score": body.full_score,
            "sort_order": body.sort_order,
        },
    )
    return _subject_detail(conn, row["id"])


@router.patch("/{subject_pid}")
def update_subject(
    subject_pid: UUID,
    body: SubjectUpdate,
    conn=Depends(get_db),
    actor=Depends(require_capability("manage_config")),
):
    target = conn.execute(
        "SELECT id, name, full_score, sort_order FROM subjects WHERE public_id = %s",
        (subject_pid,),
    ).fetchone()
    if target is None:
        raise HTTPException(status_code=404, detail="科目不存在")

    updates: list[str] = []
    params: list = []
    old_value = {
        "name": target["name"],
        "full_score": float(target["full_score"]),
        "sort_order": target["sort_order"],
    }

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="科目名称不能为空")
        if name != target["name"]:
            if target["name"] in MONTHLY_SUBJECTS:
                raise HTTPException(
                    status_code=400,
                    detail="月考固定科目不可改名（语文/数学/英语/物理/化学）",
                )
            if conn.execute(
                "SELECT 1 FROM subjects WHERE name = %s AND id <> %s",
                (name, target["id"]),
            ).fetchone():
                raise HTTPException(status_code=400, detail="科目名称已存在")
            updates.append("name = %s")
            params.append(name)
    if body.full_score is not None:
        updates.append("full_score = %s")
        params.append(body.full_score)
    if body.sort_order is not None:
        updates.append("sort_order = %s")
        params.append(body.sort_order)

    if updates:
        conn.execute(
            f"UPDATE subjects SET {', '.join(updates)} WHERE id = %s",
            (*params, target["id"]),
        )

    updated = _subject_detail(conn, target["id"])
    write_audit(
        conn,
        actor=actor["username"],
        action="subject.update",
        table_name="subjects",
        record_id=str(target["id"]),
        old_value=old_value,
        new_value={
            "name": updated["name"],
            "full_score": float(updated["full_score"]),
            "sort_order": updated["sort_order"],
        },
    )
    return updated


@router.delete("/{subject_pid}")
def delete_subject(
    subject_pid: UUID,
    conn=Depends(get_db),
    actor=Depends(require_capability("manage_config")),
):
    target = conn.execute(
        "SELECT id, name FROM subjects WHERE public_id = %s", (subject_pid,)
    ).fetchone()
    if target is None:
        raise HTTPException(status_code=404, detail="科目不存在")
    if target["name"] in MONTHLY_SUBJECTS:
        raise HTTPException(status_code=400, detail="月考固定科目不可删除")

    counts = conn.execute(
        """
        SELECT
            (SELECT count(*) FROM exam_subjects WHERE subject_id = %(id)s) AS exam_count,
            (SELECT count(*) FROM scores WHERE subject_id = %(id)s) AS score_count,
            (SELECT count(*) FROM user_subjects WHERE subject_id = %(id)s) AS user_count
        """,
        {"id": target["id"]},
    ).fetchone()
    total = counts["exam_count"] + counts["score_count"] + counts["user_count"]
    if total:
        raise HTTPException(
            status_code=400,
            detail=(
                "该科目已被引用，不能删除"
                f"（考试 {counts['exam_count']}、成绩 {counts['score_count']}、"
                f"用户授权 {counts['user_count']}）"
            ),
        )

    conn.execute("DELETE FROM subjects WHERE id = %s", (target["id"],))
    write_audit(
        conn,
        actor=actor["username"],
        action="subject.delete",
        table_name="subjects",
        record_id=str(target["id"]),
        old_value={"name": target["name"]},
    )
    return {"ok": True}
