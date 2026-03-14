# Multi Decompose Skills via Auto-Clustering

## Problem

The current system generates a single `decompose-strategy` skill from eval results. With 20 WideSearch tasks showing 41.7% row recall, the one-size-fits-all strategy fails because different task types need fundamentally different decomposition approaches (product catalogs vs timeline events vs ranking tables).

## Solution

Upgrade `reflect.py` to automatically cluster the 20 eval tasks by type, then generate a specialized decompose skill per cluster, plus a router skill that helps the orchestrator pick the right one at runtime.

## Architecture

```
eval/reflect.py (upgraded)
    Step 1: cluster_tasks()
        Input: widesearch.jsonl (query + schema) + verify_report.json (errors)
        LLM clusters 20 tasks → 3-5 types with names + member instance_ids

    Step 2: generate_cluster_skill() × N clusters
        For each cluster: collect queries, schemas, errors, trajectory digests
        LLM generates specialized SKILL.md
        Output: orchestrator_skills/decompose-{type_name}/SKILL.md

    Step 3: generate_router_skill()
        Output: orchestrator_skills/task-router/SKILL.md
        Contains type descriptions + matching rules for the orchestrator
```

## Runtime Flow (orchestrator)

```
list_orchestrator_skills
    → read_orchestrator_skill("task-router")       # identify task type
    → read_orchestrator_skill("decompose-{type}")  # load specialized strategy
    → decompose + execute_subtasks
    → read_orchestrator_skill("verify")            # self-check
    → final output
```

## Expected Clusters

| Type Name | Example Tasks | Decomposition Pattern |
|-----------|--------------|----------------------|
| product-catalog | ws_en_002, ws_en_011 | 1 worker per brand/entity |
| ranking-table | ws_en_001, ws_en_004, ws_en_005 | 1 worker per category |
| timeline-events | ws_en_003, ws_en_006, ws_en_009 | 1 worker per year/period |
| comparison-specs | ws_en_007, ws_en_008, ws_en_014 | 1 worker per entity |
| geographic-catalog | ws_en_020 | 1 worker per region/country |

## Files to Modify

1. **eval/reflect.py** — Add `cluster_tasks()`, `generate_cluster_skill()`, `generate_router_skill()`. Remove single-skill generation.
2. **orchestrator/orchestrator_agent.py** — Update system prompt to read task-router before decomposing.
3. **orchestrator_skills/task-router/SKILL.md** — New, auto-generated.
4. **orchestrator_skills/decompose-{type}/SKILL.md** — Multiple new, auto-generated.
5. **orchestrator_skills/decompose-strategy/SKILL.md** — Remove (replaced by type-specific skills).

## Success Criteria

- reflect.py produces 3-5 typed decompose skills + 1 router skill
- Orchestrator reads task-router and selects the correct decompose skill
- Re-running the 20 tasks shows measurable improvement in row recall (target: >60%)
