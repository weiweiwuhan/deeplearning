> **当前提交范围（请先阅读）**
>
> 本仓库导入了 7 个附件：README、环境变量示例、依赖清单、Dockerfile、Compose、Alembic 配置和 Git 忽略规则。配置文件已逐行添加中文注释；README 的原有教程保留在下方。
>
> 下方的业务功能、目录结构、56 项断言和验收结果是原文档描述，**不是本次验证通过的结果**。当前缺少 `app/`、`alembic/` 和 `scripts/`，无法启动 API、执行迁移或运行冒烟测试，也没有提供小程序前端。
>
> 项目目标是员工培训与考试：员工微信登录绑定、Excel 导入与部门树、课程课时与题库管理；视频进度与考试判分在文档中分属后续阶段。目前上传的文件只定义运行方式和依赖，不能证明这些功能已实现。
>
> 请补齐业务源码后再安装依赖并执行下方流程。示例密码和密钥只供本地开发，真实 `.env` 不应提交；构建镜像前应补充 `.dockerignore` 排除 `.env`、`.git`、虚拟环境等文件。依赖可安装性及版本兼容性尚未验证。

# 员工视频培训 + 考试系统 · 第 1 周脚手架

FastAPI + PostgreSQL + Redis + SQLAdmin。第 1 周结束时你应该有一个**能跑、能登录、能在后台加数据**的系统。

---

## 0. 前置条件

| 依赖 | 版本 | 检查命令 |
|---|---|---|
| Python | 3.11+ | `python3 -V` |
| Docker + Compose | 任意近期版本 | `docker compose version` |
| Git | 可选 | `git --version` |

> 没有 Docker 也行：自己装一个本地 PostgreSQL 16，把 `.env` 里的 `DATABASE_URL` 指过去即可。

---

## 目录结构

```
training-system/
├── app/
│   ├── main.py                 # 应用入口：中间件 → 路由 → 后台
│   ├── core/
│   │   ├── config.py           # 所有配置，只在这里读环境变量
│   │   ├── security.py         # JWT 签发/校验（access + bind 两类）
│   │   ├── logging.py          # 统一日志格式
│   │   ├── middleware.py       # request_id + 访问日志
│   │   └── redis.py            # Redis 客户端（第 2 周才真正用）
│   ├── db/
│   │   ├── base.py             # Base + 跨方言类型别名（JSONB/BigInt）
│   │   └── session.py          # engine + get_db 依赖
│   ├── models/                 # 9 张表
│   │   ├── org.py              # department / employee
│   │   ├── course.py           # course / lesson / enrollment
│   │   ├── watch.py            # watch_progress
│   │   └── exam.py             # question / exam / attempt
│   ├── schemas/                # Pydantic 出入参
│   ├── services/
│   │   ├── wechat.py           # code2session（含 Mock）
│   │   └── employee_import.py  # Excel 解析 + 建树 + upsert
│   ├── api/
│   │   ├── deps.py             # 当前员工、管理员密钥
│   │   ├── auth.py             # /auth/login /auth/bind
│   │   ├── employees.py        # /employees/import /departments/tree
│   │   └── health.py           # /health
│   └── admin/views.py          # SQLAdmin 8 个视图
├── alembic/                    # 迁移
│   └── versions/0001_initial.py
├── scripts/
│   ├── smoke_test.py           # 端到端验证（不用 Docker）
│   ├── make_sample_employees.py
│   └── init_db.py              # 建表兜底
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## Day 1 · 环境与骨架

### 1.1 创建项目并安装依赖

```bash
mkdir training-system && cd training-system

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

> 依赖已在 `requirements.txt` 里锁好版本。如果 `psycopg[binary]` 在你机器上装不上（缺 libpq），改用 `pip install "psycopg[binary]"` 单独重试，或装系统包：macOS `brew install libpq`，Ubuntu `apt install libpq-dev`。

### 1.2 配置环境变量

```bash
cp .env.example .env
```

**必改两项**（其余保持默认即可）：

```bash
# 生成随机密钥
openssl rand -hex 32
```

把输出分别填到 `.env` 的 `JWT_SECRET` 和 `SESSION_SECRET`。

### 1.3 启动 PostgreSQL 与 Redis

```bash
docker compose up -d postgres redis

# 等健康检查通过
docker compose ps
```

看到 `training-pg` 和 `training-redis` 都是 `healthy` 再往下走。

