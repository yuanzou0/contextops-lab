---
name: ai-agent-project-strategist
description: Evaluate AI agent and LLM infrastructure projects, separate verified implementation from marketing claims, propose prioritized product/data/engineering improvements, and turn real contributions into US-English and China-Chinese resume narratives. Use for open-source project reviews, second-development roadmaps, AI product case studies, portfolio planning, experiment design, or resume/interview positioning for data analyst, AI product manager, and product operations roles.
---

# AI Agent Project Strategist

## Objective

Turn an AI agent project into an evidence-backed product assessment, an executable improvement plan, and honest market-specific career material.

## Workflow

1. Establish contribution scope before writing career claims:
   - Distinguish creator, contributor, fork maintainer, evaluator, deployer, and researcher.
   - Never attribute upstream features, benchmarks, users, or business outcomes to the candidate.
   - Mark unmeasured outcomes as proposed metrics or experiment targets.
2. Inspect primary evidence:
   - Read the repository overview, dependency manifest, architecture, core request path, tests, evaluation code, releases, and open issues.
   - Prefer code and reproducible artifacts over README claims.
   - Label every important statement as verified, self-reported, independently reproduced, inferred, or proposed.
3. Explain the project at three levels:
   - User problem and target segment.
   - System flow and technical mechanism.
   - Business value, trade-offs, and failure modes.
4. Evaluate product readiness across quality, latency, cost, reliability, privacy, observability, compatibility, and adoption friction.
5. Produce a prioritized second-development roadmap:
   - Use P0 for correctness and safe failure.
   - Use P1 for measurable product value and differentiation.
   - Use P2 for scale, distribution, and advanced capabilities.
   - Give each proposal a user problem, implementation outline, success metric, risk, and résumé value.
6. Design validation around cost per successful task, not compression or usage alone.
7. Tailor career positioning to the requested market and role. Read [resume-positioning.md](references/resume-positioning.md) for wording rules and templates.
8. For experiment design or roadmap scoring, read [evaluation-and-roadmap.md](references/evaluation-and-roadmap.md).

## Required Output Discipline

- Lead with a clear judgment, not a feature inventory.
- Separate upstream project facts from the candidate's work.
- Use placeholders such as `[N]` and `[X%]` until real measurements exist.
- Recommend the smallest portfolio extension that proves the target role's skills.
- For data roles, emphasize event design, SQL/Python analysis, experimental validity, segmentation, and decision impact.
- For product roles, emphasize problem framing, requirements, guardrails, rollout decisions, and cross-functional trade-offs.
- For product operations roles, emphasize onboarding, monitoring, cohorts, failure recovery, adoption, and ROI.
- Explicitly say when a project is a weak fit for a role.

## Deliverables

Return only those needed by the request:

- concise project explanation;
- evidence and risk assessment;
- P0/P1/P2 improvement roadmap;
- KPI tree and experiment plan;
- US-English résumé bullets and interview pitch;
- China-Chinese résumé bullets and interview pitch;
- portfolio repository structure;
- implementation backlog with acceptance criteria.
