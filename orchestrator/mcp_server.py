"""Orchestrator MCP Server — wraps Memento-S worker pool with workboard support."""

import json
import fcntl
import os
import re
import asyncio
import sys
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _env_truthy(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


QUIET_STDERR = _env_truthy("MCP_QUIET_STDERR")
if QUIET_STDERR:
    # Suppress third-party startup banners/logs that can corrupt TUI rendering.
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# ── Protect stdout for MCP JSON-RPC protocol ──────────────────────────
# The MCP SDK uses sys.stdout.buffer (fd 1) for JSON-RPC communication.
# Any stray writes to sys.stdout (from logging, print(), or third-party
# libraries) corrupt the protocol stream and cause deadlocks because
# they share the same BufferedWriter lock with the MCP SDK's TextIOWrapper.
# Solution: replace sys.stdout with a proxy that sends writes to stderr
# but keeps .buffer pointing to the real stdout buffer for MCP SDK.
_real_stdout_buffer = sys.stdout.buffer


class _StderrProxyStdout:
    """Redirects all text writes to stderr, keeps .buffer for MCP SDK."""

    def __init__(self, real_buffer, fallback):
        self.buffer = real_buffer
        self._fallback = fallback

    def write(self, s):
        return self._fallback.write(s)

    def flush(self):
        self._fallback.flush()

    def fileno(self):
        return self._fallback.fileno()

    @property
    def encoding(self):
        return self._fallback.encoding

    def isatty(self):
        return self._fallback.isatty()

    def readable(self):
        return False

    def writable(self):
        return True


sys.stdout = _StderrProxyStdout(_real_stdout_buffer, sys.stderr)

# Bridge OPENROUTER env vars to new Memento-S LLM_* vars
if os.getenv("OPENROUTER_API_KEY") and not os.getenv("LLM_API"):
    os.environ["LLM_API"] = "openrouter"
    os.environ["LLM_MODEL"] = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")

# Set up imports from Memento-S directory
_MEMENTO_S_DIR = str(Path(__file__).resolve().parent.parent / "Memento-S")
sys.path.insert(0, _MEMENTO_S_DIR)
os.chdir(_MEMENTO_S_DIR)

from fastmcp import FastMCP

from core.agent.memento_s_agent import MementoSAgent
from core.agent.session_manager import generate_session_id
from core.tools.builtins import configure_workboard

import logging

logger = logging.getLogger(__name__)

MAX_POOL_SIZE = max(1, min(int(os.getenv("MAX_WORKERS", "10")), 100))

# ---------------------------------------------------------------------------
# Shared AppContext — pre-load heavy resources once for all workers
# ---------------------------------------------------------------------------
# MementoSAgent.__init__ calls create_app_context() which loads:
#   - SkillLibrary (disk I/O + BM25 index + jieba tokenization)
#   - EmbeddingStore (BAAI/bge-m3 ~568MB sentence-transformers model + ChromaDB)
#   - CloudCatalog (file I/O + async embedding)
#   - CrossEncoderReranker (another sentence-transformers model)
#
# Without sharing, N workers = N redundant copies of these multi-hundred-MB
# resources.  We pre-initialize once at module load and inject into each worker.
_shared_app_context = None
_shared_app_context_lock = threading.Lock()


def _get_shared_app_context():
    """Lazily initialize and return the shared AppContext singleton."""
    global _shared_app_context
    if _shared_app_context is not None:
        return _shared_app_context
    with _shared_app_context_lock:
        if _shared_app_context is not None:
            return _shared_app_context
        _stderr_print("  [WorkerPool] Pre-loading shared AppContext (embeddings, BM25, skills)...")
        _log_to_file("Pre-loading shared AppContext")
        start = time.perf_counter()
        try:
            from core.skills.provider.delta_skills.bootstrap import create_app_context
            _shared_app_context = create_app_context(init_logging=False)
            elapsed = round(time.perf_counter() - start, 2)
            _stderr_print(f"  [WorkerPool] Shared AppContext ready in {elapsed}s")
            _log_to_file(f"Shared AppContext ready in {elapsed}s")
        except Exception as exc:
            _stderr_print(f"  [WorkerPool] WARN: Failed to pre-load AppContext: {exc}")
            _log_to_file(f"Failed to pre-load AppContext: {exc}")
        return _shared_app_context


def _create_worker_agent(workspace: Path) -> MementoSAgent:
    """Create a MementoSAgent that reuses the shared AppContext.

    If the shared context is available, we inject its components
    into the agent to avoid redundant heavy initialization.
    """
    ctx = _get_shared_app_context()
    if ctx is None:
        # Fallback: let the agent do its own init
        return MementoSAgent(workspace=workspace)

    from core.llm import LLM
    from core.skills.skill_manager import SkillManager
    from core.skills.provider.delta_skill_provider import DeltaSkillsProvider
    from core.tools.builtins import configure as configure_builtin_tools

    llm = LLM()
    skill_manager = SkillManager(
        provider=DeltaSkillsProvider(app_context=ctx),
    )
    agent = MementoSAgent(
        workspace=workspace,
        llm=llm,
        skill_manager=skill_manager,
    )
    # Point builtin tools at the shared library/catalog so route_skill etc. work
    configure_builtin_tools(
        workspace,
        skill_library=ctx.library,
        cloud_catalog=ctx.cloud_catalog,
        skill_manager=skill_manager,
    )
    return agent


WORKSPACE_DIR = (Path(_MEMENTO_S_DIR) / "workspace").resolve()
WORKBOARD_PATH = WORKSPACE_DIR / ".workboard.md"
ORCHESTRATOR_SKILLS_DIR = (Path(__file__).resolve().parent.parent / "orchestrator_skills").resolve()


_ORCHESTRATOR_LOG = (Path(__file__).resolve().parent.parent / "logs" / "orchestrator.log").resolve()


def _log_to_file(msg: str) -> None:
    """Append a timestamped message to logs/orchestrator.log."""
    try:
        _ORCHESTRATOR_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(_ORCHESTRATOR_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def _stderr_print(*args: Any, **kwargs: Any) -> None:
    """Print to stderr unless MCP quiet mode is enabled."""
    if QUIET_STDERR:
        return
    kwargs.setdefault("file", sys.stderr)
    print(*args, **kwargs)

mcp = FastMCP("MementoSWorkerPool")

_semaphore = asyncio.Semaphore(MAX_POOL_SIZE)

# ---------------------------------------------------------------------------
# Workboard helpers — file-lock protected against concurrent worker access
# ---------------------------------------------------------------------------
_WORKBOARD_LOCK_PATH = WORKSPACE_DIR / ".workboard.lock"


class _WorkboardFileLock:
    """Context manager that acquires an exclusive flock on the workboard lock file.

    This prevents concurrent workers (running in the same process via asyncio)
    and any out-of-process writers from corrupting the workboard during
    read-modify-write cycles.
    """

    def __enter__(self):
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        self._fd = open(_WORKBOARD_LOCK_PATH, "w")
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self._fd, fcntl.LOCK_UN)
        self._fd.close()
        return False


def _workboard_write(content: str) -> Path:
    with _WorkboardFileLock():
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        WORKBOARD_PATH.write_text(content, encoding="utf-8")
    return WORKBOARD_PATH


def _workboard_read() -> str:
    with _WorkboardFileLock():
        if not WORKBOARD_PATH.exists():
            return "(no workboard exists)"
        return WORKBOARD_PATH.read_text(encoding="utf-8")


def _workboard_check_off_item(index_1_based: int) -> str:
    with _WorkboardFileLock():
        if not WORKBOARD_PATH.exists():
            return "check_off_item ERR: workboard does not exist"
        content = WORKBOARD_PATH.read_text(encoding="utf-8")
        pattern = re.compile(rf"^(\s*-\s)\[ \](\s+{index_1_based}\b)", re.MULTILINE)
        new_content, n = pattern.subn(r"\1[x]\2", content, count=1)
        if n == 0:
            return f"check_off_item SKIP: item {index_1_based} not found or already checked"
        WORKBOARD_PATH.write_text(new_content, encoding="utf-8")
    return f"check_off_item OK: item {index_1_based}"


def _workboard_append_result(index_1_based: int, text: str) -> str:
    with _WorkboardFileLock():
        if not WORKBOARD_PATH.exists():
            return "append_result ERR: workboard does not exist"
        content = WORKBOARD_PATH.read_text(encoding="utf-8")
        one_line = " ".join(str(text).split())[:200]
        result_line = f"- Task {index_1_based}: {one_line}"
        marker = "## Results"
        marker_idx = content.find(marker)
        if marker_idx == -1:
            content = content.rstrip() + f"\n\n{marker}\n{result_line}\n"
        else:
            marker_line_end = content.find("\n", marker_idx)
            if marker_line_end == -1:
                content += f"\n{result_line}\n"
            else:
                insert_pos = len(content)
                next_section = content.find("\n##", marker_line_end + 1)
                if next_section != -1:
                    insert_pos = next_section + 1
                content = content[:insert_pos].rstrip() + f"\n{result_line}\n" + content[insert_pos:]
        WORKBOARD_PATH.write_text(content, encoding="utf-8")
    return f"append_result OK: task {index_1_based}"


def _workboard_uses_tag_protocol() -> bool:
    with _WorkboardFileLock():
        if not WORKBOARD_PATH.exists():
            return False
        try:
            text = WORKBOARD_PATH.read_text(encoding="utf-8")
        except Exception:
            return False
        return bool(re.search(r"<t\d+_[A-Za-z0-9_:-]*>.*?</t\d+_[A-Za-z0-9_:-]*>", text, re.DOTALL))


def _resolve_orchestrator_skill_dir(skill_name: str | None) -> Path | None:
    if not isinstance(skill_name, str) or not skill_name.strip():
        return None
    candidate = (ORCHESTRATOR_SKILLS_DIR / skill_name.strip()).resolve()
    try:
        candidate.relative_to(ORCHESTRATOR_SKILLS_DIR)
    except Exception:
        return None
    if candidate.exists() and candidate.is_dir():
        return candidate
    return None


@mcp.tool
def read_orchestrator_skill(skill_name: str) -> str:
    """Read an orchestrator skill's SKILL.md content from orchestrator_skills/."""
    _stderr_print(f"  [Orchestrator] read_orchestrator_skill({skill_name!r})")
    _log_to_file(f"read_orchestrator_skill({skill_name!r})")
    skill_dir = _resolve_orchestrator_skill_dir(skill_name)
    if skill_dir is None:
        return f"read_orchestrator_skill ERR: skill not found: {skill_name!r}"
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return f"read_orchestrator_skill ERR: missing SKILL.md for: {skill_name!r}"
    try:
        content = skill_md.read_text(encoding="utf-8")
        _stderr_print(f"  [Orchestrator] read_orchestrator_skill({skill_name!r}) → {len(content)} chars")
        _log_to_file(f"read_orchestrator_skill({skill_name!r}) → {len(content)} chars")
        return content
    except Exception as exc:
        return f"read_orchestrator_skill ERR: {exc}"


@mcp.tool
def list_orchestrator_skills() -> str:
    """List locally available orchestrator skills from orchestrator_skills/."""
    _stderr_print("  [Orchestrator] list_orchestrator_skills() called")
    _log_to_file("list_orchestrator_skills() called")
    if not ORCHESTRATOR_SKILLS_DIR.exists():
        return "(no orchestrator skills found)"
    lines: list[str] = []
    try:
        for skill_dir in sorted(ORCHESTRATOR_SKILLS_DIR.iterdir(), key=lambda p: p.name.lower()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            desc = ""
            try:
                for raw_line in skill_md.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith(("#", "```", "---", "-", "*", "<")):
                        continue
                    desc = line[:200]
                    break
            except Exception:
                pass
            lines.append(f"- {skill_dir.name}: {desc}" if desc else f"- {skill_dir.name}")
    except Exception as exc:
        return f"list_orchestrator_skills ERR: {exc}"
    return "\n".join(lines) if lines else "(no orchestrator skills found)"


def _extract_tool_call_events(
    session_manager: Any,
    session_id: str,
    worker_index: int,
    subtask_id: str,
) -> list[dict[str, Any]]:
    """Extract tool_call_end events from session messages for trajectory/webpages."""
    events: list[dict[str, Any]] = []
    try:
        session = session_manager.get_session(session_id)
        if session is None:
            return events
        messages = session.get("messages", [])
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                continue
            for tc in tool_calls:
                func = tc.get("function", {})
                tc_id = tc.get("id", "")
                tool_name = func.get("name", "")
                args_str = func.get("arguments", "")
                if isinstance(args_str, dict):
                    args_str = json.dumps(args_str, ensure_ascii=False)
                # Find the matching tool result message
                result_preview = ""
                for rmsg in messages:
                    if rmsg.get("role") == "tool" and rmsg.get("tool_call_id") == tc_id:
                        result_preview = str(rmsg.get("content", ""))[:500]
                        break
                events.append(_trajectory_event(
                    "tool_call_end",
                    worker_index=worker_index,
                    subtask_id=subtask_id,
                    tool_name=tool_name,
                    args_preview=args_str[:500],
                    result_preview=result_preview,
                ))
    except Exception:
        pass
    return events


EXECUTE_SUBTASKS_DESCRIPTION = f"""
Execute 1-{MAX_POOL_SIZE} independent subtasks in parallel using Memento-S agent workers.

CRITICAL: Maximum {MAX_POOL_SIZE} subtasks per call. Split larger batches into multiple calls.

CAPABILITIES:
- Each worker is a Memento-S agent powered by Agent Skills — capable of handling most tasks
- Workers automatically select the best skill for each subtask via semantic routing
- Workers can dynamically acquire new skills on demand for specialized tasks
- Each worker handles complex tasks iteratively through multi-round execution
- Workers are STATELESS and ISOLATED — cannot see other workers' results

SUBTASK DESIGN RULES:
1. SELF-CONTAINED: Each subtask must be fully independent with complete context
   - GOOD: "Read /path/to/config.py and extract the database URL"
   - BAD: "Read the config file mentioned earlier"
2. ATOMIC: One focused task per subtask

Args:
  subtasks: List[str]
    List of 1 to {MAX_POOL_SIZE} fully self-contained task descriptions.
  workboard: str (RECOMMENDED — always provide)
    Markdown content for a shared workboard file that lists the subtasks
    and provides tagged worker slots (e.g. <t1_result></t1_result>).
    Workers can use read_workboard/edit_workboard to fill their own tags.
    Include subtask IDs (t1, t2, ...) in the board and subtask descriptions.
"""


def _trajectory_event(event: str, **fields: Any) -> dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": str(event),
        **fields,
    }


# ---------------------------------------------------------------------------
# Trajectory persistence & formatting
# ---------------------------------------------------------------------------
TRAJECTORY_LOG_DIR = Path(os.getenv(
    "TRAJECTORY_LOG_DIR",
    str(Path(__file__).resolve().parent.parent / "logs"),
))
_TRAJECTORY_FILE_LOCK = threading.Lock()


def _append_live_trajectory_event(path: Path, event: dict) -> None:
    """Append one JSON event to a live worker trajectory file."""
    try:
        line = json.dumps(event, ensure_ascii=False)
        with _TRAJECTORY_FILE_LOCK:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass


def _create_live_trajectory(idx: int, subtask: str) -> Path | None:
    """Create a per-worker trajectory file immediately with status=live."""
    try:
        TRAJECTORY_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"worker-{idx}-{ts}.jsonl"
        path = TRAJECTORY_LOG_DIR / filename
        with path.open("w", encoding="utf-8") as f:
            header = {
                "type": "header",
                "worker_index": idx,
                "subtask": subtask,
                "status": "live",
                "result_preview": "",
                "time_taken_seconds": 0.0,
                "total_events": 0,
                "ts": ts,
            }
            f.write(json.dumps(header, ensure_ascii=False) + "\n")
        return path
    except Exception as exc:
        _stderr_print(f"[warn] failed to create live trajectory for worker {idx}: {exc}")
        return None


def _save_trajectory(
    idx: int,
    subtask: str,
    trajectory: list[dict],
    result: str,
    elapsed: float,
    *,
    status: str = "finished",
    path: Path | None = None,
) -> Path | None:
    """Write final trajectory state to JSONL file (finished/failed)."""
    try:
        TRAJECTORY_LOG_DIR.mkdir(parents=True, exist_ok=True)
        if path is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            filename = f"worker-{idx}-{ts}.jsonl"
            path = TRAJECTORY_LOG_DIR / filename
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        with path.open("w", encoding="utf-8") as f:
            header = {
                "type": "header",
                "worker_index": idx,
                "subtask": subtask,
                "status": status,
                "result_preview": result[:500],
                "time_taken_seconds": elapsed,
                "total_events": len(trajectory),
                "ts": ts,
            }
            f.write(json.dumps(header, ensure_ascii=False) + "\n")
            for event in trajectory:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return path
    except Exception as exc:
        _stderr_print(f"[warn] failed to save trajectory for worker {idx}: {exc}")
        return None


def _short(text: str, max_len: int = 80) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _print_trajectory(idx: int, events: list[dict]) -> None:
    """Print a concise per-worker trajectory to stderr."""
    _stderr_print(f"\n{'─' * 60}")
    _stderr_print(f"  Worker {idx + 1} Trajectory")
    _stderr_print(f"{'─' * 60}")
    for e in events:
        event = e.get("event", "?")
        ts = e.get("ts", "")
        if event == "worker_start":
            _stderr_print(f"  [{ts}] START  subtask={_short(e.get('subtask', ''))}")
        elif event == "worker_attempt_start":
            _stderr_print(f"  [{ts}] TRY    attempt={e.get('attempt')}  subtask_id={e.get('subtask_id')}")
        elif event == "worker_prompt_built":
            _stderr_print(f"  [{ts}] PROMPT subtask_id={e.get('subtask_id')}")
        elif event == "worker_agent_invoke_start":
            _stderr_print(f"  [{ts}] AGENT  invoke_start subtask_id={e.get('subtask_id')}")
        elif event == "tool_call_end":
            _stderr_print(f"  [{ts}] TOOL   {e.get('tool_name')} result={_short(str(e.get('result_preview', '')), 80)}")
        elif event == "worker_agent_invoke_end":
            _stderr_print(f"  [{ts}] AGENT  invoke_end result={_short(str(e.get('result_preview', '')), 80)}")
        elif event == "worker_end":
            _stderr_print(f"  [{ts}] END    status={e.get('status')} sec={e.get('duration_seconds')}")
        elif event == "workboard_snapshot_read":
            _stderr_print(f"  [{ts}] BOARD  snapshot bytes={e.get('bytes')}")
        elif event == "workboard_checkbox_update":
            _stderr_print(f"  [{ts}] BOARD  checkbox item={e.get('item')} checked")
        elif event == "workboard_result_append":
            _stderr_print(f"  [{ts}] BOARD  result_append item={e.get('item')}")
    _stderr_print(f"{'─' * 60}\n")


@mcp.tool(description=EXECUTE_SUBTASKS_DESCRIPTION)
async def execute_subtasks(subtasks: List[str], workboard: str = "") -> dict:
    """Execute subtasks in parallel on Memento-S agent workers."""
    try:
        _stderr_print(f"\n{'=' * 80}")
        _stderr_print(
            f"[MementoSWorkerPool] execute_subtasks called with {len(subtasks)} subtask(s)"
        )
        _stderr_print(f"{'=' * 80}")
        for i, st in enumerate(subtasks):
            _stderr_print(f"  Subtask {i + 1}: {st}")
        _stderr_print("")

        # Reset fetch guard state so workers start fresh (prevents cross-run rate-limit carryover)
        guard_state_file = WORKSPACE_DIR / "skills" / "web-search" / ".agent" / "web_fetch_guard_state.json"
        if guard_state_file.exists():
            guard_state_file.unlink()
            _stderr_print("  [FetchGuard] Cleared web_fetch_guard_state.json for fresh run")

        # Raise per-host fetch limits so parallel workers don't exhaust quotas
        os.environ.setdefault("WEB_FETCH_MAX_PER_HOST", "50")
        os.environ.setdefault("WEB_FETCH_MAX_REPEAT_PER_URL", "10")

        if not subtasks or len(subtasks) < 1:
            raise ValueError("Must provide at least 1 subtask")
        if len(subtasks) > MAX_POOL_SIZE:
            raise ValueError(
                f"Too many subtasks ({len(subtasks)}) — max is {MAX_POOL_SIZE}"
            )

        # Write workboard if provided (workers receive a snapshot in their prompt)
        if workboard and workboard.strip():
            board_path = _workboard_write(workboard)
            _stderr_print(f"  [Workboard] Created at {board_path}")

        async def run_one(subtask: str, idx: int) -> Dict[str, Any]:
            max_retries = 3
            start_time = time.perf_counter()
            live_traj_path = _create_live_trajectory(idx, subtask)
            trajectory: list[dict[str, Any]] = []

            def record(event: str, **fields: Any) -> None:
                e = _trajectory_event(event, worker_index=idx, **fields)
                trajectory.append(e)
                if live_traj_path is not None:
                    _append_live_trajectory_event(live_traj_path, e)

            record("worker_start", subtask=subtask)

            for attempt in range(max_retries):
                try:
                    async with _semaphore:
                        subtask_id = f"t{idx + 1}"
                        worker_input = f"[Subtask ID: {subtask_id}]\n{subtask}"
                        record("worker_attempt_start", attempt=attempt + 1, subtask_id=subtask_id)

                        # Build execution prompt with workboard context
                        execution_text = worker_input
                        board_content = _workboard_read()
                        if board_content and board_content != "(no workboard exists)":
                            record("workboard_snapshot_read", bytes=len(board_content.encode("utf-8")))
                            tag_prefix = f"{subtask_id}_"
                            execution_text = (
                                f"{worker_input}\n\n"
                                "## Workboard — MANDATORY OUTPUT\n"
                                "You MUST write your results to the workboard using `edit_workboard`. "
                                "Your text reply alone is NOT delivered to the user — only workboard content is used.\n"
                                f"Your subtask ID is `{subtask_id}`. Write results to `{tag_prefix}result` tag.\n"
                                "Read the board first, then write your findings into your result tag.\n"
                                f"**IMPORTANT**: When calling `edit_workboard(\"{tag_prefix}result\", content)`, "
                                "the `content` must be ONLY your data rows (e.g. a markdown table). "
                                "Do NOT include the full workboard template, other workers' tags, or section headers.\n\n"
                                "## Skill Discovery — IMPORTANT\n"
                                "Use `route_skill(\"your sub-task description\")` to find the best skill for this task.\n"
                                "Then use `read_skill(\"skill-name\")` to learn how to use it.\n"
                                "Do NOT guess skill names or import paths — always route first.\n\n"
                                "## Execution Strategy (follow this order)\n"
                                "Step 1 — PLAN: List every sub-category mentioned in your subtask as a checklist.\n"
                                "Step 2 — SEARCH EACH ONE: For each sub-category, do a separate search query. "
                                "Do NOT rely on a single summary page — it will miss variants.\n"
                                "Step 3 — CROSS-CHECK: Use at least 2 different sources to verify completeness.\n"
                                "Step 4 — COMPILE: Merge all findings into the required format and write to workboard.\n\n"
                                "## CRITICAL RULES\n"
                                "- You MUST write results to workboard using `edit_workboard` — your text reply is NOT delivered.\n"
                                "- You have a MAXIMUM of 30 tool calls. Write to workboard BEFORE you run out.\n"
                                "- NEVER repeat the same search/fetch more than twice. If it fails, skip that item and move on.\n"
                                "- Incomplete results written to workboard are BETTER than perfect results that never get written.\n\n"
                                f"```markdown\n{board_content}\n```"
                            )
                        record("worker_prompt_built", subtask_id=subtask_id, prompt_preview=execution_text[:500])

                        # Create a worker agent reusing the shared AppContext
                        agent = _create_worker_agent(WORKSPACE_DIR)
                        configure_workboard(WORKBOARD_PATH)
                        session_id = generate_session_id()

                        record("worker_agent_invoke_start", subtask_id=subtask_id)
                        result = await agent.reply(session_id, execution_text)
                        result = result.strip()
                        record("worker_agent_invoke_end", subtask_id=subtask_id, result_preview=result[:500])

                        # Extract tool_call events from session for trajectory/webpages
                        tc_events = _extract_tool_call_events(
                            agent.session_manager, session_id, idx, subtask_id,
                        )
                        for ev in tc_events:
                            trajectory.append(ev)
                            if live_traj_path is not None:
                                _append_live_trajectory_event(live_traj_path, ev)

                    elapsed = round(time.perf_counter() - start_time, 2)
                    logger.info(
                        f"[MementoSWorkerPool] Subtask [{idx}] completed in {elapsed}s"
                    )
                    if workboard and workboard.strip():
                        _workboard_check_off_item(idx + 1)
                        record("workboard_checkbox_update", subtask_id=subtask_id, item=idx + 1, status="checked")
                        if not _workboard_uses_tag_protocol():
                            summary = result.strip().split("\n")[0][:200] if result.strip() else "completed"
                            _workboard_append_result(idx + 1, summary)
                            record("workboard_result_append", subtask_id=subtask_id, item=idx + 1, summary=summary)
                    record("worker_end", subtask_id=subtask_id, duration_seconds=elapsed, status="ok")
                    _print_trajectory(idx, trajectory)
                    traj_path = _save_trajectory(
                        idx,
                        subtask,
                        trajectory,
                        result,
                        elapsed,
                        status="finished",
                        path=live_traj_path,
                    )
                    if traj_path:
                        _stderr_print(f"  [Worker {idx + 1}] Trajectory saved → {traj_path}")
                    return {
                        "subtask_index": idx,
                        "subtask": subtask[:200],
                        "result": result[:500] if result else "",
                        "time_taken_seconds": elapsed,
                    }
                except Exception as e:
                    elapsed = round(time.perf_counter() - start_time, 2)
                    record("worker_attempt_error", attempt=attempt + 1, error=f"{type(e).__name__}: {e}")
                    if attempt < max_retries - 1:
                        logger.info(
                            f"[MementoSWorkerPool] Subtask [{idx}] attempt {attempt + 1}/{max_retries} "
                            f"failed after {elapsed}s: {type(e).__name__}: {str(e)[:200]}"
                        )
                        await asyncio.sleep(1)
                    else:
                        error_msg = f"{type(e).__name__}: {e}"
                        logger.error(
                            f"[MementoSWorkerPool] Subtask [{idx}] failed after {max_retries} attempts ({elapsed}s): {error_msg}"
                        )
                        record("worker_end", duration_seconds=elapsed, status="failed", error=error_msg)
                        _save_trajectory(
                            idx,
                            subtask,
                            [],
                            error_msg,
                            elapsed,
                            status="failed",
                            path=live_traj_path,
                        )
                        raise RuntimeError(error_msg) from e

        tasks = [run_one(st, i) for i, st in enumerate(subtasks)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful = []
        failed = []
        for result in results:
            if isinstance(result, Exception):
                failed.append({"error": str(result)})
            else:
                successful.append(result)

        # Summary
        _log_to_file(f"execute_subtasks: asyncio.gather done — {len(successful)} ok, {len(failed)} failed")
        _stderr_print(f"\n{'=' * 80}")
        _stderr_print(f"[MementoSWorkerPool] All subtasks completed")
        _stderr_print(f"  Successful: {len(successful)}/{len(subtasks)}")
        _stderr_print(f"  Failed: {len(failed)}/{len(subtasks)}")
        _stderr_print(f"{'=' * 80}\n")

        for r in successful:
            idx = r.get("subtask_index", "?")
            t = r.get("time_taken_seconds", 0)
            preview = r.get("result", "")[:200]
            _stderr_print(f"  Result {idx + 1} ({t}s): {preview}")

        # Read final workboard so orchestrator can synthesize from it
        final_board = _workboard_read()

        result_payload = {
            "results": successful,
            "failed": failed,
            "subtasks_count": len(subtasks),
            "workboard": final_board,
        }

        import json as _json
        payload_str = _json.dumps(result_payload, ensure_ascii=False)
        payload_size = len(payload_str)
        _log_to_file(
            f"execute_subtasks: payload built — {payload_size} bytes, "
            f"{len(successful)} successful, {len(failed)} failed"
        )
        _log_to_file(f"execute_subtasks: about to return")
        return result_payload

    except Exception as e:
        _log_to_file(f"execute_subtasks: EXCEPTION — {type(e).__name__}: {e}")
        logger.error(
            f"[MementoSWorkerPool] Error: {type(e).__name__}: {e}", exc_info=True
        )
        return {
            "results": [],
            "failed": [{"error": f"{type(e).__name__}: {e}"}],
            "subtasks_count": len(subtasks) if subtasks else 0,
        }




if __name__ == "__main__":
    mcp.run()
