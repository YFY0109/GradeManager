"""导入期中考试。以 Excel `rank` 表为准，学生身份与现有数据库名册核对。"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import openpyxl
import psycopg

FULL_SCORES = {
    "语文": 150,
    "数学": 150,
    "英语": 150,
    "物理": 100,
    "化学": 100,
    "生物": 100,
    "政治": 100,
    "历史": 100,
    "地理": 100,
}
SUBJECTS = list(FULL_SCORES)
EXAM_NAME = "高一期中考试"


def load_number_fixes(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    try:
        fixes = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("无法读取考号更正文件，请检查路径并使用 UTF-8 JSON。") from exc
    if not isinstance(fixes, dict) or any(
        not line.isascii() or not line.isdecimal()
        or not isinstance(student_no, str) or not student_no.strip()
        for line, student_no in fixes.items()
    ):
        raise SystemExit("考号更正文件应为 JSON 对象：行号字符串 → 数据库考号字符串。")
    return {line: student_no.strip() for line, student_no in fixes.items()}


def load_records(path: str, number_fixes: dict[str, str] | None = None) -> list[dict]:
    number_fixes = number_fixes or {}
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        if "rank" not in workbook.sheetnames:
            raise SystemExit("Excel 缺少 rank 工作表。")
        rows = list(workbook["rank"].iter_rows(values_only=True))
    finally:
        workbook.close()
    required = ["班级", "姓名", "学号", "名次", "总分", "平均分", *SUBJECTS]
    header = [str(value).strip() for value in rows[0]] if rows else []
    if not set(required).issubset(header):
        raise SystemExit("rank 工作表缺少导入所需的列。")
    idx = {name: header.index(name) for name in required}
    records = []
    for line_no, row in enumerate(rows[1:], start=2):
        if all(value is None for value in row):
            continue
        raw_name = row[idx["姓名"]]
        raw_number = row[idx["学号"]]
        name = str(raw_name).strip() if raw_name is not None else ""
        sheet_number = str(raw_number).strip() if raw_number is not None else ""
        student_no = number_fixes.get(str(line_no), sheet_number)
        if not name or not student_no:
            raise SystemExit(f"rank 第 {line_no} 行缺少姓名或考号。")
        try:
            class_name = f"{int(row[idx['班级']])}班"
            scores = {subject: Decimal(str(row[idx[subject]])) for subject in SUBJECTS}
            sheet_total = Decimal(str(row[idx["总分"]]))
            sheet_average = Decimal(str(row[idx["平均分"]]))
            rank = int(row[idx["名次"]])
        except (InvalidOperation, TypeError, ValueError, OverflowError) as exc:
            raise SystemExit(f"rank 第 {line_no} 行班级、成绩或名次格式无效。") from exc
        for subject, value in scores.items():
            if not value.is_finite() or value < 0 or value > FULL_SCORES[subject]:
                raise SystemExit(f"rank 第 {line_no} 行 {subject} 分数越界。")
        total = sum(scores.values())
        if not sheet_total.is_finite() or total != sheet_total:
            raise SystemExit(f"rank 第 {line_no} 行总分不符。")
        if not sheet_average.is_finite() or abs(total / len(SUBJECTS) - sheet_average) > Decimal("0.00001"):
            raise SystemExit(f"rank 第 {line_no} 行平均分不符。")
        records.append(
            {
                "line_no": line_no,
                "student_no": student_no,
                "excel_name": name,
                "class_name": class_name,
                "rank": rank,
                "scores": scores,
                # Excel 中 0 表示缺考；写入数据库时转为 NULL
                "db_scores": {
                    subject: None if value == 0 else value
                    for subject, value in scores.items()
                },
                "total": total,
            }
        )
    if not records:
        raise SystemExit("rank 工作表没有成绩记录。")
    if len({record["student_no"] for record in records}) != len(records):
        raise SystemExit("rank 工作表考号重复，请核对名单后使用 --number-fixes 更正。")
    if set(number_fixes) - {str(record["line_no"]) for record in records}:
        raise SystemExit("考号更正文件包含 rank 工作表中不存在的成绩行。")
    return records


def resolve_student_ids(conn, records: list[dict]) -> dict[str, int]:
    students = {
        row["student_no"]: row
        for row in conn.execute(
            "SELECT s.id, s.student_no, s.name, c.name AS class_name "
            "FROM students s JOIN classes c ON c.id = s.class_id "
            "WHERE s.student_no = ANY(%s)",
            ([record["student_no"] for record in records],),
        ).fetchall()
    }
    for record in records:
        student = students.get(record["student_no"])
        location = f"rank 第 {record['line_no']} 行"
        if student is None:
            raise SystemExit(f"{location}的考号在数据库名册中不存在。")
        if student["name"] != record["excel_name"] or student["class_name"] != record["class_name"]:
            raise SystemExit(f"{location}的姓名或班级与数据库名册不一致，请核对后再导入。")
    return {student_no: student["id"] for student_no, student in students.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx")
    parser.add_argument("--exam-name", default=EXAM_NAME)
    parser.add_argument("--exam-date", type=date.fromisoformat, metavar="YYYY-MM-DD")
    parser.add_argument("--number-fixes", type=Path, help="私有 JSON 文件：rank 工作表行号 → 正确考号")
    parser.add_argument(
        "--dsn",
        default=os.environ.get("GM_DSN", "postgresql://grademanager@127.0.0.1:15432/grademanager"),
    )
    args = parser.parse_args()

    records = load_records(args.xlsx, load_number_fixes(args.number_fixes))

    with psycopg.connect(args.dsn, row_factory=psycopg.rows.dict_row) as conn:
        if conn.execute("SELECT 1 FROM exams WHERE name = %s", (args.exam_name,)).fetchone():
            raise SystemExit(f"考试已存在: {args.exam_name}")

        student_ids = resolve_student_ids(conn, records)
        for order, name in enumerate(SUBJECTS, start=1):
            conn.execute(
                "INSERT INTO subjects (name, full_score, sort_order) VALUES (%s, %s, %s) "
                "ON CONFLICT (name) DO NOTHING",
                (name, FULL_SCORES[name], order),
            )
        subject_rows = conn.execute(
            "SELECT id, name, full_score FROM subjects WHERE name = ANY(%s)", (SUBJECTS,)
        ).fetchall()
        subject_ids = {row["name"]: row["id"] for row in subject_rows}
        if set(subject_ids) != set(SUBJECTS):
            raise SystemExit("科目补齐失败。")
        for row in subject_rows:
            if row["full_score"] != FULL_SCORES[row["name"]]:
                raise SystemExit(f"科目默认满分不一致: {row['name']}")

        exam = conn.execute(
            "INSERT INTO exams (name, exam_type, exam_date, status) "
            "VALUES (%s, 'midterm', %s, 'draft') RETURNING id",
            (args.exam_name, args.exam_date),
        ).fetchone()
        exam_id = exam["id"]
        for name in SUBJECTS:
            conn.execute(
                "INSERT INTO exam_subjects (exam_id, subject_id, full_score) VALUES (%s, %s, %s)",
                (exam_id, subject_ids[name], FULL_SCORES[name]),
            )

        score_rows = [
            (exam_id, student_ids[record["student_no"]], subject_ids[subject], record["db_scores"][subject])
            for record in records
            for subject in SUBJECTS
        ]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO scores (exam_id, student_id, subject_id, score, entered_by) "
                "VALUES (%s, %s, %s, %s, 'midterm-import')",
                score_rows,
            )

        counts = conn.execute(
            "SELECT count(*) AS scores, count(DISTINCT student_id) AS students "
            "FROM scores WHERE exam_id = %s",
            (exam_id,),
        ).fetchone()
        if counts["scores"] != len(score_rows) or counts["students"] != len(records):
            raise SystemExit("导入后成绩条数或人数不符。")

        ranked = conn.execute(
            """
            SELECT student_id, SUM(score) AS total,
                   RANK() OVER (ORDER BY SUM(score) DESC) AS rank
            FROM scores WHERE exam_id = %s
            GROUP BY student_id
            HAVING count(*) FILTER (WHERE score IS NOT NULL) = (
                SELECT count(*) FROM exam_subjects WHERE exam_id = %s
            )
            """,
            (exam_id, exam_id),
        ).fetchall()
        ranks = {row["student_id"]: (row["total"], row["rank"]) for row in ranked}
        mismatches = [
            record["line_no"]
            for record in records
            if all(value != 0 for value in record["scores"].values())
            and ranks.get(student_ids[record["student_no"]]) != (record["total"], record["rank"])
        ]
        if mismatches:
            raise SystemExit(f"总分或名次校验失败 {len(mismatches)} 条，例如 rank 行号 {mismatches[:3]}。")

        for subject in SUBJECTS:
            row = conn.execute(
                """
                SELECT count(*) AS n, avg(score) AS avg, max(score) AS max, min(score) AS min
                FROM scores WHERE exam_id = %s AND subject_id = %s
                """,
                (exam_id, subject_ids[subject]),
            ).fetchone()
            excel_values = [
                record["scores"][subject]
                for record in records
                if record["scores"][subject] != 0
            ]
            average = sum(excel_values) / len(excel_values)
            if row["n"] != len(excel_values) or abs(row["avg"] - average) > Decimal("0.00001"):
                raise SystemExit(f"单科统计不符: {subject}")
            if row["max"] != max(excel_values) or row["min"] != min(excel_values):
                raise SystemExit(f"单科最高/最低不符: {subject}")

        conn.execute(
            "INSERT INTO audit_logs (actor, action, table_name, record_id, new_value) "
            "VALUES ('midterm-import', 'exam.import', 'exams', %s, %s::jsonb)",
            (str(exam_id), json.dumps({"name": args.exam_name, **counts}, ensure_ascii=False)),
        )
    print(f"OK exam_id={exam_id} students={counts['students']} scores={counts['scores']}")
    print("rank/average/subject validation: 0 mismatches")


if __name__ == "__main__":
    main()
