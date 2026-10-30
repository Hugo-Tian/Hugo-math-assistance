# 高中数学智能学习助手：本轮实现核对与验证

日期：2026-10-16。项目：edu_reg_sys。保留 Vue 3 / FastAPI / SQLAlchemy / SQLite / MySQL 架构、页面风格、原学习业务及已有测试。未添加依赖，未提交或推送，未重置主数据库。学习计划及启动脚本已有用户工作区改动保留。

## 四项介绍对照

| 项目 | 已有代码 | 本轮补齐 | 本轮证据 |
| --- | --- | --- | --- |
| RAG | MD/TXT/文本 PDF 导入、章节/标题/页码/片段 ID、数学块切分、BGE/FAISS、关键词基线、引用原文与授权过滤 | 历史引用失效隐藏、生成期间权限变化复查、失效历史不进入新上下文 | 真实本地 BGE/FAISS + 接口测试；生成仅 Mock |
| Agent | 六类只读工具、模型 tool_calls 分派、参数白名单、本人数据绑定、先修规则、计划确认保存 | 剩余总时限约束、工具输出过大标失败、冷启动提示、执行记录展示、错题工具依据要求 | Mock 协议、接口与浏览器闭环；真实模型选择未验证 |
| 模型与服务 | 后端环境配置、有限重试、历史条数/字符预算、真实/Mock 区分、对话/计划持久化 | 完整回答 Schema、畸形响应分类、失败尝试计数、无效 usage 归未知 | 47 项 pytest、进程重启、SQLite 迁移；MySQL 在线受阻 |
| 评测 | 58 条固定案例、dev/test、检索对照、调用上限、人工评分入口、E2E | 14 项边界回归；参数 Schema 与执行成功指标分离；新原始结果 | 116 行检索、86 行 Mock 变体；真实 3 行跳过 |

## 实际结果

- 初始基线：33 passed。最终 `python -m pytest -q`：**47 passed，0 failed，0 skipped**，28.83 秒。2 条 Starlette/httpx/anyio 弃用警告，不为消警告增加依赖。
- `npm run build`：通过，54 modules，生产构建成功。
- 显式 Mock 隔离后端 + 真实本地 BGE，`npm run test:e2e`：**6 passed，0 failed，0 skipped**，24.6 秒。执行记录新增断言后 AI 子集 **2 passed**，4.7 秒。这不是 8 个不同测试。
- 独立 SQLite `tmp/validation-20261016-e2e.db`：`alembic upgrade head` 成功，`alembic check` 无差异。没有指向 adaptive_math.db。
- `scripts/verify_restart.py`：独立随机 SQLite 库，真实停止/重启后端；登录令牌、答题/掌握度/错题/报告、Mock 对话、引用、工具诊断与已确认计划保持一致。
- `scripts/verify_mysql.py`：**失败（环境）**，127.0.0.1:3307 拒绝连接，WinError 10061；没有创建验证库或触及现有 MySQL 数据。MySQL 方言 `alembic upgrade head --sql` 成功，SQL 位于忽略目录 tmp/mysql-validation-20261016.sql。离线生成不能证明事务、驱动及权限在真实 MySQL 正常。
- Vite 第一次启动因沙箱目录访问失败；获准在沙箱外启动本地测试前端后 E2E 完成。未修改应用逻辑绕过权限。

## 检索指标（真实本地，未调参）

复用原 58 条案例、原阈值与 Top-K=5；dev/test 合并运行用于本轮回归，没有用 test 修改阈值或参考答案。原始逐条结果保留 split，可分别分析。

| 指标 | 关键词词项覆盖基线 | BGE + FAISS |
| --- | --- | --- |
| 有证据案例 Hit@5 | 28/28 | 27/28 |
| Recall@5 | 1.0000 | 0.9643 |
| 证据不足案例空召回 | 3/6 | 6/6 |
| 检索平均延迟 | 2.264 ms | 14.647 ms |
| 检索 P95 | 2.864 ms | 7.212 ms |

每个当前标注案例只有一条相关片段，所以 Hit 和 Recall 相同。向量平均延迟含首次模型加载，因此可以高于 P95；不用于生产吞吐结论。关键词不是 BM25。向量并非必然更优；返回空证据也不等同于数学答案质量。

## 工具结果与回答质量

Mock 共 86 个变体（direct 28 / rag 42 / agent 16），90 次 Mock provider 调用，真实 HTTP 模型调用 0。Agent 16 行工具执行成功比例均为 1；有工具选择期望的 10 行全部满足，但固定 Mock 返回六工具，不能证明真实模型选择能力。预期计划 5/5 形成有效草稿；证据不足 6/6 拒答、测验保护 4/4。

Mock Agent 平均延迟 142.431 ms、P95 223.526 ms；RAG 平均 42.601 ms、P95 110.677 ms。仅代表本机夹具流程。逐工具耗时、模型轮次及调用次数保存在 JSON，缺失 Token 为 null。

真实 smoke 上限设为 4 次、关闭重试；配置检查只输出 key_configured=false。2 个案例产生 3 个变体，全部因 missing_api_key 跳过，实际调用 **0**。真实模型回答正确性、真实工具选择、真实延迟/Token、引用对结论支持均**未验证**，人工评分保持空值。没有付费批量评测。

原始记录：[检索 JSON](../evals/validation-20261016/retrieval-all.json)、[Mock JSON](../evals/validation-20261016/mock-all.json)、[真实跳过记录](../evals/validation-20261016/real-all.json)；同目录提供 CSV 和 Markdown。

## 启动与演示

