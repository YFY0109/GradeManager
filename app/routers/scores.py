"""成绩录入路由（范围校验 + 审计）。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..audit import audit_score_change
from ..auth import current_user
from ..db import get_db
from ..permissions import (
    assert_class_allowed,
    assert_subject_allowed,
    get_user_scope,
    require_capability,
)
from ..schemas import ScoreBatch

router = APIRouter(
    prefix="/api",
    tags=["scores"],
    dependencies=[Depends(current_user)],
    responses={
        400: {"description": "请求参数或业务校验错误"},
        401: {"description": "未登录或 token 无效"},
        403: {"description": "无权录入该班级/科目"},
        404: {"description": "资源不存在"},
    },
)


@router.post("/exams/{exam_pid}/scores")
def save_scores(
    exam_pid: UUID,
    body: ScoreBatch,
    conn=Depends(get_db),
    user=Depends(require_capability("enter_scores")),
    scope=Depends(get_user_scope),
):
    exam = conn.execute("SELECT id FROM exams WHERE public_id = %s", (exam_pid,)).fetchone()
    if exam is None:
        raise HTTPException(status_code=404, detail="考试不存在")
    exam_id = exam["id"]

    full_scores = {
        row["public_id"]: (row["id"], float(row["full_score"]))
        for row in conn.execute(
            """
            SELECT s.public_id, s.id, es.full_score
            FROM exam_subjects es JOIN subjects s ON s.id = es.subject_id
            WHERE es.exam_id = %s
            """,
            (exam_id,),
        ).fetchall()
    }
    students = {
        row["public_id"]: (row["id"], row["class_id"])
        for row in conn.execute("SELECT public_id, id, class_id FROM students").fetchall()
    }

    rows = []
    for item in body.items:
        if item.student_public_id not in students:
            raise HTTPException(
                status_code=400, detail=f"学生不存在: {item.student_public_id}"
            )
        student_id, class_id = students[item.student_public_id]
        assert_class_allowed(scope, class_id)

        if item.subject_public_id not in full_scores:
            raise HTTPException(
                status_code=400, detail=f"科目不属于该考试: {item.subject_public_id}"
            )
        subject_id, limit = full_scores[item.subject_public_id]
        assert_subject_allowed(scope, subject_id)

        if item.score is not None and (item.score < 0 or item.score > limit):
            raise HTTPException(
                status_code=400,
                detail=f"分数超出范围 0~{limit:g}: {item.student_public_id}",
            )
        rows.append((exam_id, student_id, subject_id, item.score))

    existing = {
        (r["student_id"], r["subject_id"]): r["score"]
        for r in conn.execute(
            "SELECT student_id, subject_id, score FROM scores WHERE exam_id = %s",
            (exam_id,),
        ).fetchall()
    }

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO scores (exam_id, student_id, subject_id, score, entered_by)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (exam_id, student_id, subject_id)
            DO UPDATE SET score = EXCLUDED.score, updated_at = now()
            """,
            [(e, s, sub, score, user["username"]) for e, s, sub, score in rows],
        )

    changed = 0
    for (_, student_id, subject_id, score) in rows:
        if audit_score_change(
            conn,
            actor=user["username"],
            exam_id=exam_id,
            student_id=student_id,
            subject_id=subject_id,
            old_score=existing.get((student_id, subject_id)),
            new_score=score,
        ):
            changed += 1

    return {"saved": len(rows), "changed": changed}
