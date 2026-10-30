# 课程化改造设计：从“高中数学”到“任意课程的 AI 助教”

日期：2026-10-30。状态：M1（课程化底座）、M2（前端课程化）已实施，M3–M5 未开始。

## 1. 目标与范围

**目标**：老师建立一门课、上传资料、确认知识结构后，学生即可获得有依据、不代写的辅导与练习，老师能看到全班掌握情况。新增一门课**只需要数据和配置，不需要改代码**。

**本阶段做**：

1. 课程化底座：课程、选课与课内角色，所有学习数据按课程隔离。
2. 知识图谱草拟：LLM 根据资料草拟知识点和先修关系，老师审核后生效。
3. 最简老师看板：全班掌握度、共同卡点、高频错题，全部规则计算。
4. 用第二门课（建议大学线性代数）端到端验证可迁移性。

**本阶段不做**（后续阶段）：开放题与评分细则、分级提示、学校/多租户层级、统一身份认证、合规备案、本地模型部署。

**原则**：保留现有的判题与掌握度后端规则、引用校验、测验保护；现有高中数学数据与历史记录完整迁入“默认课程”，用户无感。

## 2. 现状：哪些地方写死了

| 位置 | 写死内容 | 影响 |
| --- | --- | --- |
| `backend/models.py` `Knowledge` | 只有 `subject` 字段，无课程归属；`id` 为全局字符串主键 | 无法区分不同课程的同名知识点 |
| `backend/models.py` `User.goal_id` | 学习目标是全局唯一一个 | 学生同时修多门课时冲突 |
| `backend/config.py` | `PASS_MASTERY` 等通过标准为全局环境变量 | 不同课程无法设不同通过标准 |
| `backend/algorithms.py:8` 等 | `select(Knowledge)`、`select(Prerequisite)` 查询全部数据 | 图谱、推荐、掌握度会跨课程混算 |
| `backend/main.py:89`、`service.py:31,56`、`ai/plans.py:19` | 题目查询无课程过滤 | 搜题、组卷、计划会混入其他课程 |
| `backend/question_bank.py`、`seed.py`、`ai/materials.py` | 14 个数学知识点 ID、题库、讲义写在代码里 | 只能作为默认课程的种子数据 |
| `backend/ai/agent.py:18-21,69,72` | 系统提示词写死“高中数学”“$...$ 数学公式”“函数与导数路径” | 换课程后提示词与拒答文案错误 |
| `backend/ai/knowledge_base.py` `allowed_chunks` | 资料只按启用状态和题目授权过滤 | 检索会跨课程召回 |
| `User.role` | 只有 `student` / `admin` 两种全局角色 | 没有“某门课的老师”这一概念 |
| `src/App.vue:15,19,20` | 品牌区、侧栏、页脚写死“高中数学 第一版” | 前端无课程切换 |
| `src/pages/KnowledgeMap.vue` | 按 `chapter` 和固定坐标布局 | 节点数量和章节变化后布局失效 |
| `evals/cases.json`、`scripts/build_eval_cases.py` | 评测用例只针对数学 | 无法按课程评测 |

## 3. 数据模型

### 3.1 新增表

```text
courses
  id            str(40) PK            例：hs-math、la-2026
  name          str(100)              高中数学（函数与导数）
  subject       str(30)               math / physics / ...
  level         str(20)               middle / high / university
  language      str(10)  默认 zh
  settings      JSON                  通过标准、AI 策略，见 3.3
  status        str(20)               draft / active / archived
  created_by    FK users.id
  created_at    datetime

enrollments                           （课内角色，取代“全局老师”）
  course_id     FK courses.id   PK
  user_id       FK users.id     PK
  role          str(20)               teacher / ta / student
  goal_id       FK knowledge.id NULL  由 users.goal_id 迁来，按课程各自设定
  joined_at     datetime

knowledge_drafts                      （LLM 草拟、老师审核的图谱草稿）
  id            str(36) PK
  course_id     FK courses.id
  status        str(20)               pending / approved / rejected / superseded
  payload       JSON                  {nodes:[...], edges:[...]}，见第 5 节
  source_documents JSON               参与草拟的文档 ID
  model_meta    JSON                  模型、提示词版本、Token、耗时
  created_by / reviewed_by / created_at / reviewed_at
```

