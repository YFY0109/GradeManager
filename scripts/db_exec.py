"""执行 SQL 文件到 GradeManager 数据库。

用法（项目根目录）:
    uv run python scripts/db_exec.py db/schema.sql
"""

import sys
import psycopg

DSN = "postgresql://grademanager@127.0.0.1:15432/grademanager"


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: db_exec.py <sql-file>")
        sys.exit(1)
    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        sql = f.read()
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print(f"OK: executed {path}")


if __name__ == "__main__":
    main()
