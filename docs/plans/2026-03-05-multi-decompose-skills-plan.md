# Multi Decompose Skills Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade reflect.py to cluster 20 eval tasks by type and generate specialized decompose skills per cluster, plus a task-router skill for the orchestrator.

**Architecture:** LLM-driven clustering of eval tasks → per-cluster strategy generation → router skill for runtime type matching. The orchestrator reads the router first, then loads the matching decompose skill.

**Tech Stack:** Python, OpenRouter API (Gemini Flash for generation), eval pipeline (verify_report.json + widesearch.jsonl)

---

### Task 1: Add `cluster_tasks()` to reflect.py

**Files:**
- Modify: `eval/reflect.py`

**Step 1: Add the `cluster_tasks()` function after `build_reflection_prompt()`**

```python
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

    prompt = f"""You are an AI systems engineer. Analyze these 20 information-seeking tasks and cluster them into 3-5 task types based on their query structure, required data schema, and error patterns.

## Tasks
{json.dumps(task_summaries, indent=2, ensure_ascii=False)}

## Instructions
Group these tasks into 3-5 clusters. For each cluster, provide:
1. A kebab-case type_name (e.g., "product-catalog", "timeline-events")
2. A description of what makes this type distinct
3. The list of instance_ids that belong to this cluster
4. The recommended decomposition_pattern (how to split work across workers)

Return ONLY valid JSON array, no markdown code fences:
[
  {{
    "type_name": "example-type",
    "description": "...",
    "instance_ids": ["ws_en_001", ...],
    "decomposition_pattern": "..."
  }},
  ...
]

Requirements:
- Every task must appear in exactly one cluster
- type_name must be kebab-case, max 25 chars
- Focus on structural similarity (schema shape, data volume, temporal vs categorical)
"""

    raw = call_gemini_flash(prompt)
    # Parse JSON from response
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*\n", "", raw)
        raw = re.sub(r"\n```\s*$", "", raw)
    clusters = json.loads(raw)
    return clusters
```

**Step 2: Run reflect.py to test clustering (add temporary test code at bottom)**

Run: `python -c "import json; from eval.reflect import cluster_tasks; r=json.load(open('eval/reports/verify_report.json')); print(json.dumps(cluster_tasks(r), indent=2))"`
Expected: JSON array with 3-5 clusters covering all 20 tasks

**Step 3: Commit**

```bash
git add eval/reflect.py
git commit -m "feat: add cluster_tasks() for LLM-driven task type clustering"
```

---

### Task 2: Add `generate_cluster_skill()` to reflect.py

**Files:**
- Modify: `eval/reflect.py`

**Step 1: Add the `generate_cluster_skill()` function**

```python
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

    prompt = f"""You are an AI systems engineer. Generate a specialized decomposition strategy for the following task type.

## Task Type: {type_name}
{cluster["description"]}
Recommended pattern: {cluster["decomposition_pattern"]}

## Tasks in This Cluster
{json.dumps(task_details, indent=2, ensure_ascii=False)}

## Error Patterns for This Cluster
### Missing Rows
{json.dumps(cluster_missing, indent=2, ensure_ascii=False)[:2000]}

### Compressed Trajectories (how orchestrator actually decomposed these tasks)
{json.dumps(cluster_trajs, indent=2, ensure_ascii=False)[:3000]}

## Generate SKILL.md

Create a SKILL.md with this exact structure (no code fences around the output):

---
name: decompose-{type_name}
description: Specialized decomposition strategy for {type_name} tasks.
---

## When to Use
[Describe when the orchestrator should use this strategy — what query patterns or data shapes indicate this type]

## Decomposition Template
[Step-by-step template for how to decompose this type of task. Be SPECIFIC with examples from the actual tasks above.]

## Worker Assignment Rules
[How many workers, what each worker should cover, max rows per worker]

## Required Columns Checklist
[List the types of columns that are commonly missed in this task type and how to ensure they're included]

## Anti-Patterns
[What NOT to do — based on actual failures from the error data above]

Requirements:
- Be SPECIFIC — reference actual task IDs and column names from the data
- Include concrete examples of good vs bad decomposition
- Keep under 600 words
- Start with the --- frontmatter, no code fences"""

    return call_gemini_flash(prompt)