正常启动按 README：安装已有 requirements/package-lock 依赖，`alembic upgrade head`、`python -m backend.seed`、`scripts/start.ps1`。已有数据不重置。真实问答先在后端环境设置 LLM_API_KEY，未配置时页面明确提示；本轮没有验证实际账户模型名称可用性。

无 Key 演示沿用 `python scripts/run_mock_demo.py`，前端设置 API_PROXY_TARGET=http://127.0.0.1:8002 后 `npm run dev -- --port 5174`。脚本显式使用独立 Mock 数据库。需要本地模型缓存及已建立的索引；首次初始化按 README 的 init_knowledge 命令。

1. 登录新账号，从知识树进入“向 AI 提问”，查看来源原文、章节和片段 ID。
2. 提问库外问题，查看证据不足提示；管理员停用资料，再读取原文/历史，验证失效保护。
3. 提交练习后请求三天计划，展开执行记录查看六工具与未知 Token；新账号应显示尚未评估。
4. 点击保存计划，再开始练习；先修未满足由后端拒绝，作答和掌握度仍由原业务服务计算。
5. 刷新/重启后读取历史；用第二账号访问第一账号的会话和计划，接口拒绝。

## 可复现命令

```powershell
& ./.venv/Scripts/python.exe -m pytest -q
npm run build
& ./.venv/Scripts/python.exe scripts/verify_restart.py
& ./.venv/Scripts/python.exe scripts/evaluate.py --suite retrieval --split all --output evals/your-new-run
& ./.venv/Scripts/python.exe scripts/evaluate.py --suite mock --split all --output evals/your-new-run
# 启动显式 Mock 后端与指向它的前端，再执行：
$env:AI_MOCK_E2E='1'
$env:E2E_BASE_URL='http://127.0.0.1:5174'
npm run test:e2e
# 仅在已配置且有调用授权时执行小规模真实验证：
& ./.venv/Scripts/python.exe scripts/evaluate.py --suite real --split all --ids qa-derivative_rules-1,tools-07 --max-calls 4 --output evals/your-new-smoke
```

## 文件改动

- backend/ai/{agent,knowledge_base,provider,routes,schemas}.py：结构、权限、时间、统计及输出边界。
- src/pages/Assistant.vue：执行诊断、关闭旧原文后重新请求，保留原页面风格。
- tests/test_ai_boundaries.py：14 项边界回归，不修改或跳过原测试。
- e2e/assistant.spec.js：补执行记录与未知用量断言。
- scripts/evaluate.py：参数 Schema 与工具执行指标分离。
- scripts/verify_restart.py：增加 Mock 对话及计划真实进程重启检查。
- README.md、docs/AI_IMPLEMENTATION.md、docs/AI_TEST_RESULTS.md、evals/README.md、本报告、PROJECT_LEARNING_PLAN.md 末尾：现状、证据和教学记录。
- evals/validation-20261016/：retrieval-all、mock-all、real-all 各 JSON/CSV/MD，共 9 个文件。
- docs/screenshots/：既有 E2E 更新 admin、answer-feedback、assistant-citation-mock、assistant-plan-mock、dashboard-advanced、dashboard-foundation、mobile、report 共 8 张真实截图。

## 简历四条（当前可用表述）

1. 基于 BGE 与 FAISS 实现数学知识库 RAG，支持文档切分、向量检索、来源原文与引用校验，并实现证据不足拒答和资料权限过滤。
2. 封装学习画像、掌握度、错题、先修关系、练习推荐与知识检索六类工具，结合后端参数/权限校验生成待确认复习计划，完成 Mock 工具协议与业务流程验证。
3. 基于 Vue 3、FastAPI 与 SQLAlchemy 实现问答及学习记录管理，完善模型适配、结构化输出、上下文预算、超时重试；验证 SQLite 持久化，保留 MySQL 迁移支持。
4. 复用 58 条固定案例对比关键词与向量检索，分别记录工具执行、延迟和用量状态，通过 47 项自动化测试及 6 项端到端测试验证流程和权限隔离。

不能写“真实 LLM/Agent 效果已验证”“RAG 正确率提升 X%”“向量全面优于关键词”“本轮 MySQL 集成全部通过”“生产级高并发/完整教材覆盖”或“学习成绩提升”。引用 ID 合法不证明内容正确；生成计划的自然语言理由仍需要人工核验，结构规则无法证明每句都真实。

## 教学小练习（不记为已掌握）

- RAG，15 分钟：追踪 allowed_chunks → run_assistant → turn_view → source；停用来源后检查历史/原文，解释历史授权与当前授权。
- Agent，15 分钟：用两个账号比较 profile 和计划，再传入额外 user_id；解释模型提出调用、后端决定执行，以及草稿与保存的边界。
- 模型，15 分钟：构造缺字段、额外字段和未知 usage 三类响应；解释 JSON、Schema、业务校验的区别，以及估算预算为何不等于实际 Token。
- 评测，15 分钟：从结果选一个合法引用但不支持答案的例子，分别评引用 ID、引用支持和正确性；对比 keyword/vector 的一条失败案例，不修改参考标签。

本轮开发与自动验证由 Codex 完成。用户独立掌握情况保持原记录，不因代码通过测试自动升级。

## 已知限制

仅函数与导数路径、自编演示资料；扫描 PDF/OCR、混合检索、重排、SSE 未实现且不属此次必要改动。公式保护主要针对现有 $$ 块与 Markdown 段落，复杂 PDF 数学版式仍需导入后人工检查。提供方真实响应质量未验收。后台只读线程超时不保证线程立即终止。权限收回不能撤回已送达浏览器/模型的历史内容。MySQL 在线与生产部署仍待独立验收。