### 3.2 现有表增加 `course_id`

| 表 | 改动 | 说明 |
| --- | --- | --- |
| `knowledge` | 加 `course_id`（非空） | 新课程的 ID 用 `<课程>.<slug>` 命名（如 `la-2026.eigen`）；**现有 14 个 ID 保持不变**，归入 `hs-math` |
| `kb_documents` | 加 `course_id`（非空）；`knowledge_id` 改为可空 | 允许“整门课的资料”不挂在具体知识点上 |
| `practice_sessions` | 加 `course_id` | 组卷和测验保护按课程判断 |
| `ai_conversations` | 加 `course_id` | 对话、检索、工具都限定在本课程 |
| `users` | `goal_id` 迁入 `enrollments` 后删除；`role` 保留，仅表示平台管理员 | 课内权限一律看 `enrollments.role` |

`questions`、`attempts`、`mastery`、`mistakes` **不加列**：它们都通过 `knowledge_id` 归属课程，而知识点 ID 全局唯一。这样迁移时不需要改写 8 张表的外键值，风险最小。

> 取舍：没有把 `knowledge.id` 改成整数自增主键。那样更规范，但要同步改写 `attempts`、`mastery`、`prerequisites`、`kb_documents`、`ai_conversations`、`users` 等表的外键，还会让现有评测用例和演示数据失效。用“命名空间前缀 + 课程外键 + 应用层校验”可以达到同样的隔离效果。

### 3.3 课程级配置 `courses.settings`

```json
{
  "pass_mastery": 0.75,
  "pass_distinct": 5,
  "mastery_window": 20,
  "assessment_timeout_minutes": 120,
  "assistant": {
    "persona": "大学线性代数助教",
    "formula": "katex",
    "allow_direct_mode": false,
    "out_of_scope_message": "本课程资料没有覆盖这个问题，请补充具体概念或联系任课老师。"
  }
}
```

环境变量中的现有值作为新课程的默认值，`backend/config.py` 中的全局常量只保留兜底作用。

## 4. 权限与接口

### 4.1 角色

| 角色 | 来源 | 能做什么 |
| --- | --- | --- |
| 平台管理员 | `users.role = 'admin'` | 创建课程、指定老师、查看全平台诊断 |
| 课程老师 / 助教 | `enrollments.role` | 管理本课资料、审核图谱、导入题目、查看本课看板 |
| 学生 | `enrollments.role = 'student'` | 在已选课程内练习、提问、查看自己的报告 |

新增依赖 `course_member(course_id, roles=...)`：校验课程存在、状态可用、当前用户在该课中拥有所需角色，否则返回 404（不暴露课程是否存在）或 403。

### 4.2 路由

所有学习类接口移到课程前缀下：

```text
/api/courses                                  我的课程列表 / 管理员创建课程
/api/courses/{cid}/knowledge                  图谱与掌握度
/api/courses/{cid}/recommendations
/api/courses/{cid}/questions                  搜题
/api/courses/{cid}/sessions[/{sid}/answers]   练习
/api/courses/{cid}/report | mistakes
/api/courses/{cid}/assistant/...              对话、检索、计划
/api/courses/{cid}/teacher/dashboard          老师看板
/api/courses/{cid}/teacher/drafts[/{id}/approve]
```

过渡期保留旧路由，内部转发到 `hs-math`，前端全部切换完成后删除。

### 4.3 算法与 AI 层

