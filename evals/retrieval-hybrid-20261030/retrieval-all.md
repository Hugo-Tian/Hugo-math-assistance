# retrieval / all 实际评测

执行时间：2026-10-30T12:28:29.238143+00:00

模型：deepseek-flash；Embedding：BAAI/bge-small-zh-v1.5；Prompt：math-assistant-v1.1；索引：201623d292ae4b42b035e1d0efdca036

真实 API 调用：0；Mock 调用：0。

```json
{
  "hybrid": {
    "rows": 58,
    "executed": 58,
    "skipped": 0,
    "error_rate": 0.0,
    "hit_at_k": 1.0,
    "hit_at_k_n": 28,
    "recall_at_k": 1.0,
    "recall_at_k_n": 28,
    "insufficient_retrieval": 1.0,
    "insufficient_retrieval_n": 6,
    "tool_selection_success": null,
    "tool_selection_success_n": 0,
    "parameter_validity": null,
    "parameter_validity_n": 0,
    "tool_execution_success": null,
    "tool_execution_success_n": 0,
    "citation_id_validity": null,
    "citation_id_validity_n": 0,
    "expected_refusal": null,
    "expected_refusal_n": 0,
    "assessment_guard": null,
    "assessment_guard_n": 0,
    "automated_plan_completion": null,
    "automated_plan_completion_n": 0,
    "latency_mean_ms": 7.0152758620689655,
    "latency_p95_ms": 10.563
  },
  "keyword": {
    "rows": 58,
    "executed": 58,
    "skipped": 0,
    "error_rate": 0.0,
    "hit_at_k": 1.0,
    "hit_at_k_n": 28,
    "recall_at_k": 1.0,
    "recall_at_k_n": 28,
    "insufficient_retrieval": 0.5,
    "insufficient_retrieval_n": 6,
    "tool_selection_success": null,
    "tool_selection_success_n": 0,
    "parameter_validity": null,
    "parameter_validity_n": 0,
    "tool_execution_success": null,
    "tool_execution_success_n": 0,
    "citation_id_validity": null,
    "citation_id_validity_n": 0,
    "expected_refusal": null,
    "expected_refusal_n": 0,
    "assessment_guard": null,
    "assessment_guard_n": 0,
    "automated_plan_completion": null,
    "automated_plan_completion_n": 0,
    "latency_mean_ms": 2.648948275862069,
    "latency_p95_ms": 3.914
  },
  "vector": {
    "rows": 58,
    "executed": 58,
    "skipped": 0,
    "error_rate": 0.0,
    "hit_at_k": 0.9642857142857143,
    "hit_at_k_n": 28,
    "recall_at_k": 0.9642857142857143,
    "recall_at_k_n": 28,
    "insufficient_retrieval": 1.0,
    "insufficient_retrieval_n": 6,
    "tool_selection_success": null,
    "tool_selection_success_n": 0,
    "parameter_validity": null,
    "parameter_validity_n": 0,
    "tool_execution_success": null,
    "tool_execution_success_n": 0,
    "citation_id_validity": null,
    "citation_id_validity_n": 0,
    "expected_refusal": null,
    "expected_refusal_n": 0,
    "assessment_guard": null,
    "assessment_guard_n": 0,
    "automated_plan_completion": null,
    "automated_plan_completion_n": 0,
    "latency_mean_ms": 15.0065,
    "latency_p95_ms": 9.463
  }
}
```

Hit/Recall 仅对有相关证据标注的案例计算；拒答指标与安全指标使用各自适用分母。检索延迟包含本地模型首次加载，回答延迟包含检索、工具、模型和校验。Token 未返回时为未知。

引用 ID 合法不代表支持结论；开放回答正确性、引用支持和任务完成需在 CSV 人工填写评分。Mock 仅验证应用流程，不代表真实模型效果。未配置 Key 的 direct/RAG 行标记 skipped，不生成伪造分数。
