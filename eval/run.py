"""Batch runner for WideSearch eval tasks.

Usage:
    python eval/run.py                       # Run all 20 tasks (ws_en_001~020)
    python eval/run.py --tasks ws_en_001     # Run a single task
    python eval/run.py --tasks ws_en_001 ws_en_003  # Run specific tasks
    python eval/run.py --parallel            # Run all tasks concurrently
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "Memento-S"))

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv(PROJECT_ROOT / ".env")

from eval.utils import (
    LOGS_DIR,
    OUTPUTS_DIR,
    REPORTS_DIR,
    default_task_ids,
    load_tasks,
)
from orchestrator.orchestrator_agent import OrchestratorAgent


def build_orchestrator() -> OrchestratorAgent:
    """Create an OrchestratorAgent with the project's default config."""
    model = ChatOpenAI(
        model=os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5"),
        openai_api_key=os.getenv("OPENROUTER_API_KEY"),
        openai_api_base=os.getenv("OPENROUTER_BASE_URL"),
        temperature=0,
    )
    return OrchestratorAgent(model=model)


def _snapshot_logs() -> set[str]:
    """Return the set of trajectory filenames currently in LOGS_DIR."""
    if not LOGS_DIR.exists():
        return set()
    return {p.name for p in LOGS_DIR.glob("worker-*.jsonl")}


async def run_single_task(
    task: dict,
    orchestrator: OrchestratorAgent,
) -> dict:
    """Run a single WideSearch task through the orchestrator.

    Returns a result dict with instance_id, output, elapsed_seconds, timestamp,
    and trajectory_files (list of new log filenames created during this run).
    """
    instance_id = task["instance_id"]
    query = task["query"]

    print(f"\n{'=' * 60}")
    print(f"  Running: {instance_id}")
    print(f"  Query: {query[:120]}...")
    print(f"{'=' * 60}")

    # Snapshot logs/ before running so we can diff afterwards
    logs_before = _snapshot_logs()

    start = time.perf_counter()
    try:
        result = await orchestrator.run(query)
        output = result["output"]
    except Exception as exc:
        output = f"ERROR: {type(exc).__name__}: {exc}"
        print(f"  [!] Task {instance_id} failed: {exc}")

    elapsed = round(time.perf_counter() - start, 2)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Diff logs/ to find trajectories created by this task
    logs_after = _snapshot_logs()
    new_logs = sorted(logs_after - logs_before)

    # Save output
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUTS_DIR / f"{instance_id}.md"
    output_path.write_text(output, encoding="utf-8")

    print(f"  Done: {instance_id} ({elapsed}s) → {output_path}")
    if new_logs:
        print(f"  Trajectories: {new_logs}")

    return {
        "instance_id": instance_id,
        "output_path": str(output_path),
        "elapsed_seconds": elapsed,
        "timestamp": timestamp,
        "output_preview": output[:500],
        "trajectory_files": new_logs,
    }


async def run_sequential(tasks: list[dict]) -> list[dict]:
    """Run tasks one by one, reusing a single orchestrator."""
    orchestrator = build_orchestrator()
    results = []
    for task in tasks:
        await orchestrator.start()
        try:
            result = await run_single_task(task, orchestrator)
            results.append(result)
        finally:
            await orchestrator.close()
    return results


async def run_parallel(tasks: list[dict]) -> list[dict]:
    """Run all tasks concurrently, each with its own orchestrator."""

    async def _run_one(task: dict) -> dict:
        orch = build_orchestrator()
        await orch.start()
        try:
            return await run_single_task(task, orch)
        finally:
            await orch.close()

    results = await asyncio.gather(
        *[_run_one(t) for t in tasks],
        return_exceptions=True,
    )

    processed = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            processed.append({
                "instance_id": tasks[i]["instance_id"],
                "error": str(r),
                "elapsed_seconds": 0,
            })
        else:
            processed.append(r)
    return processed


async def main():
    parser = argparse.ArgumentParser(description="WideSearch eval batch runner")
    parser.add_argument(
        "--tasks",
        nargs="*",
        default=None,
        help="Task IDs to run (e.g., ws_en_001 ws_en_003 or ws_en_007-ws_en_020). Default: all 20.",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run tasks in parallel (default: sequential).",
    )
    args = parser.parse_args()

    # Expand range syntax: ws_en_007-ws_en_020 → ws_en_007 ws_en_008 ... ws_en_020
    raw_ids = args.tasks or default_task_ids()
    task_ids = []
    for tid in raw_ids:
        m = __import__("re").match(r"ws_en_(\d+)-ws_en_(\d+)$", tid)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            task_ids.extend(f"ws_en_{i:03d}" for i in range(start, end + 1))
        else:
            task_ids.append(tid)
    tasks = load_tasks(task_ids)

    if not tasks:
        print(f"No tasks found for IDs: {task_ids}")
        sys.exit(1)

    print(f"\nWideSearch Eval Runner")
    print(f"  Tasks: {[t['instance_id'] for t in tasks]}")
    print(f"  Mode: {'parallel' if args.parallel else 'sequential'}")

    start = time.perf_counter()

    if args.parallel:
        results = await run_parallel(tasks)
    else:
        results = await run_sequential(tasks)

    total_elapsed = round(time.perf_counter() - start, 2)

    # Save run manifest
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_elapsed_seconds": total_elapsed,
        "task_count": len(tasks),
        "results": results,
    }
    manifest_path = REPORTS_DIR / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"  All done! {len(results)} tasks in {total_elapsed}s")
    print(f"  Outputs: {OUTPUTS_DIR}")
    print(f"  Manifest: {manifest_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