```

**Step 2: Commit**

```bash
git add eval/reflect.py
git commit -m "feat: add generate_cluster_skill() for per-type strategy generation"
```

---

### Task 3: Add `generate_router_skill()` to reflect.py

**Files:**
- Modify: `eval/reflect.py`

**Step 1: Add the `generate_router_skill()` function**

```python
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
```

**Step 2: Commit**

```bash
git add eval/reflect.py
git commit -m "feat: add generate_router_skill() for task type routing"
```

---

### Task 4: Rewrite `main()` in reflect.py to use clustering pipeline

**Files:**
- Modify: `eval/reflect.py`

**Step 1: Update imports (add `re` at top if not already imported)**

Ensure these are imported at the top of reflect.py:
```python
import re
```

**Step 2: Replace the existing `main()` function**

```python
SKILLS_ROOT = PROJECT_ROOT / "orchestrator_skills"


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
        skill_content = clean_skill_content(raw_skill)

        skill_dir = SKILLS_ROOT / f"decompose-{type_name}"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(skill_content, encoding="utf-8")
        print(f"    Saved: {skill_path}")

    # Step 3: Generate router skill
    print(f"\n  Step 3: Generating task-router skill...")
    raw_router = generate_router_skill(clusters)
    router_content = clean_skill_content(raw_router)

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
```

**Step 3: Remove the old `SKILL_OUTPUT_DIR` constant and `build_reflection_prompt()` / `generate_strategy()` functions**

Delete:
- `SKILL_OUTPUT_DIR = PROJECT_ROOT / "orchestrator_skills" / "decompose-strategy"` (line 28)
- `build_reflection_prompt()` function (lines 31-123)
- `generate_strategy()` function (lines 126-129)

**Step 4: Update the docstring at the top of reflect.py**

```python
"""Self-reflection: analyze verify_report.json → generate multiple decompose skills by task type.

Usage:
    python eval/reflect.py                         # Default: read verify_report.json
    python eval/reflect.py --report path/to.json   # Custom report path

Outputs:
    orchestrator_skills/task-router/SKILL.md
    orchestrator_skills/decompose-{type}/SKILL.md  (one per cluster)
"""
```

**Step 5: Run reflect.py end-to-end**

Run: `python eval/reflect.py`
Expected:
- Prints 3-5 clusters
- Creates `orchestrator_skills/task-router/SKILL.md`
- Creates `orchestrator_skills/decompose-{type}/SKILL.md` for each cluster
- Removes old `orchestrator_skills/decompose-strategy/`

**Step 6: Commit**

```bash
git add eval/reflect.py orchestrator_skills/
git commit -m "feat: reflect.py now generates multi-type decompose skills via clustering"
```

---

### Task 5: Update `clean_skill_content()` to handle any type name

**Files:**
- Modify: `eval/reflect.py`

**Step 1: Update the fallback in `clean_skill_content()` to accept a type_name parameter**

```python
def clean_skill_content(raw: str, skill_name: str = "decompose-strategy") -> str:
    """Extract the SKILL.md content from LLM response, stripping code fences."""
    import re

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
```

**Step 2: Update callers to pass skill_name**

In `main()`, update the two calls:
```python
skill_content = clean_skill_content(raw_skill, f"decompose-{type_name}")
```
```python
router_content = clean_skill_content(raw_router, "task-router")
```

**Step 3: Commit**

```bash
git add eval/reflect.py
git commit -m "fix: clean_skill_content accepts dynamic skill names"
```

---

### Task 6: Update orchestrator system prompt for task-router flow

**Files:**
- Modify: `orchestrator/orchestrator_agent.py:63-131`

**Step 1: Update the system prompt in `_build_default_system_message()`**

Replace lines 66-72 (the YOUR JOB section) with:

```python
## YOUR JOB
1. Receive a task from the user.
2. Call `list_orchestrator_skills` to see available skills.
3. Call `read_orchestrator_skill("task-router")` to identify the task type.
4. Based on the matched type, call `read_orchestrator_skill("decompose-<type>")` to load the specialized decomposition strategy.
5. Decompose the task following the loaded strategy.
6. Call `execute_subtasks` with the list of subtask strings.
7. Synthesize the worker results into a final response.
```

**Step 2: Verify the OUTPUT section still references the verify skill (should already be correct)**

**Step 3: Commit**

```bash
git add orchestrator/orchestrator_agent.py
git commit -m "feat: orchestrator system prompt uses task-router for type-specific decomposition"
```

---

### Task 7: Run end-to-end test

**Step 1: Run reflect.py to generate all skills**

Run: `python eval/reflect.py`
Expected: Creates task-router + 3-5 decompose-{type} skills

**Step 2: Verify generated skills are readable**

Run: `ls orchestrator_skills/`
Expected: `decompose-{type1}/ decompose-{type2}/ ... task-router/ verify/ workboard/`

**Step 3: Verify each SKILL.md has valid frontmatter**

Run: `head -3 orchestrator_skills/*/SKILL.md`
Expected: Each starts with `---`

**Step 4: Push to demo branch**

```bash
git add -A
git commit -m "feat: complete multi-decompose-skills pipeline"
git push origin demo
```
