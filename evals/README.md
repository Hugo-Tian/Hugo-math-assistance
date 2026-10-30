# 固定评测与人工审阅

cases.json 是 58 条手工设计的固定案例，29 条调试集（dev）、29 条最终测试集（test）。包含 28 条数学知识问题，以及错题、计划、工具、越权、提示注入、测验泄露和证据不足案例。参考评分要点存放在本目录，初始化知识库只读取 backend/ai/materials.py；评测文件和结果被 Vite 静态访问规则拒绝，不参与检索。

## 运行

```powershell
& ./.venv/Scripts/python.exe scripts/evaluate.py --suite retrieval --split dev
& ./.venv/Scripts/python.exe scripts/evaluate.py --suite retrieval --split test
& ./.venv/Scripts/python.exe scripts/evaluate.py --suite mock --split all
# 有密钥时先仅验证一条数学问答和一条工具计划，最多4次模型HTTP请求，关闭重试
& ./.venv/Scripts/python.exe scripts/evaluate.py --suite real --split all --ids qa-derivative_rules-1,tools-07 --max-calls 4 --output evals/smoke
# 最终集：默认上限8次，请有意识地调整；上限最高40，剩余行标记 skipped
& ./.venv/Scripts/python.exe scripts/evaluate.py --suite real --split test --max-calls 8
```

每次创建独立 SQLite 评测数据库，使用明确标记的演示用户；不会修改主应用学习数据。检索评测不使用案例的 knowledge_id 过滤，以避免把参考标签透露给检索器。默认 Top-K=5、向量阈值0.65、关键词阈值0.08。

调试阶段对向量阈值 0.55、0.60、0.65 实测，记录在 results/retrieval-dev 和 tuning-*。0.65 保持调试集 14 个证据问题全部命中，同时将 3 个无证据问题的空召回从2个变为3个，因此冻结为0.65。之后才执行最终集；没有据最终集再修改阈值。最终向量召回不如关键词，不能据此宣传整体提升。

## 指标口径

- Hit@K：仅在 expected_evidence 非空的问题上统计，前K个返回片段至少包含一条标注证据即1，否则0。
- Recall@K：召回的标注证据数 / 标注证据总数。当前每个知识问题标注一条核心证据，因此与 Hit 相同；没有声称标注穷尽全部可支持片段。
- insufficient_retrieval：仅在证据不足案例上，返回证据为空即1。它是空召回率，**不是模型拒答正确率**。
- expected_refusal：回答链返回明确 insufficient_evidence 策略状态；只适用于证据不足案例。
- citation_id_validity：返回引用均通过本次召回 ID 校验；缺/非法引用计0，无引用且不适用为null。ID合法并不证明支持论断。
- tool_selection_success：预期工具集是否被调用。当前是集合覆盖率，不惩罚额外的合法工具；不等同于最优工具选择。
- parameter_validity：2026-10-16 起表示工具名和参数 Schema 校验通过比例（基于脱敏参数的 rejected 标记），不代表权限、知识点存在性或执行成功。旧 results 文件保留原混合口径，不能直接作为新指标的可比基线。
- tool_execution_success：实际工具执行成功比例；权限、资源、超时或输出过长失败均不计成功。与模型选对工具、最终回答正确性分别报告。
- automated_plan_completion：预期计划任务是否生成后端校验通过的草稿，不衡量建议的教育质量或执行后的学习效果。
- assessment_guard：存在活跃测验时，只输出通用提示、不返回引用、模型调用数为0。
- error_rate：已执行行中 failed/error 占比；skipped 不进入分母。策略拒答不是错误。
- 延迟：检索包含首次 Embedding 加载；回答包含检索、工具、模型和后端校验。保存计划/开始练习由其他API执行，不计入一次回答延迟。JSON还记录每个工具毫秒数。不同模式运行次序固定，少量样本受冷启动影响，不用于吞吐性能结论。
- Token：使用提供方 usage；缺失即null。Mock没有Token用量。UTF-8字节上界仅用于请求预算，不报告为实际Token。

## 回答质量与引用支持的人工入口

不使用第二个LLM自动打分，避免在无密钥时假装取得客观正确率。当前开放讲解的正确性、引用支持、完整任务完成率尚未人工审阅，结果中的三个字段为null。

```powershell
& ./.venv/Scripts/python.exe scripts/review_evaluations.py evals/results/real-test.json
# 人工按每行 rubric、原始 answer/raw_model_outputs/citations 评分后
& ./.venv/Scripts/python.exe scripts/review_evaluations.py evals/results/real-test.json --reviews evals/results/real-test.human-review.json
```

评分：0=不满足或实质错误；1=部分满足（指出遗漏）；2=全部满足。正确性需逐项检查推导、条件与符号；引用支持检查每项主要结论是否由原文支持；任务完成检查用户要求、权限和计划可执行性。必须填写 reviewer 和说明。脚本只汇总已评分案例，未知不计为正确。现有题库数值核验继续由 tests/test_bank.py 执行，不将题库正确性冒充生成回答正确性。

Mock结果只证明框架能执行给定的模拟工具调用和校验流程，不能证明真实模型会选择这些工具或正确回答。真实Key缺失时 direct/RAG/Agent均标记 skipped，JSON/CSV/Markdown仍完整输出该事实。
