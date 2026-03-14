"""WideSearch verification pipeline: compress trajectory + compare with gold + error report.

Usage:
    python eval/verify.py                          # Verify all 20 tasks
    python eval/verify.py --tasks ws_en_001        # Verify single task
    python eval/verify.py --skip-compress          # Skip trajectory compression
    python eval/verify.py --skip-llm-judge         # Use exact_match fallback for llm_judge columns

Outputs:
    eval/reports/verify_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from eval.utils import (
    GOLD_DIR,
    LOGS_DIR,
    OUTPUTS_DIR,
    REPORTS_DIR,
    call_gemini_flash,
    default_task_ids,
    evaluate_cell,
    find_latest_trajectories,
    load_gold_csv,
    load_tasks,
    match_columns,
    match_rows,
    norm_str,
    normalize_column_name,
    parse_markdown_table,
    parse_trajectory,
)


# ---------------------------------------------------------------------------
# Step 3a: Compress trajectory via Gemini Flash
# ---------------------------------------------------------------------------

def compress_trajectory(instance_id: str, trajectories: list[Path]) -> str:
    """Compress worker trajectories into a structured summary using Gemini Flash.

    Returns the compressed summary text.
    """
    if not trajectories:
        return "(no trajectories found)"

    # Build trajectory digest
    digest_parts = []
    for traj_path in trajectories:
        traj = parse_trajectory(traj_path)
        header = traj["header"]
        events = traj["events"]

        worker_idx = header.get("worker_index", "?")
        subtask = header.get("subtask", "?")
        status = header.get("status", "?")
        elapsed = header.get("time_taken_seconds", 0)

        # Extract key events
        tool_calls = [e for e in events if e.get("event") == "tool_call_start"]
        tool_errors = [e for e in events if e.get("event") == "tool_call_error"]
        tool_ends = [e for e in events if e.get("event") == "tool_call_end"]

        # Count by tool name (workers use bash_tool for serpapi, not literal "search")
        tool_name_counts: dict[str, int] = {}
        for t in tool_calls:
            name = t.get("tool_name", "unknown")
            tool_name_counts[name] = tool_name_counts.get(name, 0) + 1
        tool_summary = ", ".join(f"{name}×{cnt}" for name, cnt in sorted(tool_name_counts.items()))

        # Collect tool result previews for richer context
        tool_result_previews = []
        for t in tool_ends[:5]:  # first 5 results
            preview = str(t.get("result_preview", ""))[:150]
            if preview:
                tool_result_previews.append(f"  - {t.get('tool_name', '?')}: {preview}")

        result_preview = header.get("result_preview", "")

        digest_parts.append(f"""### Worker {worker_idx} (status={status}, {elapsed}s)
Subtask: {subtask[:500]}
Tool calls: {len(tool_calls)} total ({tool_summary})
Tool errors: {len(tool_errors)}
Tool result samples:
{chr(10).join(tool_result_previews) if tool_result_previews else "  (none)"}
Final result preview: {result_preview[:500]}
""")

    trajectory_digest = "\n".join(digest_parts)

    prompt = f"""Analyze this orchestrator execution trajectory for task {instance_id}.
Provide a structured summary covering:

1. **Decomposition**: How the orchestrator split the task (number of subtasks, scope of each)
2. **Per-worker summary**: What each worker searched, fetched, and returned (data volume)
3. **Issues**: Any truncations, failures, incomplete searches, or timeouts
4. **Coverage assessment**: Were all aspects of the task addressed?

Trajectory digest:
{trajectory_digest}

