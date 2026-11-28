"""生成项目 .env（若不存在）：DSN + JWT secret。"""

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
env_path = ROOT / ".env"

if env_path.exists():
    print(f".env 已存在，跳过: {env_path}")
else:
    secret = secrets.token_urlsafe(48)
    content = (
        "GM_DSN=postgresql://grademanager@127.0.0.1:15432/grademanager\n"
        f"GM_JWT_SECRET={secret}\n"
        "GM_JWT_EXPIRE_MINUTES=720\n"
    )
    env_path.write_text(content, encoding="utf-8")
    print(f"已生成: {env_path} (JWT secret 已随机生成)")
