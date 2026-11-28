"""Excel 导出路由。

- kind=full：完整成绩表（scope=grade|classes|all，列/样式由 app_config 模板控制）
- kind=grade_rank / class_rank：排名表（统一套模板样式）
- kind=stats：统计表（样式由 export.stats.template 控制）

模板配置见 app/export_config.py，读写接口见 app/routers/config_api.py。
"""

from io import BytesIO
from urllib.parse import quote
from uuid import UUID

import openpyxl
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..audit import write_audit
from ..auth import current_user
from ..db import get_db
from ..export_config import load_template
from ..export_full import build_full_workbook, load_full_data
from ..permissions import (
    assert_class_allowed,
    assert_subject_allowed,
    capabilities_for,
    get_user_scope,
    require_capability,
)
from ..xlsx_style import apply_sheet_style
from .rankings import (
    _class_id,
    _exam_id,
    _scope_class_ids,
    _subject_id,
    filter_stats,
    query_rank,
    stats_data,
)

router = APIRouter(
    prefix="/api",
    tags=["export"],
    dependencies=[Depends(current_user)],
    responses={
        400: {"description": "请求参数或业务校验错误"},
        401: {"description": "未登录或 token 无效"},
        403: {"description": "无权导出该数据范围"},
        404: {"description": "资源不存在"},
    },
)


def _xlsx_response(wb, filename: str) -> StreamingResponse:
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )


def _export_full(
    conn, exam_id: int, export_scope: str, user_scope: dict, capabilities: dict
) -> StreamingResponse:
    if export_scope not in ("all", "grade", "classes"):
        raise HTTPException(
            status_code=400, detail="scope 只支持 grade / classes / all"
        )
    if not capabilities["can_report_grade"]:
        raise HTTPException(
            status_code=403, detail="无权限导出完整成绩表（需要年级报告权限）"
        )
    if not user_scope["all_subjects"]:
        raise HTTPException(
            status_code=403, detail="无权限导出完整成绩表（包含其他科目）"
        )
    data = load_full_data(conn, exam_id)
    if not data["subjects"]:
        raise HTTPException(status_code=400, detail="该考试尚未配置科目")
    allowed_class_ids = (
        None if user_scope["all_classes"] else set(user_scope["class_ids"])
    )
    tpl = load_template(conn, "full")
    wb = openpyxl.Workbook()
    created = build_full_workbook(
        wb,
        data,
        tpl,
        export_scope,
        allowed_class_ids=allowed_class_ids,
        capabilities=capabilities,
    )
    if not created:
        raise HTTPException(status_code=400, detail="模板未启用任何工作表")
    filename = f"{data['exam']['name']}_完整成绩表.xlsx"
    return _xlsx_response(wb, filename)


