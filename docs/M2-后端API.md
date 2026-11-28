# M2 后端 API（v2 · 已按验收意见修订）

> 2026-11-27 · FastAPI 后端，客户端与完整导出打磨后续进行

## 启动

```powershell
. "$HOME\.x-cmd.root\local\data\pwsh\_index.ps1"
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- `.env` 由 `scripts/init_env.py` 生成（JWT secret 随机）
- 管理员 `admin`（密码哈希存数据库，不写入仓库）
- Swagger：`http://127.0.0.1:8000/docs`

## 主键与公开标识

- 所有业务表：内部 `id` 自增（不对外暴露）
- `classes / students / subjects / exams` 另有 `public_id UUID`（对外使用）
- API 请求/响应中的标识一律为 `public_id`

## exam_type（英文枚举）

| 值 | 含义 | 科目 |
|---|---|---|
| `weekly` | 周考 / 大练考 | 单科（创建时必须传 `subject_public_id`） |
| `monthly` | 月考 | 5 科（语数英物化） |
| `midterm` | 期中 | 当前全部科目（9 科齐备后自动全带） |
| `final` | 期末 | 当前全部科目 |

## 认证

```text
POST /api/auth/login   {"username": "admin", "password": "..."}  → {"access_token": ...}
后续：Authorization: Bearer <token>
GET  /api/auth/me
```

## 接口清单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /health | 健康检查 |
| GET | /api/classes | 班级列表（public_id） |
| GET | /api/subjects | 科目列表（public_id） |
| GET | /api/exams | 考试列表（public_id / exam_type） |
| POST | /api/exams | 创建考试 `{name, exam_type, exam_date?, subject_public_id?}` |
| GET | /api/exams/{exam_pid} | 考试详情 |
| GET | /api/exams/{exam_pid}/students?class_public_id= | 学生名单 + 成绩 |
| POST | /api/exams/{exam_pid}/scores | 批量保存 `{items:[{student_public_id, subject_public_id, score|null}]}` |
| GET | /api/exams/{exam_pid}/rankings/total | 年级总分排名 |
| GET | /api/exams/{exam_pid}/rankings/subjects/{subject_pid} | 年级单科排名 |
| GET | /api/exams/{exam_pid}/rankings/classes/{class_pid}/total | 班级总分排名 |
| GET | /api/exams/{exam_pid}/rankings/classes/{class_pid}/subjects/{subject_pid} | 班级单科排名 |
| GET | /api/exams/{exam_pid}/stats | 统计（均分/三率/分数段） |
| GET | /api/exams/{exam_pid}/export.xlsx?kind=full&scope=grade\|classes\|all | 完整成绩表（见导出阶段文档） |
| GET | /api/exams/{exam_pid}/export.xlsx?kind=grade_rank\|class_rank\|stats | 排名 / 统计导出 |
| GET/PUT | /api/config/export/full\|stats | 导出模板配置（写操作仅管理员） |

## 口径

- 缺考 = `NULL`（不存 0）
- **总分排名池**：五科齐全学生（任意一科缺考不参与总分/班位次）
- **单科排名池**：该科有成绩的学生（含部分缺考，与 Excel 一致）
- 排名：分数降序、同分按考号；`RANK` 并列同名次；响应含 `grade_rank`（年级名次）与 `class_rank`（班级名次）
- 均分：仅五科齐全学生；三率：该科有分者为分母（与 Excel 总评一致）
- 优秀 85%、及格 60%、过差 40%
- **统计数值不再四舍五入**：后端返回完整精度，显示格式化由前端负责

> 2026-11-27 导出阶段修正：班级排名原误用年级名次（已改为 `PARTITION BY class_id`）；单科排名池由“五科齐全”改为“该科有分者”。完整验收见 `docs/导出阶段.md`。

## 错误码

- 400：请求参数/业务校验错误（已登记到 OpenAPI）
- 401：未登录或 token 无效
- 404：资源不存在
- 422：请求体校验错误（FastAPI 默认）

## 导出（当前阶段）

- 已支持：排名（年级/班级/单科）、统计数据
- **完整成绩表导出（含各科位次、样式、格式化）留到专门阶段**；导出模板/样式将作为配置存入 `app_config` 表（已建立）

## 验收结果（2026-11-27 v2）

| 检查 | 结果 |
|---|---|
| 登录 admin | ✅ |
| 考试 public_id / type=monthly | ✅ |
| 年级总分排名名单和位次与基准一致 | ✅ |
| 单科/班级排名名单和位次与基准一致 | ✅ |
| 统计返回完整精度 | ✅ |
| 保存成绩（public_id） | ✅ |
| 创建考试：monthly=5 科、weekly=1 科 | ✅ |
| 导出 rank / stats | ✅（20916 / 6791 字节） |
| 测试考试清理 | ✅（考试列表恢复 1 条） |

## 客户端

按用户要求放到最后实现。
