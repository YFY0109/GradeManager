"""班级、科目、考试相关路由（含数据范围过滤）。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..audit import write_audit
from ..auth import current_user
from ..db import get_db
from ..permissions import (
    assert_class_allowed,
    capabilities_for,
    get_user_scope,
    require_capability,
)
from ..schemas import ExamCreate

COMMON_RESPONSES = {
    400: {"description": "请求参数或业务校验错误"},
    401: {"description": "未登录或 token 无效"},
    403: {"description": "无权访问该数据范围"},
    404: {"description": "资源不存在"},
}

MONTHLY_SUBJECTS = ["语文", "数学", "英语", "物理", "化学"]

router = APIRouter(
    prefix="/api",
    tags=["exams"],
    dependencies=[Depends(current_user)],
    responses=COMMON_RESPONSES,
)


@router.get("/classes")
def list_classes(conn=Depends(get_db), scope=Depends(get_user_scope)):
    if scope["all_classes"]:
        return conn.execute(
            "SELECT public_id, name, grade, head_teacher FROM classes ORDER BY id"
        ).fetchall()
    return conn.execute(
        """
        SELECT public_id, name, grade, head_teacher FROM classes
        WHERE id = ANY(%s) ORDER BY id
        """,
        (scope["class_ids"],),
    ).fetchall()


@router.get("/subjects")
def list_subjects(conn=Depends(get_db), scope=Depends(get_user_scope)):
    if scope["all_subjects"]:
        return conn.execute(
            "SELECT public_id, name, full_score, sort_order FROM subjects ORDER BY sort_order"
        ).fetchall()
    return conn.execute(
        """
        SELECT public_id, name, full_score, sort_order FROM subjects
        WHERE id = ANY(%s) ORDER BY sort_order
        """,
        (scope["subject_ids"],),
    ).fetchall()


@router.get("/exams")
def list_exams(conn=Depends(get_db)):
    return conn.execute(
        """
        SELECT e.public_id, e.name, e.exam_type, e.exam_date, e.status,
               (SELECT count(*) FROM scores s WHERE s.exam_id = e.id) AS score_rows
        FROM exams e
        ORDER BY e.id DESC
        """
    ).fetchall()


@router.post("/exams")
def create_exam(
    body: ExamCreate,
    conn=Depends(get_db),
    user=Depends(require_capability("create_exam")),
):
    """创建考试：按类型自动配置科目（仅 admin）。"""
    if conn.execute("SELECT 1 FROM exams WHERE name = %s", (body.name,)).fetchone():
        raise HTTPException(status_code=400, detail="考试名称已存在")

    if body.exam_type == "weekly":
        if body.subject_public_id is None:
            raise HTTPException(
                status_code=400, detail="周考必须指定 subject_public_id（单科）"
            )
        subjects = conn.execute(
            "SELECT id, name, full_score FROM subjects WHERE public_id = %s",
            (body.subject_public_id,),
        ).fetchall()
        if not subjects:
            raise HTTPException(status_code=404, detail="科目不存在")
    elif body.exam_type == "monthly":
        subjects = conn.execute(
            "SELECT id, name, full_score FROM subjects WHERE name = ANY(%s) ORDER BY sort_order",
            (MONTHLY_SUBJECTS,),
        ).fetchall()
        if len(subjects) != len(MONTHLY_SUBJECTS):
            raise HTTPException(
                status_code=400,
                detail="月考科目配置不完整（需要：语数英物化）",
            )
    else:  # midterm / final
        subjects = conn.execute(
            "SELECT id, name, full_score FROM subjects ORDER BY sort_order"
        ).fetchall()

    row = conn.execute(
        "INSERT INTO exams (name, exam_type, exam_date, status) "
        "VALUES (%s, %s, %s, 'draft') RETURNING id, public_id",
        (body.name, body.exam_type, body.exam_date),
    ).fetchone()
    exam_id = row["id"]
    for sub in subjects:
        conn.execute(
            "INSERT INTO exam_subjects (exam_id, subject_id, full_score) VALUES (%s, %s, %s)",
            (exam_id, sub["id"], sub["full_score"]),
        )
    # 创建考试时为全体在册学生建立成绩行（NULL=缺考），形成本次考试的名单快照
    conn.execute(
        """
        INSERT INTO scores (exam_id, student_id, subject_id, score)
        SELECT %s, st.id, es.subject_id, NULL
        FROM students st
        CROSS JOIN exam_subjects es
        WHERE st.status = 'active' AND es.exam_id = %s
        ON CONFLICT (exam_id, student_id, subject_id) DO NOTHING
        """,
        (exam_id, exam_id),
    )
    write_audit(
        conn,
        actor=user["username"],
        action="exam.create",
        table_name="exams",
        record_id=str(exam_id),
        new_value={
            "name": body.name,
            "exam_type": body.exam_type,
            "subjects": [s["name"] for s in subjects],
        },
    )
    return {
        "public_id": row["public_id"],
        "name": body.name,
        "exam_type": body.exam_type,
        "subjects": [s["name"] for s in subjects],
    }


@router.get("/exams/{exam_pid}")
def exam_detail(exam_pid: UUID, conn=Depends(get_db)):
    exam = conn.execute(
        "SELECT public_id, name, exam_type, exam_date, status, created_at "
        "FROM exams WHERE public_id = %s",
        (exam_pid,),
    ).fetchone()
    if exam is None:
        raise HTTPException(status_code=404, detail="考试不存在")
    exam["subjects"] = conn.execute(
        """
        SELECT s.public_id, s.name, es.full_score
        FROM exam_subjects es
        JOIN subjects s ON s.id = es.subject_id
        WHERE es.exam_id = (SELECT id FROM exams WHERE public_id = %s)
        ORDER BY s.sort_order
        """,
        (exam_pid,),
    ).fetchall()
    return exam


@router.get("/exams/{exam_pid}/students")
def exam_students(
    exam_pid: UUID,
    class_public_id: UUID | None = None,
    conn=Depends(get_db),
    user=Depends(require_capability("can_report_class")),
    scope=Depends(get_user_scope),
):
    exam = conn.execute(
        "SELECT id FROM exams WHERE public_id = %s", (exam_pid,)
    ).fetchone()
    if exam is None:
        raise HTTPException(status_code=404, detail="考试不存在")

    params: dict = {"exam_id": exam["id"]}
    class_clause = ""
    if class_public_id is not None:
        cls = conn.execute(
            "SELECT id FROM classes WHERE public_id = %s", (class_public_id,)
        ).fetchone()
        if cls is None:
            raise HTTPException(status_code=404, detail="班级不存在")
        assert_class_allowed(scope, cls["id"])
        class_clause = "AND st.class_id = %(class_id)s"
        params["class_id"] = cls["id"]
    else:
        if not capabilities_for(user)["can_report_grade"]:
            raise HTTPException(status_code=403, detail="无权限：查看年级报告")

    params["subject_ids"] = (
        None if scope["all_subjects"] else scope["subject_ids"]
    )
    return conn.execute(
        f"""
        SELECT st.public_id, st.student_no, st.name, c.name AS class,
               COALESCE(
                   (SELECT json_object_agg(sub.name, sc.score)
                    FROM scores sc
                    JOIN subjects sub ON sub.id = sc.subject_id
                    WHERE sc.exam_id = %(exam_id)s AND sc.student_id = st.id
                      AND (%(subject_ids)s::int[] IS NULL
                           OR sc.subject_id = ANY(%(subject_ids)s))),
                   '{{}}'::json
               ) AS scores
        FROM students st
        JOIN classes c ON c.id = st.class_id
        WHERE st.status = 'active' {class_clause}
          AND EXISTS (
              SELECT 1 FROM scores sc
              WHERE sc.exam_id = %(exam_id)s AND sc.student_id = st.id
          )
        ORDER BY st.class_id, st.student_no
        """,
        params,
    ).fetchall()
