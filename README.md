# 学程 · 网页版员工视频培训与考试

员工在浏览器登录个人账号、观看视频、完成考试；管理员在同一个网站创建账号、发布课程，查看每个人的**有效观看时长、观看比例、每次考试分数与是否通过**，并导出 CSV。

本项目已由原来的微信小程序配置脚手架改为独立网页应用，**不需要微信 AppID、小程序或 Redis**。后端采用 FastAPI + SQLAlchemy，前端为原生 HTML / CSS / JavaScript，无需 Node.js 构建。Python 3.12，本地默认 SQLite，Docker 使用 PostgreSQL 16。

## 1. 本地启动：最快体验

### 下载并安装

```bash
git clone https://github.com/weiweiwuhan/deeplearning.git
cd deeplearning
python3 -m venv .venv
source .venv/bin/activate
# Windows PowerShell：.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cp .env.example .env
# Windows PowerShell：Copy-Item .env.example .env
```

编辑 `.env`，至少将 `ADMIN_PASSWORD` 改为**自己的 12–128 位密码**。不能保留以 `CHANGE_` 开头的占位值；首次启动时未配置有效密码，程序会明确报错并退出。

```dotenv
DATABASE_URL=sqlite:///./data/training.db
DATA_DIR=./data
ADMIN_USERNAME=admin
ADMIN_PASSWORD=替换为你自己的长密码
COOKIE_SECURE=false
SESSION_HOURS=12
MAX_UPLOAD_MB=500
```

始终在仓库根目录运行：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000`，使用 `.env` 中的管理员账号和密码登录。启动时会自动执行 Alembic 迁移，并且**仅在没有管理员的数据库中**创建初始管理员。数据库和视频保存在 `data/`，重启服务不会丢失。

- 没有默认的公共管理员密码；不要将真实 `.env` 上传到 GitHub。
- 首次创建管理员后，修改 `.env` 中的密码不会重置已有账号。请在网页中修改密码或由管理员重置员工密码。
- 开发时可以添加 `--reload`；正式运行不要使用它。
- SQLite 适合本地体验、小规模单实例使用；正式部署建议采用下方 PostgreSQL 配置。

## 2. 管理员如何配置培训

1. 登录后进入「课程与账号管理」。
2. 创建员工账号，填写唯一账号、姓名和至少 12 位的初始密码。请安全地告知本人，员工可登录后修改密码。账号区分大小写，员工不能自行注册或授予管理员权限。
3. 创建课程：填写名称、介绍并选择视频。网页会读取视频时长；请核对时长正确，必要时手动调整。格式支持 **MP4 / WebM**，建议 MP4 使用 H.264 视频与 AAC 音频以兼容常见浏览器。后端校验扩展名、文件头和大小，不进行转码。
4. 设置观看要求（默认 90%）、及格分（默认 60）、考试次数（默认 3）和限时（默认 30 分钟）。
5. 点击「创建并上传视频」。上传成功后课程仍为草稿；若上传失败，草稿会保留，可在课程列表重试上传。
6. 在「添加单选题」选择课程，填写题干、每行一个选项，以及正确选项序号（从 1 开始）。判断题可用“正确 / 错误”两个选项。每门课程最多 200 题，所有题目等分计分。
7. 课程列表点击「查看试题」核对，再点击「发布」。没有视频或试题的课程不能发布。
8. 进入「学习报表」，查看观看时长、观看比例、考试状态和成绩，可按姓名、账号、课程筛选并导出 CSV。CSV 导出全部记录，不应用当前网页筛选条件。

目前采用**所有启用的员工都能学习所有已发布课程**的分发方式。每门课程一个视频、一份考试；多个视频可拆为多门课程。没有部门分组、Excel 批量导入、自动分配课程或公开注册。

课程支持发布和下架；下架后员工不能继续播放或新开考，已经开始的考试仍可交卷。暂不支持修改已创建课程参数、替换视频、修改或删除已有题目，以保留历史学习记录的含义。需要更正时新建课程并下架旧课程；下架后可以追加题目，新开考使用新题目，已开考使用冻结的试卷。

## 3. 员工如何学习与考试

1. 在网页输入自己的账号与密码登录。
2. 「我的课程」中点击「进入学习」，播放视频；系统会保留最近上报的位置，重新进入时从该位置继续。
3. 页面保持前台、正常速度播放时，每 5 秒上报进度。暂停、后台、异常间隔或拖动跨越的部分不会直接记为已观看。
4. 达到课程的观看比例后，「开始 / 继续考试」按钮启用。考试开始后计时不会因刷新或关闭网页而暂停。
5. 选择答案并交卷，立即看到服务器计算的分数与通过结果；课程卡片显示历史最高成绩。
6. 刷新后可以重新点击「开始 / 继续考试」恢复未到期的试卷，**未交卷的选择不自动保存**。已交卷的考试不能修改。
7. 超时后提交记 0 分；到期未提交的考试在报表中显示「已超时 / 0 分」，占用一次考试机会。用完次数后不能继续开考，当前版本没有后台增加次数功能。

员工只能看到自己的学习进度和成绩，不能读取后台报表、其他员工考试或正确答案。管理员可以停用账号、重置密码；这些操作会撤销该账号现有登录会话。员工自行修改密码后也需重新登录。

## 4. 观看时长的含义与边界

后台显示的「有效观看时长」是**已验证播放区间的并集长度**，单位为秒。同一段重复看不重复累计，结果不会超过课程视频时长。例如先看 0–30 秒，再看 20–50 秒，合计为 50 秒，而不是 60 秒。

服务器同时检查播放位置变化和实际经过时间：倒退不加时，明显跳跃不加时，单次最多接受 15 秒的连续上报间隔；增加的时长不能超过服务器经过时间。同一员工同一课程只允许最后打开的播放会话上报。网页会禁用倍速统计，并在隐藏页面时暂停视频。网络中断、切换页面等情况下，最近几秒可能尚未上报，重新播放相应片段即可补齐。

**这是学习行为统计，不是严格的防作弊或注意力证明**。有技术能力的使用者仍可能模拟实时上报、录屏或共享账号；系统无法证明本人始终在认真观看，也不防止视频被获授权用户保存。考试目前是固定题目、单选等分，不含随机题库、主观题、监考或视频 DRM。高要求的合规培训需要额外的身份与监考措施。

## 5. Docker + PostgreSQL 启动

安装近期 Docker 与 Docker Compose，准备 `.env`：

```bash
cp .env.example .env
# 编辑 ADMIN_PASSWORD，并把 POSTGRES_PASSWORD 改成随机字母数字密码。
# 例如使用 python -c "import secrets; print(secrets.token_hex(24))" 生成密码。
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 api
```

`POSTGRES_PASSWORD` 会拼接进数据库 URL，请使用随机字母数字密码，避免特殊字符需要 URL 转义。Compose 会自动覆盖 `DATABASE_URL`，通过容器网络连接 PostgreSQL；不需要另改示例中的 SQLite 地址。网页仍在本机 `http://127.0.0.1:8000`，API 启动时自动执行迁移、初始化管理员。

