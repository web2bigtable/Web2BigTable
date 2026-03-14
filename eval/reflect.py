"""Self-reflection: analyze verify_report.json → generate multiple decompose skills by task type.

Usage:
    python eval/reflect.py                         # Default: read verify_report.json
    python eval/reflect.py --report path/to.json   # Custom report path

Outputs:
    orchestrator_skills/task-router/SKILL.md
    orchestrator_skills/decompose-{type}/SKILL.md  (one per cluster)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from eval.utils import (
    REPORTS_DIR,
    call_gemini_flash,
    load_tasks,
    default_task_ids,
)

SKILLS_ROOT = PROJECT_ROOT / "orchestrator_skills"


def cluster_tasks(report: dict) -> list[dict]:
    """Use LLM to cluster tasks by type based on query structure, schema, and error patterns.

    Returns a list of cluster dicts:
    [
        {
            "type_name": "product-catalog",
            "description": "Tasks requiring enumeration of products across multiple brands",
            "instance_ids": ["ws_en_002", "ws_en_011"],
            "decomposition_pattern": "1 worker per brand/entity"
        },
        ...
    ]
    """
    task_ids = default_task_ids()
    tasks = load_tasks(task_ids)
    missing_cats = report.get("missing_categories", [])

    task_summaries = []
    for t in tasks:
        tid = t["instance_id"]
        eval_spec = t["evaluation"]
        # Find missing info for this task
        missing = next((m for m in missing_cats if m["instance_id"] == tid), None)
        missing_count = missing["missing_count"] if missing else 0
        total_gold = missing["total_gold"] if missing else "?"

        task_summaries.append({
            "instance_id": tid,
            "query_preview": t["query"][:300],
            "unique_columns": eval_spec["unique_columns"],
            "required_columns": eval_spec.get("required", []),
            "eval_columns": list(eval_spec.get("eval_pipeline", {}).keys()),
            "missing_rows": f"{missing_count}/{total_gold}",
        })

    prompt = f"""You are an AI systems engineer. Analyze these information-seeking tasks and cluster them by HOW they should be decomposed (the splitting strategy), NOT by their topic/domain.

## Tasks
{json.dumps(task_summaries, indent=2, ensure_ascii=False)}

## Instructions
Cluster these tasks into 3-5 groups based on the DECOMPOSITION PATTERN — how work should be split across parallel workers. The same pattern can apply to completely different topics.

Think about these dimensions:
- **Primary split axis**: by time period? by entity/brand? by geographic region? by category/rank segment?
- **Data density**: many rows per partition vs few rows with deep research per row?
- **Schema complexity**: wide tables with many technical columns vs narrow tables with text-heavy columns?

Example decomposition patterns (use these or derive your own):
- "split-by-time-period": Tasks where the natural partition is chronological (e.g., events per year, monthly data)
- "split-by-entity": Tasks where each entity/brand/organization is independent and gets its own worker
- "split-by-rank-segment": Tasks with ordered lists that should be divided into rank ranges (Top 1-10, 11-20, etc.)
- "split-by-region": Tasks where geographic or administrative boundaries define the partitions

For each cluster, provide:
1. A kebab-case type_name describing the DECOMPOSITION PATTERN (not the topic)
2. A description of WHEN and WHY to use this splitting strategy
3. The list of instance_ids that belong to this cluster
4. The decomposition_pattern details

Return ONLY valid JSON array, no markdown code fences:
[
  {{
    "type_name": "split-by-time-period",
    "description": "Use when data spans a timeline and each time segment is independent...",
    "instance_ids": ["ws_en_001", ...],
    "decomposition_pattern": "Assign one worker per time block (year, quarter, decade)..."
  }},
  ...
]

