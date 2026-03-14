"""Shared utilities for WideSearch eval pipeline.

Provides:
- OpenRouter LLM call helpers (Gemini Flash, GPT-5.1)
- Markdown table parsing / CSV comparison
- WideSearch preprocessing functions (norm_str, extract_number, url_normalize)
- Trajectory parsing
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
EVAL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVAL_DIR.parent
GOLD_DIR = EVAL_DIR / "gold"
OUTPUTS_DIR = EVAL_DIR / "outputs"
REPORTS_DIR = EVAL_DIR / "reports"
LOGS_DIR = PROJECT_ROOT / "logs"
WIDESEARCH_JSONL = EVAL_DIR / "widesearch.jsonl"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Model IDs via OpenRouter
MODEL_GEMINI_FLASH = "google/gemini-3-flash-preview"
MODEL_GPT51 = "openai/gpt-5.1"


# ---------------------------------------------------------------------------
# OpenRouter LLM helpers
# ---------------------------------------------------------------------------

def call_openrouter(
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    timeout: float = 120.0,
    retries: int = 3,
) -> str:
    """Call an OpenRouter model and return the assistant text."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/memento-ai",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as exc:
            last_err = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"OpenRouter call failed after {retries} attempts: {last_err}")


def call_gemini_flash(prompt: str, *, system: str = "") -> str:
    """Convenience wrapper for Gemini Flash calls."""
    msgs: list[dict[str, str]] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    return call_openrouter(MODEL_GEMINI_FLASH, msgs, max_tokens=8192)


def call_gpt51_judge(prompt: str, *, system: str = "") -> str:
    """Convenience wrapper for GPT-5.1 LLM judge calls."""
    msgs: list[dict[str, str]] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    return call_openrouter(MODEL_GPT51, msgs, max_tokens=2048)


# ---------------------------------------------------------------------------
# WideSearch task loading
# ---------------------------------------------------------------------------

def load_tasks(task_ids: list[str] | None = None) -> list[dict]:
    """Load tasks from widesearch.jsonl, optionally filtered by instance_id."""
    tasks = []
    with open(WIDESEARCH_JSONL, encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line.strip())
            if task_ids is None or obj["instance_id"] in task_ids:
                obj["evaluation"] = json.loads(obj["evaluation"])
                tasks.append(obj)
    return tasks


def default_task_ids() -> list[str]:
    """Return ws_en_001 through ws_en_020 and ws_en_080 through ws_en_100."""
    return [f"ws_en_{i:03d}" for i in range(1, 21)] + [f"ws_en_{i:03d}" for i in range(80, 101)]


# ---------------------------------------------------------------------------
# Gold CSV loading
# ---------------------------------------------------------------------------

def load_gold_csv(instance_id: str) -> list[dict[str, str]]:
    """Load a gold answer CSV and return list of row dicts."""
    path = GOLD_DIR / f"{instance_id}.csv"
    text = path.read_text(encoding="utf-8-sig")  # handle BOM
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


# ---------------------------------------------------------------------------
# Markdown table parsing
# ---------------------------------------------------------------------------

def parse_markdown_table(md_text: str) -> list[dict[str, str]]:
    """Parse a markdown table from text.

    Handles fenced code blocks (```markdown ... ```) and inline tables.
    Returns a list of row dicts with lowercased, stripped header keys.
    """
    # Try to extract from code block first
    code_match = re.search(r"```(?:markdown)?\s*\n(.*?)```", md_text, re.DOTALL)
    table_text = code_match.group(1) if code_match else md_text

    # Find table lines (lines starting with |)
    table_lines = [
        line.strip() for line in table_text.split("\n")
        if line.strip().startswith("|")
    ]

    if len(table_lines) < 3:
        # Fallback: try lines with | as delimiter even without leading |
        table_lines = [
            line.strip() for line in table_text.split("\n")
            if "|" in line and not line.strip().startswith("```")
        ]

    if len(table_lines) < 3:
        return []

    def split_row(line: str) -> list[str]:
        """Split a markdown table row by |, handling escaped pipes."""
        # Remove leading/trailing |
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]
        return [cell.strip() for cell in line.split("|")]

    headers = split_row(table_lines[0])

    # Skip separator line (---|----|---)
    data_start = 1
    if re.match(r"^[\s|:-]+$", table_lines[1]):
        data_start = 2

    rows = []
    for line in table_lines[data_start:]:
        if re.match(r"^[\s|:-]+$", line):
            continue
        cells = split_row(line)
        row = {}
        for i, header in enumerate(headers):
            key = header.strip()
            val = cells[i].strip() if i < len(cells) else ""
            row[key] = val
        rows.append(row)

    return rows


