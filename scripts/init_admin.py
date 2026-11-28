"""初始化管理员账号。

用法（密码通过环境变量提供，不写入代码/仓库）:
    $env:ADMIN_PASSWORD="..."
    uv run python scripts/init_admin.py admin
"""

import os
import sys

import psycopg
from argon2 import PasswordHasher

DSN = "postgresql://grademanager@127.0.0.1:15432/grademanager"


def main() -> None:
    username = sys.argv[1] if len(sys.argv) > 1 else "admin"
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        sys.exit("请通过环境变量 ADMIN_PASSWORD 提供密码")
    password_hash = PasswordHasher().hash(password)
    with psycopg.connect(DSN) as conn:
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES (%s, %s, 'admin')
            ON CONFLICT (username) DO UPDATE
            SET password_hash = EXCLUDED.password_hash,
                role = 'admin',
                token_version = users.token_version + 1
            """,
            (username, password_hash),
        )
        row = conn.execute(
            "SELECT id FROM users WHERE username = %s", (username,)
        ).fetchone()
        role = conn.execute(
            "SELECT id FROM roles WHERE code = 'admin'"
        ).fetchone()
        if row and role:
            conn.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                (row[0], role[0]),
            )
        conn.commit()
    print(f"OK: 用户 '{username}' 已初始化")


if __name__ == "__main__":
    main()