- `algorithms.graph / knowledge_view / recommend / recompute` 增加 `course_id` 参数，只读本课程知识点与先修边。先修边**必须在同一课程内**，写入时校验。
- 掌握度通过标准从 `courses.settings` 读取。
- 系统提示词改为模板，由 `persona`、`subject`、`level`、`formula`、`language` 渲染；拒答文案使用 `out_of_scope_message`。提示词版本号升为 `course-assistant-v2.0`。
- `allowed_chunks` 加 `course_id` 过滤。向量索引暂时保持全局一个，检索结果本来就先按 SQL 授权过滤，所以不会跨课程泄露；课程超过约 50 门或单课资料很大时，再改为每课一个索引。
- 六个工具全部增加课程作用域：工具从对话的 `course_id` 取课程，**不接受模型传入课程参数**，防止越权。

## 5. 知识图谱草拟流程

```text
老师上传资料（现有 MD/TXT/PDF 导入）
  → 点击“生成知识图谱草稿”
  → 后端取本课所有片段的标题、章节与前 200 字（控制 Token 预算）
  → LLM 返回 JSON：nodes + edges
  → 后端校验（失败可自动返修一次，与对话的 JSON 返修复用同一机制）
  → 写入 knowledge_drafts(status=pending)
  → 老师在审核页编辑：改名、合并、删除节点，增删先修边
  → 点击“确认生效” → 单事务写入 knowledge / prerequisites
```

**草稿格式**

```json
{
  "nodes": [{"slug": "eigen", "name": "特征值与特征向量", "chapter": "第五章",
             "description": "…", "evidence": ["chunk-id-1", "chunk-id-2"]}],
  "edges": [{"from": "determinant", "to": "eigen", "reason": "求特征值需要计算行列式"}]
}
```

**后端校验规则**

- 格式严格（与现有 `Strict` Pydantic 模型一致），`slug` 唯一且符合 `^[a-z0-9_]+$`。
- 每个节点至少引用 1 个本课程片段，引用的片段必须真实存在（复用现有引用校验思路）。
- 先修边两端都存在，整体无环（复用 `algorithms.validate_dag`）。
- 节点数 3–60，单个节点的先修不超过 5 个。

**已生效图谱的修改规则**（保护学生历史数据）

- 可以新增节点和边、修改名称和描述。
- 已有作答记录的节点**不能删除**，只能停用；不能把它的 `slug` 改成别的知识点。
- 重新草拟生成新草稿，旧的待审核草稿标为 `superseded`，**不会静默覆盖**已生效的图谱。

**题目**：本阶段沿用现有 JSON 导入，由老师提供或审核题目。LLM 按知识点草拟题目作为可选扩展，同样走“草稿 → 审核 → 生效”。

## 6. 老师看板（最简版）

全部由规则计算，不调用 LLM，结论可复现：

1. **掌握度矩阵**：学生 × 知识点，单元格显示掌握度 / 未评估 / 已通过，可按知识点排序。
2. **知识点概况**：每个知识点的平均掌握度、已评估人数、通过人数、近 7 天作答量。
3. **共同卡点**：按“推荐的下一步是哪个先修缺口”分组，例如“12 人卡在函数单调性，都影响闭区间最值”。这直接复用现有推荐算法的输出。
4. **高频错题**：错误次数最多的题目及其所属知识点，可点进原题。

数据边界：老师只能看到本课选课学生；演示用的模拟数据单独标注；学生个人页面不显示其他同学的数据。

后续可加：由 AI 根据看板生成课堂干预建议，老师采纳后才生效。

## 7. 第二门课验证

**建议课程**：大学线性代数（前 5 章，约 12–15 个知识点）。理由：能体现“覆盖到高校”，公式仍用 KaTeX，复用现有渲染；知识先修关系清晰，适合检验图谱草拟质量。

**验收标准**