### 1.4 建目录

```bash
mkdir -p app/{core,db,models,schemas,services,api,admin} alembic/versions scripts
touch app/__init__.py app/{core,db,models,schemas,services,api,admin}/__init__.py
```

> 这些文件脚手架里已经有了，这一步只是让你知道结构。

### ✅ Day 1 验收

```bash
docker compose exec postgres psql -U training -d training -c "select version();"
docker compose exec redis redis-cli ping     # 返回 PONG
```

---

## Day 2 · 9 张表与迁移

### 2.1 表清单

| # | 表 | 作用 | 第几周用 |
|---|---|---|---|
| 1 | `department` | 部门（邻接表 + path） | W1 |
| 2 | `employee` | 员工 + 微信 openid | W1 |
| 3 | `course` | 课程 | W1 |
| 4 | `lesson` | 课时（对应一个视频） | W1 |
| 5 | `enrollment` | 谁要学哪门课 | W1 |
| 6 | `watch_progress` | 观看进度（区间 + 有效时长） | **W2** |
| 7 | `question` | 题库 | W1 |
| 8 | `exam` | 试卷配置 | W1 |
| 9 | `attempt` | 考试记录 | **W3** |

第 3 周做判分时再加 `attempt_question`（题目快照）和 `attempt_answer`（答题明细），跑第二个迁移。现在不建，是为了让第 1 周的迁移保持最小可验证。

### 2.2 生成并执行迁移

脚手架里已经有手写好的 `alembic/versions/0001_initial.py`，直接执行：

```bash
alembic upgrade head
```

如果你要**自己从模型重新生成**（比如改了表结构）：

```bash
alembic revision --autogenerate -m "描述你的改动"
# 检查 alembic/versions/ 下新生成的文件，确认没有误删表/列
alembic upgrade head
```

### 2.3 验证

```bash
docker compose exec postgres psql -U training -d training -c "\dt"
```

应该看到 10 张表（9 张业务表 + `alembic_version`）。

```bash
# 看看索引建对没有
docker compose exec postgres psql -U training -d training -c "\di" | head -30
```

### ⚠️ 关于类型

`app/db/base.py` 里有两个类型别名，不要改成裸 `JSONB`：

```python
BigIntType = BigInteger().with_variant(Integer, "sqlite")
JSONType   = JSON().with_variant(JSONB(), "postgresql")
```

生产库是 PG，用 JSONB；本地跑 `scripts/smoke_test.py` 用 SQLite，SQLite 不认 JSONB。这个写法让同一份模型两边都能跑，**测试不需要 Docker**。

### ✅ Day 2 验收

```bash
alembic current      # 输出 0001_initial (head)
```

---

## Day 3 · 登录与绑定

### 3.1 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/login` | 传 `code`，已绑定直接发 token，未绑定返回 `bind_ticket` |
| POST | `/api/auth/bind` | 传 `bind_ticket` + `emp_no` + `name`，完成绑定并发 token |
| GET | `/api/employees/me` | 带 `Authorization: Bearer <token>` 取当前员工 |

### 3.2 流程

```
小程序 wx.login()
      │  code
      ▼
POST /api/auth/login
      │
      ├─ openid 已绑定 ──→ { need_bind: false, token, employee }
      │
      └─ openid 未绑定 ──→ { need_bind: true, bind_ticket }   ← 10 分钟有效
                                │
                                ▼
                     用户输入工号 + 姓名
                                │
                                ▼
                     POST /api/auth/bind
                                │
                                ▼
                     { need_bind: false, token, employee }
```

### 3.3 为什么 bind 要校验姓名

只验工号的话，员工随手填 `1001` 就绑到别人头上，后面成绩、观看记录全串。姓名做二次校验成本最低，能挡掉绝大多数误绑。

同时做了两个方向的唯一性检查：
- 这个工号是否已被别的微信绑定（返回 409）
- 这个微信是否已绑了别的工号（返回 409）

### 3.4 本地没有 AppID 怎么联调

