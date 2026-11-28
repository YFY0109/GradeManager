"""学情总览：指标、学科对比、等级分布、分段、优劣势、班级对比、扩展分析。"""

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


def _ratio(part: float | None, whole: float | None) -> float | None:
    """安全比例：分母为 0/None 时返回 None。"""
    if part is None or not whole:
        return None
    return part / whole


def _median(values: list[float]) -> float | None:
    ordered = sorted(values)
    n = len(ordered)
    if not n:
        return None
    middle = n // 2
    if n % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _summary(values: list[float], config: StatsConfig, full_score: float):
    n = len(values)
    if not n:
        return {
            "participants": 0,
            "avg": None,
            "max": None,
            "min": None,
            "median": None,
            "range": None,
            "stddev": None,
            "cv": None,
            "full_count": 0,
            "score_rate": None,
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
        "median": _median(values),
        "range": max(values) - min(values),
        "stddev": stddev,
        "cv": _ratio(stddev, avg),
        "full_count": (
            sum(1 for v in values if v >= full_score) if full_score > 0 else 0
        ),
        "score_rate": _ratio(avg, full_score),
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


def _segment_counts(values: list[float], full_score: float, count: int) -> list[int]:
    """按 _segments 相同的倒序顺序返回各班人数。"""
    buckets = [0] * count
    if full_score:
        for value in values:
            idx = min(int(value / full_score * count), count - 1)
            buckets[idx] += 1
    return list(reversed(buckets))


def _rank_class_averages(averages: list[tuple[str, float | None]]) -> dict[str, int]:
    """按均分降序排名，同分并列，无成绩的班级不排名。"""
    ranked = sorted(
        ((public_id, average) for public_id, average in averages if average is not None),
        key=lambda item: item[1],
        reverse=True,
    )
    ranks: dict[str, int] = {}
    previous = None
    rank = 0
    for position, (public_id, average) in enumerate(ranked, start=1):
        if average != previous:
            rank = position
        ranks[public_id] = rank
        previous = average
    return ranks


def _complete_students(
    students: list[dict], subjects: list[dict], score_map: dict
) -> list[tuple[dict, float]]:
    """返回所有考试科目齐全的学生及其总分。"""
    complete = []
    for student in students:
        values = [score_map.get((student["id"], sub["id"])) for sub in subjects]
        if values and all(value is not None for value in values):
            complete.append((student, sum(values)))
    return complete


def _student_ranks(complete: list[tuple[dict, float]]) -> dict[int, int]:
    """总分排名：降序，同分并列，返回 student_id -> 名次。"""
    ordered = sorted(complete, key=lambda item: item[1], reverse=True)
    ranks: dict[int, int] = {}
    previous = None
    rank = 0
    for position, (student, total) in enumerate(ordered, start=1):
        if total != previous:
            rank = position
        ranks[student["id"]] = rank
        previous = total
    return ranks


def _student_brief(student: dict, value: float) -> dict:
    return {
        "student_public_id": str(student["public_id"]),
        "student_no": student["student_no"],
        "name": student["name"],
        "class": student["class"],
        "value": value,
    }


def _build_analytics(
    *,
    class_id: int | None,
    caps: dict,
    config: StatsConfig,
    all_subjects: list[dict],
    subjects: list[dict],
    classes: list[dict],
    students: list[dict],
    score_map: dict,
    full_total: float,
) -> dict:
    """构建扩展分析（全部基于已加载的内存数据）。"""
    class_students = {
        cls["id"]: [s for s in students if s["class_id"] == cls["id"]]
        for cls in classes
    }
    grade_complete = _complete_students(students, all_subjects, score_map)
    class_complete = {
        cls["id"]: _complete_students(class_students[cls["id"]], all_subjects, score_map)
        for cls in classes
    }
    grade_ranks = _student_ranks(grade_complete)
    max_rank = max(grade_ranks.values()) if grade_ranks else 0
    top_n = min(config.top_n, len(grade_complete)) if grade_complete else 0
    visible_classes = (
        classes if class_id is None else [c for c in classes if c["id"] == class_id]
    )
    can_rank = (
        caps["can_rank_grade"] if class_id is None else caps["can_rank_class"]
    )

    # 优秀生 / 学困生
    top_bottom = None
    if can_rank and top_n and caps["view_total"]:
        rows = []
        for cls in visible_classes:
            items = class_complete[cls["id"]]
            eligible = len(items)
            top_count = sum(
                1
                for student, _total in items
                if grade_ranks.get(student["id"], 0) <= top_n
            )
            bottom_count = sum(
                1
                for student, _total in items
                if max_rank and grade_ranks.get(student["id"], 0) > max_rank - top_n
            )
            rows.append(
                {
                    "class": cls["name"],
                    "eligible": eligible,
                    "top_count": top_count,
                    "top_ratio": _ratio(top_count, eligible),
                    "bottom_count": bottom_count,
                    "bottom_ratio": _ratio(bottom_count, eligible),
                }
            )
        top_bottom = {"n": top_n, "classes": rows}

    # 名次段人数
    rank_bands = None
    if can_rank and grade_ranks and caps["view_total"]:
        bands = [10, 50, 100, 200]
        rows = []
        for cls in visible_classes:
            items = class_complete[cls["id"]]
            eligible = len(items)
            counts = {
                str(band): sum(
                    1
                    for student, _total in items
                    if grade_ranks.get(student["id"], 0) <= band
                )
                for band in bands
            }
            rows.append(
                {
                    "class": cls["name"],
                    "eligible": eligible,
                    "counts": counts,
                    "ratios": {
                        band: _ratio(count, eligible)
                        for band, count in counts.items()
                    },
                }
            )
        rank_bands = {"bands": bands, "classes": rows}

    # 分数段按班（总分）
    class_segments = None
    if caps["view_total"] and full_total:
        segment_meta = _segments(
            [total for _student, total in grade_complete],
            full_total,
            config.segment_count,
        )
        labels = [item["label"] for item in segment_meta]
        rows = []
        for cls in visible_classes:
            values = [total for _student, total in class_complete[cls["id"]]]
            counts_list = _segment_counts(values, full_total, config.segment_count)
            counts = dict(zip(labels, counts_list))
            rows.append(
                {
                    "class": cls["name"],
                    "eligible": len(values),
                    "counts": counts,
                    "ratios": {
                        label: _ratio(count, len(values))
                        for label, count in counts.items()
                    },
                }
            )
        class_segments = {
            "segments": [
                {"label": item["label"], "min": item["min"], "max": item["max"]}
                for item in segment_meta
            ],
            "classes": rows,
        }

    # 学科均衡度（学生各科得分率的标准差/极差，按班汇总）
    balance = None
    if caps["view_subject"] and len(subjects) >= 2:
        rows = []
        for cls in visible_classes:
            stds = []
            ranges = []
            for student, _total in class_complete[cls["id"]]:
                rates = []
                for sub in subjects:
                    score = score_map.get((student["id"], sub["id"]))
                    if score is None:
                        rates = []
                        break
                    rates.append(score / float(sub["full_score"]))
                if len(rates) != len(subjects):
                    continue
                mean = sum(rates) / len(rates)
                stds.append(
                    math.sqrt(sum((rate - mean) ** 2 for rate in rates) / len(rates))
                )
                ranges.append(max(rates) - min(rates))
            rows.append(
                {
                    "class": cls["name"],
                    "eligible": len(stds),
                    "avg_std": (sum(stds) / len(stds)) if stds else None,
                    "avg_range": (sum(ranges) / len(ranges)) if ranges else None,
                }
            )
        balance = {"subjects": [sub["name"] for sub in subjects], "classes": rows}

    # 班级离散度（各班各科标准差/变异系数）
    dispersion = None
    if caps["view_subject"] and subjects:
        rows = []
        for cls in visible_classes:
            cls_students = class_students[cls["id"]]
            values = {}
            for sub in subjects:
                scores = [
                    score_map[(s["id"], sub["id"])]
                    for s in cls_students
                    if score_map.get((s["id"], sub["id"])) is not None
                ]
                n = len(scores)
                if n:
                    avg = sum(scores) / n
                    stddev = math.sqrt(
                        sum((value - avg) ** 2 for value in scores) / n
                    )
                else:
                    avg = None
                    stddev = None
                values[sub["name"]] = {
                    "participants": n,
                    "stddev": stddev,
                    "cv": _ratio(stddev, avg),
                }
            rows.append({"class": cls["name"], "values": values})
        dispersion = {
            "subjects": [sub["name"] for sub in subjects],
            "classes": rows,
        }

    # 临界生对比
    lines = config.cutoff_lines
    critical = {
        "configured": bool(lines),
        "lines": [],
        "total": [],
        "subjects": [],
    }
    for line in lines:
        critical["lines"].append(
            {
                "name": line.name,
                "total": line.total,
                "subject_ratio": line.subject_ratio,
                "margin": config.critical_margin,
                "subject_margin": config.subject_margin,
            }
        )
        if caps["view_total"] and line.total is not None:
            class_rows = []
            for cls in visible_classes:
                items = class_complete[cls["id"]]
                hits = [
                    (student, total)
                    for student, total in items
                    if abs(total - line.total) <= config.critical_margin
                ]
                row = {
                    "class": cls["name"],
                    "eligible": len(items),
                    "count": len(hits),
                    "ratio": _ratio(len(hits), len(items)),
                }
                if class_id is not None:
                    row["students"] = [
                        _student_brief(student, total) for student, total in hits
                    ]
                class_rows.append(row)
            critical["total"].append(
                {
                    "line": line.name,
                    "total": line.total,
                    "margin": config.critical_margin,
                    "classes": class_rows,
                }
            )
        if caps["view_subject"] and line.subject_ratio is not None:
            for sub in subjects:
                full_score = float(sub["full_score"])
                class_rows = []
                for cls in visible_classes:
                    hits = []
                    valid = 0
                    for student in class_students[cls["id"]]:
                        score = score_map.get((student["id"], sub["id"]))
                        if score is None:
                            continue
                        valid += 1
                        if abs(score / full_score - line.subject_ratio) <= config.subject_margin:
                            hits.append((student, score))
                    row = {
                        "class": cls["name"],
                        "participants": valid,
                        "count": len(hits),
                        "ratio": _ratio(len(hits), valid),
                    }
                    if class_id is not None:
                        row["students"] = [
                            _student_brief(student, score) for student, score in hits
                        ]
                    class_rows.append(row)
                critical["subjects"].append(
                    {
                        "line": line.name,
                        "subject": sub["name"],
                        "ratio": line.subject_ratio,
                        "margin": config.subject_margin,
                        "classes": class_rows,
                    }
                )

    # 进线分析
    cutoffs = {"configured": bool(lines), "lines": []}
    for line in lines:
        grade_online = {
            student["id"]
            for student, total in grade_complete
            if line.total is not None and total >= line.total
        }
        class_rows = []
        for cls in visible_classes:
            items = class_complete[cls["id"]]
            eligible = len(items)
            row = {"class": cls["name"], "eligible": eligible}
            if caps["view_total"] and line.total is not None:
                online = sum(1 for _student, total in items if total >= line.total)
                row.update(
                    {
                        "total_online": online,
                        "total_rate": _ratio(online, eligible),
                        "contribution_rate": _ratio(online, len(grade_online)),
                    }
                )
            else:
                row.update(
                    {
                        "total_online": None,
                        "total_rate": None,
                        "contribution_rate": None,
                    }
                )
            subject_rows = {}
            double_rows = {}
            if caps["view_subject"] and line.subject_ratio is not None:
                for sub in subjects:
                    full_score = float(sub["full_score"])
                    threshold = full_score * line.subject_ratio
                    valid = [
                        score_map[(s["id"], sub["id"])]
                        for s in class_students[cls["id"]]
                        if score_map.get((s["id"], sub["id"])) is not None
                    ]
                    online_count = sum(1 for value in valid if value >= threshold)
                    subject_rows[sub["name"]] = {
                        "online": online_count,
                        "participants": len(valid),
                        "rate": _ratio(online_count, len(valid)),
                    }
                    if line.total is not None and caps["view_total"]:
                        double_count = sum(
                            1
                            for student, total in items
                            if total >= line.total
                            and score_map.get((student["id"], sub["id"])) is not None
                            and score_map[(student["id"], sub["id"])] >= threshold
                        )
                        double_rows[sub["name"]] = {
                            "online": double_count,
                            "rate": _ratio(double_count, eligible),
                        }
                    else:
                        double_rows[sub["name"]] = {"online": None, "rate": None}
            row["subjects"] = subject_rows
            row["double"] = double_rows
            class_rows.append(row)
        cutoffs["lines"].append(
            {
                "name": line.name,
                "total": line.total,
                "subject_ratio": line.subject_ratio,
                "classes": class_rows,
            }
        )

    return {
        "top_bottom": top_bottom,
        "rank_bands": rank_bands,
        "class_segments": class_segments,
        "balance": balance,
        "dispersion": dispersion,
        "critical": critical,
        "cutoffs": cutoffs,
    }


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
        SELECT st.id, st.public_id, st.student_no, st.name, st.class_id,
               c.name AS class
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

    # 学科统计 + 单科等级/分段
    subject_rows = []
    subject_levels: dict[str, list[dict]] = {}
    subject_segments: dict[str, list[dict]] = {}
    for sub in subjects:
        full_score = float(sub["full_score"])
        values = [
            score_map[(s["id"], sub["id"])]
            for s in scoped_students
            if score_map.get((s["id"], sub["id"])) is not None
        ]
        summary = _summary(values, config, full_score)
        summary.update(
            {
                "public_id": str(sub["public_id"]),
                "name": sub["name"],
                "full_score": full_score,
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
        subject_levels[sub["name"]] = _grade_distribution(
            values, full_score, config
        )
        subject_segments[sub["name"]] = _segments(
            values, full_score, config.segment_count
        )

    # 缺考名单（按科目）
    absentees = []
    for sub in subjects:
        missing = [
            {
                "student_public_id": str(s["public_id"]),
                "student_no": s["student_no"],
                "name": s["name"],
                "class": s["class"],
            }
            for s in scoped_students
            if score_map.get((s["id"], sub["id"])) is None
        ]
        if missing:
            absentees.append({"subject": sub["name"], "students": missing})

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
    if caps["view_total"]:
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
                "total_rank": None,
                "subject_avg": cls_subject_avg,
                "subject_rank": {},
            }
        )

    if not caps["view_total"]:
        for row in class_rows:
            row["total_avg"] = None
            row["total_max"] = None
            row["total_min"] = None

    if caps["can_rank_grade"]:
        total_ranks = _rank_class_averages(
            [(row["class_public_id"], row["total_avg"]) for row in class_rows]
        )
        subject_ranks = {
            sub["name"]: _rank_class_averages([
                (row["class_public_id"], row["subject_avg"][sub["name"]])
                for row in class_rows
            ])
            for sub in subjects
        }
        for row in class_rows:
            class_public_id = row["class_public_id"]
            row["total_rank"] = total_ranks.get(class_public_id)
            row["subject_rank"] = {
                name: rank_map.get(class_public_id) for name, rank_map in subject_ranks.items()
            }

    for row in subject_rows:
        row["rank"] = None
    if class_id is not None:
        current_class = next(row for row in class_rows if row["id"] == class_id)
        for row in subject_rows:
            row["rank"] = current_class["subject_rank"].get(row["name"])
        # 班级报告只返回当前班级的汇总。
        class_rows = [current_class]
    for row in class_rows:
        row.pop("id", None)

    analytics = _build_analytics(
        class_id=class_id,
        caps=caps,
        config=config,
        all_subjects=all_subjects,
        subjects=subjects,
        classes=classes,
        students=students,
        score_map=score_map,
        full_total=full_total,
    )

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
        "subject_levels": subject_levels,
        "subject_segments": subject_segments,
        "absentees": absentees,
        "advantages": advantages,
        "classes": class_rows,
        "analytics": analytics,
    }
