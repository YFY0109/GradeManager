"""导出模板配置：模型、默认值、校验与存取。

配置存放于 app_config 表：
- export.full.template   完整成绩表模板
- export.stats.template  统计导出模板

读取时用 Pydantic 校验并按字段默认值补齐（缺省项自动回退默认）。
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONFIG_KEYS = {
    "full": "export.full.template",
    "stats": "export.stats.template",
}


class StrictModel(BaseModel):
    """配置模型基类：拒绝未知字段，字段名与别名均可解析。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class FieldConfig(StrictModel):
    enabled: bool = True
    label: str = ""
    width: float = Field(default=6.0, gt=0, le=100)
    number_format: str | None = None


class FullFields(StrictModel):
    """完整成绩表的固定列（顺序固定：班级/姓名/学号/名次/班位次/[科目]/总分/平均分）。"""

    class_: FieldConfig = Field(
        default_factory=lambda: FieldConfig(label="班级", width=5.38),
        alias="class",
    )
    name: FieldConfig = Field(
        default_factory=lambda: FieldConfig(label="姓名", width=8.25)
    )
    student_no: FieldConfig = Field(
        default_factory=lambda: FieldConfig(label="学号", width=9.25)
    )
    grade_rank: FieldConfig = Field(
        default_factory=lambda: FieldConfig(label="名次", width=4.5)
    )
    class_rank: FieldConfig = Field(
        default_factory=lambda: FieldConfig(
            enabled=False, label="班位次", width=5.5
        )
    )
    total: FieldConfig = Field(
        default_factory=lambda: FieldConfig(label="总分", width=6.0)
    )
    average: FieldConfig = Field(
        default_factory=lambda: FieldConfig(label="平均分", width=6.38)
    )


class SubjectColumns(StrictModel):
    """每个科目的列：得分 / 班位次 / 级位次（标签支持 {subject} 占位符）。"""

    score: FieldConfig = Field(
        default_factory=lambda: FieldConfig(label="{subject}", width=5.38)
    )
    class_rank: FieldConfig = Field(
        default_factory=lambda: FieldConfig(
            enabled=False, label="{subject}班次", width=5.38
        )
    )
    grade_rank: FieldConfig = Field(
        default_factory=lambda: FieldConfig(label="{subject}次", width=5.38)
    )


class SheetsConfig(StrictModel):
    grade: bool = True
    classes: bool = True


class AbsentText(StrictModel):
    full: str = "缺考"
    partial: str = "部分缺考"


class FontConfig(StrictModel):
    name: str = "宋体"
    size: float = Field(default=12, gt=0, le=72)


class HeaderStyle(StrictModel):
    bold: bool = False
    fill: str | None = None  # RRGGBB，None 为无填充


class NumberFormats(StrictModel):
    score: str = "0.#"
    total: str = "0.#"
    average: str = "0.0"
    rank: str = "0"


class PrintConfig(StrictModel):
    orientation: Literal["portrait", "landscape"] = "portrait"
    paper_size: int = 9  # 9 = A4
    fit_to_width: int = Field(default=1, ge=0)
    print_title_rows: str | None = "1:1"
    margins: dict[str, float] | None = None  # left/right/top/bottom/header/footer


class StylesConfig(StrictModel):
    font: FontConfig = Field(default_factory=FontConfig)
    header: HeaderStyle = Field(default_factory=HeaderStyle)
    border: Literal["thin", "medium", "none"] = "thin"
    horizontal: Literal["center", "left", "right"] = "center"
    vertical: Literal["center", "top", "bottom"] = "center"
    freeze_header: bool = True
    row_height: float | None = None
    number_formats: NumberFormats = Field(default_factory=NumberFormats)
    print: PrintConfig = Field(default_factory=PrintConfig, alias="print")


class FullTemplate(StrictModel):
    version: int = 1
    sheets: SheetsConfig = Field(default_factory=SheetsConfig)
    title: str | None = None  # 支持 {exam_name}；None 表示不加标题行
    fields: FullFields = Field(default_factory=FullFields)
    subject_columns: SubjectColumns = Field(default_factory=SubjectColumns)
    absent_text: AbsentText = Field(default_factory=AbsentText)
    styles: StylesConfig = Field(default_factory=StylesConfig)


def _stats_styles() -> StylesConfig:
    """统计表默认样式：参考学校成绩分析表（仿宋 11、表头加粗）。"""
    return StylesConfig(
        font=FontConfig(name="仿宋", size=11),
        header=HeaderStyle(bold=True),
    )


class StatsTemplate(StrictModel):
    version: int = 1
    title: str | None = "{exam_name}成绩分析表"  # 支持 {exam_name}
    styles: StylesConfig = Field(default_factory=_stats_styles)


TEMPLATE_MODELS = {"full": FullTemplate, "stats": StatsTemplate}


def load_template(conn, name: str):
    """读取配置并与默认值合并（未知字段忽略，缺失字段回退默认），返回模型实例。"""
    model = TEMPLATE_MODELS[name]
    row = conn.execute(
        "SELECT value FROM app_config WHERE key = %s", (CONFIG_KEYS[name],)
    ).fetchone()
    data = row["value"] if row and row["value"] else {}
    return model.model_validate(data)


def save_template(conn, name: str, body: dict) -> dict:
    """校验并保存配置，返回规范化后的完整配置。"""
    model = TEMPLATE_MODELS[name]
    tpl = model.model_validate(body)
    value = tpl.model_dump(by_alias=True)
    conn.execute(
        """
        INSERT INTO app_config (key, value, updated_at)
        VALUES (%s, %s::jsonb, now())
        ON CONFLICT (key)
        DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (CONFIG_KEYS[name], json.dumps(value, ensure_ascii=False)),
    )
    return value