1. 新增课程的过程中**不改任何代码**，只通过界面或导入脚本完成。
2. 端到端跑通：建课 → 上传资料 → 草拟图谱 → 老师审核生效 → 导入每个知识点约 5 道题 → 学生练习 → 掌握度与推荐更新 → 助手回答引用线性代数资料 → 老师看板显示数据。
3. **隔离验证**：线性代数的检索、工具、推荐、看板中，不出现任何高中数学内容；反之亦然。
4. **回归验证**：高中数学课程的现有 52 项 pytest、浏览器测试和评测结果与改造前一致。
5. 图谱草拟质量：记录老师审核时修改的节点和边的比例，作为后续优化草拟提示词的基线。

## 8. 迁移方案（Alembic）

一个新 revision，按以下顺序执行，MySQL 与 SQLite 都要验证：

1. 建表 `courses`、`enrollments`、`knowledge_drafts`。
2. 插入默认课程 `hs-math`，其 `settings` 取当前环境变量的值。
3. 给 `knowledge`、`kb_documents`、`practice_sessions`、`ai_conversations` 加可空的 `course_id`，全部回填为 `hs-math`。
4. 为所有现有用户创建 `hs-math` 的选课记录：学生为 `student`，管理员同时为平台管理员和该课 `teacher`；`users.goal_id` 复制到 `enrollments.goal_id`。
5. 把 `course_id` 改为非空，加外键和索引；删除 `users.goal_id`。
6. `downgrade` 反向执行；仅当库中只有 `hs-math` 一门课时允许降级。

**迁移验证**：复制当前 `adaptive_math.db` 执行升级，比较升级前后每个演示账号的报告、掌握度、错题、推荐完全一致。方法与现有 `scripts/verify_restart.py` 相同。

## 9. 测试计划

| 类别 | 用例 |
| --- | --- |
| 隔离 | A 课学生检索、工具、搜题、组卷、计划都拿不到 B 课数据；跨课程先修边写入被拒绝 |
| 权限 | 学生访问看板 403；A 课老师访问 B 课看板 404；未选课用户访问课程 404 |
| 草稿 | 有环、引用不存在的片段、slug 重复、节点数超限都被拒绝；返修一次后成功；已生效节点删除被拒 |
| 迁移 | 升级后旧数据报告不变；旧路由转发结果与新路由一致 |
| 看板 | 共同卡点分组与推荐算法输出一致；模拟数据被标注 |
| 评测 | `evals/cases.json` 增加 `course_id` 字段；新增线性代数用例约 30 条，含证据不足与跨课程问题 |

## 10. 任务清单与里程碑

规模：S ≈ 半天，M ≈ 1–2 天，L ≈ 3 天以上。

**M1 课程化底座（后端）**

- [x] M · 新增 `courses`、`enrollments`、`knowledge_drafts` 模型与迁移，回填 `hs-math`（`72c7254ab8c4`）
- [x] M · 课程权限依赖（`backend/courses.py` 的 `course_context` / `course_staff`）；课程路由前缀；旧路由转发
- [x] M · 算法层、搜题、组卷、计划、报告按课程过滤；课程级通过标准
- [x] M · AI 层：提示词模板、`allowed_chunks` 课程过滤、工具课程作用域
- [x] S · 迁移验证脚本（`scripts/verify_course_migration.py`）
- [x] M · 隔离与权限测试（`tests/test_courses.py`）；现有测试全部通过

**M2 前端课程化**

- [x] M · 课程列表与切换，路由带课程 ID（`/c/:course/…`），Pinia 保存当前课程
- [x] S · 去掉品牌区、侧栏、页脚中写死的“高中数学”
- [x] M · 知识地图改为根据图谱自动分层布局（按先修拓扑排序），不依赖固定坐标

**M3 知识图谱草拟与审核**

- [ ] M · 草拟接口：片段摘要、Token 预算、调用模型、校验、一次返修
- [ ] L · 老师审核页：节点和边的编辑、合并、确认生效
- [ ] S · 已生效图谱的修改保护规则

**M4 老师看板**

- [ ] M · 看板接口：掌握度矩阵、知识点概况、共同卡点、高频错题
- [ ] M · 看板页面

