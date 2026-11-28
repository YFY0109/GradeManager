"""应用配置：从项目根目录 .env 读取。"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DSN = os.getenv("GM_DSN", "postgresql://grademanager@127.0.0.1:15432/grademanager")
JWT_SECRET = os.getenv("GM_JWT_SECRET", "")
JWT_ALG = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("GM_JWT_EXPIRE_MINUTES", "720"))

if not JWT_SECRET:
    raise RuntimeError("GM_JWT_SECRET 未设置：请先运行 uv run python scripts/init_env.py")
