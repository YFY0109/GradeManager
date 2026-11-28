"""学情总览：指标、学科对比、等级分布、分段、优劣势、班级对比。"""

from __future__ import annotations

import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from ..db import get_db
from ..permissions import (
    assert_class_allowed,
    capabilities_for,
    get_user_scope,
)
from ..stats_config import StatsConfig, load_stats_config
from .rankings import _class_id, _exam_id

router = APIRouter(
    prefix="/api",
    tags=["overview"],
    dependencies=[Depends(current_user)],
    responses={
        401: {"description": "未登录或 token 无效"},
        403: {"description": "无权访问该班级"},
        404: {"description": "考试或班级不存在"},
    },
)


def _f(value) -> float | None:
    return float(value) if value is not None else None


def _summary(values: list[float], config: StatsConfig, full_score: float):
    n = len(values)
    if not n:
        return {
            "participants": 0,
            "avg": None,
            "max": None,
            "min": None,
            "stddev": None,
            "excellent": 0,
            "good": 0,
            "pass": 0,
            "poor": 0,
            "excellent_rate": 0,
            "good_rate": 0,
            "pass_rate": 0,
            "poor_rate": 0,
        }
    avg = sum(values) / n
    stddev = math.sqrt(sum((v - avg) ** 2 for v in values) / n)
    excellent = sum(1 for v in values if v >= full_score * config.excellent)
    good = sum(1 for v in values if v >= full_score * config.good)
    pass_count = sum(1 for v in values if v >= full_score * config.pass_)
    poor = sum(1 for v in values if v <= full_score * config.poor)
    return {
        "participants": n,
        "avg": avg,
        "max": max(values),
        "min": min(values),
        "stddev": stddev,
        "excellent": excellent,
        "good": good,
        "pass": pass_count,
        "poor": poor,
        "excellent_rate": excellent / n,
        "good_rate": good / n,
        "pass_rate": pass_count / n,
        "poor_rate": poor / n,
    }


def _grade_distribution(
    totals: list[float], full_total: float, config: StatsConfig
) -> list[dict]:
    n = len(totals)
    levels = (
        config.ratio_levels
        if config.grade_mode == "ratio"
        else config.rank_levels
    )
    counts = {level.name: 0 for level in levels}
    if n:
        if config.grade_mode == "ratio":
            for total in totals:
                ratio = total / full_total if full_total else 0
                for level in levels:
                    if ratio >= level.threshold:
                        counts[level.name] += 1
                        break
                else:
                    counts[levels[-1].name] += 1
        else:
            ordered = sorted(totals, reverse=True)
            for pos, _total in enumerate(ordered, start=1):
                ratio = pos / n
                for level in levels:
                    if ratio <= level.threshold:
                        counts[level.name] += 1
                        break
                else:
                    counts[levels[-1].name] += 1
    return [
        {
            "name": level.name,
            "threshold": level.threshold,
            "count": counts[level.name],
            "ratio": counts[level.name] / n if n else 0,
        }
        for level in levels
    ]


def _segments(
    values: list[float], full_score: float, count: int
) -> list[dict]:
    n = len(values)
    buckets = [0] * count
    if n and full_score:
        for value in values:
            ratio = value / full_score
            idx = min(int(ratio * count), count - 1)
            buckets[idx] += 1
    result = []
    for i in range(count - 1, -1, -1):
        lo = i / count
        hi = (i + 1) / count
        result.append(
            {
                "label": f"{int(lo * 100)}-{int(hi * 100)}%",
                "min": lo * full_score,
                "max": hi * full_score,
                "count": buckets[i],
                "ratio": buckets[i] / n if n else 0,
            }
        )
    return result


