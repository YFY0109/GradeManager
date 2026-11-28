"""完整成绩表：数据构建 + Excel 生成。

口径与 API 完全一致：
- 任意一科缺考 → 不进入排名池（年级/班级/单科位次均为空）
- 总分 = 各科之和；平均分 = 总分 / 科目数（仅齐全学生）
- 缺考显示：全部缺考 → 「缺考」，部分缺考 → 「部分缺考」，单科空值留空
"""

from __future__ import annotations

from decimal import Decimal

from openpyxl.utils import get_column_letter

from .xlsx_style import apply_sheet_style


def load_full_data(conn, exam_id: int) -> dict:
    exam = conn.execute(
        "SELECT id, name, exam_type FROM exams WHERE id = %s", (exam_id,)
    ).fetchone()
    subjects = conn.execute(
        """
        SELECT s.id, s.name, s.sort_order
        FROM exam_subjects es
        JOIN subjects s ON s.id = es.subject_id
        WHERE es.exam_id = %s
        ORDER BY s.sort_order
        """,
        (exam_id,),
    ).fetchall()
    classes = conn.execute("SELECT id, name FROM classes ORDER BY id").fetchall()
    students = conn.execute(
        """
        SELECT st.id, st.student_no, st.name, st.class_id, c.name AS class_name
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
    scores = conn.execute(
        "SELECT student_id, subject_id, score FROM scores WHERE exam_id = %s",
        (exam_id,),
    ).fetchall()
    return {
        "exam": exam,
        "subjects": subjects,
        "classes": classes,
        "students": students,
        "score_map": {
            (r["student_id"], r["subject_id"]): r["score"] for r in scores
        },
    }


def _rank(items: list[tuple[int, Decimal, str]]) -> dict[int, int]:
    """RANK 语义：分数降序，同分同名次（考号仅用于稳定排序）。"""
    ordered = sorted(items, key=lambda x: (-x[1], x[2]))
    result: dict[int, int] = {}
    prev_value = None
    prev_rank = 0
    for pos, (sid, value, _no) in enumerate(ordered, start=1):
        if prev_value is None or value != prev_value:
            prev_rank = pos
            prev_value = value
        result[sid] = prev_rank
    return result


def build_rankings(data: dict) -> dict:
    """计算每名学生的总分/平均分/年级名次/班级名次/单科名次。"""
    subjects = data["subjects"]
    students = data["students"]
    score_map = data["score_map"]
    classes = data["classes"]

    info: dict[int, dict] = {}
    complete_ids: list[int] = []
    for st in students:
        values = [score_map.get((st["id"], sub["id"])) for sub in subjects]
        absent = sum(1 for v in values if v is None)
        if absent == 0 and subjects:
            total = sum(values, Decimal(0))
            info[st["id"]] = {
                "total": total,
                "average": total / len(subjects),
                "absent": 0,
            }
            complete_ids.append(st["id"])
        else:
            info[st["id"]] = {"total": None, "average": None, "absent": absent}

    no_map = {st["id"]: st["student_no"] for st in students}
    class_map = {st["id"]: st["class_id"] for st in students}

    grade_rank = _rank(
        [(sid, info[sid]["total"], no_map[sid]) for sid in complete_ids]
    )

    class_rank: dict[int, int] = {}
    for cls in classes:
        ids = [sid for sid in complete_ids if class_map[sid] == cls["id"]]
        if ids:
            class_rank.update(
                _rank([(sid, info[sid]["total"], no_map[sid]) for sid in ids])
            )

    subject_grade_rank: dict[tuple[int, int], int] = {}
    subject_class_rank: dict[tuple[int, int], int] = {}
    for sub in subjects:
        # 单科排名池 = 该科有成绩的学生（与 Excel 一致；部分缺考仍参加有分科目）
        item_ids = [
            st["id"]
            for st in students
            if score_map.get((st["id"], sub["id"])) is not None
        ]
        items = [
            (sid, score_map[(sid, sub["id"])], no_map[sid]) for sid in item_ids
        ]
        subject_grade_rank.update(
            {(sid, sub["id"]): rank for sid, rank in _rank(items).items()}
        )
        class_items: dict[int, list] = {}
        for item in items:
            class_items.setdefault(class_map[item[0]], []).append(item)
        for cls_items in class_items.values():
            subject_class_rank.update(
                {
                    (sid, sub["id"]): rank
                    for sid, rank in _rank(cls_items).items()
                }
            )

    return {
        "info": info,
        "grade_rank": grade_rank,
        "class_rank": class_rank,
        "subject_grade_rank": subject_grade_rank,
        "subject_class_rank": subject_class_rank,
    }


def build_columns(data: dict, tpl, capabilities: dict | None = None) -> list[dict]:
    """按模板配置生成列描述（顺序：班级/姓名/学号/名次/[科目]/总分/平均分）。"""
    fmt = tpl.styles.number_formats
    fields = tpl.fields
    cols: list[dict] = []

    def allowed(key: str) -> bool:
        return capabilities is None or bool(capabilities.get(key))

    def add(key, field, kind, number_format=None):
        if field.enabled:
            cols.append(
                {
                    "key": key,
                    "label": field.label,
                    "width": field.width,
                    "number_format": number_format,
                    "kind": kind,
                }
            )

    add("class", fields.class_, "class")
    add("name", fields.name, "name")
    add("student_no", fields.student_no, "student_no")
    if allowed("can_rank_grade"):
        add("grade_rank", fields.grade_rank, "grade_rank", fmt.rank)
    if allowed("can_rank_class"):
        add("class_rank", fields.class_rank, "class_rank", fmt.rank)

    sc = tpl.subject_columns
    for sub in data["subjects"]:
        if sc.score.enabled and allowed("view_subject"):
            cols.append(
                {
                    "key": f"score:{sub['id']}",
                    "label": sc.score.label.format(subject=sub["name"]),
                    "width": sc.score.width,
                    "number_format": fmt.score,
                    "kind": "score",
                    "subject_id": sub["id"],
                }
            )
        if sc.grade_rank.enabled and allowed("can_rank_grade"):
            cols.append(
                {
                    "key": f"grade_rank:{sub['id']}",
                    "label": sc.grade_rank.label.format(subject=sub["name"]),
                    "width": sc.grade_rank.width,
                    "number_format": fmt.rank,
                    "kind": "subject_grade_rank",
                    "subject_id": sub["id"],
                }
            )
        if sc.class_rank.enabled and allowed("can_rank_class"):
            cols.append(
                {
                    "key": f"class_rank:{sub['id']}",
                    "label": sc.class_rank.label.format(subject=sub["name"]),
                    "width": sc.class_rank.width,
                    "number_format": fmt.rank,
                    "kind": "subject_class_rank",
                    "subject_id": sub["id"],
                }
            )

    if allowed("view_total"):
        add("total", fields.total, "total", fmt.total)
        add("average", fields.average, "average", fmt.average)
    return cols


def _absent_text(info: dict, total_absent: int, tpl) -> str | None:
    """缺考三态文字：全科缺考 / 部分缺考；无缺考返回 None。"""
    if info["absent"] == 0:
        return None
    if info["absent"] == total_absent:
        return tpl.absent_text.full
    return tpl.absent_text.partial


def _cell_value(st: dict, col: dict, data: dict, ranks: dict, tpl):
    kind = col["kind"]
    sid = st["id"]
    info = ranks["info"][sid]
    total_absent = len(data["subjects"])
    absent_text = _absent_text(info, total_absent, tpl)

    if kind == "class":
        return st["class_name"]
    if kind == "name":
        return st["name"]
    if kind == "student_no":
        return st["student_no"]
    if kind == "grade_rank":
        return absent_text if absent_text else ranks["grade_rank"].get(sid)
    if kind == "class_rank":
        return absent_text if absent_text else ranks["class_rank"].get(sid)
    if kind == "score":
        return data["score_map"].get((sid, col["subject_id"]))
    if kind == "subject_grade_rank":
        return (
            absent_text
            if absent_text
            else ranks["subject_grade_rank"].get((sid, col["subject_id"]))
        )
    if kind == "subject_class_rank":
        return (
            absent_text
            if absent_text
            else ranks["subject_class_rank"].get((sid, col["subject_id"]))
        )
    if kind == "total":
        return info["total"] if absent_text is None else absent_text
    if kind == "average":
        return info["average"]
    return None


def _sorted_students(
    data: dict,
    ranks: dict,
    class_id: int | None = None,
    allowed_class_ids: set[int] | None = None,
) -> list[dict]:
    students = data["students"]
    if class_id is not None:
        students = [st for st in students if st["class_id"] == class_id]
    if allowed_class_ids is not None:
        students = [st for st in students if st["class_id"] in allowed_class_ids]

    def key(st):
        info = ranks["info"][st["id"]]
        if info["total"] is None:
            return (1, 0, st["student_no"])
        rank = (
            ranks["class_rank"].get(st["id"], 0)
            if class_id is not None
            else ranks["grade_rank"].get(st["id"], 0)
        )
        return (0, rank, st["student_no"])

    return sorted(students, key=key)


def _write_sheet(ws, students, columns, data, ranks, tpl, title: str | None):
    title_rows = 0
    row_idx = 1
    if title:
        ws.cell(row=1, column=1, value=title)
        if len(columns) > 1:
            ws.merge_cells(
                start_row=1, start_column=1, end_row=1, end_column=len(columns)
            )
        title_rows = 1
        row_idx = 2

    for col_idx, col in enumerate(columns, start=1):
        ws.cell(row=row_idx, column=col_idx, value=col["label"])

    for offset, st in enumerate(students, start=1):
        r = row_idx + offset
        for col_idx, col in enumerate(columns, start=1):
            ws.cell(
                row=r,
                column=col_idx,
                value=_cell_value(st, col, data, ranks, tpl),
            )

    n_rows = row_idx + len(students)
    apply_sheet_style(
        ws,
        n_cols=len(columns),
        n_rows=n_rows,
        styles=tpl.styles,
        widths=[col["width"] for col in columns],
        number_formats={
            idx: col["number_format"]
            for idx, col in enumerate(columns, start=1)
            if col["number_format"]
        },
        title_rows=title_rows,
        header_rows=1,
    )
    if title_rows:
        # 标题行：加大加粗、居中、无边框
        from openpyxl.styles import Alignment, Font

        cell = ws.cell(row=1, column=1)
        cell.font = Font(
            name=tpl.styles.font.name,
            size=tpl.styles.font.size + 4,
            bold=True,
        )
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = (tpl.styles.font.size + 4) * 1.8

    if tpl.styles.print.print_title_rows and title_rows:
        # 标题存在时，重复打印行应为表头行
        ws.print_title_rows = f"{row_idx}:{row_idx}"


def build_full_workbook(
    wb,
    data: dict,
    tpl,
    scope: str = "all",
    allowed_class_ids: set[int] | None = None,
    capabilities: dict | None = None,
) -> list[str]:
    """向工作簿写入完整成绩表，返回实际生成的 sheet 名列表。

    scope:
    - grade：仅年级总表
    - classes：年级总表 + 各班
    - all：按模板 sheets 配置（默认两者都导）

    allowed_class_ids：数据范围过滤（排名仍按全量数据计算，仅裁剪输出）。
    capabilities：按能力裁剪总分/排名/单科列。
    """
    ranks = build_rankings(data)
    columns = build_columns(data, tpl, capabilities)
    exam_name = data["exam"]["name"]
    title = tpl.title.format(exam_name=exam_name) if tpl.title else None

    want_grade = scope in ("all", "classes") or (scope == "grade")
    want_classes = scope in ("all", "classes")
    if scope == "all":
        want_grade = tpl.sheets.grade
        want_classes = tpl.sheets.classes

    created: list[str] = []
    if want_grade:
        ws = wb.active
        ws.title = "年级"
        _write_sheet(
            ws,
            _sorted_students(
                data, ranks, allowed_class_ids=allowed_class_ids
            ),
            columns,
            data,
            ranks,
            tpl,
            title,
        )
        created.append("年级")

    if want_classes:
        for cls in data["classes"]:
            if allowed_class_ids is not None and cls["id"] not in allowed_class_ids:
                continue
            students = _sorted_students(data, ranks, class_id=cls["id"])
            if not students:
                continue
            sheet_name = cls["name"][:31]
            ws = wb.create_sheet(sheet_name)
            _write_sheet(ws, students, columns, data, ranks, tpl, title)
            created.append(sheet_name)

    return created