**M5 第二门课验收**

- [ ] M · 准备线性代数资料与题目，按第 7 节完整走一遍
- [ ] S · 线性代数评测用例与结果记录；更新 README 与简历描述

建议顺序为 M1 → M2 → M4 → M3 → M5。看板先于草拟，是因为它只依赖底座，能尽早用现有数学数据展示老师视角；草拟功能工作量最大，放在底座稳定之后。

### M1 实施记录（2026-10-30）

- 学习与助手路由各挂载两次：`/api/courses/{cid}/…` 与旧的 `/api/…`（等同 `hs-math`），现有前端无需改动。助手路由中的对话 ID 参数由 `{cid}` 改名为 `{conv_id}`，避免与课程 ID 冲突。
- 算法与服务通过 `Scope`（课程、通过标准、学习目标）运行；作答提交从练习记录本身取得课程，不信任请求路径。
- 测验保护按课程判断：一门课未完成的练习不会挡住另一门课的助手。超时时长可在 `courses.settings.assessment_timeout_minutes` 覆盖。
- 向量索引与调用追踪仍为平台级，只有平台管理员可重建 / 查看。
- 验证：pytest 56 项通过（新增 4 项课程隔离与权限测试）；全新库迁移 + 初始化 + `alembic check` 通过；在真实演示库副本上升级、降级、再升级均通过，`verify_course_migration.py` 核对 10 名用户、126 条掌握度、18 条错题、10 条推荐与迁移前一致；MySQL 仅离线生成迁移 SQL，未在真实 MySQL 上执行。浏览器 E2E 因本机未安装 Playwright 浏览器未运行，改为在应用内浏览器人工核对首页与知识地图。
- 已知未做：`recommendations` 表未加课程列（推荐快照仍可从知识点推断课程）；前端仍是单课程界面（M2）。

### M2 实施记录（2026-10-30）

- 页面路由统一放在 `/c/:course/…` 下；未带课程的路径（页面内链接、跳转、旧书签）由全局路由守卫改写到当前课程，各页面原有的短路径无需修改。访问未加入的课程会退回当前课程。
- `store.api` 自动为课程内接口加上 `/api/courses/{course}` 前缀；账号级接口（登录、`/me`、课程列表）保持不变。上传资料改用同一请求函数。
- 侧栏在加入多门课程时显示课程切换下拉框（移动端同样可见）；老师入口按课内角色（老师 / 助教）或平台管理员显示。向量索引重建与调用追踪仍只对平台管理员显示。
- 学习目标改从推荐结果中读取（按课程）；登录后先加载课程数据再进入页面，避免页面读到空目标。
- 知识地图改为按先修深度分层：最左列为学习起点，每个知识点位于其最深先修的右一列，连线全部从左指向右；章节以颜色图例区分。首次打开时缩放不低于 60% 并居中显示选中节点，“适应窗口”可查看全图。
- 验证：`npm run build` 通过；在独立演示库（含“线性代数（演示）”第二门课）上于应用内浏览器核对登录、课程切换、两门课的知识地图、旧式链接跳转与移动端布局。浏览器 E2E 因本机未安装 Playwright 浏览器未运行。

## 11. 风险

| 风险 | 应对 |
| --- | --- |
| LLM 草拟的图谱质量不稳定 | 老师审核是必经步骤；记录修改比例；草稿可反复生成，不影响已生效图谱 |
| 迁移破坏现有数据 | 只加列不改外键值；在数据库副本上做前后对比；保留降级路径 |
| 字符串 ID 前缀依赖约定 | 写入时由后端统一生成 `<课程>.<slug>`，不接受用户直接填写完整 ID |
| 全局向量索引规模变大 | 检索前已有 SQL 授权过滤；规模变大后再拆为每课一个索引 |
| 范围蔓延 | 开放题、分级提示、多学校层级明确留到下一阶段 |
