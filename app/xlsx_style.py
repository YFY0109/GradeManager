"""openpyxl 通用样式工具：字体/边框/对齐/列宽/冻结/打印。

所有导出共用，样式参数来自导出模板配置（export_config.StylesConfig）。
"""

from __future__ import annotations

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties


def apply_sheet_style(
    ws,
    *,
    n_cols: int,
    n_rows: int,
    styles,
    widths: list[float] | None = None,
    number_formats: dict[int, str] | None = None,
    title_rows: int = 0,
    header_rows: int = 1,
    freeze: bool | None = None,
) -> None:
    """给已写入数据的工作表套样式。

    行结构：第 1..title_rows 行为标题（合并、加大加粗、无边框），
    紧接着 header_rows 行为表头，其余为数据。
    """
    border_name = styles.border
    side = Side(style=border_name) if border_name != "none" else None
    border = Border(left=side, right=side, top=side, bottom=side) if side else Border()
    body_font = Font(name=styles.font.name, size=styles.font.size)
    header_font = Font(
        name=styles.font.name, size=styles.font.size, bold=styles.header.bold
    )
    title_font = Font(
        name=styles.font.name, size=styles.font.size + 4, bold=True
    )
    header_fill = (
        PatternFill("solid", fgColor=styles.header.fill)
        if styles.header.fill
        else None
    )
    align = Alignment(
        horizontal=styles.horizontal,
        vertical=styles.vertical,
        wrap_text=False,
    )
    title_align = Alignment(horizontal="center", vertical="center")

    formats = number_formats or {}
    header_end = title_rows + header_rows
    for row in ws.iter_rows(min_row=1, max_row=n_rows, min_col=1, max_col=n_cols):
        for cell in row:
            if cell.row <= title_rows:
                cell.font = title_font
                cell.alignment = title_align
                continue
            if cell.row <= header_end:
                cell.font = header_font
                cell.border = border
                cell.alignment = align
                if header_fill is not None:
                    cell.fill = header_fill
            else:
                cell.font = body_font
                cell.border = border
                cell.alignment = align
                if cell.column in formats:
                    cell.number_format = formats[cell.column]

    if widths:
        for idx, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(idx)].width = width

    if styles.row_height:
        for row_idx in range(1, n_rows + 1):
            ws.row_dimensions[row_idx].height = styles.row_height

    do_freeze = styles.freeze_header if freeze is None else freeze
    if do_freeze and header_end:
        ws.freeze_panes = f"A{header_end + 1}"

    p = styles.print
    ws.page_setup.orientation = p.orientation
    ws.page_setup.paperSize = p.paper_size
    ws.page_setup.fitToWidth = p.fit_to_width
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    if p.print_title_rows:
        ws.print_title_rows = p.print_title_rows
    if p.margins:
        for key, value in p.margins.items():
            if hasattr(ws.page_margins, key):
                setattr(ws.page_margins, key, value)
