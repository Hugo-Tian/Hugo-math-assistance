# real / all 实际评测

执行时间：2026-10-30T12:21:10.146220+00:00

模型：deepseek-flash；Embedding：BAAI/bge-small-zh-v1.5；Prompt：math-assistant-v1.1；索引：201623d292ae4b42b035e1d0efdca036

真实 API 调用：3；Mock 调用：0。

```json
{
  "agent": {
    "rows": 1,
    "executed": 1,
    "skipped": 0,
    "error_rate": 1.0,
    "hit_at_k": null,
    "hit_at_k_n": 0,
    "recall_at_k": null,
    "recall_at_k_n": 0,
    "insufficient_retrieval": null,
    "insufficient_retrieval_n": 0,
    "tool_selection_success": 1.0,
    "tool_selection_success_n": 1,
    "parameter_validity": 1.0,
    "parameter_validity_n": 1,
    "tool_execution_success": 1.0,
    "tool_execution_success_n": 1,
    "citation_id_validity": null,
    "citation_id_validity_n": 0,
    "expected_refusal": null,
    "expected_refusal_n": 0,
    "assessment_guard": null,
    "assessment_guard_n": 0,
    "automated_plan_completion": 0.0,
    "automated_plan_completion_n": 1,
    "latency_mean_ms": 11870.034,
    "latency_p95_ms": 11870.034
  }
}
```

Hit/Recall 仅对有相关证据标注的案例计算；拒答指标与安全指标使用各自适用分母。检索延迟包含本地模型首次加载，回答延迟包含检索、工具、模型和校验。Token 未返回时为未知。

引用 ID 合法不代表支持结论；开放回答正确性、引用支持和任务完成需在 CSV 人工填写评分。Mock 仅验证应用流程，不代表真实模型效果。未配置 Key 的 direct/RAG 行标记 skipped，不生成伪造分数。
