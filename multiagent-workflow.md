# Multi-Agent Workflow: Orchestrator + Memento-S Workers via MCP

## Architecture

```
User Query
    |
main.py (cleanup workboard, create model)
    |
Orchestrator Agent (LangChain create_agent)
    |  LLM decomposes task into subtasks
    |  Optionally creates a shared workboard (markdown)
    |
    +-- calls MCP tool: execute_subtasks(["subtask1", ...], workboard="...")
                |
        orchestrator/mcp_server.py (wraps Memento-S with workboard support)
            |-- writes workboard to workspace/.workboard.md (if provided)
            |-- does NOT inject workboard instructions into subtasks
            |
            +-- Worker 0: route_skill() -> run_one_skill_loop()
            +-- Worker 1: route_skill() -> run_one_skill_loop()
            +-- Worker N: route_skill() -> run_one_skill_loop()
            |       |
            |       +-- workers discover workboard on their own via
            |           read_workboard / edit_workboard ops (available in
            |           system prompt from planning.py)
            |
            +-- Returns aggregated results to orchestrator

Memento-S/mcp_server.py = standalone version (no workboard param)
orchestrator/mcp_server.py = orchestrator version (adds workboard param)
```

## Memento-S Agent Internals

Memento-S is a modular, skill-based agent. Workers do **not** use OpenAI function calling or MCP tool calls. Instead, they use an **ops-based architecture**:

1. The LLM receives a system prompt listing available op types (`planning.py`)
2. The LLM returns JSON: `{"ops": [{"type": "read_file", "path": "..."}]}`
3. The bridge executor (`skill_executor.py`) routes each op by type to the right handler
4. Results are fed back to the LLM for multi-round execution

```
Memento-S/
+-- agent.py                    # Slim re-export facade + CLI REPL
+-- mcp_server.py               # MCP server with execute_subtasks + workboard
+-- core/
|   +-- config.py               # All env vars, constants, op-type sets
|   +-- llm.py                  # LLM client (OpenRouter / Anthropic)
|   +-- router.py               # route_skill() -- semantic + LLM routing
|   +-- workboard.py            # Shared workboard (thread-safe read/write/edit)
|   +-- utils/
|   |   +-- json_utils.py       # JSON parsing & repair
|   |   +-- path_utils.py       # Path resolution, truncation
|   |   +-- logging_utils.py    # Event logging
|   +-- skill_engine/
|       +-- __init__.py          # Public export surface
|       +-- skill_runner.py      # Facade: re-exports planning + execution
|       +-- planning.py          # ask_for_plan(), validate_plan_for_skill()
|       +-- execution.py         # run_one_skill(), run_one_skill_loop()
|       +-- summarization.py     # Output summarization
|       +-- skill_executor.py    # Bridge op execution (fs/terminal/web/uv/workboard)
|       +-- skill_resolver.py    # Skill lookup & dynamic fetch
|       +-- skill_catalog.py     # Catalog parsing, semantic routing
|       +-- skill_utils.py       # Helpers
+-- cli/                         # CLI REPL with slash commands, history
|   +-- main.py
|   +-- workflow_runner.py
|   +-- skill_search.py
+-- skills/                      # Built-in bridge skills
    +-- filesystem/SKILL.md
    +-- terminal/SKILL.md
    +-- web-search/SKILL.md + scripts/
    +-- uv-pip-install/SKILL.md
    +-- skill-creator/SKILL.md + scripts/ + references/
```

**Key functions** (all re-exported from `agent.py`):

| Function | Module | Purpose |
|---|---|---|
| `route_skill(user_text, skills, skills_xml, *, routing_goal=...)` | `core.router` | Semantic + LLM routing -> returns `{"action": "next_step", "name": "skill_name", ...}` |
| `run_one_skill_loop(user_text, skill_name, max_rounds=50)` | `core.skill_engine.execution` | Multi-round skill execution with planning loop |
| `run_one_skill(user_text, skill_name)` | `core.skill_engine.execution` | Single-shot skill execution |
| `load_available_skills_block()` | `core.skill_engine.skill_catalog` | Load skills XML from AGENTS.md |
| `parse_available_skills(skills_xml)` | `core.skill_engine.skill_catalog` | Parse XML into list of skill dicts |
| `openrouter_messages(system, messages)` | `core.llm` | Call LLM (OpenRouter/Anthropic) |
| `ensure_skill_available(name)` | `core.skill_engine.skill_resolver` | Fetch/install missing skills |