`.env` 里设 `WECHAT_MOCK=true`，`code2session` 会直接返回 `mock_openid_<你的code>`，整个登录→绑定→考试链路可以完整跑通。**上线前必须改成 false。**

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"code":"test-001"}'
```

### 3.5 真机联调

拿到 AppID/Secret 后：

```bash
WECHAT_MOCK=false
WX_APPID=wx1234567890abcdef
WX_SECRET=你的secret
```

> ⚠️ `code` 只能用一次、5 分钟过期。前端不要在 `onLoad` 里缓存 code 后重复提交，否则第二次必然报 `40163 code been used`。

### ✅ Day 3 验收

```bash
# 未绑定时
curl -s -X POST localhost:8000/api/auth/login -H 'Content-Type: application/json' -d '{"code":"abc"}'
# → {"need_bind":true,"token":null,"bind_ticket":"eyJ...","employee":null}

# 绑定（需先导入员工）
curl -s -X POST localhost:8000/api/auth/bind -H 'Content-Type: application/json' \
  -d '{"bind_ticket":"<上一步的>","emp_no":"E001","name":"张三"}'
# → {"need_bind":false,"token":"eyJ...","employee":{...}}
```

---

## Day 4 · Excel 导入与部门树

### 4.1 生成示例文件

```bash
python scripts/make_sample_employees.py
# 产出 sample_employees.xlsx，10 行，含三级部门
```

### 4.2 表头规则

| 列 | 必需 | 可识别别名 |
|---|---|---|
| 工号 | ✅ | 员工工号 / 员工编号 / emp_no |
| 姓名 | ✅ | 员工姓名 / name |
| 部门 | ❌ | 所属部门 / department |
| 手机号 | ❌ | 手机 / 电话 / phone |

部门支持 `技术部/后端组` 这种路径写法，**导入时自动建树**，HR 不用先手工建部门。

### 4.3 导入接口

```bash
curl -X POST localhost:8000/api/employees/import \
  -H "X-Admin-Key: dev-admin-key" \
  -F "file=@sample_employees.xlsx"
```

返回：

```json
{
  "total": 10,
  "created": 10,
  "updated": 0,
  "skipped": 0,
  "departments_created": 9,
  "errors": []
}
```

**再次导入同一份文件**会走 update 分支（`created: 0, updated: 10`），不会产生重复员工，也不会重复建部门。

### 4.4 容错设计

| 情况 | 行为 |
|---|---|
| 某行工号为空 | 记入 `errors`，跳过该行，其余正常入库 |
| 某行姓名为空 | 同上 |
| 文件内工号重复 | 保留第一条，后面的记 `skipped` |
| 表头缺「工号」或「姓名」 | 整个请求 400，不写任何数据 |
| 上传 .csv / 损坏文件 | 400 |
| 超过 5000 行 / 10MB | 拒绝 |

单事务提交：要么整批成功，要么整批回滚。**但行级错误不会导致整批失败**——这是故意的，HR 导入 500 人时不能因为一行缺姓名就全部白干。

### 4.5 部门树

```bash
curl localhost:8000/api/departments/tree
```

```json
[
  {
    "id": 1, "name": "技术部", "path": "/1", "employee_count": 0,
    "children": [
      {"id": 2, "name": "后端组", "path": "/1/2", "employee_count": 2, "children": []},
      {"id": 3, "name": "前端组", "path": "/1/3", "employee_count": 1, "children": []}
    ]
  }
]
```

`path` 形如 `/1/2`，第 2 周查「某部门及所有下级的学习情况」时一条 `WHERE path LIKE '/1/%'` 就够，不用递归 CTE。

### ✅ Day 4 验收

```bash
# 导入后确认人数
docker compose exec postgres psql -U training -d training \
  -c "select count(*) from employee; select count(*) from department;"
