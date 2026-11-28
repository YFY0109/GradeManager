"""排名与统计路由。

排名仅包含"五科齐全"的学生（任意一科缺考不进入排名池）。
总分排名与单科排名使用独立路径，避免参数歧义。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from ..db import get_db
from ..permissions import (
    assert_class_allowed,
    assert_subject_allowed,
    capabilities_for,
    get_user_scope,
    require_capability,
)
from ..stats_config import load_stats_config

COMMON_RESPONSES = {
    400: {"description": "请求参数或业务校验错误"},
    401: {"description": "未登录或 token 无效"},
    404: {"description": "资源不存在"},
}

router = APIRouter(
    prefix="/api",
    tags=["rankings"],
    dependencies=[Depends(current_user)],
    responses=COMMON_RESPONSES,
)


def _exam_id(conn, exam_pid: UUID) -> int:
    row = conn.execute("SELECT id FROM exams WHERE public_id = %s", (exam_pid,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="考试不存在")
    return row["id"]


def _class_id(conn, class_pid: UUID) -> int:
    row = conn.execute("SELECT id FROM classes WHERE public_id = %s", (class_pid,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="班级不存在")
    return row["id"]


def _subject_id(conn, subject_pid: UUID) -> int:
    row = conn.execute("SELECT id FROM subjects WHERE public_id = %s", (subject_pid,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="科目不存在")
    return row["id"]


def query_rank(
    conn,
    exam_id: int,
    subject_id: int | None = None,
    class_id: int | None = None,
    scope: str = "grade",
    class_ids: list[int] | None = None,
):
    """分数序排名（同时给出年级名次与班级名次）。

    - 总分排名池：该考试所有科目均有成绩的学生
    - 单科排名池：该科有成绩的学生（与 Excel 一致）
    - 分数降序；RANK 并列同名次
    - 年级名次：全年级 RANK；班级名次：PARTITION BY 班级 RANK
    - scope 只决定返回顺序（class 按班内名次，grade 按年级名次）
    - class_ids 用于数据范围过滤（None = 全部班级）
    """
    if subject_id is None:
        base = """
        WITH exam_scores AS (
            SELECT sc.student_id, sc.subject_id, sc.score
            FROM scores sc
            JOIN exam_subjects es
              ON es.exam_id = sc.exam_id AND es.subject_id = sc.subject_id
            WHERE sc.exam_id = %(exam_id)s
        ),
        per AS (
            SELECT student_id, SUM(score) AS value
            FROM exam_scores GROUP BY student_id
        ),
        ok AS (
            SELECT student_id FROM exam_scores
            GROUP BY student_id
            HAVING count(*) = (
                       SELECT count(*) FROM exam_subjects
                       WHERE exam_id = %(exam_id)s
                   )
               AND bool_and(score IS NOT NULL)
        ),
        base AS (
            SELECT st.public_id AS student_public_id, st.student_no, st.name,
                   st.class_id, c.public_id AS class_public_id, c.name AS class,
                   p.value
            FROM per p
            JOIN ok USING (student_id)
            JOIN students st ON st.id = p.student_id
            JOIN classes c ON c.id = st.class_id
            WHERE st.status = 'active'
        )
        """
        params = {"exam_id": exam_id, "class_id": class_id}
    else:
        base = """
        WITH base AS (
            SELECT st.public_id AS student_public_id, st.student_no, st.name,
                   st.class_id, c.public_id AS class_public_id, c.name AS class,
                   sc.score AS value
            FROM scores sc
            JOIN exam_subjects es
              ON es.exam_id = sc.exam_id AND es.subject_id = sc.subject_id
            JOIN students st ON st.id = sc.student_id
            JOIN classes c ON c.id = st.class_id
            WHERE sc.exam_id = %(exam_id)s AND sc.subject_id = %(subject_id)s
              AND sc.score IS NOT NULL
              AND st.status = 'active'
        )
        """
        params = {
            "exam_id": exam_id,
            "subject_id": subject_id,
            "class_id": class_id,
        }

    order_col = "class_rank" if (scope == "class" and class_id is not None) else "grade_rank"
    params["class_ids"] = class_ids
    sql = (
        base
        + f"""
        , ranked AS (
            SELECT *,
                   RANK() OVER (ORDER BY value DESC) AS grade_rank,
                   RANK() OVER (PARTITION BY class_id ORDER BY value DESC) AS class_rank
            FROM base
        )
        SELECT student_public_id, student_no, name, class_public_id, class,
               value, grade_rank, class_rank
        FROM ranked
        WHERE (%(class_id)s::int IS NULL OR class_id = %(class_id)s)
          AND (%(class_ids)s::int[] IS NULL OR class_id = ANY(%(class_ids)s))
        ORDER BY {order_col}, student_no
        """
    )
    return conn.execute(sql, params).fetchall()


def _scope_class_ids(scope: dict) -> list[int] | None:
    return None if scope["all_classes"] else scope["class_ids"]


@router.get("/exams/{exam_pid}/rankings/total")
def grade_total_rank(
    exam_pid: UUID,
    conn=Depends(get_db),
    user=Depends(require_capability("can_rank_grade")),
    scope=Depends(get_user_scope),
):
    if not capabilities_for(user)["view_total"]:
        raise HTTPException(status_code=403, detail="无权限：查看总分")
    return query_rank(
        conn, _exam_id(conn, exam_pid), class_ids=_scope_class_ids(scope)
    )


@router.get("/exams/{exam_pid}/rankings/subjects/{subject_pid}")
def grade_subject_rank(
    exam_pid: UUID,
    subject_pid: UUID,
    conn=Depends(get_db),
    scope=Depends(get_user_scope),
    user=Depends(require_capability("can_rank_grade")),
):
    if not capabilities_for(user)["view_subject"]:
        raise HTTPException(status_code=403, detail="无权限：查看单科")
    subject_id = _subject_id(conn, subject_pid)
    assert_subject_allowed(scope, subject_id)
    return query_rank(
        conn,
        _exam_id(conn, exam_pid),
        subject_id=subject_id,
        class_ids=_scope_class_ids(scope),
    )


@router.get("/exams/{exam_pid}/rankings/classes/{class_pid}/total")
def class_total_rank(
    exam_pid: UUID,
    class_pid: UUID,
    conn=Depends(get_db),
    user=Depends(require_capability("can_rank_class")),
    scope=Depends(get_user_scope),
):
    if not capabilities_for(user)["view_total"]:
        raise HTTPException(status_code=403, detail="无权限：查看总分")
    class_id = _class_id(conn, class_pid)
    assert_class_allowed(scope, class_id)
    return query_rank(
        conn,
        _exam_id(conn, exam_pid),
        class_id=class_id,
        scope="class",
    )


@router.get("/exams/{exam_pid}/rankings/classes/{class_pid}/subjects/{subject_pid}")
def class_subject_rank(
    exam_pid: UUID,
    class_pid: UUID,
    subject_pid: UUID,
    conn=Depends(get_db),
    scope=Depends(get_user_scope),
    user=Depends(require_capability("can_rank_class")),
):
    if not capabilities_for(user)["view_subject"]:
        raise HTTPException(status_code=403, detail="无权限：查看单科")
    class_id = _class_id(conn, class_pid)
    subject_id = _subject_id(conn, subject_pid)
    assert_class_allowed(scope, class_id)
    assert_subject_allowed(scope, subject_id)
    return query_rank(
        conn,
        _exam_id(conn, exam_pid),
        subject_id=subject_id,
        class_id=class_id,
        scope="class",
    )


def stats_data(exam_pid: UUID, conn):
    exam_id = _exam_id(conn, exam_pid)
    config = load_stats_config(conn)
    thresholds = {
        "exam_id": exam_id,
        "excellent": config.excellent,
        "good": config.good,
        "pass": config.pass_,
        "poor": config.poor,
    }

    ok_rows = conn.execute(
        """
        SELECT sc.student_id FROM scores sc
        JOIN exam_subjects es
          ON es.exam_id = sc.exam_id AND es.subject_id = sc.subject_id
        JOIN students st ON st.id = sc.student_id
        WHERE sc.exam_id = %s AND st.status = 'active'
        GROUP BY sc.student_id
        HAVING count(*) = (
                   SELECT count(*) FROM exam_subjects
                   WHERE exam_id = %s
               )
           AND bool_and(sc.score IS NOT NULL)
        """,
        (exam_id, exam_id),
    ).fetchall()
    ok_ids = [r["student_id"] for r in ok_rows]

    totals = conn.execute(
        """
        SELECT st.id AS student_id, st.class_id, c.public_id AS class_public_id,
               c.name AS class, SUM(sc.score) AS total
        FROM scores sc
        JOIN exam_subjects es
          ON es.exam_id = sc.exam_id AND es.subject_id = sc.subject_id
        JOIN students st ON st.id = sc.student_id
        JOIN classes c ON c.id = st.class_id
        WHERE sc.exam_id = %s AND sc.student_id = ANY(%s)
          AND st.status = 'active'
        GROUP BY st.id, st.class_id, c.public_id, c.name
        """,
        (exam_id, ok_ids),
    ).fetchall()

    subject_avgs = conn.execute(
        """
        SELECT sub.id AS subject_id, sub.name AS subject, es.full_score,
               AVG(sc.score) AS avg_score,
               STDDEV_POP(sc.score) AS stddev,
               count(sc.score) AS participants
        FROM scores sc
        JOIN students st ON st.id = sc.student_id
        JOIN exam_subjects es
          ON es.exam_id = sc.exam_id AND es.subject_id = sc.subject_id
        JOIN subjects sub ON sub.id = sc.subject_id
        WHERE sc.exam_id = %s AND sc.score IS NOT NULL
          AND st.status = 'active'
        GROUP BY sub.id, sub.name, es.full_score, sub.sort_order
        ORDER BY sub.sort_order
        """,
        (exam_id,),
    ).fetchall()

    class_subject_avgs = conn.execute(
        """
        SELECT st.class_id, sub.name AS subject, AVG(sc.score) AS avg_score
        FROM scores sc
        JOIN students st ON st.id = sc.student_id
        JOIN exam_subjects es
          ON es.exam_id = sc.exam_id AND es.subject_id = sc.subject_id
        JOIN subjects sub ON sub.id = sc.subject_id
        WHERE sc.exam_id = %s AND sc.score IS NOT NULL
          AND st.status = 'active'
        GROUP BY st.class_id, sub.name, sub.sort_order
        ORDER BY st.class_id, sub.sort_order
        """,
        (exam_id,),
    ).fetchall()
    class_avg_map: dict[int, dict[str, float]] = {}
    for row in class_subject_avgs:
        class_avg_map.setdefault(row["class_id"], {})[row["subject"]] = float(
            row["avg_score"]
        )

    rates = conn.execute(
        """
        SELECT st.class_id, c.name AS class, sub.id AS subject_id, sub.name AS subject,
               es.full_score,
               count(sc.score) FILTER (WHERE sc.score IS NOT NULL) AS participants,
               count(*) FILTER (WHERE sc.score >= es.full_score * %(excellent)s) AS excellent,
               count(*) FILTER (WHERE sc.score >= es.full_score * %(good)s) AS good,
               count(*) FILTER (WHERE sc.score >= es.full_score * %(pass)s) AS pass,
               count(*) FILTER (WHERE sc.score <= es.full_score * %(poor)s) AS poor
        FROM scores sc
        JOIN students st ON st.id = sc.student_id
        JOIN classes c ON c.id = st.class_id
        JOIN exam_subjects es
          ON es.exam_id = sc.exam_id AND es.subject_id = sc.subject_id
        JOIN subjects sub ON sub.id = sc.subject_id
        WHERE sc.exam_id = %(exam_id)s
          AND st.status = 'active'
        GROUP BY st.class_id, c.name, sub.id, sub.name, es.full_score, sub.sort_order
        ORDER BY st.class_id, sub.sort_order
        """,
        thresholds,
    ).fetchall()

    grade_rates = conn.execute(
        """
        SELECT sub.id AS subject_id, sub.name AS subject, es.full_score,
               count(sc.score) FILTER (WHERE sc.score IS NOT NULL) AS participants,
               count(*) FILTER (WHERE sc.score >= es.full_score * %(excellent)s) AS excellent,
               count(*) FILTER (WHERE sc.score >= es.full_score * %(good)s) AS good,
               count(*) FILTER (WHERE sc.score >= es.full_score * %(pass)s) AS pass,
               count(*) FILTER (WHERE sc.score <= es.full_score * %(poor)s) AS poor
        FROM scores sc
        JOIN students st ON st.id = sc.student_id
        JOIN exam_subjects es
          ON es.exam_id = sc.exam_id AND es.subject_id = sc.subject_id
        JOIN subjects sub ON sub.id = sc.subject_id
        WHERE sc.exam_id = %(exam_id)s
          AND st.status = 'active'
        GROUP BY sub.id, sub.name, es.full_score, sub.sort_order
        ORDER BY sub.sort_order
        """,
        thresholds,
    ).fetchall()

    full_total = conn.execute(
        "SELECT COALESCE(SUM(full_score), 0) AS v FROM exam_subjects WHERE exam_id = %s",
        (exam_id,),
    ).fetchone()["v"]

    def segments(values):
        seg = {"90%+": 0, "80-90%": 0, "70-80%": 0, "60-70%": 0, "<60%": 0}
        for v in values:
            ratio = float(v) / float(full_total) if full_total else 0
            if ratio >= 0.9:
                seg["90%+"] += 1
            elif ratio >= 0.8:
                seg["80-90%"] += 1
            elif ratio >= 0.7:
                seg["70-80%"] += 1
            elif ratio >= 0.6:
                seg["60-70%"] += 1
            else:
                seg["<60%"] += 1
        return seg

    class_names = {
        r["id"]: (r["public_id"], r["name"])
        for r in conn.execute("SELECT id, public_id, name FROM classes").fetchall()
    }
    per_class = {}
    for t in totals:
        per_class.setdefault(t["class_id"], []).append(float(t["total"]))

    def rates_for(class_id=None):
        out = {}
        for r in rates:
            if class_id is not None and r["class_id"] != class_id:
                continue
            p = r["participants"]
            out[r["subject"]] = {
                "participants": p,
                "excellent": r["excellent"],
                "good": r["good"],
                "pass": r["pass"],
                "poor": r["poor"],
                "excellent_rate": (r["excellent"] / p) if p else 0,
                "good_rate": (r["good"] / p) if p else 0,
                "pass_rate": (r["pass"] / p) if p else 0,
                "poor_rate": (r["poor"] / p) if p else 0,
            }
        return out

    classes_out = []
    for cid, (cpid, name) in class_names.items():
        ts = per_class.get(cid, [])
        classes_out.append(
            {
                "class_public_id": cpid,
                "class": name,
                "students": len(ts),
                "total_avg": (sum(ts) / len(ts)) if ts else None,
                "total_max": max(ts) if ts else None,
                "total_min": min(ts) if ts else None,
                "subject_avg": class_avg_map.get(cid, {}),
                "subject_rates": rates_for(cid),
            }
        )

    all_totals = [float(t["total"]) for t in totals]

    return {
        "exam_public_id": exam_pid,
        "full_total": float(full_total),
        "grade": {
            "students": len(all_totals),
            "total_avg": (sum(all_totals) / len(all_totals)) if all_totals else None,
            "total_max": max(all_totals) if all_totals else None,
            "total_min": min(all_totals) if all_totals else None,
            "subject_avg": {r["subject"]: float(r["avg_score"]) for r in subject_avgs},
            "subject_rates": {
                r["subject"]: {
                    "participants": r["participants"],
                    "excellent": r["excellent"],
                    "good": r["good"],
                    "pass": r["pass"],
                    "poor": r["poor"],
                    "excellent_rate": (r["excellent"] / r["participants"]) if r["participants"] else 0,
                    "good_rate": (r["good"] / r["participants"]) if r["participants"] else 0,
                    "pass_rate": (r["pass"] / r["participants"]) if r["participants"] else 0,
                    "poor_rate": (r["poor"] / r["participants"]) if r["participants"] else 0,
                }
                for r in grade_rates
            },
            "total_segments": segments(all_totals),
        },
        "classes": classes_out,
    }


def filter_stats(
    data: dict,
    *,
    conn,
    scope: dict,
    include_total: bool = True,
) -> dict:
    """按用户范围裁剪统计结果（班级/科目/总分可见性）。"""
    class_public_ids: set[str] | None = None
    if not scope["all_classes"]:
        rows = conn.execute(
            "SELECT public_id FROM classes WHERE id = ANY(%s)",
            (scope["class_ids"],),
        ).fetchall()
        class_public_ids = {str(r["public_id"]) for r in rows}

    subject_names: set[str] | None = None
    if not scope["all_subjects"]:
        rows = conn.execute(
            "SELECT name FROM subjects WHERE id = ANY(%s)",
            (scope["subject_ids"],),
        ).fetchall()
        subject_names = {r["name"] for r in rows}

    grade = data["grade"]
    if not include_total:
        data["full_total"] = None
        grade["students"] = None
        grade["total_avg"] = None
        grade["total_max"] = None
        grade["total_min"] = None
        grade["total_segments"] = {}
    if subject_names is not None:
        grade["subject_avg"] = {
            k: v for k, v in grade["subject_avg"].items() if k in subject_names
        }
        grade["subject_rates"] = {
            k: v for k, v in grade["subject_rates"].items() if k in subject_names
        }

    classes = []
    for item in data["classes"]:
        if (
            class_public_ids is not None
            and str(item["class_public_id"]) not in class_public_ids
        ):
            continue
        if not include_total:
            item["students"] = None
            item["total_avg"] = None
            item["total_max"] = None
            item["total_min"] = None
        if subject_names is not None:
            item["subject_avg"] = {
                k: v for k, v in item["subject_avg"].items() if k in subject_names
            }
            item["subject_rates"] = {
                k: v for k, v in item["subject_rates"].items() if k in subject_names
            }
        classes.append(item)
    data["classes"] = classes
    return data


@router.get("/exams/{exam_pid}/stats")
def stats(
    exam_pid: UUID,
    conn=Depends(get_db),
    user=Depends(require_capability("can_report_grade")),
    scope=Depends(get_user_scope),
):
    if not capabilities_for(user)["view_stats"]:
        raise HTTPException(status_code=403, detail="无权限：查看汇总指标")
    data = stats_data(exam_pid, conn)
    return filter_stats(
        data,
        conn=conn,
        scope=scope,
        include_total=capabilities_for(user)["view_total"],
    )
