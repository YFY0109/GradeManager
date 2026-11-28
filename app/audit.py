"""审计日志写入工具。"""

from __future__ import annotations

import json
from decimal import Decimal


def _json(value):
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def write_audit(
    conn,
    *,
    actor: str,
    action: str,
    table_name: str,
    record_id: str | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_logs
            (actor, action, table_name, record_id, old_value, new_value)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)
        """,
        (actor, action, table_name, record_id, _json(old_value), _json(new_value)),
    )


def audit_score_change(
    conn,
    *,
    actor: str,
    exam_id: int,
    student_id: int,
    subject_id: int,
    old_score,
    new_score,
) -> bool:
    """记录单条成绩变更；值未变化返回 False。"""
    old = Decimal(str(old_score)) if old_score is not None else None
    new = Decimal(str(new_score)) if new_score is not None else None
    if old == new:
        return False
    payload_old = None
    payload_new = None
    if old is not None:
        payload_old = {
            "exam_id": exam_id,
            "student_id": student_id,
            "subject_id": subject_id,
            "score": float(old),
        }
    if new is not None:
        payload_new = {
            "exam_id": exam_id,
            "student_id": student_id,
            "subject_id": subject_id,
            "score": float(new),
        }
    write_audit(
        conn,
        actor=actor,
        action="score.create" if old is None else "score.update",
        table_name="scores",
        record_id=f"exam={exam_id};student={student_id};subject={subject_id}",
        old_value=payload_old,
        new_value=payload_new,
    )
    return True