Output a concise structured summary (max 500 words)."""

    return call_gemini_flash(prompt)


# ---------------------------------------------------------------------------
# Step 3b: Compare with gold answer
# ---------------------------------------------------------------------------

def compare_with_gold(
    instance_id: str,
    task: dict,
    *,
    skip_llm_judge: bool = False,
) -> dict[str, Any]:
    """Compare system output with gold CSV using WideSearch eval pipeline.

    Returns detailed scoring report.
    """
    eval_spec = task["evaluation"]
    unique_columns = eval_spec["unique_columns"]
    required_columns = eval_spec.get("required", [])
    eval_pipeline = eval_spec.get("eval_pipeline", {})

    # Load system output
    output_path = OUTPUTS_DIR / f"{instance_id}.md"
    if not output_path.exists():
        return {
            "instance_id": instance_id,
            "error": f"Output file not found: {output_path}",
            "scores": {},
        }

    output_text = output_path.read_text(encoding="utf-8")
    pred_rows = parse_markdown_table(output_text)

    if not pred_rows:
        return {
            "instance_id": instance_id,
            "error": "Failed to parse markdown table from output",
            "scores": {},
            "output_preview": output_text[:500],
        }

    # Load gold
    gold_rows = load_gold_csv(instance_id)

    # Build column mappings
    # eval_col → output_header (for predicted rows)
    output_headers = list(pred_rows[0].keys()) if pred_rows else []
    all_eval_cols = list(set(required_columns + unique_columns))
    col_mapping = match_columns(output_headers, all_eval_cols)

    # eval_col → gold_header (for gold rows)
    gold_headers = list(gold_rows[0].keys()) if gold_rows else []
    gold_col_mapping = match_columns(gold_headers, all_eval_cols)

    # Match rows
    matched, missing, extra = match_rows(pred_rows, gold_rows, unique_columns, col_mapping)

    # Evaluate each matched row
    cell_results: list[dict] = []
    column_scores: dict[str, dict] = {}

    for pred_row, gold_row in matched:
        for eval_col, pipeline in eval_pipeline.items():
            # Get predicted value via output column mapping
            output_col = col_mapping.get(eval_col)
            if output_col is None:
                gold_col = gold_col_mapping.get(eval_col, eval_col)
                cell_results.append({
                    "eval_col": eval_col,
                    "gold_val": gold_row.get(gold_col, gold_row.get(eval_col, "")),
                    "pred_val": "(column missing)",
                    "correct": False,
                    "metric": "missing_column",
                })
                continue

            pred_val = pred_row.get(output_col, "")
            # Get gold value via gold column mapping
            gold_col = gold_col_mapping.get(eval_col, eval_col)
            gold_val = gold_row.get(gold_col, gold_row.get(eval_col, ""))

            # Skip empty gold values
            if not gold_val.strip():
                continue

            # Optionally skip LLM judge for faster runs
            effective_pipeline = dict(pipeline)
            if skip_llm_judge and pipeline.get("metric", [""])[0] == "llm_judge":
                effective_pipeline = {
                    "preprocess": pipeline.get("preprocess", []),
                    "metric": ["exact_match"],
                }

            result = evaluate_cell(pred_val, gold_val, effective_pipeline)
            result["eval_col"] = eval_col
            result["gold_val"] = gold_val
            result["pred_val"] = pred_val
            cell_results.append(result)

            # Aggregate by column
            if eval_col not in column_scores:
                column_scores[eval_col] = {"correct": 0, "total": 0, "metric": pipeline.get("metric", ["?"])[0]}
            column_scores[eval_col]["total"] += 1
            if result["correct"]:
                column_scores[eval_col]["correct"] += 1

    # Compute per-column accuracy
    for col, scores in column_scores.items():
        scores["accuracy"] = (
            round(scores["correct"] / scores["total"], 4)
            if scores["total"] > 0
            else 0.0
        )

    # Compute overall accuracy
    total_cells = sum(1 for r in cell_results if r.get("metric") != "missing_column")
    correct_cells = sum(1 for r in cell_results if r.get("correct", False))
    overall_accuracy = round(correct_cells / total_cells, 4) if total_cells > 0 else 0.0

    # Errors summary
    incorrect_cells = [r for r in cell_results if not r.get("correct", False)]

    return {
        "instance_id": instance_id,
        "total_gold_rows": len(gold_rows),
        "total_pred_rows": len(pred_rows),
        "matched_rows": len(matched),
        "missing_rows": len(missing),
        "extra_rows": len(extra),
        "overall_accuracy": overall_accuracy,
        "column_scores": column_scores,
        "missing_row_keys": [
            {col: row.get(gold_col_mapping.get(col, col), row.get(col, "")) for col in unique_columns}
            for row in missing[:20]  # Limit to 20 examples
        ],
        "extra_row_keys": [
            {col_mapping.get(col, col): row.get(col_mapping.get(col, col), "") for col in unique_columns}
            for row in extra[:20]
        ],
        "incorrect_cells_sample": incorrect_cells[:30],
        "column_mapping_used": col_mapping,
    }


# ---------------------------------------------------------------------------
# Step 3c: Error report aggregation
# ---------------------------------------------------------------------------

def generate_error_report(
    task_reports: list[dict],
    compressed_trajectories: dict[str, str],
) -> dict[str, Any]:
    """Aggregate error patterns across all tasks.

    Returns a structured error report.
    """
    # Aggregate error patterns
    missing_categories: list[dict] = []
    incomplete_columns: dict[str, int] = {}
    decomposition_issues: list[str] = []
    search_depth_issues: list[str] = []

    for report in task_reports:
        iid = report.get("instance_id", "?")

        # Missing rows → potentially missed subcategories
        if report.get("missing_rows", 0) > 0:
            missing_categories.append({
                "instance_id": iid,
                "missing_count": report["missing_rows"],
                "total_gold": report.get("total_gold_rows", 0),
                "examples": report.get("missing_row_keys", [])[:5],
            })

        # Low-accuracy columns → incomplete data
        for col, scores in report.get("column_scores", {}).items():
            if scores.get("accuracy", 1.0) < 0.8:
                key = f"{iid}.{col}"
                incomplete_columns[key] = round(scores.get("accuracy", 0), 4)

        # Check trajectory for decomposition issues
        traj_summary = compressed_trajectories.get(iid, "")
        if "truncat" in traj_summary.lower() or "timeout" in traj_summary.lower():
            decomposition_issues.append(f"{iid}: truncation/timeout detected in trajectory")
        if report.get("matched_rows", 0) < report.get("total_gold_rows", 0) * 0.5:
            decomposition_issues.append(
                f"{iid}: only {report.get('matched_rows', 0)}/{report.get('total_gold_rows', 0)} rows matched — "
                "orchestrator may have missed subcategories"
            )

    # Overall stats
    total_gold = sum(r.get("total_gold_rows", 0) for r in task_reports)
    total_matched = sum(r.get("matched_rows", 0) for r in task_reports)
    total_missing = sum(r.get("missing_rows", 0) for r in task_reports)
    avg_accuracy = (
        round(sum(r.get("overall_accuracy", 0) for r in task_reports) / len(task_reports), 4)
        if task_reports
        else 0.0
    )

    return {
        "summary": {
            "total_tasks": len(task_reports),
            "total_gold_rows": total_gold,
            "total_matched_rows": total_matched,
            "total_missing_rows": total_missing,
            "row_recall": round(total_matched / total_gold, 4) if total_gold else 0.0,
            "average_cell_accuracy": avg_accuracy,
        },
        "missing_categories": missing_categories,
        "incomplete_columns": incomplete_columns,
        "decomposition_issues": decomposition_issues,
        "search_depth_issues": search_depth_issues,
        "per_task_reports": task_reports,
        "compressed_trajectories": compressed_trajectories,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="WideSearch verify pipeline")
    parser.add_argument("--tasks", nargs="*", default=None, help="Task IDs to verify")
    parser.add_argument("--skip-compress", action="store_true", help="Skip trajectory compression")
    parser.add_argument("--skip-llm-judge", action="store_true", help="Use exact_match fallback instead of LLM judge")
    args = parser.parse_args()

    task_ids = args.tasks or default_task_ids()
    tasks = load_tasks(task_ids)

    if not tasks:
        print(f"No tasks found for IDs: {task_ids}")
        sys.exit(1)

    # Load trajectory mapping from run manifest (instance_id → trajectory files)
    manifest_path = REPORTS_DIR / "run_manifest.json"
    traj_mapping: dict[str, list[str]] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for r in manifest.get("results", []):
            iid_ = r.get("instance_id", "")
            files = r.get("trajectory_files", [])
            if iid_ and files:
                traj_mapping[iid_] = files
        if traj_mapping:
            print(f"  Loaded trajectory mapping for {len(traj_mapping)} task(s) from manifest")

    print(f"\nWideSearch Verify Pipeline")
    print(f"  Tasks: {[t['instance_id'] for t in tasks]}")
    print(f"  Skip compress: {args.skip_compress}")
    print(f"  Skip LLM judge: {args.skip_llm_judge}")

    compressed_trajectories: dict[str, str] = {}
    task_reports: list[dict] = []

    for task in tasks:
        iid = task["instance_id"]
        print(f"\n--- Verifying {iid} ---")

        # Step 3a: Compress trajectory
        if not args.skip_compress:
            # Use manifest mapping if available; otherwise fall back to heuristic
            if iid in traj_mapping:
                traj_paths = [LOGS_DIR / f for f in traj_mapping[iid] if (LOGS_DIR / f).exists()]
                print(f"  Compressing {len(traj_paths)} trajectory file(s) from manifest...")
            else:
                print(f"  [warn] No trajectory mapping for {iid} in manifest, skipping compress")
                traj_paths = []

            if traj_paths:
                compressed = compress_trajectory(iid, traj_paths)
                compressed_trajectories[iid] = compressed
                print(f"  Compressed: {len(compressed)} chars")
            else:
                compressed_trajectories[iid] = "(no trajectories mapped for this task)"
        else:
            compressed_trajectories[iid] = "(compression skipped)"

        # Step 3b: Compare with gold
        print(f"  Comparing with gold answer...")
        start = time.time()
        report = compare_with_gold(iid, task, skip_llm_judge=args.skip_llm_judge)
        elapsed = round(time.time() - start, 2)
        report["verify_elapsed_seconds"] = elapsed
        task_reports.append(report)

        # Print summary
        print(f"  Rows: {report.get('matched_rows', 0)}/{report.get('total_gold_rows', 0)} matched, "
              f"{report.get('missing_rows', 0)} missing, {report.get('extra_rows', 0)} extra")
        print(f"  Overall accuracy: {report.get('overall_accuracy', 0):.2%}")
        for col, scores in report.get("column_scores", {}).items():
            print(f"    {col}: {scores.get('accuracy', 0):.2%} ({scores['correct']}/{scores['total']}) [{scores['metric']}]")
        print(f"  Done ({elapsed}s)")

    # Step 3c: Error report
    print(f"\n--- Generating error report ---")
    error_report = generate_error_report(task_reports, compressed_trajectories)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "verify_report.json"
    report_path.write_text(
        json.dumps(error_report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\n{'=' * 60}")
    print(f"  Verify Report: {report_path}")
    print(f"  Summary:")
    summary = error_report["summary"]
    print(f"    Tasks: {summary['total_tasks']}")
    print(f"    Row recall: {summary['row_recall']:.2%}")
    print(f"    Avg cell accuracy: {summary['average_cell_accuracy']:.2%}")
    print(f"    Missing categories: {len(error_report['missing_categories'])}")
    print(f"    Incomplete columns: {len(error_report['incomplete_columns'])}")
    print(f"    Decomposition issues: {len(error_report['decomposition_issues'])}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