**Op types available to workers** (defined in `config.py`, listed in LLM system prompt via `planning.py`):

| Category | Op Types |
|---|---|
| Filesystem | `read_file`, `write_file`, `edit_file`, `replace_text`, `append_file`, `list_directory`, `directory_tree`, `create_directory`, `mkdir`, `move_file`, `copy_file`, `delete_file`, `file_info`, `search_files`, `file_exists` |
| Terminal | `run_command`, `shell` |
| Web | `web_search`, `search`, `google_search`, `fetch`, `fetch_url`, `fetch_markdown` |
| UV pip | `check`, `install`, `list` |
| Workboard | `read_workboard`, `edit_workboard` |
| Meta | `call_skill` |

**Execution flow inside a single worker**:

```
subtask string
    |
route_skill(subtask, skills, skills_xml)
    -> semantic pre-filter (BM25/Qwen/Memento embeddings)
    -> LLM picks skill + instruction
    -> returns {"action": "next_step", "name": "filesystem", ...}
    |
run_one_skill_loop(subtask, skill_name)
    -> loads SKILL.md
    -> ask_for_plan() -> LLM generates JSON ops
    |   (system prompt includes all op types: filesystem, terminal,
    |    web, uv, AND workboard ops)
    |
    -> execute_skill_plan() ->
    |   1. Pre-extract any workboard ops from the ops list
    |   2. Execute workboard ops via _execute_workboard_ops()
    |   3. Execute remaining ops via the skill's builtin executor
    |   4. Merge workboard + skill results
    |
    -> check for CONTINUE / auto-continue heuristics
    -> loop until final answer or max_rounds
    |
result string
```

## Project Structure

```
memento-team/
+-- Memento-S/
|   +-- agent.py              # Re-export facade
|   +-- mcp_server.py         # Standalone MCP server (no workboard param)
|   +-- core/
|   |   +-- config.py         # Constants, op-type sets (incl. WORKBOARD_OP_TYPES)
|   |   +-- workboard.py      # Thread-safe shared workboard (read/write/edit)
|   |   +-- skill_engine/
|   |       +-- planning.py       # LLM system prompt (lists all op types incl. workboard)
|   |       +-- skill_executor.py # Bridge execution + workboard pre-extraction
|   |       +-- execution.py      # run_one_skill_loop()
|   |       +-- ...
|   +-- cli/
|   +-- skills/
+-- orchestrator/
|   +-- __init__.py
|   +-- orchestrator_agent.py # Orchestrator agent (LangChain create_agent)
|   +-- mcp_server.py         # Orchestrator MCP server (adds workboard param)
+-- main.py                   # Entry point
```

---

## 1. MCP Servers

Two MCP server variants exist:

- **`Memento-S/mcp_server.py`** — Standalone version. No workboard parameter. Used when running Memento-S workers independently.
- **`orchestrator/mcp_server.py`** — Orchestrator version. Adds the `workboard` parameter and calls `write_board()` to create the shared workboard file. Does **not** inject workboard instructions into subtasks — workers discover the workboard on their own via `read_workboard` op (available in the system prompt from `planning.py`).

### `orchestrator/mcp_server.py` (used by the orchestrator)