```bash
# 验证健康状态与数据库版本
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health').read().decode())"
docker compose exec api alembic current

# 更新版本（正式数据库更新前先备份）
git pull --ff-only
docker compose up -d --build

# 停止服务，保留数据
docker compose down
```

数据分别保存在 `pgdata` 与 `trainingdata` 命名卷中。**不要执行 `docker compose down -v`，否则会删除数据库与视频**。首次初始化以后，改 `.env` 的 PostgreSQL 密码并不会同步修改数据库用户密码，需要先在数据库内正确改密，再同步配置。

> 从本地 SQLite 切换到 PostgreSQL 时不会自动迁移历史数据。两种模式对应不同数据库与视频目录。正式使用前确定部署模式；已有数据需另行安排迁移。

### 对外提供网页访问

默认 Compose 只绑定 `127.0.0.1:8000`。如果部署在远端服务器，可先用 SSH 隧道从自己电脑体验：

```bash
ssh -L 8000:127.0.0.1:8000 用户名@服务器地址
```

然后在自己电脑浏览器访问 `http://127.0.0.1:8000`。员工正式访问应配置域名、证书和 HTTPS 反向代理，将域名转发到服务器 `127.0.0.1:8000`。将 `.env` 中 `COOKIE_SECURE=true` 后执行 `docker compose up -d --force-recreate api`；这个设置开启后必须通过 HTTPS 登录，本机 HTTP 调试需保持 false。

Nginx 已配置有效证书时，可在对应 HTTPS `server` 中使用：

```nginx
client_max_body_size 500m;
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_read_timeout 300s;
}
```

同时配置证书、HTTP 到 HTTPS 跳转、防火墙与反向代理登录限流。不要直接将数据库端口暴露公网。当前应用内登录限流按账号和请求来源记录，**仅适用于单进程**；代理后的来源识别与多实例统一限流需要由可信代理明确配置，不能盲目信任客户端转发头。默认保持一个 Uvicorn worker。

如需更大视频，需同时调整 `MAX_UPLOAD_MB` 和反向代理上传限制。浏览器兼容性取决于视频编码；后端不会自动转码。

## 6. 数据备份

- 本地模式：停止服务后备份整个 `data/` 目录（数据库与 `videos/`）。恢复时使用同一版本代码及配置。
- Docker 模式：备份 PostgreSQL 与视频卷，两者需协调到一致的时间点。建议在无上传、无考试写入的维护窗口进行。

```bash
# 将数据库导出到宿主机（正式环境请存入安全备份位置）
docker compose exec -T postgres pg_dump -U training training > training-backup.sql

# 将视频数据归档到当前目录，请在维护窗口运行
docker compose exec -T api tar -C /app/data -czf - . > training-videos.tar.gz
```

备份可能含个人数据，不要提交到 Git；恢复前先在独立环境验证。网页密码只保存加盐 PBKDF2 摘要，登录 cookie 为 HttpOnly / SameSite，服务器只保存会话 token 的摘要。原始视频与成绩需要访问控制和定期备份。

## 7. 测试与数据库迁移

