# Memento Teams

Multi-agent orchestration system that decomposes complex tasks into parallel subtasks and executes them using skill-based worker agents. Includes a self-improving eval pipeline that learns decomposition strategies from past runs.

## Quick Start

```bash
curl -sSL https://raw.githubusercontent.com/nj19257/memento-team/demo_test/install.sh | bash
```

Then launch the TUI:

```bash
memento-teams
```

## Architecture

```
User Query (TUI)
    |
    v
Orchestrator Agent (LangChain)
    |  1. Load orchestrator skills (task-router → decompose-*)
    |  2. LLM decomposes task into subtasks
    |  3. Create workboard for worker coordination
    |
    +-- calls MCP tool: execute_subtasks(["subtask1", ...], workboard="...")
                |
                v
        MCP Server (FastMCP, stdio transport)
            |-- Worker 0: MementoSAgent → route_skill() → run_one_skill_loop()
            |-- Worker 1: MementoSAgent → route_skill() → run_one_skill_loop()
            +-- Worker N: MementoSAgent → route_skill() → run_one_skill_loop()
                |   (shared AppContext: embeddings, skill catalog, ChromaDB)
                |   (workboard coordination via read/edit_workboard)
                v
        Aggregated results returned to orchestrator
                |
                v
        Orchestrator synthesizes final response
```

## Key Components

| File | Purpose |
|---|---|
| [tui_app.py](tui_app.py) | Textual TUI — primary interface for submitting tasks and inspecting workers |
| [orchestrator/orchestrator_agent.py](orchestrator/orchestrator_agent.py) | LangChain-based orchestrator that decomposes tasks and dispatches to workers via MCP |
| [orchestrator/mcp_server.py](orchestrator/mcp_server.py) | FastMCP server exposing `execute_subtasks`, workboard, and skill tools — runs up to 10 workers in parallel |
| [Memento-S/core/agent/memento_s_agent.py](Memento-S/core/agent/memento_s_agent.py) | Worker agent — skill routing, planning, and execution |
| [Memento-S/core/config.py](Memento-S/core/config.py) | Centralized configuration from environment variables |
| [Memento-S/core/router.py](Memento-S/core/router.py) | Skill routing — BM25 + sentence-transformers (BAAI/bge-m3) + LLM selection |
| [orchestrator_skills/](orchestrator_skills/) | Auto-generated decomposition strategies (task-router + decompose-* skills) |

## Self-Improving Eval Pipeline

Memento Teams includes a learning loop that automatically improves the orchestrator's decomposition strategies:

```
 Run (eval/run.py)          Verify (eval/verify.py)         Reflect (eval/reflect.py)
┌──────────────────┐    ┌───────────────────────────┐    ┌──────────────────────────┐
│ Execute tasks    │───>│ Compare output vs gold    │───>│ Cluster tasks by pattern │
│ via orchestrator │    │ Score accuracy per column  │    │ Generate decompose skills│
│ Save outputs &   │    │ Generate error report      │    │ Generate task-router     │
│ worker logs      │    │ Compress trajectories      │    │ Write to orchestrator_   │
└──────────────────┘    └───────────────────────────┘    │ skills/                  │
                                                         └──────────────────────────┘
```

**One-click learning:**

```bash
./eval/learn.sh                    # Run all tasks → verify → reflect
./eval/learn.sh --parallel         # Run tasks concurrently
./eval/learn.sh --skip-run         # Re-verify + reflect only (reuse existing outputs)
```

**Individual stages:**

```bash
python eval/run.py --parallel                  # Run eval tasks
python eval/verify.py                          # Verify against gold answers
python eval/reflect.py                         # Generate new orchestrator skills
```

The pipeline uses 200 WideSearch benchmark tasks (100 EN + 100 ZH), with 41 tasks having gold CSV answers for automated scoring.

## Built-in Skills

| Skill | Description |
|---|---|
| `filesystem` | Read, write, edit, search, and manage files and directories |
| `terminal` | Execute shell commands with safety checks |
| `web-search` | Google search via SerpAPI + URL fetching |
| `uv-pip-install` | Python package management via uv/pip |
| `skill-creator` | Dynamically create new skills at runtime |

Workers automatically select the best skill for each subtask via semantic routing (BM25 + embeddings + LLM). If no existing skill matches, the system can dynamically fetch or create new skills on demand.

## How It Works

1. **User** submits a task via the TUI
2. **Orchestrator** loads orchestrator skills (task-router identifies decomposition type)
3. **Orchestrator** LLM decomposes task into self-contained subtasks with a shared workboard
4. **Orchestrator** calls `execute_subtasks()` on the MCP server
5. **MCP server** runs each subtask through a Memento-S worker:
   - `route_skill()` — semantic pre-filter (BM25/embeddings) + LLM picks the best skill
   - `run_one_skill_loop()` — loads `SKILL.md`, generates a JSON operation plan, executes bridge ops, loops until done
   - Workers coordinate via workboard (read/edit tagged sections)