def normalize_column_name(name: str) -> str:
    """Normalize a column name for matching: lowercase, remove spaces/special chars."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def match_columns(
    output_headers: list[str],
    eval_columns: list[str],
) -> dict[str, str]:
    """Map eval column names to output header names via fuzzy matching.

    Returns {eval_col_normalized: output_header_original}
    """
    mapping: dict[str, str] = {}
    norm_to_orig: dict[str, str] = {}
    for h in output_headers:
        norm_to_orig[normalize_column_name(h)] = h

    for ecol in eval_columns:
        norm_ecol = normalize_column_name(ecol)
        if norm_ecol in norm_to_orig:
            mapping[ecol] = norm_to_orig[norm_ecol]
        else:
            # Try substring match
            for norm_h, orig_h in norm_to_orig.items():
                if norm_ecol in norm_h or norm_h in norm_ecol:
                    mapping[ecol] = orig_h
                    break

    return mapping


# ---------------------------------------------------------------------------
# WideSearch preprocessing functions
# ---------------------------------------------------------------------------

def norm_str(s: str) -> str:
    """Normalize string: lowercase, collapse whitespace, strip."""
    if not isinstance(s, str):
        s = str(s)
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def extract_number(s: str) -> float | None:
    """Extract the first numeric value from a string."""
    if not isinstance(s, str):
        s = str(s)
    # Remove commas in numbers
    s = s.replace(",", "")
    match = re.search(r"-?\d+\.?\d*", s)
    if match:
        return float(match.group())
    return None


def url_normalize(url: str) -> str:
    """Normalize a URL for comparison: lowercase, strip trailing slash, remove www."""
    if not isinstance(url, str):
        url = str(url)
    url = url.strip().lower()
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path.split("/")[0]
    host = re.sub(r"^www\.", "", host)
    path = parsed.path.rstrip("/")
    return f"{host}{path}"


# ---------------------------------------------------------------------------
# WideSearch eval metrics
# ---------------------------------------------------------------------------

def eval_exact_match(pred: str, gold: str) -> bool:
    """Exact match after norm_str."""
    return norm_str(pred) == norm_str(gold)


def eval_number_near(pred: str, gold: str, tolerance: float = 0.05) -> bool:
    """Number near: extract numbers and compare within tolerance."""
    pred_num = extract_number(pred)
    gold_num = extract_number(gold)
    if pred_num is None or gold_num is None:
        return False
    if gold_num == 0:
        return abs(pred_num) < 1e-9
    return abs(pred_num - gold_num) / abs(gold_num) <= tolerance


def eval_url_match(pred: str, gold: str) -> bool:
    """URL match after normalization."""
    return url_normalize(pred) == url_normalize(gold)


def eval_llm_judge(pred: str, gold: str, criterion: str) -> bool:
    """LLM judge: use GPT-5.1 to evaluate semantic equivalence."""
    prompt = f"""You are an evaluation judge. Compare the predicted answer with the reference answer.

Criterion: {criterion}

Reference answer: {gold}
Predicted answer: {pred}

Does the predicted answer satisfy the criterion when compared to the reference?
Answer ONLY "YES" or "NO"."""

    result = call_gpt51_judge(prompt)
    return "YES" in result.upper()


def evaluate_cell(
    pred: str,
    gold: str,
    pipeline: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate a single cell using the WideSearch eval pipeline spec.

    Args:
        pred: predicted value
        gold: gold value
        pipeline: {"preprocess": [...], "metric": [...], "criterion": ...}

    Returns:
        {"correct": bool, "metric": str, "pred_norm": str, "gold_norm": str}
    """
    pred_norm = pred
    gold_norm = gold

    # Apply preprocessing
    preprocess = pipeline.get("preprocess", [])
    for pp in preprocess:
        if pp == "norm_str":
            pred_norm = norm_str(pred_norm)
            gold_norm = norm_str(gold_norm)
        elif pp == "extract_number":
            # Keep originals for number comparison
            pass

    metric = pipeline.get("metric", ["exact_match"])[0]
    criterion = pipeline.get("criterion", "")

    if metric == "exact_match":
        correct = eval_exact_match(pred, gold)
    elif metric == "number_near":
        tolerance = float(criterion) if criterion else 0.05
        correct = eval_number_near(pred, gold, tolerance)
    elif metric == "url_match":
        correct = eval_url_match(pred, gold)
    elif metric == "llm_judge":
        correct = eval_llm_judge(pred, gold, str(criterion))
    else:
        correct = eval_exact_match(pred, gold)

    return {
        "correct": correct,
        "metric": metric,
        "pred_norm": str(pred_norm),
        "gold_norm": str(gold_norm),
    }