```

---

## Day 5 · 后台、健康检查与日志

### 5.1 后台

浏览器打开 <http://localhost:8000/admin>

默认账号：`admin` / `admin123`（在 `.env` 里改，**上线前必须改**）。

已经挂好 8 个视图：

| 视图 | 能做什么 |
|---|---|
| 部门 | 增删改查、按 path 排序 |
| 员工 | 增删改查、搜索工号/姓名/手机、按状态和部门筛选 |
| 课程 | 增删改查 |
| 课时 | 增删改查、按课程筛选 |
| 题目 | 增删改查（选项和答案是 JSON） |
| 考试 | 增删改查 |
| 观看进度 | 只读 + CSV 导出 |
| 考试记录 | 只读 + CSV 导出 |

> 界面是英文的——sqladmin 没有中文包。第 4 周换成 Vue3 后台时一并解决。第 1 周不纠结这个。

### 5.2 加题目的 JSON 格式

`options`（选项）：
```json
[{"key": "A", "text": "选项一"}, {"key": "B", "text": "选项二"}]
```

`answer`（答案）：
- 单选 / 判断：`"A"`
- 多选：`["A", "C"]`

判断题固定 `A=正确`、`B=错误`。

### 5.3 健康检查

```bash
curl -s localhost:8000/api/health | python3 -m json.tool
```

```json
{
  "status": "ok",
  "app": "training-system",
  "version": "0.1.0",
  "components": {"database": "up", "redis": "up"}
}
```

**设计要点**：
- 数据库不可用 → 返回 **503**，让负载均衡摘掉这台
- Redis 不可用 → 仍然 **200**，只在 `components.redis` 标 `down`

原因：第 1 周主链路不依赖 Redis，如果把它算作致命错误，Redis 抖动一下整站就被摘了，反而放大故障。

### 5.4 日志

启动后每条请求会打一行：

```
2026-10-30 10:15:32 INFO  [app.access] POST /api/auth/login -> 200 12.4ms rid=a3f1c9d2e8b74501
```

`rid` 会同时写进响应头 `X-Request-ID`。用户反馈问题时让他报这个 id，你直接 grep 一条日志就能定位整条请求。

---

## 一键验证（不用 Docker）

```bash
python scripts/smoke_test.py
```

这个脚本用临时 SQLite 跑完整链路，**56 项断言**，覆盖：

- 健康检查（含 Redis 挂掉时的降级行为）
- 未绑定登录 → 绑定失败 → 导入 → 绑定成功 → 取当前员工
- 伪造 token 被拒、无 token 被拒
- 重复导入走 update 不重复建部门
- 脏数据（空工号/空姓名/文件内重复）逐行拦截
- 表头不认识 / .csv / 损坏文件 / 错误密钥 全部正确报错
- SQLAdmin 8 个列表页 + 3 个含 JSON 字段的表单页能正常渲染
- OpenAPI 文档包含全部关键接口

预期输出：

```
通过 56 项，失败 0 项
全部通过 ✅
```

**每次改完代码先跑这个**，比开 Docker 快得多。

---

## 常见问题

**`psycopg.OperationalError: connection refused`**
Postgres 没起来或端口没映射。`docker compose ps` 看状态，`docker compose logs postgres` 看日志。

**`alembic upgrade head` 报 `Target database is not up to date`**
有未提交的迁移。`alembic current` 和 `alembic history` 对比一下。

**`RuntimeError: Event loop is closed`**
多半是在同步函数里调了 async 的 `code2session`。`/auth/login` 是 `async def`，`/auth/bind` 是 `def`，别改混。

**后台登录后一直跳回登录页**
`SESSION_SECRET` 没配或每次重启都变。固定写死一个值。

**导入报「缺少必需列」**
Excel 第一行必须是表头，且含「工号」「姓名」。合并单元格会导致表头错位，先取消合并。

**中文乱码**
Excel 用 `xlsx` 不要用 `csv`。csv 的编码问题 openpyxl 救不了。

---

## 第 1 周验收清单

- [ ] `docker compose ps` 两个服务 healthy
- [ ] `alembic current` 显示 `0001_initial (head)`
- [ ] `psql \dt` 看到 9 张业务表
- [ ] `python scripts/smoke_test.py` 全部通过
- [ ] 浏览器能打开 `/admin` 并登录
- [ ] 能通过后台新增一门课程和一道题目
- [ ] `curl /api/health` 返回 200 且 database=up
- [ ] 用示例 Excel 导入成功，部门树正确

**此时如果小程序类目还没确认，立刻去确认。** 这是唯一可能让整个计划作废的变量——微信「教育服务-在线视频课程」类目要求教育主管部门资质，普通企业营业执照过不了。公司有企业微信的话，直接走企微自建应用能完全绕开这个问题。

---

## 第 2 周要接的东西

代码里已经预留好位置：

| 位置 | 用途 |
|---|---|
| `watch_progress.segments` / `effective_seconds` | 区间合并算法写入 |
| `watch_progress.session_id` | 单设备播放互斥 |
| `core/redis.py` | 播放会话锁、进度上报限流 |
| `lesson.vod_file_id` | 腾讯云 VOD FileId |
| `api/deps.require_admin` | 换成 JWT + 角色校验 |