```python
"""Orchestrator MCP Server -- wraps Memento-S worker pool with workboard support."""

import os
import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Set up imports from Memento-S directory
_MEMENTO_S_DIR = str(Path(__file__).resolve().parent.parent / "Memento-S")
sys.path.insert(0, _MEMENTO_S_DIR)
os.chdir(_MEMENTO_S_DIR)

from fastmcp import FastMCP

from agent import (
    run_one_skill_loop,
    route_skill,
    load_available_skills_block,
    parse_available_skills,
    has_local_skill_dir,
    ensure_skill_available,
    AGENTS_MD,
    DEBUG,
)
from core.workboard import write_board, cleanup_board, get_board_path

import logging

logger = logging.getLogger(__name__)

MAX_POOL_SIZE = 5

mcp = FastMCP("MementoSWorkerPool")

_semaphore = asyncio.Semaphore(MAX_POOL_SIZE)

EXECUTE_SUBTASKS_DESCRIPTION = f"""
Execute 1-{MAX_POOL_SIZE} independent subtasks in parallel using Memento-S agent workers.
...
Args:
  subtasks: List[str]
    List of 1 to {MAX_POOL_SIZE} fully self-contained task descriptions.
  workboard: str (optional)
    Markdown content for a shared workboard file. The content is written
    directly as-is. Workers can read and edit it during execution.
"""

# ... _load_skills_catalog(), _execute_single_subtask() identical to standalone ...

@mcp.tool(description=EXECUTE_SUBTASKS_DESCRIPTION)
async def execute_subtasks(subtasks: List[str], workboard: str = "") -> dict:
    """Execute subtasks in parallel on Memento-S agent workers."""
    # ... validation ...

    # Write workboard if provided (workers discover it on their own)
    if workboard and workboard.strip():
        board_path = write_board(workboard)
        print(f"  [Workboard] Created at {board_path}", file=sys.stderr)

    # ... run_one(), gather, return results (same as standalone) ...
```

### `Memento-S/mcp_server.py` (standalone, no workboard)

```python
"""Memento-S Worker Pool MCP Server -- dispatches subtasks to agent.py"""

import os, asyncio, sys, time
from pathlib import Path
from typing import Any, Dict, List

os.chdir(Path(__file__).resolve().parent)

from fastmcp import FastMCP
from agent import (run_one_skill_loop, route_skill, ...)

# No workboard imports -- standalone version

@mcp.tool(description=EXECUTE_SUBTASKS_DESCRIPTION)
async def execute_subtasks(subtasks: List[str]) -> dict:
    # No workboard parameter -- workers can still use workboard ops
    # if a workboard file exists (e.g. created externally)
    ...
```

---

## 2. Shared Workboard -- `Memento-S/core/workboard.py`

Thread-safe shared markdown file that parallel workers can read and edit for coordination. Protected by a module-level `threading.Lock` so concurrent workers (running via `asyncio.to_thread()`) can safely access the same file.

```python
"""Shared workboard for coordinating parallel Memento-S workers."""

from __future__ import annotations

import threading
from pathlib import Path

from core.config import WORKSPACE_DIR

_lock = threading.Lock()


def get_board_path() -> Path:
    """Return the canonical workboard file path."""
    return WORKSPACE_DIR / ".workboard.md"


def cleanup_board() -> None:
    """Delete the workboard file if it exists."""
    with _lock:
        path = get_board_path()
        if path.exists():
            path.unlink()


def write_board(content: str) -> Path:
    """Write *content* to the workboard file (creates parent dirs as needed)."""
    with _lock:
        path = get_board_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


def read_board() -> str:
    """Return the full markdown content of the workboard."""
    with _lock:
        path = get_board_path()
        if not path.exists():
            return "(no workboard exists)"
        return path.read_text(encoding="utf-8")


def edit_board(old_text: str, new_text: str) -> str:
    """Find-and-replace *old_text* with *new_text* in the workboard."""
    with _lock:
        path = get_board_path()
        if not path.exists():
            return "edit_board ERR: workboard does not exist"
        content = path.read_text(encoding="utf-8")
        if old_text not in content:
            return f"edit_board ERR: old_text not found in workboard"
        new_content = content.replace(old_text, new_text, 1)
        path.write_text(new_content, encoding="utf-8")
        return "edit_board OK"
```

---

## 3. Workboard Op Execution -- `Memento-S/core/skill_engine/skill_executor.py`

Workers emit workboard ops (`read_workboard`, `edit_workboard`) alongside normal skill ops. The key mechanism that makes this work:

**`execute_skill_plan()`** pre-extracts workboard ops before dispatching to any builtin skill executor, then merges the results:

