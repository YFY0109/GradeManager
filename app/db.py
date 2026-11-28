"""数据库连接。"""

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from .config import DSN


@contextmanager
def get_conn():
    conn = psycopg.connect(DSN, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db():
    """FastAPI 依赖：每个请求一个连接，自动提交/回滚。"""
    with get_conn() as conn:
        yield conn
