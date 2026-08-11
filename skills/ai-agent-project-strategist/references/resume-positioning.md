# Resume Positioning Reference

## Ownership vocabulary

Use verbs that match evidence:

| Actual role | Safe verbs |
|---|---|
| Original/core author | built, designed, launched, owned |
| Upstream contributor | contributed, implemented, fixed, evaluated |
| Fork or extension author | extended, integrated, developed on top of |
| Independent evaluator | evaluated, benchmarked, analyzed, reproduced |
| User/deployer | deployed, configured, tested, documented |

Never convert upstream README numbers into personal impact. Write `the project reports X` in analysis; omit it from résumé bullets unless independently reproduced.

## US market

Prefer action + method + measured outcome + decision impact. Keep bullets direct and specific. Use `percentage points` for rate changes and state the baseline. Strong titles include:

- `AI Agent Cost & Performance Analytics`
- `AI Agent Context Optimization — Independent Evaluation`
- `AI Infrastructure Product Case Study`

For product management, show problem discovery, requirements, success metrics, experiments, guardrails, and rollout decisions. For product operations, show cohort segmentation, onboarding, monitoring, incident/fallback workflows, and ROI. For data analysis, show event schemas, SQL/Python pipelines, experimental design, uncertainty, dashboards, and recommendations.

Template:

> Designed a paired evaluation across `[N]` AI-agent tasks, measuring input tokens, P95 latency, retrieval frequency, and task completion; identified `[segment]` as the highest-value workload with `[X%]` lower quality-adjusted cost.

## China market

Use `项目背景 / 核心工作 / 项目成果` when space allows. Connect technical work to business judgment and implementation. Avoid vague phrases such as “深入参与” and “赋能业务.”

Template:

> 设计 `[N]` 个 AI Agent 任务的压缩组/基准组配对实验，使用 Python/SQL 分析 Token、P95 时延、召回率与任务完成率，识别 `[场景]` 为最高收益用户群，单次成功任务成本降低 `[X%]`。

## Metric guardrails

Prefer:

- cost per successful task;
- quality-adjusted token savings;
- task completion rate;
- P50/P95 end-to-end latency;
- exact-context recall success;
- tool selection false-negative rate;
- silent failure and fallback rate;
- manual intervention rate.

Avoid optimizing compression ratio alone.