Requirements:
- Every task must appear in exactly one cluster
- type_name must describe the SPLITTING STRATEGY, not the topic
- Two tasks about completely different topics CAN be in the same cluster if they need the same splitting approach
- type_name must be kebab-case, max 25 chars
"""

    raw = call_gemini_flash(prompt)
    # Parse JSON from response
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*\n", "", raw)
        raw = re.sub(r"\n```\s*$", "", raw)
    clusters = json.loads(raw)
    return clusters


def generate_cluster_skill(cluster: dict, report: dict) -> str:
    """Generate a specialized decompose SKILL.md for a single task type cluster.

    Args:
        cluster: dict with type_name, description, instance_ids, decomposition_pattern
        report: the full verify_report.json dict
    """
    type_name = cluster["type_name"]
    instance_ids = cluster["instance_ids"]

    # Gather data for tasks in this cluster
    tasks = load_tasks(instance_ids)
    missing_cats = report.get("missing_categories", [])
    compressed_trajs = report.get("compressed_trajectories", {})

    cluster_missing = [m for m in missing_cats if m["instance_id"] in instance_ids]
    cluster_trajs = {k: v for k, v in compressed_trajs.items() if k in instance_ids}

    task_details = []
    for t in tasks:
        eval_spec = t["evaluation"]
        task_details.append({
            "instance_id": t["instance_id"],
            "query_preview": t["query"][:400],
            "unique_columns": eval_spec["unique_columns"],
            "required_columns": eval_spec.get("required", []),
            "eval_columns": list(eval_spec.get("eval_pipeline", {}).keys()),
        })

    prompt = f"""You are an AI systems engineer. Based on the evaluation data below, extract GENERAL decomposition principles for this task type. The output must be a reusable strategy that works for ANY task of this type, not just the specific tasks shown here.

## Task Type: {type_name}
{cluster["description"]}
Recommended pattern: {cluster["decomposition_pattern"]}

## Reference Data (use to extract patterns, do NOT reference directly in output)
### Sample Tasks in This Cluster
{json.dumps(task_details, indent=2, ensure_ascii=False)}

### Observed Error Patterns
{json.dumps(cluster_missing, indent=2, ensure_ascii=False)[:2000]}

### Observed Decomposition Trajectories
{json.dumps(cluster_trajs, indent=2, ensure_ascii=False)[:3000]}

## Generate SKILL.md

Create a SKILL.md with this exact structure (no code fences around the output):

---
name: decompose-{type_name}
description: Specialized decomposition strategy for {type_name} tasks.
---

## When to Use
[Describe the GENERAL query patterns and data shapes that indicate this task type. Use abstract descriptions, not specific topics.]

## Decomposition Template
[Step-by-step template using GENERIC placeholders like "entity A", "time period X". Explain the underlying PRINCIPLE behind each step, not just what to do.]

## Worker Assignment Rules
[General rules: max rows per worker, how to partition, when to add verification workers]

## Required Columns Checklist
[CATEGORIES of commonly missed columns (e.g., "secondary attributes", "temporal metadata") with generic examples. Do not list specific column names from the training data.]

## Anti-Patterns
[General failure modes derived from the error data. Describe the PATTERN of failure, not specific instances. Use hypothetical examples if needed.]

CRITICAL Requirements:
- Do NOT reference any specific task IDs (ws_en_XXX), specific column names, specific brands, people, or topics from the training data
- Use GENERIC examples and placeholders instead (e.g., "Brand A", "Entity X", "metric Y")
- Extract the UNDERLYING PRINCIPLE from each observed pattern
- The skill must be equally useful for a task the system has never seen before
- Keep under 600 words
- Start with the --- frontmatter, no code fences"""

    return call_gemini_flash(prompt)


def generate_router_skill(clusters: list[dict]) -> str:
    """Generate the task-router SKILL.md that helps the orchestrator identify the task type.

    Args:
        clusters: list of cluster dicts from cluster_tasks()
    """
    prompt = f"""You are an AI systems engineer. Generate a task-router skill that helps an orchestrator identify which type of information-seeking task it's facing.

## Available Task Types
{json.dumps(clusters, indent=2, ensure_ascii=False)}

## Generate SKILL.md

Create a SKILL.md with this exact structure (no code fences around the output):

---
name: task-router
description: Identifies the task type and directs the orchestrator to the correct decompose skill.
---

