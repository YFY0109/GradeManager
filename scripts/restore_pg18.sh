#!/bin/bash
# GradeManager: PG 16.10 -> 18.6 数据恢复（在服务器上执行）
# 前置：宝塔已安装 PostgreSQL 18.6；备份在 /root/backup/pg16-20261127/
set -uo pipefail

PG=/www/server/pgsql
BACKUP=/root/backup/pg16-20261127
PORT="${1:-5432}"

echo "== version =="
"$PG/bin/postgres" --version

echo "== prepare readable dump =="
cp "$BACKUP/full.sql" /tmp/pg16restore.sql
chown postgres:postgres /tmp/pg16restore.sql
chmod 600 /tmp/pg16restore.sql
grep -v '^CREATE ROLE postgres;$' /tmp/pg16restore.sql > /tmp/pg16restore.clean.sql
chown postgres:postgres /tmp/pg16restore.clean.sql
chmod 600 /tmp/pg16restore.clean.sql

echo "== restore =="
su postgres -s /bin/bash -c "$PG/bin/psql -h /tmp -p $PORT -U postgres -d postgres -f /tmp/pg16restore.clean.sql"
echo "restore exit: $?"

echo "== databases =="
su postgres -s /bin/bash -c "$PG/bin/psql -h /tmp -p $PORT -U postgres -c '\\l'"

echo "== roles =="
su postgres -s /bin/bash -c "$PG/bin/psql -h /tmp -p $PORT -U postgres -c '\\du'"

echo "== halo tables =="
su postgres -s /bin/bash -c "$PG/bin/psql -h /tmp -p $PORT -U postgres -d halo -c '\\dt'" | head -15

rm -f /tmp/pg16restore.sql /tmp/pg16restore.clean.sql
echo "== done =="
