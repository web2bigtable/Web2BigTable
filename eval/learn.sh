#!/usr/bin/env bash
#
# Memento-Teams: One-click learning pipeline
# Chains: run → verify → reflect to auto-generate orchestrator skills.
#
# Usage:
#   ./eval/learn.sh                              # Run all tasks (sequential)
#   ./eval/learn.sh --parallel                   # Run all tasks concurrently
#   ./eval/learn.sh --tasks ws_en_001 ws_en_003  # Run specific tasks only
#   ./eval/learn.sh --skip-run                   # Skip run, only verify + reflect
#   ./eval/learn.sh --skip-compress              # Skip trajectory compression in verify
#   ./eval/learn.sh --skip-llm-judge             # Use exact_match instead of LLM judge
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

log_info()    { echo -e "${CYAN}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[ OK ]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[FAIL]${NC} $1"; }

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
SKIP_RUN=0
PARALLEL=""
TASKS=""
VERIFY_FLAGS=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-run)       SKIP_RUN=1; shift ;;
        --parallel)       PARALLEL="--parallel"; shift ;;
        --skip-compress)  VERIFY_FLAGS="$VERIFY_FLAGS --skip-compress"; shift ;;
        --skip-llm-judge) VERIFY_FLAGS="$VERIFY_FLAGS --skip-llm-judge"; shift ;;
        --tasks)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
                TASKS="$TASKS $1"
                shift
            done
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Usage: $0 [--parallel] [--tasks ID...] [--skip-run] [--skip-compress] [--skip-llm-judge]"
            exit 1
            ;;
    esac
done

TASK_ARGS=""
if [[ -n "$TASKS" ]]; then
    TASK_ARGS="--tasks $TASKS"
fi

# ---------------------------------------------------------------------------
# Detect Python runner (uv run or plain python)
# ---------------------------------------------------------------------------
if command -v uv &>/dev/null && [[ -f "$PROJECT_ROOT/pyproject.toml" ]]; then
    PY="uv run python"
else
    PY="python"
fi

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo ""
echo -e "${CYAN}╔═════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║         Memento-Teams Learning Pipeline            ║${NC}"
echo -e "${CYAN}║           run → verify → reflect                   ║${NC}"
echo -e "${CYAN}╚═════════════════════════════════════════════════════╝${NC}"
echo ""
log_info "Project root: $PROJECT_ROOT"
log_info "Python:       $PY"
[[ -n "$TASKS" ]]    && log_info "Tasks:        $TASKS" || log_info "Tasks:        all"
[[ -n "$PARALLEL" ]] && log_info "Mode:         parallel" || log_info "Mode:         sequential"
[[ $SKIP_RUN -eq 1 ]] && log_info "Skipping:     run (verify + reflect only)"
echo ""

cd "$PROJECT_ROOT"
TOTAL_START=$SECONDS

# ---------------------------------------------------------------------------
# Stage 1: Run
# ---------------------------------------------------------------------------
if [[ $SKIP_RUN -eq 0 ]]; then
    echo -e "${CYAN}━━━ Stage 1/3: Run eval tasks ━━━━━━━━━━━━━━━━━━━━━${NC}"
    if $PY eval/run.py $PARALLEL $TASK_ARGS; then
        log_success "Stage 1 complete: eval tasks finished"
    else
        log_error "Stage 1 failed: eval/run.py exited with error"
        exit 1
    fi
    echo ""
else
    log_warn "Stage 1 skipped (--skip-run)"
    echo ""
fi

# ---------------------------------------------------------------------------
# Stage 2: Verify
# ---------------------------------------------------------------------------
echo -e "${CYAN}━━━ Stage 2/3: Verify results ━━━━━━━━━━━━━━━━━━━━━${NC}"
if $PY eval/verify.py $TASK_ARGS $VERIFY_FLAGS; then
    log_success "Stage 2 complete: verification report generated"
else
    log_error "Stage 2 failed: eval/verify.py exited with error"
    exit 1
fi
echo ""

# ---------------------------------------------------------------------------
# Stage 3: Reflect
# ---------------------------------------------------------------------------
echo -e "${CYAN}━━━ Stage 3/3: Reflect & generate skills ━━━━━━━━━━━${NC}"
if $PY eval/reflect.py; then
    log_success "Stage 3 complete: orchestrator skills updated"
else
    log_error "Stage 3 failed: eval/reflect.py exited with error"
    exit 1
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
ELAPSED=$(( SECONDS - TOTAL_START ))
MINUTES=$(( ELAPSED / 60 ))
SECS=$(( ELAPSED % 60 ))

echo ""
echo -e "${GREEN}╔═════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║            Learning Pipeline Complete!              ║${NC}"
echo -e "${GREEN}╚═════════════════════════════════════════════════════╝${NC}"
echo ""
log_success "Total time: ${MINUTES}m ${SECS}s"
log_success "Outputs:    eval/outputs/*.md"
log_success "Report:     eval/reports/verify_report.json"
log_success "Skills:     orchestrator_skills/decompose-*/SKILL.md"
echo ""
