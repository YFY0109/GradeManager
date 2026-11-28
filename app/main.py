"""GradeManager API 入口。"""

from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .routers import (
    audit,
    auth,
    config_api,
    exams,
    export,
    overview,
    rankings,
    roles,
    scores,
    subjects,
    users,
)

app = FastAPI(
    title="GradeManager API",
    description="成绩管理系统后端 API",
    version="0.5.0",
)


@app.middleware("http")
async def csrf_origin_guard(request: Request, call_next):
    """Cookie 会话的跨站请求防护：非 GET 请求校验 Origin/Referer 与 Host 同源。"""
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin:
            parsed = urlparse(origin)
            host_name = request.headers.get("host", "").split(":")[0]
            if (
                parsed.hostname
                and parsed.hostname != host_name
                and parsed.hostname not in ("localhost", "127.0.0.1")
            ):
                return JSONResponse(
                    {"detail": "跨站请求被拒绝"}, status_code=403
                )
    return await call_next(request)


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(subjects.router)
app.include_router(audit.router)
app.include_router(config_api.router)
app.include_router(exams.router)
app.include_router(scores.router)
app.include_router(rankings.router)
app.include_router(overview.router)
app.include_router(export.router)


@app.get("/health")
def health():
    return {"status": "ok"}
