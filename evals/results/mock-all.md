# mock / all 实际评测

执行时间：2026-09-14T02:09:25.370160+00:00

模型：deepseek-flash；Embedding：BAAI/bge-small-zh-v1.5；Prompt：math-assistant-v1.0；索引：201623d292ae4b42b035e1d0efdca036

真实 API 调用：0；Mock 调用：90。

```json
{
  "agent": {
    "rows": 16,
    "executed": 16,
    "skipped": 0,
    "error_rate": 0.0,
    "hit_at_k": null,
    "hit_at_k_n": 0,
    "recall_at_k": null,
    "recall_at_k_n": 0,
    "insufficient_retrieval": null,
    "insufficient_retrieval_n": 0,
    "tool_selection_success": 1.0,
    "tool_selection_success_n": 10,
    "parameter_validity": 1.0,
    "parameter_validity_n": 16,
    "citation_id_validity": 1.0,
    "citation_id_validity_n": 16,
    "expected_refusal": null,
    "expected_refusal_n": 0,
    "assessment_guard": null,
    "assessment_guard_n": 0,
    "automated_plan_completion": 1.0,
    "automated_plan_completion_n": 5,
    "latency_mean_ms": 133.7441875,
    "latency_p95_ms": 175.433
  },
  "direct": {
    "rows": 28,
    "executed": 28,
    "skipped": 0,
    "error_rate": 0.0,
    "hit_at_k": null,
    "hit_at_k_n": 0,
    "recall_at_k": null,
    "recall_at_k_n": 0,
    "insufficient_retrieval": null,
    "insufficient_retrieval_n": 0,
    "tool_selection_success": null,
    "tool_selection_success_n": 0,
    "parameter_validity": null,
    "parameter_validity_n": 0,
    "citation_id_validity": null,
    "citation_id_validity_n": 0,
    "expected_refusal": null,
    "expected_refusal_n": 0,
    "assessment_guard": null,
    "assessment_guard_n": 0,
    "automated_plan_completion": null,
    "automated_plan_completion_n": 0,
    "latency_mean_ms": 10.474321428571429,
    "latency_p95_ms": 36.334
  },
  "rag": {
    "rows": 42,
    "executed": 42,
    "skipped": 0,
    "error_rate": 0.0,
    "hit_at_k": null,
    "hit_at_k_n": 0,
    "recall_at_k": null,
    "recall_at_k_n": 0,
    "insufficient_retrieval": null,
    "insufficient_retrieval_n": 0,
    "tool_selection_success": null,
    "tool_selection_success_n": 0,
    "parameter_validity": null,
    "parameter_validity_n": 0,
    "citation_id_validity": 1.0,
    "citation_id_validity_n": 29,
    "expected_refusal": 1.0,
    "expected_refusal_n": 6,
    "assessment_guard": 1.0,
    "assessment_guard_n": 4,
    "automated_plan_completion": null,
    "automated_plan_completion_n": 0,
    "latency_mean_ms": 34.90304761904762,
    "latency_p95_ms": 103.51
  }
}
```

Hit/Recall 仅对有相关证据标注的案例计算；拒答指标与安全指标使用各自适用分母。检索延迟包含本地模型首次加载，回答延迟包含检索、工具、模型和校验。Token 未返回时为未知。

引用 ID 合法不代表支持结论；开放回答正确性、引用支持和任务完成需在 CSV 人工填写评分。Mock 仅验证应用流程，不代表真实模型效果。未配置 Key 的 direct/RAG 行标记 skipped，不生成伪造分数。
