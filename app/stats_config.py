"""统计口径配置（阈值、等级分布）。"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONFIG_KEY = "stats.config"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GradeLevel(StrictModel):
    name: str
    threshold: float = Field(ge=0, le=1)


class CutoffLine(StrictModel):
    """分数线：总分线用绝对分，单科线用得分率。"""

    name: str = Field(min_length=1, max_length=40)
    total: float | None = Field(default=None, ge=0)
    subject_ratio: float | None = Field(default=None, gt=0, le=1)


class StatsConfig(StrictModel):
    excellent: float = Field(default=0.85, gt=0, le=1)
    good: float = Field(default=0.70, gt=0, le=1)
    pass_: float = Field(default=0.60, gt=0, le=1, alias="pass")
    poor: float = Field(default=0.30, gt=0, le=1)
    grade_mode: Literal["ratio", "rank"] = "ratio"
    # ratio 模式：threshold 为最低分比例（降序）
    ratio_levels: list[GradeLevel] = Field(
        default_factory=lambda: [
            GradeLevel(name="A", threshold=0.85),
            GradeLevel(name="B", threshold=0.70),
            GradeLevel(name="C", threshold=0.60),
            GradeLevel(name="D", threshold=0.40),
            GradeLevel(name="E", threshold=0.0),
        ],
        min_length=1,
    )
    # rank 模式：threshold 为累计名次比例上限（升序）
    rank_levels: list[GradeLevel] = Field(
        default_factory=lambda: [
            GradeLevel(name="A", threshold=0.10),
            GradeLevel(name="B", threshold=0.30),
            GradeLevel(name="C", threshold=0.60),
            GradeLevel(name="D", threshold=0.85),
            GradeLevel(name="E", threshold=1.0),
        ],
        min_length=1,
    )
    segment_count: int = Field(default=10, ge=2, le=20)
    # 优秀生/学困生人数（前 N / 后 N）
    top_n: int = Field(default=10, ge=1, le=100)
    # 临界生：总分浮动分、单科得分率浮动比例
    critical_margin: float = Field(default=20, ge=0, le=200)
    subject_margin: float = Field(default=0.05, ge=0, le=0.3)
    # 进线分析分数线；为空时前端提示到配置页设置
    cutoff_lines: list[CutoffLine] = Field(default_factory=list, max_length=10)


def load_stats_config(conn) -> StatsConfig:
    row = conn.execute(
        "SELECT value FROM app_config WHERE key = %s", (CONFIG_KEY,)
    ).fetchone()
    data = row["value"] if row and row["value"] else {}
    return StatsConfig.model_validate(data)


def save_stats_config(conn, body: dict) -> dict:
    config = StatsConfig.model_validate(body)
    value = config.model_dump(by_alias=True)
    conn.execute(
        """
        INSERT INTO app_config (key, value, updated_at)
        VALUES (%s, %s::jsonb, now())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (CONFIG_KEY, json.dumps(value, ensure_ascii=False)),
    )
    return value
