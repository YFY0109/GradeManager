# GradeManager

GradeManager 是面向学校的成绩管理系统。教师在浏览器里录入成绩，按班级或年级查看测验报告，并导出 Excel 成绩表。后端使用 FastAPI 和 PostgreSQL，前端使用 Vue 3、TypeScript 和 Element Plus。

## 功能

- **考试与录入**：创建周考、月考、期中和期末考试。每场考试保留自己的科目、满分和名单；支持按班录入和批量保存，空分表示缺考。
- **测验报告**：查看年级或班级的学情总览。学生成绩表将总分、单科分数和对应名次排在一起，支持按姓名或考号搜索、按名次排序和对比考试。可见科目、年排和班排由账号权限决定。
- **导出与管理**：导出成绩表、排名表和统计表；按班级与科目授权，管理用户、角色和学科，并查询操作日志。

## 本地运行

需要 PostgreSQL、Python 3.12 或更新版本、`uv` 和 Node.js 24。

### 1. 初始化开发库

创建一个空的 `grademanager` 数据库及同名角色，并授予该角色在库中创建表的权限。以下初始化脚本使用 `127.0.0.1:15432`；如果数据库需要口令，可通过 `.pgpass` 提供。

在项目根目录执行：

```bash
uv sync --frozen
uv run python scripts/init_env.py
uv run python scripts/db_exec.py db/schema.sql
uv run python scripts/db_exec.py db/002_m2_enhancements.sql
uv run python scripts/db_exec.py db/003_m3_auth.sql
uv run python scripts/db_exec.py db/004_roles.sql
```

`init_env.py` 会为新环境生成 `.env` 和随机的 `GM_JWT_SECRET`。应用的数据库连接由 `.env` 中的 `GM_DSN` 指定。

### 2. 创建管理员并启动后端

```bash
read -r -s -p '管理员密码：' ADMIN_PASSWORD
ADMIN_PASSWORD="$ADMIN_PASSWORD" uv run python scripts/init_admin.py admin
unset ADMIN_PASSWORD
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

后端启动后，可在 <http://127.0.0.1:8000/docs> 查看 API。

### 3. 启动前端

另开一个终端，在项目根目录执行：

```bash
cd web
npm ci
npm run dev
```

打开 <http://localhost:5173>。开发服务器会将 `/api` 请求转发给本地后端。

## 构建与部署

在 `web/` 执行 `npm run build` 会进行类型检查，并将静态文件生成到 `web/dist/`。GitHub Actions 的 **Build web** 工作流使用锁定依赖构建同一套文件，产物名为 `web-dist`。

线上由 Nginx 提供静态文件，将 `/api` 和 `/health` 转发给 FastAPI。发布和运维步骤见[部署文档](docs/M4-部署.md)。

## 数据与文档

- 已导入的成绩以 PostgreSQL 为准。原始 Excel、私有更正文件、数据库备份和 `.env` 存放在部署环境中。
- [数据导入](docs/M1-数据导入.md) · [期中导入](docs/期中导入记录.md) · [权限说明](docs/权限细化方案.md) · [前端开发](web/README.md)