## How to Use
1. Read the user's query
2. Match it against the task types below
3. Call `read_orchestrator_skill("decompose-<matched_type>")` to load the specialized strategy

## Task Types

[For each type, provide:]
### <type_name>
**Match when:** [clear criteria — what words, patterns, or structures in the query indicate this type]
**Load skill:** `decompose-<type_name>`
**Key signal:** [the strongest indicator — e.g., "query mentions multiple brands/products"]

[Repeat for all types]

## Default Fallback
If no type matches clearly, use general decomposition principles:
- Split by entity or category
- Keep each worker under 30 rows
- List all required columns in every subtask

Requirements:
- Match criteria must be concrete and unambiguous
- Order types from most to least specific (specific matches first)
- Keep under 400 words
- Start with the --- frontmatter, no code fences"""

    return call_gemini_flash(prompt)


def clean_skill_content(raw: str, skill_name: str = "decompose-strategy") -> str:
    """Extract the SKILL.md content from LLM response, stripping code fences."""
    # Try to extract from code block
    match = re.search(r"```(?:markdown|md)?\s*\n(---.*?)```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()

    # If it starts with --- (frontmatter), use as-is
    if raw.strip().startswith("---"):
        return raw.strip()

    # Fallback: wrap in frontmatter
    return f"""---
name: {skill_name}
description: Auto-generated skill.
---

{raw.strip()}"""


def main():
    parser = argparse.ArgumentParser(description="WideSearch self-reflection → multi-skill generation")
    parser.add_argument(
        "--report",
        default=None,
        help="Path to verify_report.json (default: eval/reports/verify_report.json)",
    )
    args = parser.parse_args()

    report_path = Path(args.report) if args.report else REPORTS_DIR / "verify_report.json"

    if not report_path.exists():
        print(f"Error: Report not found at {report_path}")
        print("Run 'python eval/verify.py' first to generate the verification report.")
        sys.exit(1)

    report = json.loads(report_path.read_text(encoding="utf-8"))

    print(f"\nWideSearch Multi-Skill Reflection Pipeline")
    print(f"  Report: {report_path}")
    print(f"  Summary: {report.get('summary', {})}")

    # Step 1: Cluster tasks
    print(f"\n  Step 1: Clustering tasks by type...")
    clusters = cluster_tasks(report)
    print(f"  Found {len(clusters)} task types:")
    for c in clusters:
        print(f"    - {c['type_name']}: {c['instance_ids']}")

    # Step 2: Generate per-cluster decompose skills
    print(f"\n  Step 2: Generating decompose skills per cluster...")
    for c in clusters:
        type_name = c["type_name"]
        print(f"    Generating decompose-{type_name}...")
        raw_skill = generate_cluster_skill(c, report)
        skill_content = clean_skill_content(raw_skill, f"decompose-{type_name}")

        skill_dir = SKILLS_ROOT / f"decompose-{type_name}"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(skill_content, encoding="utf-8")
        print(f"    Saved: {skill_path}")

    # Step 3: Generate router skill
    print(f"\n  Step 3: Generating task-router skill...")
    raw_router = generate_router_skill(clusters)
    router_content = clean_skill_content(raw_router, "task-router")

    router_dir = SKILLS_ROOT / "task-router"
    router_dir.mkdir(parents=True, exist_ok=True)
    router_path = router_dir / "SKILL.md"
    router_path.write_text(router_content, encoding="utf-8")
    print(f"    Saved: {router_path}")

    # Clean up old single decompose-strategy if it exists
    old_strategy = SKILLS_ROOT / "decompose-strategy"
    if old_strategy.exists():
        import shutil
        shutil.rmtree(old_strategy)
        print(f"\n  Removed old decompose-strategy skill")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  Multi-Skill Reflection Complete!")
    print(f"  Generated {len(clusters)} decompose skills + 1 router skill:")
    for c in clusters:
        print(f"    - orchestrator_skills/decompose-{c['type_name']}/SKILL.md")
    print(f"    - orchestrator_skills/task-router/SKILL.md")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