```python
def execute_skill_plan(skill_name: str, plan: dict) -> str:
    normalized = normalize_plan_shape(plan)
    skill = str(skill_name or "").strip()
    # ...

    # Pre-extract workboard ops (orthogonal to any skill)
    workboard_results: list[str] = []
    if skill != "workboard":
        remaining_ops = []
        wb_ops = []
        for op in ops:
            op_type_raw = (
                str(op.get("type") or "").strip().lower()
                if isinstance(op, dict) else ""
            )
            if op_type_raw in WORKBOARD_OP_TYPES:
                wb_ops.append(op)
            else:
                remaining_ops.append(op)
        if wb_ops:
            workboard_results.append(_execute_workboard_ops({"ops": wb_ops}))
        ops = remaining_ops
        normalized["ops"] = ops
        if not ops:
            return "\n".join(workboard_results)

    # Dispatch to builtin skill executor
    if skill == "skill-creator":
        skill_result = _execute_skill_creator_plan(normalized)
    elif skill == "filesystem":
        skill_result = _execute_filesystem_ops(normalized)
    elif skill == "terminal":
        skill_result = _execute_terminal_ops(normalized)
    # ... etc

    # Merge workboard + skill results
    if workboard_results:
        result = "\n\n".join(workboard_results) + "\n\n" + skill_result
    else:
        result = skill_result
    return result
```

This ensures a worker routed to e.g. `"filesystem"` can still use workboard ops in the same plan without the filesystem executor rejecting them as unknown.

---

## 4. LLM System Prompt -- `Memento-S/core/skill_engine/planning.py`

The `ask_for_plan()` system prompt tells the LLM which op types are available. Workboard ops are included in the closed list:

```python
system_prompt = (
    "Follow the loaded SKILL.md exactly and return JSON only (no markdown). "
    'If no external actions are needed, return {"final":"..."}. '
    'If actions are needed, return {"ops":[...]} using bridge-friendly op types only: '
    "call_skill, run_command/shell, filesystem ops (...), web ops (...), "
    "uv ops (check/install/list), and workboard ops (read_workboard/edit_workboard). "
    "A shared workboard (workspace/.workboard.md) is always available for coordinating with other parallel workers. "
    "Use read_workboard as your first op to see the team's task board, then edit_workboard to update your progress when done. "
    # ...
)
```

---

## 5. Orchestrator Agent -- `orchestrator/orchestrator_agent.py`

LangChain orchestrator using `create_agent()`. Decomposes the task via its system prompt, then calls `execute_subtasks` with an optional `workboard` parameter.

