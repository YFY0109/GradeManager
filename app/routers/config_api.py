"""系统配置路由：导出模板的读取与更新。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from ..audit import write_audit
from ..auth import current_user
from ..db import get_db
from ..export_config import TEMPLATE_MODELS, load_template, save_template
from ..permissions import require_capability
from ..stats_config import load_stats_config, save_stats_config

router = APIRouter(
    prefix="/api/config",
    tags=["config"],
    dependencies=[Depends(current_user)],
    responses={
        400: {"description": "请求参数或业务校验错误"},
        401: {"description": "未登录或 token 无效"},
        403: {"description": "需要管理员权限"},
        404: {"description": "资源不存在"},
        422: {"description": "配置校验失败"},
    },
)


@router.get("/export/{name}")
def get_export_config(
    name: str,
    conn=Depends(get_db),
    _user=Depends(require_capability("manage_config")),
):
    """读取导出模板（full=完整成绩表，stats=统计表），缺失项返回默认值。"""
    if name not in TEMPLATE_MODELS:
        raise HTTPException(status_code=404, detail="未知导出模板")
    return load_template(conn, name).model_dump(by_alias=True)


@router.put("/export/{name}")
def put_export_config(
    name: str,
    body: dict,
    conn=Depends(get_db),
    actor=Depends(require_capability("manage_config")),
):
    """更新导出模板（仅管理员）。提交完整配置，未提供的字段回退默认值。"""
    if name not in TEMPLATE_MODELS:
        raise HTTPException(status_code=404, detail="未知导出模板")
    try:
        result = save_template(conn, name, body)
        write_audit(
            conn,
            actor=actor["username"],
            action="config.update",
            table_name="app_config",
            record_id=f"export.{name}",
            new_value={"name": name},
        )
        return result
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
                for err in exc.errors()
            ],
        )


@router.get("/stats")
def get_stats_config(
    conn=Depends(get_db),
    _user=Depends(require_capability("manage_config")),
):
    """统计口径配置（三率阈值、等级模式）。"""
    return load_stats_config(conn).model_dump(by_alias=True)


@router.put("/stats")
def put_stats_config(
    body: dict,
    conn=Depends(get_db),
    actor=Depends(require_capability("manage_config")),
):
    """更新统计口径（仅管理员）。"""
    try:
        result = save_stats_config(conn, body)
        write_audit(
            conn,
            actor=actor["username"],
            action="config.update",
            table_name="app_config",
            record_id="stats.config",
            new_value={"key": "stats.config"},
        )
        return result
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
                for err in exc.errors()
            ],
        )