@router.get("/exams/{exam_pid}/overview")
def overview(
    exam_pid: UUID,
    class_pid: UUID | None = None,
    conn=Depends(get_db),
    user=Depends(current_user),
    scope=Depends(get_user_scope),
):
    exam_id = _exam_id(conn, exam_pid)
    class_id = _class_id(conn, class_pid) if class_pid else None
    caps = capabilities_for(user)
    if not caps["view_stats"]:
        raise HTTPException(status_code=403, detail="无权限：查看汇总指标")
    if class_id is not None:
        if not caps["can_report_class"]:
            raise HTTPException(status_code=403, detail="无权限：查看班级报告")
        assert_class_allowed(scope, class_id)
    else:
        if not caps["can_report_grade"]:
            raise HTTPException(status_code=403, detail="无权限：查看年级报告")

    config = load_stats_config(conn)
    all_subjects = conn.execute(
        """
        SELECT s.id, s.public_id, s.name, es.full_score, s.sort_order
        FROM exam_subjects es
        JOIN subjects s ON s.id = es.subject_id
        WHERE es.exam_id = %s
        ORDER BY s.sort_order
        """,
        (exam_id,),
    ).fetchall()
    subjects = all_subjects
    if not scope["all_subjects"]:
        allowed = set(scope["subject_ids"])
        subjects = [s for s in all_subjects if s["id"] in allowed]
    if not caps["view_subject"]:
        subjects = []
    classes = conn.execute(
        "SELECT id, public_id, name FROM classes ORDER BY id"
    ).fetchall()
    students = conn.execute(
        """
        SELECT st.id, st.student_no, st.name, st.class_id, c.name AS class
        FROM students st
        JOIN classes c ON c.id = st.class_id
        WHERE st.status = 'active'
          AND EXISTS (
              SELECT 1 FROM scores sc
              WHERE sc.exam_id = %s AND sc.student_id = st.id
          )
        ORDER BY st.class_id, st.student_no
        """,
        (exam_id,),
    ).fetchall()
    score_rows = conn.execute(
        "SELECT student_id, subject_id, score FROM scores WHERE exam_id = %s",
        (exam_id,),
    ).fetchall()
    score_map = {
        (r["student_id"], r["subject_id"]): _f(r["score"]) for r in score_rows
    }

    scoped_students = (
        students
        if class_id is None
        else [s for s in students if s["class_id"] == class_id]
    )
    scoped_ids = {s["id"] for s in scoped_students}
    full_total = sum(float(s["full_score"]) for s in all_subjects)

    # 年级各科均分/标准差（用于超均率与 z 分数）
    grade_subject: dict[int, dict] = {}
    for sub in subjects:
        values = [
            score_map[(s["id"], sub["id"])]
            for s in students
            if score_map.get((s["id"], sub["id"])) is not None
        ]
        grade_subject[sub["id"]] = {
            "avg": (sum(values) / len(values)) if values else None,
            "stddev": (
                math.sqrt(
                    sum((v - sum(values) / len(values)) ** 2 for v in values)
                    / len(values)
                )
                if values
                else None
            ),
        }

    # 学科统计
    subject_rows = []
    for sub in subjects:
        values = [
            score_map[(s["id"], sub["id"])]
            for s in scoped_students
            if score_map.get((s["id"], sub["id"])) is not None
        ]
        summary = _summary(values, config, float(sub["full_score"]))
        summary.update(
            {
                "public_id": str(sub["public_id"]),
                "name": sub["name"],
                "full_score": float(sub["full_score"]),
                "absent": len(scoped_students) - summary["participants"],
                "above_avg_rate": (
                    summary["avg"] / grade_subject[sub["id"]]["avg"]
                    if summary["avg"] is not None
                    and grade_subject[sub["id"]]["avg"]
                    else None
                ),
            }
        )
        subject_rows.append(summary)

    # 学科排名在班级视角下计算（该班该科在年级各班中的排名）

    # 总分（齐全学生）
    complete = []
    for student in scoped_students:
        values = [
            score_map.get((student["id"], sub["id"])) for sub in all_subjects
        ]
        if values and all(v is not None for v in values):
            complete.append((student["id"], sum(values)))

    total_values = [total for _, total in complete]
    total_summary = _summary(total_values, config, full_total)
    total_summary.update(
        {
            "public_id": None,
            "name": "总分",
            "full_score": full_total,
            "absent": len(scoped_students) - len(complete),
            "rank": None,
            "above_avg_rate": None,
        }
    )

    # 等级分布/分段（总分）；无总分权限时清空
    if capabilities_for(user)["view_total"]:
        grade_levels = _grade_distribution(total_values, full_total, config)
        segments = _segments(total_values, full_total, config.segment_count)
    else:
        total_summary = None
        grade_levels = []
        segments = []

    # 优劣势学科（班级视角）
    advantages = {"strong": [], "weak": [], "z_scores": {}}
    if class_id is not None:
        z_scores = {}
        for row in subject_rows:
            sub = next(s for s in subjects if s["name"] == row["name"])
            grade = grade_subject[sub["id"]]
            if (
                row["avg"] is not None
                and grade["avg"] is not None
                and grade["stddev"]
            ):
                z_scores[row["name"]] = (
                    row["avg"] - grade["avg"]
                ) / grade["stddev"]
        ordered = sorted(z_scores.items(), key=lambda item: item[1], reverse=True)
        advantages = {
            "strong": [name for name, z in ordered if z > 0],
            "weak": [name for name, z in ordered if z < 0],
            "z_scores": z_scores,
        }

    # 班级对比
    class_rows = []
    for cls in classes:
        cls_students = [s for s in students if s["class_id"] == cls["id"]]
        cls_complete = []
        for student in cls_students:
            values = [
                score_map.get((student["id"], sub["id"])) for sub in all_subjects
            ]
            if values and all(v is not None for v in values):
                cls_complete.append(sum(values))
        cls_subject_avg = {}
        for sub in subjects:
            values = [
                score_map[(s["id"], sub["id"])]
                for s in cls_students
                if score_map.get((s["id"], sub["id"])) is not None
            ]
            cls_subject_avg[sub["name"]] = (
                (sum(values) / len(values)) if values else None
            )
        class_rows.append(
            {
                "id": cls["id"],
                "class_public_id": str(cls["public_id"]),
                "class": cls["name"],
                "students": len(cls_students),
                "complete": len(cls_complete),
                "total_avg": (
                    (sum(cls_complete) / len(cls_complete))
                    if cls_complete
                    else None
                ),
                "subject_avg": cls_subject_avg,
            }
        )

    if not caps["view_total"]:
        for row in class_rows:
            row["total_avg"] = None
            row["total_max"] = None
            row["total_min"] = None

    # 班级视角：该班该科在年级各班中的排名（1=最高）
    for row in subject_rows:
        row["rank"] = None
    current_public = None
    if class_id is not None:
        current_public = str(
            next(c["public_id"] for c in classes if c["id"] == class_id)
        )
    if class_id is not None and caps["can_rank_grade"]:
        for row in subject_rows:
            name = row["name"]
            values = [
                (c["class_public_id"], c["subject_avg"].get(name))
                for c in class_rows
                if c["subject_avg"].get(name) is not None
            ]
            values.sort(key=lambda item: item[1], reverse=True)
            for pos, (public_id, _avg) in enumerate(values, start=1):
                if public_id == current_public:
                    row["rank"] = pos
                    break
    # 班级报告只返回当前班级，不能泄露其他班级的对比数据
    if class_id is not None:
        class_rows = [
            c for c in class_rows if c["class_public_id"] == current_public
        ]
    for row in class_rows:
        row.pop("id", None)

    return {
        "exam_public_id": str(exam_pid),
        "scope": {
            "type": "class" if class_id is not None else "grade",
            "class": (
                next(
                    {
                        "public_id": str(c["public_id"]),
                        "name": c["name"],
                    }
                    for c in classes
                    if c["id"] == class_id
                )
                if class_id is not None
                else None
            ),
        },
        "config": config.model_dump(by_alias=True),
        "students": len(scoped_students),
        "full_total": full_total,
        "subjects": subject_rows,
        "total": total_summary,
        "grade_levels": grade_levels,
        "segments": segments,
        "advantages": advantages,
        "classes": class_rows,
    }