# ---------------------------------------------------------------------------
# Row matching using unique_columns
# ---------------------------------------------------------------------------

def match_rows(
    pred_rows: list[dict[str, str]],
    gold_rows: list[dict[str, str]],
    unique_columns: list[str],
    col_mapping: dict[str, str],
) -> tuple[
    list[tuple[dict, dict]],   # matched (pred_row, gold_row)
    list[dict],                 # missing from pred (gold only)
    list[dict],                 # extra in pred (pred only)
]:
    """Match predicted rows to gold rows using unique_columns as composite key.

    col_mapping maps eval_col → output_header.
    Gold CSV headers may differ from eval_col names (e.g., 'Subject' vs 'subject'),
    so we build a separate gold_col_mapping for gold rows.
    """

    def _resolve_col(row: dict, eval_col: str, header_mapping: dict[str, str]) -> str:
        """Get value from row, trying eval_col name, mapped header, and normalized fallback."""
        # Direct match
        if eval_col in row:
            return row[eval_col]
        # Mapped header
        mapped = header_mapping.get(eval_col)
        if mapped and mapped in row:
            return row[mapped]
        # Fallback: normalize-match against row keys
        norm_target = normalize_column_name(eval_col)
        for k, v in row.items():
            if normalize_column_name(k) == norm_target:
                return v
        return ""

    def make_key(row: dict, columns: list[str], header_mapping: dict[str, str]) -> tuple:
        return tuple(norm_str(_resolve_col(row, col, header_mapping)) for col in columns)

    # Build gold column mapping (eval_col → gold_header)
    if gold_rows:
        gold_headers = list(gold_rows[0].keys())
        gold_col_mapping = match_columns(gold_headers, unique_columns)
    else:
        gold_col_mapping = {}

    # Index gold rows
    gold_by_key: dict[tuple, dict] = {}
    for row in gold_rows:
        key = make_key(row, unique_columns, gold_col_mapping)
        gold_by_key[key] = row

    matched = []
    extra = []

    pred_matched_keys = set()
    for pred_row in pred_rows:
        key = make_key(pred_row, unique_columns, col_mapping)
        if key in gold_by_key:
            matched.append((pred_row, gold_by_key[key]))
            pred_matched_keys.add(key)
        else:
            extra.append(pred_row)

    missing = [
        row for row in gold_rows
        if make_key(row, unique_columns, gold_col_mapping) not in pred_matched_keys
    ]

    return matched, missing, extra


# ---------------------------------------------------------------------------
# Trajectory parsing
# ---------------------------------------------------------------------------

def parse_trajectory(jsonl_path: Path) -> dict[str, Any]:
    """Parse a worker trajectory JSONL file."""
    lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
    if not lines:
        return {"header": {}, "events": []}
    header = json.loads(lines[0])
    events = [json.loads(line) for line in lines[1:] if line.strip()]
    return {"header": header, "events": events}


def find_trajectories_for_run(run_timestamp: str | None = None) -> list[Path]:
    """Find trajectory JSONL files in logs/, optionally filtered by timestamp prefix."""
    if not LOGS_DIR.exists():
        return []
    paths = sorted(LOGS_DIR.glob("worker-*.jsonl"), key=lambda p: p.stat().st_mtime)
    if run_timestamp:
        paths = [p for p in paths if run_timestamp in p.name]
    return paths


def find_latest_trajectories(n_workers: int = 0) -> list[Path]:
    """Find the latest batch of trajectory files (by modification time)."""
    if not LOGS_DIR.exists():
        return []
    all_paths = sorted(LOGS_DIR.glob("worker-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not all_paths:
        return []
    if n_workers > 0:
        return all_paths[:n_workers]
    # Group by close timestamps (within 5 min of latest)
    latest_mtime = all_paths[0].stat().st_mtime
    batch = [p for p in all_paths if latest_mtime - p.stat().st_mtime < 300]
    return batch