6. **MCP server** returns aggregated results
7. **Orchestrator** synthesizes worker results into a final response

## Setup

### One-Click Install

```bash
curl -sSL https://raw.githubusercontent.com/nj19257/memento-team/demo_test/install.sh | bash
```

The installer will:
- Install `uv` (if not present)
- Clone the repo (branch `demo_test`)
- Install all dependencies (`Memento-S` + orchestrator)
- Download router assets (skill catalog + optional embeddings)
- Configure `.env` interactively (API keys)
- Create the `memento-teams` command

### Manual Setup

Prerequisites: Python 3.12+, `uv`, git

```bash
git clone --branch demo_test https://github.com/nj19257/memento-team.git
cd memento-team

# Install Memento-S worker dependencies
cd Memento-S && uv sync --python 3.12 && cd ..

# Install orchestrator dependencies
uv sync --python 3.12
```

Create a `.env` file in the project root:

```env
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=anthropic/claude-sonnet-4-5
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
SERPAPI_API_KEY=...
```

### Run

```bash
memento-teams
```

Or directly:

```bash
uv run python -c "from tui_app import MementoTeams; MementoTeams().run()"
```

## TUI

```bash
memento-teams
```

- Submit tasks directly from the interface (`Ctrl+Enter` or **Run Task**)
- Session-scoped worker list from `logs/worker-*.jsonl` (current task only)
- Per-worker status label (`live` / `finished`)
- Click any worker row to inspect execution steps/events
- Live workboard view from `Memento-S/workspace/.workboard.md`
- Workboard history is preserved per session as `.workboard-<session_id>.md`
- Final orchestrator output panel

Controls:

- `Ctrl+Enter`: Run task
- `r`: Refresh worker list
- `q`: Quit

## Configuration

All configuration is centralized in [Memento-S/core/config.py](Memento-S/core/config.py) and read from environment variables. Key settings:

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | — | API key for LLM calls (required) |
| `OPENROUTER_MODEL` | `anthropic/claude-sonnet-4-5` | Model for Memento-S workers |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | LLM API base URL |
| `SERPAPI_API_KEY` | — | API key for web search skill |
| `MAX_WORKERS` | `10` | Max parallel workers per task |
| `SEMANTIC_ROUTER_ENABLED` | `true` | Enable semantic skill pre-filtering |
| `SEMANTIC_ROUTER_TOP_K` | `4` | Number of candidate skills for LLM routing |
| `SKILL_DYNAMIC_FETCH_ENABLED` | `true` | Auto-fetch missing skills from catalog |
| `DEBUG` | `false` | Enable debug logging |
| `WORKSPACE_DIR` | `Memento-S/workspace` | Workboard location shown in TUI |

## Project Structure

```
memento-team/
├── install.sh                          # One-click installer
├── pyproject.toml                      # Root project (orchestrator deps + entry point)
├── tui_app.py                          # Textual TUI
├── main.py                             # Standalone entry point (non-TUI)
├── orchestrator/
│   ├── orchestrator_agent.py           # LangChain orchestrator agent
│   └── mcp_server.py                   # FastMCP server (execute_subtasks + workboard)
├── orchestrator_skills/                # Auto-generated decomposition strategies
│   ├── task-router/SKILL.md            # Routes queries to decompose strategies
│   ├── decompose-split-by-entity/      # Split by entity/brand
│   ├── decompose-split-by-time-period/ # Split by chronological range
│   ├── decompose-split-by-category/    # Split by categorical dimension
│   ├── decompose-split-by-rank-segment/# Split by rank ranges
│   └── ...                             # More patterns auto-generated by reflect.py
├── eval/
│   ├── learn.sh                        # One-click learning pipeline (run → verify → reflect)
│   ├── run.py                          # Batch eval task runner
│   ├── verify.py                       # Verification & scoring vs gold answers
│   ├── reflect.py                      # Self-reflection → skill generation
│   ├── utils.py                        # Shared eval utilities
│   ├── widesearch.jsonl                # 200 WideSearch benchmark tasks
│   ├── gold/                           # Gold CSV answers (41 tasks)
│   ├── outputs/                        # System outputs (*.md)
│   └── reports/                        # Run manifests & verify reports
├── Memento-S/
│   ├── pyproject.toml                  # Worker dependencies
│   ├── core/
│   │   ├── agent/memento_s_agent.py    # Worker agent class
│   │   ├── config.py                   # Configuration & constants
│   │   ├── router.py                   # Skill routing logic
│   │   ├── llm.py                      # LLM wrapper (OpenRouter)
│   │   ├── skills/                     # Skill management & providers
│   │   └── tools/                      # Tool implementations
│   └── skills/                         # Built-in skill definitions
│       ├── filesystem/
│       ├── terminal/
│       ├── web-search/
│       ├── uv-pip-install/
│       └── skill-creator/
└── logs/                               # Worker trajectory logs (*.jsonl)
```