```bash
# 在仓库根目录、激活虚拟环境后运行
python -m unittest discover -s tests -v
# 等价的旧入口
python scripts/smoke_test.py
```

测试使用临时 SQLite 数据库，不会写入 `.env` 指向的正式数据。覆盖登录、密码摘要、权限与跨站保护、视频鉴权与 Range 请求、跳转/暂停/过期上报、区间去重、学习门槛、限时考试、服务器判分、重复交卷、并发开考/交卷、密码重置与停用、限流、报表与 CSV 公式处理。另有浏览器完整学习流程测试，见 `tests/browser_smoke.cjs` 的文件头说明。

数据库首次版本为 `0001`，包含 6 张业务表与 Alembic 版本表。后续改模型时：

```bash
alembic revision --autogenerate -m "说明结构改动"
# 审查新迁移，备份数据库后执行
alembic upgrade head
alembic current
```

启动程序只执行仓库中已存在的迁移，不自动生成迁移、不清空业务数据。`python -m scripts.init_db` 可在不启动 Web 服务的情况下迁移并初始化管理员。

## 8. 代码导航

```text
app/
  database.py        # 环境配置、数据库连接、6 张业务表
  security.py        # 密码哈希、会话 token 哈希
  schemas.py         # 输入校验、字段长度与数值边界
  main.py            # 登录、视频、观看统计、考试、管理与导出接口
  static/
    index.html       # 员工学习与管理员网页
    style.css        # 响应式布局
    app.js           # 网页交互、播放上报、考试与后台操作
alembic/             # 数据库迁移环境与版本
scripts/             # 独立初始化与冒烟测试入口
tests/               # API 集成测试、浏览器流程测试
.env.example         # 环境变量说明，不含真实账号密码
Dockerfile           # 非 root 应用镜像与健康检查
docker-compose.yml   # PostgreSQL + API + 数据卷
```

主要 API：登录 `/api/login`，个人信息 `/api/me`，课程 `/api/courses`，受保护视频 `/media/{course_id}`，观看上报 `/api/courses/{course_id}/watch/heartbeat`，开考 `/api/courses/{course_id}/exam`，交卷 `/api/attempts/{attempt_id}/submit`，后台报表 `/api/admin/reports`。完整接口可在服务启动后查看 `/docs`。

所有写操作要求 `X-Requested-With: training-web` 请求头，网页已自动携带；用 `/docs` 或脚本调试时也必须添加此头，并携带登录获得的 cookie。服务仅面向同源网页，不配置跨域开放接口。

## 9. 常见问题

- **Windows 启动报 `UnicodeDecodeError: 'gbk' codec can't decode ...`**：旧版本 `alembic.ini` 的中文注释与 Windows 默认 GBK 编码冲突。运行 `git pull --ff-only` 更新配置后重启；临时可用 `python -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8000`。仓库内 `alembic.ini` 使用 ASCII 注释以兼容 Alembic 命令行和应用自动迁移，请保持该文件为 ASCII；业务 Python、网页与本 README 仍使用 UTF-8。不需要修改数据库、删除 `data/` 或更改系统区域设置。

- **首次启动提示设置 ADMIN_PASSWORD**：编辑仓库根目录 `.env`，设置至少 12 位的独立密码，重启。
- **登录后一直显示未登录**：检查是否在 HTTP 地址设置了 `COOKIE_SECURE=true`，以及是否混用了不同主机名。HTTPS 对外部署应开启 Secure，本机 HTTP 关闭。
- **登录报 429**：账号 10 分钟内失败达到 10 次会暂时限制；同来源请求也有 40 次的窗口限制。等待窗口到期，并核对账号密码。
- **网页没有课程**：检查是否已上传视频、添加题目并发布；草稿只对管理员可见。
- **视频无法播放**：确认浏览器支持对应编码，推荐 MP4/H.264/AAC；下架课程或停用账号会禁止新的视频请求。
- **观看进度停住或不足 100%**：保持页面前台、正常速度并避免跳转；核对管理员配置时长与视频实际时长；网络断开时未上报部分需重新观看。
- **修改配置后未生效**：本地需重启；Compose 的 `.env` 更改需重新创建 API 容器。已初始化账号和数据库密码不会因修改配置自动重置。

当前仓库提供可自行部署的网页系统，提交代码不会自动创建公网网站、域名或 TLS 证书。

## 10. 本次实现的验证结果

- 13 项 API 集成测试全部通过（含模拟 Windows GBK 的启动回归测试），覆盖正常流程、权限校验、观看统计、限时考试和并发提交。
- 真实 Chromium 完成了网页建账号、上传 12 秒视频、添加试题、发布、员工实际播放、考试 100 分、后台报表及 CSV 的完整流程；登录页同时检查了桌面和手机宽度。
- Docker 镜像构建通过，API 以非 root 用户运行；PostgreSQL 与 API 健康检查通过。
- 实际 PostgreSQL 环境验证了 12 秒观看记录、并发开考与交卷、100 分成绩及导出；重启 API 后视频、观看时长和成绩仍正常。

这些结果验证的是独立测试数据，不代表已经配置了你的正式员工账号、培训视频或公网部署。
