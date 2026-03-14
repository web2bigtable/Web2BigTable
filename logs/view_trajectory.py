#!/usr/bin/env python3
"""Trajectory viewer for Memento-S agent workers.

Reads per-worker trajectory JSONL files and renders a clear,
human-readable visualization of each agent's execution journey.

Usage:
    python view_trajectory.py                     # show latest trajectory
    python view_trajectory.py worker-0-*.jsonl    # show specific file(s)
    python view_trajectory.py --all               # show all trajectories
    python view_trajectory.py --list              # list available files
"""

import json
import sys
from pathlib import Path

LOGS_DIR = Path(__file__).resolve().parent

# ── ANSI colours ──────────────────────────────────────────────────────────
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"
C_BLUE = "\033[34m"


def _short(text: str, max_len: int = 100) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    return text[:max_len] + "..." if len(text) > max_len else text


def _render_event(e: dict) -> str | None:
    """Render a single trajectory event into a formatted line."""
    event = e.get("event", "?")
    ts = e.get("ts", "")[11:19]  # HH:MM:SS from ISO

    if event == "run_one_skill_loop_start":
        skill = e.get("skill_name", "?")
        task = _short(e.get("user_text", ""), 70)
        return f"  {C_GREEN}START{C_RESET}     {C_DIM}{ts}{C_RESET}  skill={C_CYAN}{skill}{C_RESET}  task={task}"

    if event == "run_one_skill_loop_round_start":
        return f"  {C_DIM}ROUND     {ts}  round={e.get('round')}{C_RESET}"

    if event == "run_one_skill_loop_round_plan":
        plan = e.get("plan", {})
        if not isinstance(plan, dict):
            return f"  {C_YELLOW}PLAN{C_RESET}      {C_DIM}{ts}{C_RESET}  round={e.get('round')}  (non-dict plan)"
        ops = plan.get("ops", [])
        final = plan.get("final", "")
        if isinstance(ops, list) and ops:
            op_types = [str(o.get("type", "?")) for o in ops if isinstance(o, dict)]
            return f"  {C_YELLOW}PLAN{C_RESET}      {C_DIM}{ts}{C_RESET}  round={e.get('round')}  ops={op_types}"
        elif final:
            return f"  {C_YELLOW}PLAN{C_RESET}      {C_DIM}{ts}{C_RESET}  round={e.get('round')}  final={_short(str(final), 80)}"
        else:
            return f"  {C_YELLOW}PLAN{C_RESET}      {C_DIM}{ts}{C_RESET}  round={e.get('round')}  (no ops/final)"

    if event == "ask_for_plan_input":
        return f"  {C_DIM}LLM_REQ   {ts}  skill={e.get('skill_name', '?')}{C_RESET}"

    if event == "ask_for_plan_parsed":
        plan = e.get("plan", {})
        if isinstance(plan, dict):
            keys = list(plan.keys())[:5]
            return f"  {C_DIM}LLM_RESP  {ts}  keys={keys}{C_RESET}"
        return None

    if event == "execute_skill_plan_input":
        plan = e.get("normalized_plan", {})
        ops = plan.get("ops", []) if isinstance(plan, dict) else []
        op_summary = []
        for o in (ops if isinstance(ops, list) else []):
            if isinstance(o, dict):
                op_type = o.get("type", "?")
                # Show key details per op type
                if op_type == "shell":
                    cmd = _short(str(o.get("command", "")), 60)
                    op_summary.append(f"shell({cmd})")
                elif op_type in ("read_file", "write_file", "edit_file", "patch"):
                    path = _short(str(o.get("path", o.get("file", ""))), 40)
                    op_summary.append(f"{op_type}({path})")
                elif op_type in ("read_workboard", "edit_workboard", "append_workboard"):
                    old = _short(str(o.get("old_text", "")), 30)
                    new = _short(str(o.get("new_text", "")), 30)
                    if old or new:
                        op_summary.append(f"{op_type}({old} → {new})")
                    else:
                        op_summary.append(op_type)
                elif op_type == "web_search":
                    q = _short(str(o.get("query", "")), 50)
                    op_summary.append(f"web_search({q})")
                else:
                    op_summary.append(op_type)
        return f"  {C_BLUE}EXEC_IN{C_RESET}   {C_DIM}{ts}{C_RESET}  skill={e.get('skill_name', '?')}  ops={op_summary}"

    if event == "execute_skill_plan_output":
        result = _short(str(e.get("result", "")), 120)
        is_continue = result.startswith("CONTINUE:")
        colour = C_MAGENTA if is_continue else C_GREEN
        label = "EXEC_OUT" if not is_continue else "EXEC_CNT"
        return f"  {colour}{label}{C_RESET}  {C_DIM}{ts}{C_RESET}  skill={e.get('skill_name', '?')}  result={result}"

    if event == "run_one_skill_loop_continue":
        output = _short(str(e.get("output", "")), 100)
        return f"  {C_MAGENTA}CONTINUE{C_RESET}  {C_DIM}{ts}{C_RESET}  round={e.get('round')}  output={output}"

    if event == "run_one_skill_loop_auto_continue":
        feedback = _short(str(e.get("feedback", "")), 80)
        return f"  {C_MAGENTA}AUTO_CNT{C_RESET}  {C_DIM}{ts}{C_RESET}  round={e.get('round')}  {feedback}"

    if event == "run_one_skill_loop_exec_error":
        err = _short(str(e.get("error", "")), 100)
        return f"  {C_RED}EXEC_ERR{C_RESET}  {C_DIM}{ts}{C_RESET}  round={e.get('round')}  {err}"

    if event == "run_one_skill_loop_end":
        mode = e.get("mode", "?")
        result = _short(str(e.get("result", "")), 100)
        return f"  {C_GREEN}END{C_RESET}       {C_DIM}{ts}{C_RESET}  round={e.get('round')}  mode={C_BOLD}{mode}{C_RESET}  result={result}"

    if event == "route_skill_input":
        text = _short(str(e.get("user_text", "")), 70)
        return f"  {C_CYAN}ROUTE_IN{C_RESET}  {C_DIM}{ts}{C_RESET}  task={text}"

    if event == "route_skill_output":
        decision = e.get("decision", {})
        action = decision.get("action", "?") if isinstance(decision, dict) else "?"
        name = decision.get("name", "") if isinstance(decision, dict) else ""
        return f"  {C_CYAN}ROUTE_OUT{C_RESET} {C_DIM}{ts}{C_RESET}  action={action}  skill={C_BOLD}{name}{C_RESET}"

    if event == "llm_request":
        model = e.get("model", "?")
        return f"  {C_DIM}LLM_CALL  {ts}  model={model}{C_RESET}"

    if event == "llm_response":
        tokens = e.get("usage", {})
        if isinstance(tokens, dict):
            inp = tokens.get("prompt_tokens", "?")
            out = tokens.get("completion_tokens", "?")
            return f"  {C_DIM}LLM_DONE  {ts}  tokens_in={inp} tokens_out={out}{C_RESET}"
        return f"  {C_DIM}LLM_DONE  {ts}{C_RESET}"

    if event == "semantic_router_selected":
        selected = e.get("selected_skills", [])
        names = [s.get("name", "?") for s in selected if isinstance(s, dict)][:5]
        return f"  {C_CYAN}SEM_ROUTE{C_RESET} {C_DIM}{ts}{C_RESET}  top_skills={names}"

    # Fallback: show unknown events dimmed
    return f"  {C_DIM}{'?':9s} {ts}  {event}{C_RESET}"


