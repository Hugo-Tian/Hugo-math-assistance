# 知序 · 课程级 AI 助教

从“高中数学智能学习助手”泛化而来：老师建立课程、上传资料、审核 AI 草拟的知识图谱后，学生获得有依据、不代写的辅导与练习，老师看到全班掌握情况。新增一门课只需要数据，不需要改代码。

**课程化改造（2026-10-30）**，设计与各里程碑实施记录见 [课程化设计](docs/GENERALIZATION_DESIGN.md)：

- 多课程与课内角色（老师 / 助教 / 学生），学习数据、检索、工具、对话按课程隔离；页面路由 `/c/<课程>/…`，接口 `/api/courses/<课程>/…`，旧路径等同默认课程 `hs-math`。
- 教学看板：全班掌握度矩阵、共同卡点、高频错题，全部规则计算。
- 知识图谱草拟：模型依据课程资料起草知识点与先修关系，后端严格校验，老师编辑后生效，生效不删除已有知识点。
- 第二门课验收：大学线性代数（12 个知识点、96 道参数化题）通过公开接口导入，端到端验收 16/16 通过，含真实模型问答与学习计划；检索与草拟质量见 [线性代数验收记录](evals/linalg-acceptance-20261030/README.md)。
- 新增课程：准备 `data/courses/<课程>/`（course.json、notes/*.md、graph.json、questions.json），运行 `python scripts/import_course.py data/courses/<课程> --api http://127.0.0.1:8000`；加 `--graph draft` 则先由模型草拟图谱再按参考图谱审核生效。
- 已有数据库升级：`alembic upgrade head` 会把现有数据整体迁入 `hs-math`；可先用 `python scripts/verify_course_migration.py` 在副本上核对迁移前后结果一致。

以下为高中数学版本的原始说明（仍是默认课程）。

在现有学习闭环上集成对话、知识库 RAG、工具调用 Agent 和三天复习计划。保留思维导图知识树及原闯关页面。LLM 组织讲解，后端继续负责判题、权限、掌握度和写入。

**本轮验证（2026-10-16）**：47 项 pytest、6 项浏览器端到端测试通过，前端构建成功；补充执行记录断言后，2 项 AI 浏览器测试再次通过。真实本地 BGE/FAISS 检索已运行；LLM 和工具选择仅通过 Mock/协议测试。当前后端未配置 API Key，真实模型调用为 0，默认真实模式明确报未配置，不静默回退。SQLite 隔离库迁移及进程重启持久化通过；MySQL 服务未启动，本轮仅完成离线迁移 SQL 生成，不能宣称 MySQL 集成验收通过。详见 [本轮核对、验证与四条简历介绍](docs/VALIDATION_20261016.md)。

本轮完善了完整回答 Schema、历史引用权限复查、生成期间权限变化保护、工具总时限与执行状态、冷启动说明，以及失败请求次数/未知 Token 处理。保留原 Vue 页面、六类只读工具和后端判题/掌握度规则；没有新增依赖。

## AI 功能启动

完成下方基础安装、迁移与题库初始化后：

```powershell
Copy-Item .env.example .env
# 编辑 .env：设置 LLM_API_KEY、LLM_MODEL、LLM_BASE_URL；不要提交 .env
& ./.venv/Scripts/python.exe scripts/init_knowledge.py --index --download-model
./scripts/start.ps1
```

首次索引需要下载真实中文模型；后续使用本地缓存。42 条自编讲义覆盖 14 个知识点，未导入官方教材。管理员从“知识库管理”导入 MD/TXT/文本 PDF，然后重建索引。扫描 PDF 明确提示需要 OCR。知识库说明、工具参数、权限边界见 [AI 模块说明](docs/AI_IMPLEMENTATION.md) 和 [工具 Schema](docs/AI_TOOL_SCHEMAS.json)。

无 Key 的独立测试环境：终端 1 运行 `& ./.venv/Scripts/python.exe scripts/run_mock_demo.py`；终端 2 运行 `$env:API_PROXY_TARGET='http://127.0.0.1:8002'; npm run dev -- --port 5174`。它使用 `tmp/assistant_mock.db`，页面明确显示 Mock；不能用于演示真实模型能力。

评测命令及指标见 [评测说明](evals/README.md)，实际结果见 [AI 验证记录](docs/AI_TEST_RESULTS.md)，展示与简历见 [三分钟演示](docs/AI_DEMO_AND_RESUME.md)。以下为复用的基础学习系统说明。

从原始《高中数学智能学习系统.html》迭代出的可运行作品集项目。高中数学第一版，14 个独立知识点、140 道原创演示单选题，打通：**学生作答 → 持久化 → 掌握度 → 先修缺口 → 动态推荐 → 针对练习 → 报告**。

![学习首页](docs/screenshots/dashboard-foundation.png)

技术：Vue 3、Vite、Vue Router、Pinia、KaTeX；FastAPI、SQLAlchemy、Alembic；MySQL，附 SQLite 无配置本地演示。规则算法无需付费 API。保留原型紫色风格及知识树、闯关、练习、搜题、错题本、报告入口。

## 快速运行（Windows PowerShell）

需要 Python 3.11+、Node.js 20.19+ 或 22.12+。在项目根目录执行；终端中的 `python` 应是带 pip/venv 的 Python 安装。本次机器的系统 python 是 MSYS2 版本，实际使用 Codex 附带的 CPython 建立了 `.venv`，现有环境可直接跳到迁移/启动命令。

```powershell
python -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -r requirements.txt
npm ci

# 不创建 .env 时默认使用项目目录的 adaptive_math.db，适合直接演示
& ./.venv/Scripts/python.exe -m alembic upgrade head
& ./.venv/Scripts/python.exe -m backend.seed

# 终端 1
& ./.venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# 终端 2
npm run dev
```

访问 http://127.0.0.1:5173 ，接口文档 http://127.0.0.1:8000/docs 。已安装依赖后，也可执行 `./scripts/start.ps1` 一起启动；首次安装用 `./scripts/start.ps1 -Install`。启动器 Ctrl+C 时停止它创建的后端。端口被占用时先关闭本项目旧实例。

macOS/Linux 可对应使用 `python3 -m venv .venv`、`.venv/bin/python` 和相同模块命令。

初始化仅在知识点表为空时插入演示数据，不重置已有答题。重复运行会输出 Already initialized。不要把删除数据库当作日常启动步骤。

`requirements.lock.txt` 保存本次实际安装的完整 Python 依赖版本；若要复现本次测试环境，可用 `pip install -r requirements.lock.txt` 替代上面的依赖安装命令。前端使用 package-lock.json 与 npm ci 固定依赖。

## MySQL

已在本机独立 MySQL 9.5 实例上实测迁移、初始化、并发幂等、通关和两账号推荐。项目使用标准 SQLAlchemy/MySQL 类型；附 Docker MySQL 8.4 配置，但 Docker 容器启动未在本环境验证。

用自己的 MySQL 管理账号创建项目专用空库/账号，避免使用日常业务库：

```sql
CREATE DATABASE adaptive_math CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'math_user'@'localhost' IDENTIFIED BY '替换为本地密码';
GRANT ALL PRIVILEGES ON adaptive_math.* TO 'math_user'@'localhost';
```

复制 `.env.example` 为 `.env`，修改 DATABASE_URL 中的账号密码。密码含 `@`、`#` 等字符时 URL 编码。随后执行 Alembic 和 seed，再启动后端。切换数据库不会自动搬运原 SQLite 历史；两个库是独立的数据集。

如使用 Docker：在 `.env` 设置 MYSQL_PASSWORD 和 MYSQL_ROOT_PASSWORD；执行 `docker compose up -d db`，等待 healthy，并把 DATABASE_URL 改为 `mysql+pymysql://math_user:你的密码@127.0.0.1:3307/adaptive_math?charset=utf8mb4`。卷 `math_data` 保留数据。

本次额外的独立 MySQL 验证程序见 `scripts/verify_mysql.py`，它只针对专门初始化的本地 3307 实例创建随机命名验证库，不可直接指向已有业务服务。验证过程和注意事项见 [测试记录](docs/TEST_RESULTS.md)。

## 演示账号

默认密码均为 `DemoMath2026!`，可在**首次初始化前**通过 DEMO_PASSWORD 替换。修改环境变量不会改变已经创建的密码。

| 用户名 | 角色 | 同一目标下的初始状态 |
| --- | --- | --- |
| demo_foundation | 学生 | 20 条模拟记录，集合/定义域/求值已通过，单调性需要巩固 |
| demo_advanced | 学生 | 50 条模拟记录，前 9 点已通过，导数计算需要巩固 |
| demo_admin | 管理员 | 维护知识点、题目/JSON 导入，查看两个演示学生概况 |

两学生目标均为“闭区间最值”，初始推荐分别为“函数单调性”和“导数计算”。数据使用与实际提交相同的后端服务初始化，并标记 simulated=true；页面展示模拟历史数量。注册新账号可查看“未评估”的真实冷启动。E2E 创建的 `e2e_时间戳` 账号用于测试，记录为自动化浏览器的实际作答，不是模拟历史。

## 测试与构建

```powershell
& ./.venv/Scripts/python.exe -m pytest -q
& ./.venv/Scripts/python.exe -m alembic check
& ./.venv/Scripts/python.exe scripts/verify_restart.py
npm run build
npx playwright install chromium
# 先启动 8000 后端和 5173 前端
npm run test:e2e
```

pytest 每例使用独立临时库，不修改演示库。浏览器测试新增测试学生，并对演示账号进行只读和拒绝写入场景；不会重置数据。`verify_restart.py` 使用独立数据库和 8011 端口，实际停止/重新创建后端进程，对比前后报告与会话。

前端生产产物为 dist。部署时用静态服务器提供 dist 并将 `/api` 代理至 FastAPI，SPA 其他路由回退 index.html；不要把整个工程根目录作为生产静态目录。Vite 开发服务也已拒绝访问题库答案文件、数据库和后端源码。`vite preview` 仅预览静态产物，未配置 API 代理，不作为完整系统启动命令。

## 文档与目录

- [原工程评估与实施记录](docs/INITIAL_REVIEW.md)
- [模型、算法、阈值、冷启动及局限](docs/ALGORITHM_AND_DATA.md)
- [实际测试结果](docs/TEST_RESULTS.md)
- [约 3 分钟演示流程与简历描述](docs/DEMO_AND_RESUME.md)
- `backend/`：API、事务、规则、数据模型、题库及初始化。
- `migrations/`：真实 Alembic 迁移；修改模型后新增 revision，不改旧迁移。
- `src/`：学生和管理员 Vue 页面、Pinia 数据层、KaTeX 安全渲染。
- `data/demo_questions.json`：140 题完整审阅/导入样例，含答案，仅供管理员离线使用。
- `tests/`、`e2e/`：业务、题库与浏览器验证。
- `docs/screenshots/`：实际运行截图。

题库为 14 个可核验的参数化题型、每型 10 个实例，不是 140 种独立命题；难度等级为演示编排，未经过真实学生校准。第一版只做函数与导数学习路径，不宣称全学科或全地区教材覆盖。视频、拍照未开放。AI 讲解已实现但真实模型验收受 API Key 缺失阻塞；旧版文档中“AI 未开放”属于升级前状态。没有虚构学习效果、用户规模或性能提升。