```python
"""OrchestratorAgent -- LangChain orchestrator that decomposes tasks and dispatches to Memento-S workers."""

from __future__ import annotations

import logging
import os
import sys
import traceback
from typing import Any, AsyncGenerator, Mapping, Sequence

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """
    LangChain orchestrator agent that decomposes tasks into subtasks
    and dispatches them to Memento-S workers via MCP.

    Architecture:
    - Uses LangChain BaseChatModel for LLM interactions
    - Connects to Memento-S MCP server for parallel task execution
    - Uses create_agent() to build the agent graph
    - Supports both streaming and non-streaming execution

    Usage:
        orchestrator = OrchestratorAgent(model=ChatOpenAI(model="gpt-4o"))
        await orchestrator.start()
        result = await orchestrator.run("Build a web scraper for news articles")
        await orchestrator.close()
    """

    DEFAULT_COMMAND = sys.executable
    DEFAULT_ARGS: Sequence[str] = ("orchestrator/mcp_server.py",)

    def __init__(
        self,
        *,
        name: str = "orchestrator",
        model: BaseChatModel,
        description: str | None = None,
        command: str | None = None,
        args: Sequence[str] | None = None,
        env: Mapping[str, str] | None = None,
        system_message: str | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self._description = description or (
            "Decomposes complex tasks into subtasks and dispatches "
            "them to Memento-S worker agents for parallel execution."
        )
        self._command = command or self.DEFAULT_COMMAND
        self._args = list(args) if args is not None else list(self.DEFAULT_ARGS)
        self._env = dict(os.environ if env is None else env)
        self._system_message = system_message or self._build_default_system_message()
        self._mcp_client: MultiServerMCPClient | None = None
        self._agent_graph: Any = None

    def _build_default_system_message(self) -> str:
        return """You are an Orchestrator Agent coordinating a pool of Memento-S workers.

## YOUR JOB
1. Receive a task from the user.
2. Decompose it into focused, self-contained subtasks.
3. Call `execute_subtasks` with the list of subtask strings.
4. Synthesize the worker results into a final response.

## DECOMPOSITION STRATEGY
- One focused goal per subtask -- maximize parallelism
- Each subtask must be SELF-CONTAINED with full context
- Workers are STATELESS -- never write "use the result from subtask 1"
- Keep subtasks atomic and bounded
- If the task has many parts, split into bounded slices

## CRITICAL: Workers are STATELESS
- Write SELF-CONTAINED descriptions with full details
- Never write "find details for the above" -- workers have no context
- GOOD: "Read the file /home/user/project/config.py and extract the database URL"
- BAD: "Read the config file mentioned earlier"

## WORKER CAPABILITIES
Each worker is a Memento-S agent powered by Agent Skills -- capable of handling most tasks
including file operations, shell commands, web search, package management, and more.
Workers automatically select the best skill for each subtask and can dynamically
acquire new skills on demand. Each worker handles complex tasks iteratively.
Based on this, focus on decomposing the task into clear, self-contained subtasks.

## WORKBOARD (WORKER COORDINATION)
When calling execute_subtasks, you can include a `workboard` parameter -- a markdown
string that creates a shared workboard file all workers can read and edit during execution.
Workers can use `read_workboard` and `edit_workboard` ops to coordinate in real time.
Use any markdown format you find appropriate for the task.

## OUTPUT
- After receiving worker results, synthesize into a clear final response
"""

    async def start(self) -> None:
        """Initialize MCP connection to worker pool and build the agent graph."""
        env = dict(self._env)

        mcp_servers = {
            "memento_worker_pool": {
                "command": self._command,
                "args": self._args,
                "env": env,
                "transport": "stdio",
            }
        }

        self._mcp_client = MultiServerMCPClient(mcp_servers)
        tools = await self._mcp_client.get_tools()

        self._agent_graph = create_agent(
            model=self.model,
            tools=tools,
            system_prompt=self._system_message,
        )

    async def run(self, query: str | list[dict]) -> dict[str, Any]:
        """Execute the orchestrator agent and return the complete result."""
        self._ensure_started()

        if isinstance(query, str):
            query_preview = query[:200] + "..." if len(query) > 200 else query
            logger.info(f"[Orchestrator] Query: {query_preview}")
            messages = [{"role": "user", "content": query}]
        else:
            messages = query

        try:
            result = await self._agent_graph.ainvoke({"messages": messages})
            output = self._extract_output(result)
            logger.info(f"[Orchestrator] Result: {output[:300]}...")
            return {"output": output, "raw": result}
        except Exception as e:
            logger.error(f"[Orchestrator] Error: {e}\n{traceback.format_exc()}")
            raise

    async def stream(
        self, query: str | list[dict]
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Execute the orchestrator agent and stream updates."""
        self._ensure_started()

        if isinstance(query, str):
            messages = [{"role": "user", "content": query}]
        else:
            messages = query

        async for chunk in self._agent_graph.astream(
            {"messages": messages},
            stream_mode="updates",
            config={"recursion_limit": 50},
        ):
            yield chunk

    async def close(self) -> None:
        """Close MCP connections and cleanup."""
        self._mcp_client = None
        self._agent_graph = None

    def _ensure_started(self) -> None:
        if self._agent_graph is None:
            raise RuntimeError("OrchestratorAgent not started. Call start() first.")

    @staticmethod
    def _extract_output(result: Any) -> str:
        """Best-effort extraction of the final answer from LangChain agent results."""
        if isinstance(result, dict):
            messages = result.get("messages")
            if isinstance(messages, (list, tuple)) and messages:
                last = messages[-1]
                content = getattr(last, "content", None)
                if content:
                    return str(content)
            if "output" in result and result["output"]:
                return str(result["output"])
        return str(result)
```

---

## 6. Entry Point -- `main.py`