def render_trajectory(filepath: Path) -> None:
    """Read and render a single trajectory file."""
    events = []
    header = None
    with filepath.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") == "header":
                header = record
            else:
                events.append(record)

    # Title bar
    print(f"\n{C_BOLD}{'═' * 80}{C_RESET}")
    if header:
        idx = header.get("worker_index", "?")
        subtask = _short(header.get("subtask", ""), 70)
        elapsed = header.get("time_taken_seconds", "?")
        total = header.get("total_events", len(events))
        print(f"  {C_BOLD}Worker {idx}{C_RESET}  |  {total} events  |  {elapsed}s")
        print(f"  Task: {subtask}")
        result_preview = _short(header.get("result_preview", ""), 120)
        print(f"  Result: {C_DIM}{result_preview}{C_RESET}")
    else:
        print(f"  {C_BOLD}{filepath.name}{C_RESET}  |  {len(events)} events")
    print(f"{C_BOLD}{'─' * 80}{C_RESET}")

    # Events
    for e in events:
        line = _render_event(e)
        if line is not None:
            print(line)

    print(f"{C_BOLD}{'═' * 80}{C_RESET}\n")


def list_trajectory_files() -> list[Path]:
    """Find all worker trajectory JSONL files, sorted by modification time (newest first)."""
    files = sorted(LOGS_DIR.glob("worker-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def main() -> None:
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        return

    if "--list" in args:
        files = list_trajectory_files()
        if not files:
            print(f"No trajectory files found in {LOGS_DIR}")
            return
        print(f"\nTrajectory files in {LOGS_DIR}:\n")
        for f in files:
            # Read header to show summary
            try:
                with f.open("r") as fh:
                    first_line = json.loads(fh.readline())
                if first_line.get("type") == "header":
                    subtask = _short(first_line.get("subtask", ""), 50)
                    elapsed = first_line.get("time_taken_seconds", "?")
                    total = first_line.get("total_events", "?")
                    print(f"  {f.name:40s}  {total:>4} events  {elapsed:>6}s  {subtask}")
                else:
                    print(f"  {f.name}")
            except Exception:
                print(f"  {f.name}")
        print()
        return

    # Determine which files to show
    if "--all" in args:
        files = list_trajectory_files()
    elif args:
        files = []
        for a in args:
            p = Path(a)
            if not p.is_absolute():
                p = LOGS_DIR / a
            if p.exists():
                files.append(p)
            else:
                # Try glob
                matches = list(LOGS_DIR.glob(a))
                files.extend(sorted(matches, key=lambda x: x.stat().st_mtime))
        if not files:
            print(f"No matching files found. Use --list to see available trajectories.")
            return
    else:
        # Show latest
        files = list_trajectory_files()
        if not files:
            print(f"No trajectory files found in {LOGS_DIR}")
            print("Run the MCP server with a task to generate trajectory data.")
            return
        # Show latest session (files created within 2 seconds of newest)
        newest_mtime = files[0].stat().st_mtime
        files = [f for f in files if abs(f.stat().st_mtime - newest_mtime) < 2]

    for f in files:
        render_trajectory(f)


if __name__ == "__main__":
    main()