def _export_rank(
    conn,
    exam_id: int,
    kind: str,
    subject_id,
    class_id,
    user_scope: dict,
) -> StreamingResponse:
    tpl = load_template(conn, "full")
    fmt = tpl.styles.number_formats
    rows = query_rank(
        conn,
        exam_id,
        subject_id=subject_id,
        class_id=class_id,
        scope="class" if kind == "class_rank" else "grade",
        class_ids=None if class_id is not None else _scope_class_ids(user_scope),
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "排名"
    ws.append(["名次", "考号", "姓名", "班级", "分数"])
    rank_key = "class_rank" if kind == "class_rank" else "grade_rank"
    for r in rows:
        ws.append(
            [
                r[rank_key],
                r["student_no"],
                r["name"],
                r["class"],
                float(r["value"]) if r["value"] is not None else None,
            ]
        )
    apply_sheet_style(
        ws,
        n_cols=5,
        n_rows=len(rows) + 1,
        styles=tpl.styles,
        widths=[8, 12, 10, 8, 8],
        number_formats={1: fmt.rank, 5: fmt.score},
    )

    ws2 = wb.create_sheet("缺考名单")
    ws2.append(["考号", "姓名", "班级", "缺考科目数"])
    absent_class_ids = (
        [class_id] if class_id is not None else _scope_class_ids(user_scope)
    )
    absent = conn.execute(
        """
        SELECT st.student_no, st.name, c.name AS class,
               count(*) FILTER (WHERE sc.score IS NULL) AS absent_count
        FROM students st
        JOIN classes c ON c.id = st.class_id
        JOIN exam_subjects es ON es.exam_id = %(exam_id)s
        LEFT JOIN scores sc
          ON sc.exam_id = es.exam_id
         AND sc.student_id = st.id
         AND sc.subject_id = es.subject_id
        WHERE st.status = 'active'
          AND (%(subject_id)s::int IS NULL OR es.subject_id = %(subject_id)s)
          AND (%(class_ids)s::int[] IS NULL OR st.class_id = ANY(%(class_ids)s))
          AND EXISTS (
              SELECT 1 FROM scores sc2
              WHERE sc2.exam_id = %(exam_id)s AND sc2.student_id = st.id
          )
        GROUP BY st.student_no, st.name, c.name
        HAVING count(*) FILTER (WHERE sc.score IS NULL) > 0
        ORDER BY st.student_no
        """,
        {
            "exam_id": exam_id,
            "subject_id": subject_id,
            "class_ids": absent_class_ids,
        },
    ).fetchall()
    for a in absent:
        ws2.append([a["student_no"], a["name"], a["class"], a["absent_count"]])
    apply_sheet_style(
        ws2,
        n_cols=4,
        n_rows=len(absent) + 1,
        styles=tpl.styles,
        widths=[12, 10, 8, 12],
        number_formats={4: "0"},
    )

    filename = f"考试_{'班级' if kind == 'class_rank' else '年级'}排名.xlsx"
    return _xlsx_response(wb, filename)


def _export_stats(
    conn, exam_pid: UUID, exam_id: int, user: dict, user_scope: dict
) -> StreamingResponse:
    if not capabilities_for(user)["can_report_grade"] or not capabilities_for(
        user
    )["view_stats"]:
        raise HTTPException(
            status_code=403,
            detail="无权限：导出统计表（需要年级报告与汇总指标权限）",
        )
    tpl = load_template(conn, "stats")
    data = stats_data(exam_pid, conn)
    data = filter_stats(
        data,
        conn=conn,
        scope=user_scope,
        include_total=capabilities_for(user)["view_total"],
    )
    styles = tpl.styles

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "年级统计"

    title_rows = 0
    row = 1
    if tpl.title:
        exam_name = conn.execute(
            "SELECT name FROM exams WHERE id = %s", (exam_id,)
        ).fetchone()["name"]
        ws.cell(row=1, column=1, value=tpl.title.format(exam_name=exam_name))
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=11)
        title_rows = 1
        row = 2

    g = data["grade"]
    ws.cell(row=row, column=1, value="指标")
    ws.cell(row=row, column=2, value="值")
    row += 1
    for label, value, fmt in (
        ("参考人数", g["students"], "0"),
        ("总分平均", g["total_avg"], "0.00"),
        ("最高分", g["total_max"], "0.#"),
        ("最低分", g["total_min"], "0.#"),
    ):
        ws.cell(row=row, column=1, value=label)
        ws.cell(row=row, column=2, value=value).number_format = fmt
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="分数段")
    ws.cell(row=row, column=2, value="人数")
    row += 1
    for key, value in g["total_segments"].items():
        ws.cell(row=row, column=1, value=key)
        ws.cell(row=row, column=2, value=value).number_format = "0"
        row += 1

    row += 1
    headers = ["科目", "平均分", "参评", "优秀", "优秀率", "良好", "良好率", "及格", "及格率", "过差", "过差率"]
    for idx, text in enumerate(headers, start=1):
        ws.cell(row=row, column=idx, value=text)
    row += 1
    for sub, r in g["subject_rates"].items():
        values = [
            (sub, None),
            (g["subject_avg"].get(sub), "0.00"),
            (r["participants"], "0"),
            (r["excellent"], "0"),
            (r["excellent_rate"], "0.00%"),
            (r["good"], "0"),
            (r["good_rate"], "0.00%"),
            (r["pass"], "0"),
            (r["pass_rate"], "0.00%"),
            (r["poor"], "0"),
            (r["poor_rate"], "0.00%"),
        ]
        for idx, (value, fmt) in enumerate(values, start=1):
            cell = ws.cell(row=row, column=idx, value=value)
            if fmt:
                cell.number_format = fmt
        row += 1

    apply_sheet_style(
        ws,
        n_cols=11,
        n_rows=row - 1,
        styles=styles,
        widths=[10, 10, 8, 8, 10, 8, 10, 8, 10, 8, 10],
        title_rows=title_rows,
        header_rows=1,
    )
    if title_rows:
        from openpyxl.styles import Alignment, Font

        cell = ws.cell(row=1, column=1)
        cell.font = Font(name=styles.font.name, size=styles.font.size + 4, bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        if styles.print.print_title_rows:
            ws.print_title_rows = f"{title_rows + 1}:{title_rows + 1}"

    ws2 = wb.create_sheet("班级统计")
    subject_names = list(data["grade"]["subject_rates"].keys())
    ws2.append(
        ["班级", "人数", "总分均", "最高", "最低"]
        + [f"{name}均" for name in subject_names]
    )
    for c in data["classes"]:
        sa = c["subject_avg"]
        ws2.append(
            [
                c["class"],
                c["students"],
                c["total_avg"],
                c["total_max"],
                c["total_min"],
            ]
            + [sa.get(name) for name in subject_names]
        )
    apply_sheet_style(
        ws2,
        n_cols=5 + len(subject_names),
        n_rows=len(data["classes"]) + 1,
        styles=styles,
        widths=[8, 8, 10, 8, 8] + [9] * len(subject_names),
        number_formats={
            **{2: "0", 3: "0.00", 4: "0", 5: "0"},
            **{
                idx: "0.00"
                for idx in range(6, 6 + len(subject_names))
            },
        },
    )

    return _xlsx_response(wb, "考试统计.xlsx")


@router.get("/exams/{exam_pid}/export.xlsx")
def export_xlsx(
    exam_pid: UUID,
    kind: str = "grade_rank",
    scope: str = "all",
    subject_pid: UUID | None = None,
    class_pid: UUID | None = None,
    conn=Depends(get_db),
    user=Depends(require_capability("export")),
    user_scope=Depends(get_user_scope),
):
    exam_id = _exam_id(conn, exam_pid)
    audit_payload = {
        "kind": kind,
        "scope": scope,
        "subject_public_id": str(subject_pid) if subject_pid else None,
        "class_public_id": str(class_pid) if class_pid else None,
    }

    if kind == "full":
        write_audit(
            conn,
            actor=user["username"],
            action="export.download",
            table_name="exports",
            record_id=str(exam_id),
            new_value=audit_payload,
        )
        return _export_full(
            conn, exam_id, scope, user_scope, capabilities_for(user)
        )

    if kind in ("grade_rank", "class_rank"):
        caps = capabilities_for(user)
        if kind == "grade_rank" and not caps["can_rank_grade"]:
            raise HTTPException(status_code=403, detail="无权限：导出年级排名")
        if kind == "class_rank" and not caps["can_rank_class"]:
            raise HTTPException(status_code=403, detail="无权限：导出班级排名")
        if kind == "class_rank" and class_pid is None:
            raise HTTPException(status_code=400, detail="class_rank 需要 class_pid")
        subject_id = _subject_id(conn, subject_pid) if subject_pid else None
        class_id = _class_id(conn, class_pid) if class_pid else None
        if subject_id is None:
            if not capabilities_for(user)["view_total"]:
                raise HTTPException(
                    status_code=403, detail="无权限：查看总分与总分排名"
                )
        else:
            if not caps["view_subject"]:
                raise HTTPException(status_code=403, detail="无权限：导出单科排名")
            assert_subject_allowed(user_scope, subject_id)
        if class_id is not None:
            assert_class_allowed(user_scope, class_id)
        write_audit(
            conn,
            actor=user["username"],
            action="export.download",
            table_name="exports",
            record_id=str(exam_id),
            new_value=audit_payload,
        )
        return _export_rank(
            conn, exam_id, kind, subject_id, class_id, user_scope
        )

    if kind == "stats":
        write_audit(
            conn,
            actor=user["username"],
            action="export.download",
            table_name="exports",
            record_id=str(exam_id),
            new_value=audit_payload,
        )
        return _export_stats(conn, exam_pid, exam_id, user, user_scope)

    raise HTTPException(
        status_code=400,
        detail="kind 只支持 full / grade_rank / class_rank / stats",
    )
