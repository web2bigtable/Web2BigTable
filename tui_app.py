"""Textual TUI for orchestrator runs and live worker trajectory inspection."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
import re
import time
import traceback
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Collapsible, DataTable, Footer, Header, Input, Select, Static, TextArea
try:
    from textual.widgets import MarkdownViewer
except Exception:
    MarkdownViewer = None  # type: ignore[assignment]

from orchestrator.orchestrator_agent import OrchestratorAgent

ROOT = Path(__file__).resolve().parent
LOGS_DIR = ROOT / "logs"

# Available models for the selector (label, value)
# Values are exact OpenRouter model IDs — see https://openrouter.ai/models
MODEL_OPTIONS: list[tuple[str, str]] = [
    ("DeepSeek V3.2", "deepseek/deepseek-v3.2"),
    ("GPT-5.2", "openai/gpt-5.2"),
    ("GPT-5.1", "openai/gpt-5.1"),
    ("GPT-5 mini", "openai/gpt-5-mini"),
    ("GPT-4.1", "openai/gpt-4.1"),
    ("GPT-4o mini", "openai/gpt-4o-mini"),
    ("Gemini 3 Flash", "google/gemini-3-flash-preview"),
    ("Gemini 3.1 Pro", "google/gemini-3.1-pro-preview"),
    ("Claude Sonnet 4.6", "anthropic/claude-sonnet-4.6"),
    ("Claude Sonnet 4.5", "anthropic/claude-sonnet-4.5"),
    ("Claude Opus 4.6", "anthropic/claude-opus-4.6"),
    ("Claude Opus 4.5", "anthropic/claude-opus-4.5"),
]

# ---------------------------------------------------------------------------
# Workboard helpers (inline — no core.workboard module in this repo)
# ---------------------------------------------------------------------------
WORKBOARD_PATH = ROOT / "Memento-S" / "workspace" / ".workboard.md"


def get_board_path() -> Path:
    return WORKBOARD_PATH


def cleanup_board() -> None:
    try:
        if WORKBOARD_PATH.exists():
            WORKBOARD_PATH.unlink()
    except Exception:
        pass


class Web2BigTable(App):
    TITLE = "Web2BigTable"
    """Minimal Textual UI for running tasks and inspecting worker logs."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #layout {
        height: 1fr;
    }

    #left {
        layout: vertical;
        width: 36%;
        min-width: 36;
        padding: 1;
        border: round #666666;
    }

    #right {
        width: 3fr;
        padding: 1;
        border: round #666666;
    }

    #tab_bar {
        height: 3;
        margin-bottom: 1;
        border-bottom: solid #3a3a3a;
        padding: 0 1;
    }

    .tab_btn {
        margin-right: 0;
        min-width: 18;
        border: none;
        border-top: round #4a4a4a;
        border-left: round #4a4a4a;
        border-right: round #4a4a4a;
        background: #1a1a1a;
        color: #a8b4c7;
    }

    .tab_btn.active_tab {
        background: #262626;
        color: #d9e7ff;
        text-style: bold;
        border-top: round #7a7a7a;
        border-left: round #7a7a7a;
        border-right: round #7a7a7a;
    }

    .tab_btn:focus {
        background: #262626;
        color: #d9e7ff;
        border-top: round #7a7a7a;
        border-left: round #7a7a7a;
        border-right: round #7a7a7a;
    }

    #task_input {
        height: 1fr;
        min-height: 6;
        margin-bottom: 1;
        color: #dfe8f5;
    }

    #settings_collapsible {
        height: auto;
        padding: 0;
    }

    #model_row {
        height: 3;
        margin-bottom: 1;
    }

    #model_row_compact {
        height: 4;
        margin-bottom: 1;
    }

    .compact_field {
        layout: vertical;
        height: 4;
        margin-right: 1;
    }

    .key_field {
        layout: vertical;
        height: 4;
        margin-bottom: 1;
    }

    .key_label {
        width: auto;
        height: auto;
        padding: 0;
        color: #b8ddff;
    }

    .key_input {
        width: 1fr;
    }

    #model_label {
        width: auto;
        height: auto;
        padding: 0 0 0 0;
        color: #b8ddff;
    }

    #model_select {
        width: 1fr;
        min-width: 12;
    }

    #task_controls {
        layout: vertical;
        height: 3;
        margin-bottom: 1;
    }

    #action_row {
        height: 3;
    }

    #workers_label {
        width: auto;
        height: auto;
        padding: 0 0 0 0;
        color: #82d2ff;
    }

    #workers_count {
        width: 10;
        margin-right: 1;
    }

    #run_task {
        width: 1fr;
        min-width: 12;
        margin-bottom: 0;
    }

    #stop_task {
        width: 1fr;
        min-width: 10;
        margin-bottom: 0;
        margin-left: 1;
        background: #6b2020;
        color: #f0f0f0;
        border: round #8b3030;
    }

    #stop_task:disabled {
        background: #3a1a1a;
        color: #666666;
        border: round #4a2a2a;
    }

    Button.-primary {
        background: #2f4f6f;
        color: #f0f0f0;
        border: round #4e6a86;
    }

    Button.-primary:hover {
        background: #3a5f84;
    }

    #workers_table {
        height: 1fr;
        color: #d6e4f4;
    }

    #left_task {
        layout: vertical;
        height: 2fr;
        min-height: 18;
        overflow-y: auto;
    }

    #left_workers {
        height: 3fr;
    }

    #steps_table {
        height: 1fr;
        margin-bottom: 1;
        color: #d6e4f4;
    }

    #steps_filters {
        height: auto;
        margin-bottom: 1;
    }

    .steps_filter_input {
        width: 1fr;
        margin-right: 1;
    }

    #steps_subtask {
        margin-bottom: 1;
        border: round #666666;
        padding: 0 1;
        color: #dce8be;
    }

    #steps_worker_row {
        color: #b8ddff;
        margin-bottom: 1;
    }

    #workboard {
        height: 1fr;
        margin-bottom: 1;
        color: #f0f0f0;
    }

    #board_view_bar, #final_view_bar {
        height: 3;
        margin-bottom: 1;
    }

    .subtab_btn {
        margin-right: 1;
        min-width: 10;
        color: #d9e7ff;
    }

    .subtab_btn.active_subtab {
        text-style: bold;
    }

    .workboard_container {
        border: round #666666;
    }

    #final_output {
        height: 1fr;
        border: round #666666;
        padding: 0 1;
        color: #f3e2b1;
    }

    #progress_workflow {
        height: 1fr;
        border: round #666666;
        padding: 0 1;
        color: #d9e7ff;
    }

    #webpages_table {
        height: 1fr;
        color: #d6e4f4;
    }

    .section_title {
        margin: 0 0 1 0;
        text-style: bold;
        color: #f2c57a;
    }

    #title_task {
        color: #f0be70;
    }

    #title_workers {
        color: #82d2ff;
    }

    #title_steps {
        color: #9ec7ff;
    }

    #title_workboard {
        color: #9ec7ff;
    }

    #title_final {
        color: #f1d18a;
    }

    .hidden {
        display: none;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh_workers", "Refresh Workers"),
        ("ctrl+enter", "run_task", "Run Task"),
        ("c", "copy_final", "Copy Final Output"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.orchestrator: OrchestratorAgent | None = None
        self._task_running: bool = False
        self._running_task_handle: asyncio.Task | None = None
        self._worker_files: list[Path] = []
        self._worker_row_key_to_path: dict[Any, Path] = {}
        self._selected_worker_path: Path | None = None
        self._selected_worker_mtime: float = -1.0
        self._workboard_last_text: str = ""
        self._session_id: str | None = None
        self._last_session_id: str | None = None
        self._session_started_at: float = 0.0
        self._session_file_baseline: set[str] = set()
        self._current_session_files: list[Path] = []
        self._session_board_path: Path | None = None
        self._last_task_running_state: bool = False
        self._last_session_file_signature: list[tuple[str, int]] = []
        self._active_tab: str = "progress"
        self._board_view: str = "raw"
        self._final_view: str = "raw"
        self._final_last_text: str = ""
        self._max_workers: int = 5
        load_dotenv()
        self._openrouter_key: str = os.getenv("OPENROUTER_API_KEY", "")
        self._serper_key: str = os.getenv("SERPER_API_KEY", "")
        env_model = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v3.2")
        # Use env model if it matches a known option, otherwise default
        known_values = [v for _, v in MODEL_OPTIONS]
        self._selected_model: str = env_model if env_model in known_values else known_values[0]
        env_worker_model = os.getenv("WORKER_MODEL", "")
        self._selected_worker_model: str = env_worker_model if env_worker_model in known_values else self._selected_model
        self._session_worker_order: list[str] = []
        self._steps_filter_tool: str = ""
        self._steps_filter_subtask_id: str = ""
        self._steps_group_enabled: bool = True
        self._webpages_last_count: int = -1
        self._orchestrator_start_error: str | None = None
        self._orchestrator_traj_path: Path | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="layout"):
            with Vertical(id="left"):
                with Vertical(id="left_task"):
                    yield Static("Task", id="title_task", classes="section_title")
                    yield TextArea("", id="task_input")
                    with Horizontal(id="task_controls"):
                        with Horizontal(id="action_row"):
                            yield Button("Run Task", id="run_task", variant="primary")
                            yield Button("Stop", id="stop_task", variant="error", disabled=True)
                            yield Button("Clear", id="clear_task", variant="default")
                            yield Select(self._load_example_options(), id="example_select", prompt="Load Example", allow_blank=True)
                    with Collapsible(title="Settings", id="settings_collapsible", collapsed=True):
                        with Horizontal(id="model_row_compact"):
                            with Vertical(classes="compact_field"):
                                yield Static("Orchestrator:", id="model_label")
                                yield Select(
                                    [(label, value) for label, value in MODEL_OPTIONS],
                                    id="model_select",
                                    value=self._selected_model,
                                    allow_blank=False,
                                )
                            with Vertical(classes="compact_field"):
                                yield Static("Worker:", id="worker_model_label")
                                yield Select(
                                    [(label, value) for label, value in MODEL_OPTIONS],
                                    id="worker_model_select",
                                    value=self._selected_worker_model,
                                    allow_blank=False,
                                )
                            with Vertical(classes="compact_field"):
                                yield Static("Workers:", id="workers_label")
                                yield Input("5", id="workers_count", type="integer", max_length=3)
                        with Vertical(classes="key_field"):
                            yield Static("OpenRouter API Key:", classes="key_label")
                            yield Input(self._openrouter_key, id="openrouter_key_input", password=True, placeholder="sk-or-...", classes="key_input")
                        with Vertical(classes="key_field"):
                            yield Static("Serper Key:", classes="key_label")
                            yield Input(self._serper_key, id="serper_key_input", password=True, placeholder="Serper key (optional)", classes="key_input")
                with Vertical(id="left_workers"):
                    yield Static("Workers (live)", id="title_workers", classes="section_title")
                    yield DataTable(id="workers_table")
            with Vertical(id="right"):
                with Horizontal(id="tab_bar"):
                    yield Button("Progress", id="tab_progress", classes="tab_btn active_tab")
                    yield Button("Workboard", id="tab_board", classes="tab_btn")
                    yield Button("Execution Steps", id="tab_steps", classes="tab_btn")
                    yield Button("Final Output", id="tab_final", classes="tab_btn")
                    yield Button("Web Pages", id="tab_webpages", classes="tab_btn")

                with Vertical(id="panel_progress"):
                    yield Static("Workflow", id="title_progress", classes="section_title")
                    yield TextArea("", id="progress_workflow", read_only=True)

                with Vertical(id="panel_steps", classes="hidden"):
                    yield Static("Execution Steps (selected worker)", id="title_steps", classes="section_title")
                    yield Static("(no worker selected)", id="steps_worker_row")
                    yield Static("(select a worker to view its subtask)", id="steps_subtask")
                    with Horizontal(id="steps_filters"):
                        yield Input(placeholder="Filter tool_name (e.g. edit_workboard)", id="steps_filter_tool", classes="steps_filter_input")
                        yield Input(placeholder="Filter subtask_id (e.g. t1)", id="steps_filter_subtask", classes="steps_filter_input")
                        yield Button("Grouping: On", id="steps_group_toggle", classes="subtab_btn active_subtab", variant="primary")
                        yield Button("Clear", id="steps_filter_clear", classes="subtab_btn")
                    yield DataTable(id="steps_table")

                with Vertical(id="panel_board"):
                    yield Static("Workboard", id="title_workboard", classes="section_title")
                    with Horizontal(id="board_view_bar"):
                        yield Button("Raw", id="board_raw", classes="subtab_btn active_subtab", variant="primary")
                        yield Button("Rendered", id="board_rendered", classes="subtab_btn")
                    with Vertical(id="workboard_raw_panel", classes=""):
                        with Vertical(classes="workboard_container"):
                            yield TextArea("(no workboard exists)", id="workboard", read_only=True)
                    with Vertical(id="workboard_rendered_panel", classes="hidden"):
                        with Vertical(id="workboard_rendered_container", classes="workboard_container"):
                            if MarkdownViewer is not None:
                                yield MarkdownViewer("(no workboard exists)")
                            else:
                                yield Static(
                                    "MarkdownViewer unavailable in current Textual install.",
                                    id="workboard_rendered_fallback",
                                )

                with Vertical(id="panel_final", classes="hidden"):
                    yield Static("Final Output", id="title_final", classes="section_title")
                    with Horizontal(id="final_view_bar"):
                        yield Button("Raw", id="final_raw", classes="subtab_btn active_subtab", variant="primary")
                        yield Button("Rendered", id="final_rendered", classes="subtab_btn")
                    with Vertical(id="final_raw_panel"):
                        yield TextArea("", id="final_output", read_only=True)
                    with Vertical(id="final_rendered_panel", classes="hidden"):
                        with Vertical(id="final_rendered_container"):
                            if MarkdownViewer is not None:
                                yield MarkdownViewer("")
                            else:
                                yield Static("MarkdownViewer unavailable.", id="final_rendered_fallback")

                with Vertical(id="panel_webpages", classes="hidden"):
                    yield Static("Web Pages", id="title_webpages", classes="section_title")
                    yield DataTable(id="webpages_table")
        yield Footer()

    async def on_mount(self) -> None:
        workers_table = self.query_one("#workers_table", DataTable)
        workers_table.add_columns("Worker", "Status", "Events", "Seconds", "Timestamp")
        workers_table.cursor_type = "row"

        steps_table = self.query_one("#steps_table", DataTable)
        steps_table.add_columns("Time", "Subtask", "Tool", "Event", "Details")
        steps_table.cursor_type = "row"

        webpages_table = self.query_one("#webpages_table", DataTable)
        webpages_table.add_columns("Worker", "URL", "Description")
        webpages_table.cursor_type = "row"

        self.set_interval(1.0, self._refresh_workers)
        self.set_interval(1.0, self._refresh_selected_worker_steps)
        self.set_interval(1.0, self._refresh_workboard)
        self.set_interval(1.0, self._refresh_progress)
        self.set_interval(2.0, self._refresh_webpages)

        await self._start_orchestrator()
        self._set_active_tab("progress")
        self._set_board_view("raw")
        self._refresh_workers()
        self._refresh_workboard()

    async def on_unmount(self) -> None:
        if self.orchestrator is not None:
            await self.orchestrator.close()

    async def _start_orchestrator(self) -> None:
        try:
            if self.orchestrator is not None:
                await self.orchestrator.close()
                self.orchestrator = None
            load_dotenv()
            api_key = self._openrouter_key or os.getenv("OPENROUTER_API_KEY", "")
            model = ChatOpenAI(
                model=self._selected_model,
                openai_api_key=api_key,
                openai_api_base=os.getenv("OPENROUTER_BASE_URL"),
                temperature=0,
            )
            child_env = dict(os.environ)
            child_env["OPENROUTER_MODEL"] = self._selected_worker_model
            if api_key:
                child_env["OPENROUTER_API_KEY"] = api_key
            if self._serper_key:
                child_env["SERPER_API_KEY"] = self._serper_key
            # Prevent MCP server stderr logs from corrupting Textual rendering.
            child_env["MCP_QUIET_STDERR"] = "1"
            child_env.setdefault("FASTMCP_LOG_LEVEL", "ERROR")
            child_env.setdefault("FASTMCP_QUIET", "1")
            child_env["MAX_WORKERS"] = str(self._max_workers)
            self.orchestrator = OrchestratorAgent(model=model, env=child_env)
            await self.orchestrator.start()
            self._orchestrator_start_error = None
        except Exception as exc:
            self.orchestrator = None
            err_detail = (
                "Failed to start orchestrator.\n\n"
                f"{type(exc).__name__}: {exc}\n\n"
                f"{traceback.format_exc()}"
            )
            self._orchestrator_start_error = err_detail
            # Write error to file for debugging
            try:
                (ROOT / "logs" / "orchestrator_start_error.log").write_text(err_detail, encoding="utf-8")
            except Exception:
                pass

    def _save_env_key(self, key_name: str, key_value: str) -> None:
        """Persist a key=value to the .env file."""
        env_path = ROOT / ".env"
        try:
            if env_path.exists():
                lines = env_path.read_text().splitlines()
                found = False
                for i, line in enumerate(lines):
                    if line.startswith(f"{key_name}="):
                        lines[i] = f"{key_name}={key_value}"
                        found = True
                        break
                if not found:
                    lines.append(f"{key_name}={key_value}")
                env_path.write_text("\n".join(lines) + "\n")
            else:
                env_path.write_text(f"{key_name}={key_value}\n")
        except Exception:
            pass

    def action_refresh_workers(self) -> None:
        self._refresh_workers(force=True)

    def action_run_task(self) -> None:
        self._trigger_run_task()

    def action_copy_final(self) -> None:
        """Copy final output text to system clipboard."""
        text = self._final_last_text
        if not text:
            self.notify("No final output to copy.", severity="warning")
            return
        import subprocess
        try:
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
            self.notify("Final output copied to clipboard.")
        except Exception:
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode("utf-8"),
                    check=True,
                )
                self.notify("Final output copied to clipboard.")
            except Exception:
                self.notify("Failed to copy — no clipboard tool found.", severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run_task":
            self._trigger_run_task()
        elif event.button.id == "stop_task":
            self._stop_task()
        elif event.button.id == "clear_task":
            self.query_one("#task_input", TextArea).clear()
        elif event.button.id == "tab_progress":
            self._set_active_tab("progress")
        elif event.button.id == "tab_board":
            self._set_active_tab("board")
        elif event.button.id == "tab_steps":
            self._set_active_tab("steps")
        elif event.button.id == "tab_final":
            self._set_active_tab("final")
        elif event.button.id == "tab_webpages":
            self._set_active_tab("webpages")
            self._refresh_webpages()
        elif event.button.id == "board_raw":
            self._set_board_view("raw")
        elif event.button.id == "board_rendered":
            self._set_board_view("rendered")
        elif event.button.id == "final_raw":
            self._set_final_view("raw")
        elif event.button.id == "final_rendered":
            self._set_final_view("rendered")
        elif event.button.id == "steps_group_toggle":
            self._steps_group_enabled = not self._steps_group_enabled
            btn = self.query_one("#steps_group_toggle", Button)
            btn.label = f"Grouping: {'On' if self._steps_group_enabled else 'Off'}"
            btn.variant = "primary" if self._steps_group_enabled else "default"
            btn.set_class(self._steps_group_enabled, "active_subtab")
            if self._selected_worker_path is not None and self._selected_worker_path.exists():
                self._load_worker_steps(self._selected_worker_path)
        elif event.button.id == "steps_filter_clear":
            self._steps_filter_tool = ""
            self._steps_filter_subtask_id = ""
            try:
                self.query_one("#steps_filter_tool", Input).value = ""  # type: ignore[arg-type]
                self.query_one("#steps_filter_subtask", Input).value = ""  # type: ignore[arg-type]
            except Exception:
                pass
            if self._selected_worker_path is not None and self._selected_worker_path.exists():
                self._load_worker_steps(self._selected_worker_path)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "model_select" and event.value != Select.BLANK:
            self._selected_model = str(event.value)
            if not self._task_running:
                asyncio.create_task(self._start_orchestrator())
        elif event.select.id == "worker_model_select" and event.value != Select.BLANK:
            self._selected_worker_model = str(event.value)
            if not self._task_running:
                asyncio.create_task(self._start_orchestrator())
        elif event.select.id == "example_select":
            if event.value == Select.BLANK:
                return
            self._on_example_selected(int(event.value))

    def on_input_changed(self, event) -> None:  # Textual Input.Changed
        widget_id = getattr(getattr(event, "input", None), "id", None)
        if widget_id == "workers_count":
            return
        if widget_id == "openrouter_key_input":
            new_key = str(getattr(getattr(event, "input", None), "value", "") or "").strip()
            if new_key != self._openrouter_key:
                self._openrouter_key = new_key
                os.environ["OPENROUTER_API_KEY"] = new_key
                self._save_env_key("OPENROUTER_API_KEY", new_key)
                if not self._task_running:
                    asyncio.create_task(self._start_orchestrator())
            return
        if widget_id == "serper_key_input":
            new_key = str(getattr(getattr(event, "input", None), "value", "") or "").strip()
            if new_key != self._serper_key:
                self._serper_key = new_key
                os.environ["SERPER_API_KEY"] = new_key
                self._save_env_key("SERPER_API_KEY", new_key)
            return
        value = str(getattr(getattr(event, "input", None), "value", "") or "").strip()
        if widget_id == "steps_filter_tool":
            self._steps_filter_tool = value
        elif widget_id == "steps_filter_subtask":
            self._steps_filter_subtask_id = value
        else:
            return
        if self._selected_worker_path is not None and self._selected_worker_path.exists():
            self._load_worker_steps(self._selected_worker_path)

    @staticmethod
    def _load_example_tasks() -> list[dict]:
        """Load example tasks from example_task.json."""
        example_path = ROOT / "example_task.json"
        try:
            with example_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return [data]
        except Exception:
            pass
        return []

    @staticmethod
    def _load_example_options() -> list[tuple[str, str]]:
        """Return Select options from example_task.json."""
        example_path = ROOT / "example_task.json"
        try:
            with example_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            tasks = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
        except Exception:
            tasks = []
        return [(t.get("task_name", f"Example {i+1}"), str(i)) for i, t in enumerate(tasks)]

    def _on_example_selected(self, index: int) -> None:
        """Load the selected example task into the task input."""
        try:
            tasks = self._load_example_tasks()
            if index < len(tasks):
                text = tasks[index].get("input", "")
                ta = self.query_one("#task_input", TextArea)
                ta.text = text
        except Exception as e:
            self.notify(f"Failed to load example: {e}", severity="error")

    def _trigger_run_task(self) -> None:
        if self._task_running:
            return

        task_input = self.query_one("#task_input", TextArea)
        task = task_input.text.strip()
        if not task:
            output = self.query_one("#final_output", TextArea)
            output.text = "Task input is empty."
            self._final_last_text = output.text
            return

        # Read desired worker count from input.
        try:
            raw = self.query_one("#workers_count", Input).value.strip()
            new_max = max(1, min(int(raw), 100))
        except (ValueError, Exception):
            new_max = self._max_workers

        if new_max != self._max_workers:
            self._max_workers = new_max
            # Restart orchestrator with updated MAX_WORKERS env.
            self._running_task_handle = asyncio.create_task(self._restart_and_run(task))
            return

        if self.orchestrator is None:
            err = self._orchestrator_start_error or "Orchestrator is not ready."
            output = self.query_one("#final_output", TextArea)
            output.text = err
            self._final_last_text = err
            self._update_rendered_final(self._final_last_text)
            self._set_active_tab("final")
            return

        self._running_task_handle = asyncio.create_task(self._run_task(task))

    def _stop_task(self) -> None:
        if not self._task_running:
            return
        # Cancel the running asyncio task
        if self._running_task_handle is not None and not self._running_task_handle.done():
            self._running_task_handle.cancel()
        # Kill the orchestrator MCP connection to stop workers
        if self.orchestrator is not None:
            asyncio.create_task(self._force_stop())

    async def _force_stop(self) -> None:
        """Close and rebuild orchestrator to kill all worker processes."""
        try:
            if self.orchestrator is not None:
                await self.orchestrator.close()
                self.orchestrator = None
        except Exception:
            pass
        output = self.query_one("#final_output", TextArea)
        output.text = "Task stopped by user."
        self._final_last_text = "Task stopped by user."
        self._update_rendered_final(self._final_last_text)
        self._task_running = False
        self._running_task_handle = None
        run_btn = self.query_one("#run_task", Button)
        run_btn.disabled = False
        run_btn.label = "Run Task"
        stop_btn = self.query_one("#stop_task", Button)
        stop_btn.disabled = True
        # Restart orchestrator so it's ready for the next task
        await self._start_orchestrator()

    async def _restart_and_run(self, task: str) -> None:
        await self._start_orchestrator()
        if self.orchestrator is None:
            err = self._orchestrator_start_error or "Failed to restart orchestrator."
            output = self.query_one("#final_output", TextArea)
            output.text = err
            self._final_last_text = err
            self._update_rendered_final(self._final_last_text)
            self._set_active_tab("final")
            self._running_task_handle = None
            return
        await self._run_task(task)

    def _create_orchestrator_trajectory(self, task: str) -> Path | None:
        """Create an orchestrator trajectory JSONL file with a live header."""
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            filename = f"orchestrator-{ts}.jsonl"
            path = LOGS_DIR / filename
            header = {
                "type": "header",
                "worker_index": -1,
                "subtask": task,
                "status": "live",
                "result_preview": "",
                "time_taken_seconds": 0.0,
                "total_events": 0,
                "ts": ts,
            }
            with path.open("w", encoding="utf-8") as f:
                f.write(json.dumps(header, ensure_ascii=False) + "\n")
            return path
        except Exception:
            return None

    def _append_orchestrator_event(self, path: Path, event: dict) -> None:
        """Append one JSON event to the orchestrator trajectory file."""
        try:
            record = {k: v for k, v in event.items() if k != "content_full"}
            line = json.dumps(record, ensure_ascii=False)
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _finalize_orchestrator_trajectory(
        self,
        path: Path,
        task: str,
        events: list[dict],
        result: str,
        elapsed: float,
        status: str = "finished",
    ) -> None:
        """Rewrite the orchestrator trajectory file with final header."""
        try:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            header = {
                "type": "header",
                "worker_index": -1,
                "subtask": task,
                "status": status,
                "result_preview": result[:500],
                "time_taken_seconds": elapsed,
                "total_events": len(events),
                "ts": ts,
            }
            with path.open("w", encoding="utf-8") as f:
                f.write(json.dumps(header, ensure_ascii=False) + "\n")
                for ev in events:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _parse_stream_chunk(self, chunk: dict) -> list[dict]:
        """Parse a LangChain astream(stream_mode='updates') chunk into trajectory events."""
        events: list[dict] = []
        ts = datetime.now(timezone.utc).isoformat()
        for node_name, node_data in chunk.items():
            messages = None
            if isinstance(node_data, dict):
                messages = node_data.get("messages")
            if not isinstance(messages, (list, tuple)):
                continue
            for msg in messages:
                msg_type = getattr(msg, "type", None)
                if msg_type == "ai":
                    content = getattr(msg, "content", "")
                    tool_calls = getattr(msg, "tool_calls", None) or []
                    if tool_calls:
                        for tc in tool_calls:
                            tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                            tc_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                            tc_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
                            events.append({
                                "ts": ts,
                                "event": "orchestrator_tool_call",
                                "node": node_name,
                                "tool_name": str(tc_name),
                                "tool_call_id": str(tc_id),
                                "args_preview": self._short(json.dumps(tc_args, ensure_ascii=False, default=str), 500),
                            })
                    if isinstance(content, str) and content.strip():
                        events.append({
                            "ts": ts,
                            "event": "orchestrator_message",
                            "node": node_name,
                            "content_preview": self._short(content, 500),
                            "content_full": content,
                        })
                    elif isinstance(content, list):
                        text_parts = []
                        for block in content:
                            if isinstance(block, str):
                                text_parts.append(block)
                            elif isinstance(block, dict) and block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                        text = "\n".join(p for p in text_parts if p.strip())
                        if text.strip():
                            events.append({
                                "ts": ts,
                                "event": "orchestrator_message",
                                "node": node_name,
                                "content_preview": self._short(text, 500),
                                "content_full": text,
                            })
                elif msg_type == "tool":
                    tool_name = getattr(msg, "name", "")
                    tool_content = getattr(msg, "content", "")
                    tool_call_id = getattr(msg, "tool_call_id", "")
                    content_str = tool_content if isinstance(tool_content, str) else json.dumps(tool_content, ensure_ascii=False, default=str)
                    events.append({
                        "ts": ts,
                        "event": "orchestrator_tool_result",
                        "node": node_name,
                        "tool_name": str(tool_name),
                        "tool_call_id": str(tool_call_id),
                        "result_preview": self._short(content_str, 500),
                    })
        return events

    async def _run_task(self, task: str) -> None:
        self._task_running = True
        run_btn = self.query_one("#run_task", Button)
        run_btn.disabled = True
        run_btn.label = "Task Running"
        stop_btn = self.query_one("#stop_task", Button)
        stop_btn.disabled = False
        output = self.query_one("#final_output", TextArea)
        output.text = "Task is running. Final output will appear here when execution completes."
        self._final_last_text = ""
        self._set_active_tab("progress")

        if self.orchestrator is None:
            err_text = self._orchestrator_start_error or "Run failed: orchestrator is not available."
            output.text = err_text
            self._final_last_text = err_text
            self._update_rendered_final(self._final_last_text)
            self._set_active_tab("final")
            self._task_running = False
            run_btn.disabled = False
            run_btn.label = "Run Task"
            stop_btn.disabled = True
            return

        try:
            self._session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            self._session_started_at = time.time()
            self._prepare_new_session_board(self._session_id)
            self._session_file_baseline = {
                p.name
                for p in LOGS_DIR.glob("worker-*.jsonl")
                if p.name.startswith("worker-")
            }
            self._session_file_baseline.update(
                p.name for p in LOGS_DIR.glob("orchestrator-*.jsonl")
            )
            self._current_session_files = []
            self._session_worker_order = []
            self._selected_worker_path = None
            self._selected_worker_mtime = -1.0
            self.query_one("#steps_worker_row", Static).update("(no worker selected)")
            self.query_one("#steps_subtask", Static).update("(select a worker to view its subtask)")
            self.query_one("#steps_table", DataTable).clear(columns=False)

            # Create orchestrator trajectory file
            orch_traj_path = self._create_orchestrator_trajectory(task)
            self._orchestrator_traj_path = orch_traj_path
            orch_events: list[dict] = []
            start_ts = datetime.now(timezone.utc).isoformat()
            start_event = {"ts": start_ts, "event": "orchestrator_start", "task": task}
            orch_events.append(start_event)
            if orch_traj_path:
                self._append_orchestrator_event(orch_traj_path, start_event)

            # Use streaming to capture orchestrator trajectory
            final = ""
            last_ai_content = ""
            async for chunk in self.orchestrator.stream(task):
                parsed = self._parse_stream_chunk(chunk)
                for ev in parsed:
                    orch_events.append(ev)
                    if orch_traj_path:
                        self._append_orchestrator_event(orch_traj_path, ev)
                    # Track last AI message for final output
                    if ev.get("event") == "orchestrator_message":
                        last_ai_content = ev.get("content_full") or ev.get("content_preview", "")

            # Extract final output from the last AI message
            final = last_ai_content.strip()

            elapsed = round(time.time() - self._session_started_at, 2)
            end_event = {"ts": datetime.now(timezone.utc).isoformat(), "event": "orchestrator_end", "status": "ok", "duration_seconds": elapsed}
            orch_events.append(end_event)
            if orch_traj_path:
                self._finalize_orchestrator_trajectory(orch_traj_path, task, orch_events, final, elapsed, status="finished")

            output.text = final or "(no output)"
            self._final_last_text = final or "(no output)"
            self._update_rendered_final(self._final_last_text)
            self._set_active_tab("final")
            self._last_session_id = self._session_id
        except asyncio.CancelledError:
            # Stopped by user — _force_stop handles UI reset
            return
        except Exception as exc:
            err_text = f"Run failed: {exc}\n\n{traceback.format_exc()}"
            elapsed = round(time.time() - self._session_started_at, 2)
            end_event = {"ts": datetime.now(timezone.utc).isoformat(), "event": "orchestrator_end", "status": "failed", "error": str(exc), "duration_seconds": elapsed}
            if self._orchestrator_traj_path:
                self._append_orchestrator_event(self._orchestrator_traj_path, end_event)
                self._finalize_orchestrator_trajectory(self._orchestrator_traj_path, task, [], err_text, elapsed, status="failed")
            output.text = err_text
            self._final_last_text = err_text
            self._update_rendered_final(self._final_last_text)
            self._last_session_id = self._session_id
        finally:
            self._task_running = False
            self._running_task_handle = None
            run_btn.disabled = False
            run_btn.label = "Run Task"
            stop_btn.disabled = True

    def _refresh_workers(self, force: bool = False) -> None:
        worker_files = sorted(
            LOGS_DIR.glob("worker-*.jsonl"),
            key=lambda p: p.stat().st_mtime,
        )
        orch_files = sorted(
            LOGS_DIR.glob("orchestrator-*.jsonl"),
            key=lambda p: p.stat().st_mtime,
        )
        all_files = worker_files + orch_files
        self._worker_files = all_files

        if self._session_id is None:
            files_raw: list[Path] = []
        else:
            files_raw = [
                p
                for p in all_files
                if p.name not in self._session_file_baseline
                and p.stat().st_mtime >= (self._session_started_at - 1.0)
            ]

        by_name = {p.name: p for p in files_raw}
        known = set(self._session_worker_order)
        new_names = [p.name for p in files_raw if p.name not in known]
        for name in new_names:
            self._session_worker_order.append(name)
        self._session_worker_order = [n for n in self._session_worker_order if n in by_name]
        # Sort orchestrator files first, then workers
        self._session_worker_order.sort(key=lambda n: (0 if n.startswith("orchestrator-") else 1, n))
        files = [by_name[n] for n in self._session_worker_order]

        file_signature = [
            (p.name, int(p.stat().st_mtime_ns))
            for p in files
        ]
        run_state_changed = self._last_task_running_state != self._task_running
        if (
            not force
            and not self._task_running
            and not run_state_changed
            and file_signature == self._last_session_file_signature
        ):
            return
        self._current_session_files = files
        self._last_task_running_state = self._task_running
        self._last_session_file_signature = file_signature
        self._worker_row_key_to_path.clear()

        table = self.query_one("#workers_table", DataTable)
        table.clear(columns=False)
        selected_name = (
            self._selected_worker_path.name
            if self._selected_worker_path is not None
            else None
        )
        selected_row_index: int | None = None

        now = time.time()
        for idx, path in enumerate(files):
            header = self._read_header(path)
            worker_label, timestamp = self._worker_and_ts_from_file(path)
            header_status = str(header.get("status", "")).strip().lower()
            if header_status in {"live", "finished", "failed"}:
                worker_status = header_status
            elif self._task_running and (now - path.stat().st_mtime) < 2.0:
                worker_status = "live"
            else:
                worker_status = "finished"
            if worker_status == "live":
                events = self._live_event_count(path)
                seconds = self._live_elapsed_seconds(header, path, now)
            else:
                events = header.get("total_events", "?")
                seconds = header.get("time_taken_seconds", "?")
            is_orchestrator = path.name.startswith("orchestrator-")
            if worker_status == "live":
                status_cell: str | Text = Text("running", style="bold #61d47a")
            elif worker_status == "finished":
                status_cell = Text("finished", style="bold #ef6b73")
            else:
                status_cell = Text(worker_status, style="bold #ef6b73")
            if is_orchestrator:
                worker_label = Text(worker_label, style="bold #f2c57a")
            subtask = str(header.get("subtask", ""))
            subtask = self._short(subtask, 70)
            row_key = path.name
            added_key = table.add_row(
                worker_label,
                status_cell,
                str(events),
                str(seconds),
                timestamp,
                key=row_key,
            )
            self._worker_row_key_to_path[added_key] = path
            if selected_name is not None and path.name == selected_name:
                selected_row_index = idx

        # Keep highlight on previously selected worker after table refresh.
        if selected_row_index is not None:
            try:
                table.move_cursor(row=selected_row_index, column=0, animate=False)
            except Exception:
                try:
                    table.cursor_coordinate = (selected_row_index, 0)
                except Exception:
                    pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table = event.data_table
        if table.id != "workers_table":
            return

        path = self._worker_row_key_to_path.get(event.row_key)
        if path is None:
            return

        self._selected_worker_path = path
        self._selected_worker_mtime = -1.0
        self.query_one("#steps_worker_row", Static).update(self._format_worker_row(path))
        header = self._read_header(path)
        subtask = str(header.get("subtask", "")).strip() or "(subtask unavailable)"
        self.query_one("#steps_subtask", Static).update(subtask)
        self._set_active_tab("steps")
        self._load_worker_steps(path)

    def _set_active_tab(self, tab: str) -> None:
        if tab not in {"progress", "board", "steps", "final", "webpages"}:
            return
        self._active_tab = tab

        panel_progress = self.query_one("#panel_progress", Vertical)
        panel_steps = self.query_one("#panel_steps", Vertical)
        panel_board = self.query_one("#panel_board", Vertical)
        panel_final = self.query_one("#panel_final", Vertical)
        panel_webpages = self.query_one("#panel_webpages", Vertical)

        tab_progress = self.query_one("#tab_progress", Button)
        tab_board = self.query_one("#tab_board", Button)
        tab_steps = self.query_one("#tab_steps", Button)
        tab_final = self.query_one("#tab_final", Button)
        tab_webpages = self.query_one("#tab_webpages", Button)

        panel_progress.set_class(tab != "progress", "hidden")
        panel_steps.set_class(tab != "steps", "hidden")
        panel_board.set_class(tab != "board", "hidden")
        panel_final.set_class(tab != "final", "hidden")
        panel_webpages.set_class(tab != "webpages", "hidden")

        tab_progress.set_class(tab == "progress", "active_tab")
        tab_board.set_class(tab == "board", "active_tab")
        tab_steps.set_class(tab == "steps", "active_tab")
        tab_final.set_class(tab == "final", "active_tab")
        tab_webpages.set_class(tab == "webpages", "active_tab")

    def _set_board_view(self, mode: str) -> None:
        if mode not in {"raw", "rendered"}:
            return
        self._board_view = mode
        raw_panel = self.query_one("#workboard_raw_panel", Vertical)
        rendered_panel = self.query_one("#workboard_rendered_panel", Vertical)
        raw_btn = self.query_one("#board_raw", Button)
        rendered_btn = self.query_one("#board_rendered", Button)

        raw_panel.set_class(mode != "raw", "hidden")
        rendered_panel.set_class(mode != "rendered", "hidden")
        raw_btn.set_class(mode == "raw", "active_subtab")
        rendered_btn.set_class(mode == "rendered", "active_subtab")
        raw_btn.variant = "primary" if mode == "raw" else "default"
        rendered_btn.variant = "primary" if mode == "rendered" else "default"
        if mode == "rendered":
            seed = self._workboard_last_text or "(no workboard exists)"
            self._update_rendered_workboard(seed)

    def _set_final_view(self, mode: str) -> None:
        if mode not in {"raw", "rendered"}:
            return
        self._final_view = mode
        raw_panel = self.query_one("#final_raw_panel", Vertical)
        rendered_panel = self.query_one("#final_rendered_panel", Vertical)
        raw_btn = self.query_one("#final_raw", Button)
        rendered_btn = self.query_one("#final_rendered", Button)

        raw_panel.set_class(mode != "raw", "hidden")
        rendered_panel.set_class(mode != "rendered", "hidden")
        raw_btn.set_class(mode == "raw", "active_subtab")
        rendered_btn.set_class(mode == "rendered", "active_subtab")
        raw_btn.variant = "primary" if mode == "raw" else "default"
        rendered_btn.variant = "primary" if mode == "rendered" else "default"
        if mode == "rendered":
            self._update_rendered_final(self._final_last_text)

    def _update_rendered_final(self, text: str) -> None:
        if MarkdownViewer is None:
            try:
                fallback = self.query_one("#final_rendered_fallback", Static)
                fallback.update(text)
            except Exception:
                pass
            return
        container = self.query_one("#final_rendered_container", Vertical)
        try:
            for child in list(container.children):
                child.remove()
        except Exception:
            pass
        container.mount(MarkdownViewer(self._escape_xml_tags(text)))

    def _refresh_selected_worker_steps(self) -> None:
        if self._selected_worker_path is None or not self._selected_worker_path.exists():
            return
        mtime = self._selected_worker_path.stat().st_mtime
        if mtime <= self._selected_worker_mtime:
            return
        self._selected_worker_mtime = mtime
        self.query_one("#steps_worker_row", Static).update(
            self._format_worker_row(self._selected_worker_path)
        )
        self._load_worker_steps(self._selected_worker_path)

    def _load_worker_steps(self, path: Path) -> None:
        table = self.query_one("#steps_table", DataTable)
        table.clear(columns=False)

        row_count = 0
        last_group_key: tuple[str, str] | None = None
        for event in self._read_events(path):
            ts = self._event_time(event)
            name = str(event.get("event", ""))
            tool_name = self._event_tool_name(event)
            subtask_id = self._event_subtask_id(event)
            if self._steps_filter_tool and self._steps_filter_tool.lower() not in tool_name.lower():
                continue
            if self._steps_filter_subtask_id and self._steps_filter_subtask_id.lower() not in subtask_id.lower():
                continue
            if self._steps_group_enabled:
                group_key = (subtask_id or "-", tool_name or f"event:{name}")
                if group_key != last_group_key:
                    group_label = f"subtask={group_key[0]} | tool={group_key[1]}"
                    table.add_row("", "", "", "group", group_label)
                    row_count += 1
                    last_group_key = group_key
            detail = self._event_detail(event)
            table.add_row(ts, subtask_id or "-", tool_name or "-", name, detail)
            row_count += 1

        # Auto-follow newest events: keep viewport pinned to the last row.
        if row_count > 0:
            last_row = row_count - 1
            try:
                table.move_cursor(row=last_row, column=0, animate=False)
            except Exception:
                try:
                    table.cursor_coordinate = (last_row, 0)
                except Exception:
                    pass

    def _refresh_workboard(self) -> None:
        board_widget = self.query_one("#workboard", TextArea)
        if self._session_id is None and not self._task_running:
            text = "(no active task session yet)"
            if text != self._workboard_last_text:
                self._workboard_last_text = text
                board_widget.text = text
                self._update_rendered_workboard(text)
            return

        board_path = get_board_path()
        if not board_path.exists():
            text = "(no workboard exists)"
        else:
            try:
                text = board_path.read_text(encoding="utf-8")
                # Persist a session-specific live copy for later inspection.
                if self._session_board_path is not None:
                    self._session_board_path.write_text(text, encoding="utf-8")
            except Exception as exc:
                text = f"(failed to read workboard: {exc})"

        if text != self._workboard_last_text:
            self._workboard_last_text = text
            board_widget.load_text(text)
            self._update_rendered_workboard(text)

    def _refresh_progress(self) -> None:
        """Update the Progress panel with a concise workflow summary."""
        files = self._current_session_files
        widget = self.query_one("#progress_workflow", TextArea)

        # Separate orchestrator and worker files
        orch_files = [p for p in files if p.name.startswith("orchestrator-")]
        worker_files = [p for p in files if p.name.startswith("worker-")]
        total = len(worker_files)

        if total == 0 and not orch_files and not self._task_running:
            widget.text = ""
            return

        lines: list[str] = []

        # Orchestrator status
        for path in orch_files:
            header = self._read_header(path)
            status = str(header.get("status", "")).strip().lower()
            task_preview = self._short(str(header.get("subtask", "")).strip(), 80)
            if status == "live":
                event_count = self._live_event_count(path)
                now = time.time()
                secs = self._live_elapsed_seconds(header, path, now)
                lines.append(f"  ...   orchestrator: {task_preview}  ({secs}s, {event_count} events)")
            elif status == "finished":
                secs = header.get("time_taken_seconds", "?")
                lines.append(f"  done  orchestrator: {task_preview}  ({secs}s)")
            elif status == "failed":
                lines.append(f"  FAIL  orchestrator: {task_preview}")
            else:
                lines.append(f"  ...   orchestrator: {task_preview}")

        # Worker status
        finished = 0
        for idx, path in enumerate(worker_files):
            header = self._read_header(path)
            subtask = self._short(str(header.get("subtask", "")).strip(), 90)
            status = str(header.get("status", "")).strip().lower()
            if status == "finished":
                finished += 1
                secs = header.get("time_taken_seconds", "?")
                lines.append(f"  done  t{idx+1}: {subtask}  ({secs}s)")
            elif status == "failed":
                finished += 1
                lines.append(f"  FAIL  t{idx+1}: {subtask}")
            else:
                lines.append(f"  ...   t{idx+1}: {subtask}")

        header_line = f"[{finished}/{total}]" if total > 0 else "[0/0]"
        if self._task_running and finished >= total and total > 0:
            header_line += " synthesizing..."
        elif not self._task_running and total > 0:
            header_line += " done"

        widget.text = header_line + "\n" + "\n".join(lines)

    _RE_URL = re.compile(r'https?://[^\s"\'\\,\)>]+')

    def _refresh_webpages(self) -> None:
        """Scan current session worker logs for URLs surfaced by web/search tool calls."""
        if self._active_tab != "webpages":
            return
        table = self.query_one("#webpages_table", DataTable)
        files = self._current_session_files
        rows: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for idx, path in enumerate(files):
            worker_label = f"t{idx + 1}"
            try:
                for line in path.read_text(errors="replace").splitlines():
                    try:
                        entry = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if entry.get("event") != "tool_call_end":
                        continue
                    tool_name = str(entry.get("tool_name", ""))
                    if tool_name not in {"bash_tool", "view"}:
                        continue
                    args_raw = entry.get("args_preview", "")
                    result_raw = str(entry.get("result_preview", "") or "")
                    try:
                        args = json.loads(args_raw)
                    except (json.JSONDecodeError, ValueError):
                        args = {}

                    description = str(args.get("description", "")).strip()
                    texts: list[str] = []
                    command = str(args.get("command", "") or "")
                    if command:
                        texts.append(command)
                    if result_raw:
                        texts.append(result_raw)
                    # `view` may carry the URL under `path` in some tool variants.
                    path_value = str(args.get("path", "") or "")
                    if path_value:
                        texts.append(path_value)

                    found_any = False
                    for source_text in texts:
                        for url in self._RE_URL.findall(source_text):
                            cleaned = url.rstrip(".,;)]}")
                            if not cleaned or cleaned in seen:
                                continue
                            seen.add(cleaned)
                            rows.append((worker_label, cleaned, description[:80] or tool_name))
                            found_any = True
                    if found_any:
                        continue

                    # Fallback: parse SerpAPI-style result lines like `https://...\\n   snippet`.
                    for match in re.finditer(r"https?://[^\s\\]+", result_raw):
                        url = match.group(0).rstrip(".,;)]}")
                        if url in seen:
                            continue
                        seen.add(url)
                        rows.append((worker_label, url, description[:80] or tool_name))
            except Exception:
                continue
        table.clear(columns=False)
        for row in rows:
            table.add_row(*row)

    @staticmethod
    def _escape_xml_tags(text: str) -> str:
        """Escape XML-style tags so MarkdownViewer doesn't swallow them."""
        return re.sub(r"<(/?[A-Za-z0-9_:-]+)>", r"`<\1>`", text)

    def _update_rendered_workboard(self, text: str) -> None:
        if MarkdownViewer is None:
            fallback = self.query_one("#workboard_rendered_fallback", Static)
            fallback.update(text)
            return
        container = self.query_one("#workboard_rendered_container", Vertical)
        try:
            for child in list(container.children):
                child.remove()
        except Exception:
            pass
        container.mount(MarkdownViewer(self._escape_xml_tags(text)))

    def _prepare_new_session_board(self, new_session_id: str) -> None:
        """Archive previous board (if any) and start a fresh board for this session."""
        board_path = get_board_path()
        board_path.parent.mkdir(parents=True, exist_ok=True)

        session_board = board_path.parent / f".workboard-{new_session_id}.md"
        self._session_board_path = session_board

        if board_path.exists():
            archive_session = self._last_session_id or datetime.now(timezone.utc).strftime(
                "%Y%m%dT%H%M%SZ"
            )
            archived = board_path.parent / f".workboard-{archive_session}.md"
            i = 1
            while archived.exists():
                archived = board_path.parent / f".workboard-{archive_session}-{i}.md"
                i += 1
            try:
                board_path.rename(archived)
            except Exception:
                # Fallback: if rename fails, try explicit cleanup to avoid stale board reuse.
                cleanup_board()

        # Fresh board file for the new session (workers will overwrite with orchestrator content).
        initial = f"# Task Board ({new_session_id})\n\n## Subtasks\n\n## Shared Context\n\n## Results\n"
        board_path.write_text(initial, encoding="utf-8")
        session_board.write_text(initial, encoding="utf-8")

    @staticmethod
    def _worker_and_ts_from_file(path: Path) -> tuple[str, str]:
        # orchestrator-20260217T143202Z.jsonl
        m_orch = re.match(r"orchestrator-([^.]+)\.jsonl$", path.name)
        if m_orch:
            return "orchestrator", m_orch.group(1)
        # worker-3-20260217T143202Z.jsonl
        m = re.match(r"worker-(\d+)-([^.]+)\.jsonl$", path.name)
        if not m:
            return path.stem, "-"
        worker_idx = m.group(1)
        ts = m.group(2)
        return f"worker-{worker_idx}", ts

    @staticmethod
    def _read_header(path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as f:
                first = f.readline().strip()
            if not first:
                return {}
            data = json.loads(first)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _live_elapsed_seconds(header: dict[str, Any], path: Path, now_ts: float) -> str:
        """Best-effort elapsed seconds for a live worker."""
        raw = str(header.get("ts", "")).strip()
        if raw:
            try:
                started = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                elapsed = max(0.0, now_ts - started.timestamp())
                return f"{elapsed:.1f}"
            except Exception:
                pass
        try:
            elapsed = max(0.0, now_ts - path.stat().st_mtime)
            return f"{elapsed:.1f}"
        except Exception:
            return "?"

    @staticmethod
    def _live_event_count(path: Path) -> int | str:
        """Count currently written trajectory events (excluding header line)."""
        try:
            with path.open("r", encoding="utf-8") as f:
                lines = sum(1 for line in f if line.strip())
            return max(0, lines - 1)
        except Exception:
            return "?"

    def _format_worker_row(self, path: Path) -> Text:
        """Format worker summary matching the workers list row fields."""
        header = self._read_header(path)
        now = time.time()
        worker_label, timestamp = self._worker_and_ts_from_file(path)
        header_status = str(header.get("status", "")).strip().lower()
        if header_status in {"live", "finished", "failed"}:
            worker_status = header_status
        elif self._task_running and (now - path.stat().st_mtime) < 2.0:
            worker_status = "live"
        else:
            worker_status = "finished"
        status_label = "running" if worker_status == "live" else worker_status

        if worker_status == "live":
            events = self._live_event_count(path)
            seconds = self._live_elapsed_seconds(header, path, now)
        else:
            events = header.get("total_events", "?")
            seconds = header.get("time_taken_seconds", "?")

        status_style = "#61d47a" if status_label == "running" else "#ef6b73"
        return Text.assemble(
            ("Worker: ", "bold #9ec7ff"),
            (worker_label, "#d6e4f4"),
            (" | ", "#9aa4b2"),
            ("Status: ", "bold #9ec7ff"),
            (status_label, f"bold {status_style}"),
            (" | ", "#9aa4b2"),
            ("Events: ", "bold #9ec7ff"),
            (str(events), "#d6e4f4"),
            (" | ", "#9aa4b2"),
            ("Seconds: ", "bold #9ec7ff"),
            (str(seconds), "#d6e4f4"),
            (" | ", "#9aa4b2"),
            ("Timestamp: ", "bold #9ec7ff"),
            (timestamp, "#d6e4f4"),
        )

    @staticmethod
    def _read_events(path: Path) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(record, dict) and record.get("type") != "header":
                        events.append(record)
        except Exception:
            return []
        return events

    @staticmethod
    def _event_time(event: dict[str, Any]) -> str:
        ts = str(event.get("ts", ""))
        if "T" in ts and len(ts) >= 19:
            return ts[11:19]
        return ts[:8]

    @classmethod
    def _event_detail(cls, event: dict[str, Any]) -> str:
        name = str(event.get("event", ""))
        if name == "run_one_skill_loop_start":
            return f"skill={event.get('skill_name', '?')} task={cls._short(str(event.get('user_text', '')), 80)}"
        if name == "run_one_skill_loop_round_plan":
            plan = event.get("plan", {})
            if isinstance(plan, dict):
                ops = plan.get("ops", [])
                if isinstance(ops, list):
                    op_types = [str(o.get("type", "?")) for o in ops if isinstance(o, dict)]
                    return f"round={event.get('round')} ops={op_types}"
                if plan.get("final"):
                    return cls._short(f"final={plan.get('final')}", 120)
            return cls._short(str(plan), 120)
        if name == "execute_skill_plan_output":
            return cls._short(str(event.get("result", "")), 140)
        if name == "run_one_skill_loop_end":
            return cls._short(f"mode={event.get('mode')} result={event.get('result', '')}", 140)
        if name == "route_skill_output":
            decision = event.get("decision", {})
            return cls._short(str(decision), 140)
        if name == "worker_start":
            return cls._short(f"subtask={event.get('subtask', '')}", 140)
        if name == "worker_attempt_start":
            return f"attempt={event.get('attempt')} subtask_id={event.get('subtask_id')}"
        if name == "worker_prompt_built":
            return cls._short(f"subtask_id={event.get('subtask_id')} prompt={event.get('prompt_preview', '')}", 140)
        if name == "agent_tools_loaded":
            return cls._short(f"tools={event.get('tool_names', [])}", 140)
        if name == "agent_run_start":
            return f"message_count={event.get('message_count')}"
        if name == "agent_run_end":
            return f"result_type={event.get('result_type')}"
        if name == "tool_call_start":
            return cls._short(f"{event.get('tool_name')} args={event.get('args_preview', '')}", 140)
        if name == "tool_call_end":
            return cls._short(
                f"{event.get('tool_name')} {event.get('duration_ms')}ms result={event.get('result_preview', '')}",
                140,
            )
        if name == "tool_call_error":
            return cls._short(
                f"{event.get('tool_name')} ERR {event.get('duration_ms')}ms error={event.get('error', '')}",
                140,
            )
        if name == "workboard_snapshot_read":
            return f"bytes={event.get('bytes')}"
        if name == "workboard_checkbox_update":
            return f"item={event.get('item')} checked"
        if name == "workboard_result_append":
            return cls._short(f"item={event.get('item')} summary={event.get('summary', '')}", 140)
        if name == "worker_agent_invoke_start":
            return f"subtask_id={event.get('subtask_id')}"
        if name == "worker_agent_invoke_end":
            return cls._short(f"subtask_id={event.get('subtask_id')} result={event.get('result_preview', '')}", 140)
        if name == "worker_attempt_error":
            return cls._short(f"attempt={event.get('attempt')} error={event.get('error', '')}", 140)
        if name == "worker_end":
            return cls._short(f"status={event.get('status')} sec={event.get('duration_seconds')}", 140)
        # Orchestrator events
        if name == "orchestrator_start":
            return cls._short(f"task={event.get('task', '')}", 140)
        if name == "orchestrator_message":
            return cls._short(f"[{event.get('node', '')}] {event.get('content_preview', '')}", 140)
        if name == "orchestrator_tool_call":
            return cls._short(f"[{event.get('node', '')}] {event.get('tool_name', '')} args={event.get('args_preview', '')}", 140)
        if name == "orchestrator_tool_result":
            return cls._short(f"[{event.get('node', '')}] {event.get('tool_name', '')} result={event.get('result_preview', '')}", 140)
        if name == "orchestrator_end":
            return cls._short(f"status={event.get('status')} sec={event.get('duration_seconds')}", 140)

        # Generic fallback: include compact JSON without very large fields.
        compact = {
            k: v
            for k, v in event.items()
            if k not in {"session_id", "messages", "result", "output", "user_text"}
        }
        return cls._short(json.dumps(compact, ensure_ascii=False), 140)

    @staticmethod
    def _event_tool_name(event: dict[str, Any]) -> str:
        return str(event.get("tool_name") or "").strip()

    @staticmethod
    def _event_subtask_id(event: dict[str, Any]) -> str:
        sid = str(event.get("subtask_id") or "").strip()
        if sid:
            return sid
        # For orchestrator events, use node name as a pseudo-subtask-id
        node = str(event.get("node") or "").strip()
        return node

    @staticmethod
    def _short(text: str, max_len: int = 120) -> str:
        one_line = text.replace("\n", " ").strip()
        if len(one_line) <= max_len:
            return one_line
        return one_line[: max_len - 3] + "..."


def main() -> None:
    Web2BigTable().run()


if __name__ == "__main__":
    main()