```python
"""Entry point for the multi-agent workflow."""

import asyncio
import os
import sys

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from orchestrator.orchestrator_agent import OrchestratorAgent

load_dotenv()

# Ensure Memento-S is on the import path for workboard cleanup
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Memento-S"))


async def main():
    # Clean up old workboard from previous runs
    try:
        from core.workboard import cleanup_board
        cleanup_board()
    except Exception:
        pass  # Non-fatal
    model = ChatOpenAI(
        model=os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5"),
        openai_api_key=os.getenv("OPENROUTER_API_KEY"),
        openai_api_base=os.getenv("OPENROUTER_BASE_URL"),
        temperature=0,
    )
    orchestrator = OrchestratorAgent(model=model)

    await orchestrator.start()

    task = input("Enter your task: ")
    result = await orchestrator.run(task)

    print("\n=== Final Result ===")
    print(result["output"])

    await orchestrator.close()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 7. Package Init -- `orchestrator/__init__.py`

```python
from .orchestrator_agent import OrchestratorAgent

__all__ = ["OrchestratorAgent"]
```

---

## Dependencies

```
langchain>=0.3
langchain-openai>=0.3
langchain-mcp-adapters>=0.1
fastmcp>=0.1
```

Plus everything already in `Memento-S/requirements.txt` (anthropic, dotenv, etc.)

## Setup

```bash
pip install langchain langchain-openai langchain-mcp-adapters fastmcp

# Set API keys (OpenRouter is used for both orchestrator and workers)
export OPENROUTER_API_KEY="sk-or-..."
export OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
export OPENROUTER_MODEL="anthropic/claude-sonnet-4.5"  # optional, this is the default

# Run
python main.py
```

## Execution Flow

1. **`main.py`** cleans up any old workboard, creates the LLM model via OpenRouter
2. **Orchestrator agent** LLM reasons about the task, decomposes it into subtasks, and optionally creates a workboard markdown
3. **Orchestrator** calls `execute_subtasks(["subtask1", "subtask2", ...], workboard="...")` on `orchestrator/mcp_server.py`
4. **MCP server** writes the workboard to `workspace/.workboard.md` (no injection into subtasks)
5. **MCP server** runs each subtask through Memento-S `agent.py`:
   - `route_skill()` -> semantic pre-filter + LLM picks the best skill
   - `run_one_skill_loop()` -> loads SKILL.md, generates plan (LLM knows about workboard ops from `planning.py` system prompt), executes bridge ops, loops until done
   - `execute_skill_plan()` -> pre-extracts workboard ops, runs them alongside the skill's own ops, merges results
6. **Workers** discover and use the shared workboard on their own via `read_workboard` / `edit_workboard` ops
7. **MCP server** returns all results to the orchestrator
8. **Orchestrator** synthesizes worker results into a final response

## Workboard Coordination Flow

```
Orchestrator
    |
    +-- execute_subtasks(subtasks=[...], workboard="| # | Worker | Task | Status |\n...")
            |
            +-- orchestrator/mcp_server.py writes workboard to workspace/.workboard.md
            +-- subtasks dispatched as-is (no injection)
            |
            +-- Worker 0 (filesystem skill):
            |     planning.py system prompt lists workboard ops as available
            |     LLM discovers workboard and emits:
            |       {"ops": [{"type": "read_file", ...}, {"type": "edit_workboard", ...}]}
            |     execute_skill_plan("filesystem", plan):
            |       -> pre-extract edit_workboard -> _execute_workboard_ops() -> "edit_board OK"
            |       -> remaining [read_file] -> _execute_filesystem_ops() -> file content
            |       -> merge -> "edit_board OK\n\nfile content"
            |
            +-- Worker 1 (terminal skill):
            |     LLM discovers workboard and emits:
            |       {"ops": [{"type": "run_command", ...}, {"type": "read_workboard"}]}
            |     execute_skill_plan("terminal", plan):
            |       -> pre-extract read_workboard -> _execute_workboard_ops() -> board content
            |       -> remaining [run_command] -> _execute_terminal_ops() -> command output
            |       -> merge -> "board content\n\ncommand output"
            |
            +-- Results aggregated and returned to orchestrator
```
