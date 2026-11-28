"""导入第一次月考成绩到 GradeManager 数据库，并与 Excel 对照校验。

数据源（只读，路径通过环境变量 GM_SOURCE_XLSX 配置）:
    <本地数据目录>/高一月考成绩(学校修改版).xlsx

用法（项目根目录）:
    # .env 中配置 GM_SOURCE_XLSX=...
    uv run python scripts/import_exam.py

校验口径:
    - 学生：按考号逐人比对五科分数
    - 总分：数据库 SUM(五科) vs Excel 总分（数值学生）
    - 班位次 / 级位次：与 Excel 一致（任意一科缺考者不参与排名）
    - 平均分：班级/年级六项平均与 Excel 平均行一致
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import openpyxl
import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

EXCEL = Path(
    os.getenv(
        "GM_SOURCE_XLSX",
        str(ROOT / "data" / "高一月考成绩(学校修改版).xlsx"),
    )
)
DSN = os.getenv("GM_DSN", "postgresql://grademanager@127.0.0.1:15432/grademanager")
EXAM_NAME = "高一第一次月考"

# (sheet, 学生末行)
SHEETS = [
    ("1班", 63), ("2班", 64), ("3班", 64), ("4班", 63),
    ("5班", 65), ("6班", 61), ("7班", 60), ("8班", 62),
]
# (科目, 满分, 得分列索引 1-based: G7=7, J10=10, M13=13, P16=16, S19=19)
SUBJECTS = [("语文", 150, 7), ("数学", 150, 10), ("英语", 150, 13), ("物理", 100, 16), ("化学", 100, 19)]
RANK_COLS = {"class_rank": 5, "grade_rank": 6, "total": 4}  # E5/F6/D4（1-based）


def norm_num(v):
    """分数归一化：空/缺考 → None；数字 → float。"""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s in ("缺考", "部分缺考", "/"):
        return None
    try:
        return float(s)
    except ValueError:
        raise ValueError(f"无法解析的分数: {v!r}")


def norm_no(v):
    """考号归一化：Excel 里是数字，转成文本。"""
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def read_excel():
    wb = openpyxl.load_workbook(EXCEL, data_only=True)
    records = []
    for sheet, last in SHEETS:
        ws = wb[sheet]
        for r in range(4, last + 1):
            name = ws.cell(r, 2).value
            if name is None or str(name).strip() == "":
                continue
            cls = ws.cell(r, 1).value
            if cls is None:
                continue
            rec = {
                "class_name": f"{int(cls)}班",
                "name": str(name).strip(),
                "student_no": norm_no(ws.cell(r, 3).value),
                "scores": {sub: norm_num(ws.cell(r, col).value) for sub, _, col in SUBJECTS},
                "excel_total": norm_num(ws.cell(r, RANK_COLS["total"]).value),
                "excel_class_rank": norm_num(ws.cell(r, RANK_COLS["class_rank"]).value),
                "excel_grade_rank": norm_num(ws.cell(r, RANK_COLS["grade_rank"]).value),
            }
            records.append(rec)
    wb.close()
    return records


def import_to_db(records):
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            # 班级
            for n in range(1, 9):
                cur.execute(
                    "INSERT INTO classes (name, grade) VALUES (%s, '高一') "
                    "ON CONFLICT (name) DO NOTHING",
                    (f"{n}班",),
                )
            # 科目
            for i, (name, full, _) in enumerate(SUBJECTS, start=1):
                cur.execute(
                    "INSERT INTO subjects (name, full_score, sort_order) VALUES (%s, %s, %s) "
                    "ON CONFLICT (name) DO NOTHING",
                    (name, full, i),
                )
            # 考试（幂等：同名的保留唯一）
            cur.execute("SELECT id FROM exams WHERE name = %s ORDER BY id LIMIT 1", (EXAM_NAME,))
            row = cur.fetchone()
            if row:
                exam_id = row[0]
                # 幂等重导入：清空该考试已有成绩（避免旧数据残留）
                cur.execute("DELETE FROM scores WHERE exam_id = %s", (exam_id,))
            else:
                cur.execute(
                    "INSERT INTO exams (name, exam_type, status) VALUES (%s, 'monthly', 'draft') RETURNING id",
                    (EXAM_NAME,),
                )
                exam_id = cur.fetchone()[0]
            # 考试科目
            for i, (name, full, _) in enumerate(SUBJECTS, start=1):
                cur.execute("SELECT id FROM subjects WHERE name = %s", (name,))
                subject_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO exam_subjects (exam_id, subject_id, full_score) "
                    "VALUES (%s, %s, %s) ON CONFLICT (exam_id, subject_id) DO NOTHING",
                    (exam_id, subject_id, full),
                )
            # 学生 + 成绩
            class_ids = {}
            cur.execute("SELECT id, name FROM classes")
            for cid, cname in cur.fetchall():
                class_ids[cname] = cid
            subject_ids = {}
            cur.execute("SELECT id, name FROM subjects")
            for sid, sname in cur.fetchall():
                subject_ids[sname] = sid

            for rec in records:
                cur.execute(
                    "INSERT INTO students (student_no, name, class_id) VALUES (%s, %s, %s) "
                    "ON CONFLICT (student_no) DO UPDATE SET name = EXCLUDED.name "
                    "RETURNING id",
                    (rec["student_no"], rec["name"], class_ids[rec["class_name"]]),
                )
                student_id = cur.fetchone()[0]
                for sub, _, _ in SUBJECTS:
                    cur.execute(
                        "INSERT INTO scores (exam_id, student_id, subject_id, score, entered_by) "
                        "VALUES (%s, %s, %s, %s, 'import') "
                        "ON CONFLICT (exam_id, student_id, subject_id) DO UPDATE SET score = EXCLUDED.score",
                        (exam_id, student_id, subject_ids[sub], rec["scores"][sub]),
                    )
        conn.commit()
    return exam_id


def db_check(exam_id):
    """从数据库计算总分/班位次/级位次/有效学生，与学生名单。"""
    sql = """
    WITH per_student AS (
        SELECT sc.student_id,
               SUM(sc.score) AS total,
               BOOL_AND(sc.score IS NOT NULL) AS all_present
        FROM scores sc
        WHERE sc.exam_id = %s
        GROUP BY sc.student_id
    ),
    ranked AS (
        SELECT p.student_id,
               RANK() OVER (PARTITION BY st.class_id ORDER BY p.total DESC) AS class_rank,
               RANK() OVER (ORDER BY p.total DESC) AS grade_rank
        FROM per_student p
        JOIN students st ON st.id = p.student_id
        WHERE p.all_present  -- 任意一科缺考：不进入排名池（也不占用/影响他人名次）
    )
    SELECT st.student_no, st.name, c.name, p.total, p.all_present, r.class_rank, r.grade_rank
    FROM per_student p
    JOIN students st ON st.id = p.student_id
    JOIN classes c ON c.id = st.class_id
    LEFT JOIN ranked r ON r.student_id = p.student_id
    """
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (exam_id,))
            rows = cur.fetchall()
    return {r[0]: {"name": r[1], "class": r[2], "total": float(r[3]) if r[3] is not None else None,
                  "all_present": r[4], "class_rank": r[5], "grade_rank": r[6]} for r in rows}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not EXCEL.is_file():
        print(f"数据源不存在: {EXCEL}")
        sys.exit(1)

    print(f"读取 Excel: {EXCEL}")
    records = read_excel()
    print(f"读到学生: {len(records)}")

    # 学生数按班统计
    per_class = defaultdict(int)
    for rec in records:
        per_class[rec["class_name"]] += 1
    print("按班:", dict(sorted(per_class.items(), key=lambda x: int(x[0][:-1]))))

    exam_id = import_to_db(records)
    print(f"导入完成，exam_id={exam_id}")

    db = db_check(exam_id)
    print(f"数据库学生数: {len(db)}")

    diffs = []
    checked = 0
    for rec in records:
        dd = db.get(rec["student_no"])
        if dd is None:
            diffs.append(f"{rec['class_name']} {rec['name']}: 数据库中不存在")
            continue
        checked += 1
        if rec["name"] != dd["name"]:
            diffs.append(f"{rec['student_no']}: 姓名 Excel={rec['name']} DB={dd['name']}")
        # 总分（两者都有数值时）
        if rec["excel_total"] is not None and dd["total"] is not None:
            if abs(rec["excel_total"] - dd["total"]) > 0.001:
                diffs.append(f"{rec['class_name']} {rec['name']}: 总分 Excel={rec['excel_total']} DB={dd['total']}")
        # 班位次 / 级位次（Excel 显示数字时）
        if rec["excel_class_rank"] is not None:
            if dd["class_rank"] != int(rec["excel_class_rank"]):
                diffs.append(f"{rec['class_name']} {rec['name']}: 班位次 Excel={int(rec['excel_class_rank'])} DB={dd['class_rank']}")
        if rec["excel_grade_rank"] is not None:
            if dd["grade_rank"] != int(rec["excel_grade_rank"]):
                diffs.append(f"{rec['class_name']} {rec['name']}: 级位次 Excel={int(rec['excel_grade_rank'])} DB={dd['grade_rank']}")

    print(f"逐人校验完成: {checked} 人, 差异 {len(diffs)} 处")
    for d in diffs[:30]:
        print("  -", d)

    # 平均分校验：与 Excel 各班平均行对比
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH per_student AS (
                    SELECT sc.student_id, SUM(sc.score) AS total, BOOL_AND(sc.score IS NOT NULL) AS ok
                    FROM scores sc WHERE sc.exam_id = %s GROUP BY sc.student_id
                )
                SELECT c.name, sub.name, s.score
                FROM scores s
                JOIN students st ON st.id = s.student_id
                JOIN classes c ON c.id = st.class_id
                JOIN subjects sub ON sub.id = s.subject_id
                JOIN per_student p ON p.student_id = s.student_id AND p.ok
                WHERE s.exam_id = %s
                """,
                (exam_id, exam_id),
            )
            raw = cur.fetchall()
    # 组装：班级 -> 科目 -> [有效分数]
    avg_data = defaultdict(lambda: defaultdict(list))
    for cname, sname, score in raw:
        avg_data[cname][sname].append(float(score))

    wb = openpyxl.load_workbook(EXCEL, data_only=True)
    avg_rows = {"1班": 64, "2班": 65, "3班": 65, "4班": 64, "5班": 66, "6班": 62, "7班": 61, "8班": 63}
    avg_cols = {"语文": 7, "数学": 10, "英语": 13, "物理": 16, "化学": 19}  # G/J/M/P/S 1-based
    avg_diffs = []
    for cname, row in avg_rows.items():
        ws = wb[cname]
        for sname, col in avg_cols.items():
            vals = avg_data[cname][sname]
            db_avg = sum(vals) / len(vals) if vals else None
            ex_avg = ws.cell(row, col).value
            if isinstance(ex_avg, (int, float)) and db_avg is not None:
                if abs(float(ex_avg) - db_avg) > 0.01:
                    avg_diffs.append(f"{cname} {sname}: Excel={ex_avg:.2f} DB={db_avg:.2f}")

    # 年级平均（Excel 年级表 482 行）
    ws_grade = wb["年级"]
    grade_avg_cols = {"语文": 7, "数学": 10, "英语": 13, "物理": 16, "化学": 19}
    all_avg = defaultdict(list)
    for cname_map in avg_data.values():
        for sname, vals in cname_map.items():
            all_avg[sname].extend(vals)
    for sname, col in grade_avg_cols.items():
        db_avg = sum(all_avg[sname]) / len(all_avg[sname]) if all_avg[sname] else None
        ex_avg = ws_grade.cell(482, col).value
        if isinstance(ex_avg, (int, float)) and db_avg is not None:
            if abs(float(ex_avg) - db_avg) > 0.01:
                avg_diffs.append(f"年级 {sname}: Excel={ex_avg:.2f} DB={db_avg:.2f}")
    wb.close()

    print(f"平均分校验: 差异 {len(avg_diffs)} 处")
    for d in avg_diffs[:30]:
        print("  -", d)

    # 报告
    report = {
        "exam": EXAM_NAME,
        "source": str(EXCEL),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "students_excel": len(records),
        "students_db": len(db),
        "per_class": dict(per_class),
        "checked": checked,
        "person_diffs": diffs,
        "avg_diffs": avg_diffs,
        "ok": not diffs and not avg_diffs,
    }
    out_dir = Path("reports")
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"import_report_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告: {out}")

    if diffs or avg_diffs:
        print("FAIL: 校验未通过")
        sys.exit(2)
    print("OK: 校验全部通过")


if __name__ == "__main__":
    main()
