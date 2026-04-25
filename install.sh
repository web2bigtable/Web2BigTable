#!/usr/bin/env bash
#
# Web2BigTable One-Click Installer (uv version)
# Usage: curl -sSL https://raw.githubusercontent.com/Web2BigTable/Web2BigTable/main/install.sh | bash
#        or: ./install.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Config
REPO_URL="https://github.com/Web2BigTable/Web2BigTable.git"
REPO_BRANCH="main"
INSTALL_DIR="${WEB2BIGTABLE_INSTALL_DIR:-$HOME/web2bigtable}"
DEFAULT_OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL="deepseek/deepseek-v3.2"
ROUTER_DATASET_REPO="AgentFly/router-data"

print_banner() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════════════════╗"
    echo "║                                                                       ║"
    echo "║                            Web2BigTable                               ║"
    echo "║              Bi-Level Multi-Agent Web-to-Table Search                 ║"
    echo "║                          Installer (uv)                               ║"
    echo "║                                                                       ║"
    echo "╚═══════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_command() { command -v "$1" &> /dev/null; }

_read_env_value() {
    local file="$1"
    local key="$2"
    [ -f "$file" ] || return 0
    local line
    line="$(grep -E "^${key}=" "$file" | tail -n 1 || true)"
    [ -n "$line" ] || return 0
    line="${line#*=}"
    line="${line%\"}"
    line="${line#\"}"
    printf '%s' "$line"
}

_upsert_env_value() {
    local file="$1"
    local key="$2"
    local value="$3"
    mkdir -p "$(dirname "$file")"
    [ -f "$file" ] || touch "$file"

    local tmp="${file}.tmp.$$"
    awk -v k="$key" -v v="$value" '
        BEGIN { done = 0 }
        $0 ~ ("^" k "=") {
            if (!done) {
                print k "=" v
                done = 1
            }
            next
        }
        { print }
        END {
            if (!done) print k "=" v
        }
    ' "$file" > "$tmp"
    mv "$tmp" "$file"
}

_prompt_required() {
    local label="$1"
    local current="$2"
    local secret="$3"
    local default_value="$4"
    local input=""

    while true; do
        if [ -n "$current" ]; then
            if [ "$secret" = "1" ]; then
                printf "%s (press Enter to keep existing): " "$label" > /dev/tty
                IFS= read -r -s input < /dev/tty || input=""
                printf "\n" > /dev/tty
                if [ -z "$input" ]; then
                    input="$current"
                fi
            else
                printf "%s [%s]: " "$label" "$current" > /dev/tty
                IFS= read -r input < /dev/tty || input=""
                if [ -z "$input" ]; then
                    input="$current"
                fi
            fi
        elif [ -n "$default_value" ]; then
            printf "%s [%s]: " "$label" "$default_value" > /dev/tty
            IFS= read -r input < /dev/tty || input=""
            if [ -z "$input" ]; then
                input="$default_value"
            fi
        else
            if [ "$secret" = "1" ]; then
                printf "%s: " "$label" > /dev/tty
                IFS= read -r -s input < /dev/tty || input=""
                printf "\n" > /dev/tty
            else
                printf "%s: " "$label" > /dev/tty
                IFS= read -r input < /dev/tty || input=""
            fi
        fi

        if [ -n "$input" ]; then
            printf '%s' "$input"
            return 0
        fi
        printf "Input required. Please try again.\n" > /dev/tty
    done
}

# Install uv if not present
install_uv() {
    if check_command uv; then
        log_success "uv: $(uv --version 2>&1)"
        return 0
    fi

    log_info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    if check_command uv; then
        log_success "uv installed: $(uv --version 2>&1)"
    else
        log_error "Failed to install uv. Please install manually: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
}

# Check if running from local project directory
is_local_install() {
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    [ -f "$script_dir/tui_app.py" ] && [ -f "$script_dir/main.py" ] && [ -d "$script_dir/orchestrator" ]
}

# Clone or update repository
setup_repository() {
    log_info "Setting up repository..."

    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    if is_local_install; then
        log_info "Detected local installation from: $script_dir"
        INSTALL_DIR="$script_dir"
        cd "$INSTALL_DIR"
        log_success "Using local directory: $INSTALL_DIR"
    elif [ -d "$INSTALL_DIR/.git" ]; then
        log_info "Repository exists, updating..."
        cd "$INSTALL_DIR"
        # Update remote URL if it changed
        local current_remote
        current_remote="$(git remote get-url origin 2>/dev/null || true)"
        if [ -n "$current_remote" ] && [ "$current_remote" != "$REPO_URL" ]; then
            log_info "Updating remote URL: $current_remote -> $REPO_URL"
            git remote set-url origin "$REPO_URL"
        fi
        git stash -q 2>/dev/null || true
        git fetch origin "$REPO_BRANCH"
        git checkout "$REPO_BRANCH" 2>/dev/null || git checkout -b "$REPO_BRANCH" "origin/$REPO_BRANCH"
        git pull --rebase || log_warn "Git pull failed, continuing with existing code"
        git stash pop -q 2>/dev/null || true
        log_success "Repository updated at $INSTALL_DIR (branch: $REPO_BRANCH)"
    else
        log_info "Cloning repository to $INSTALL_DIR..."
        git clone --branch "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
        log_success "Repository cloned to $INSTALL_DIR (branch: $REPO_BRANCH)"
    fi
}

# Install dependencies using uv sync
install_dependencies() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}            Installing Dependencies (uv sync)                  ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""

    cd "$INSTALL_DIR"

    # Ensure Python 3.12
    log_info "Installing Python 3.12..."
    uv python install 3.12

    # Step 1: Install Memento-S dependencies
    log_info "Installing Memento-S dependencies..."
    cd "$INSTALL_DIR/Memento-S"
    uv sync --python 3.12
    log_success "Memento-S dependencies installed!"

    # Step 2: Install root orchestrator dependencies (textual, langchain, etc.)
    log_info "Installing orchestrator dependencies..."
    cd "$INSTALL_DIR"
    uv sync --python 3.12
    log_success "Orchestrator dependencies installed!"

    # Download nltk data for crawl4ai (via Memento-S venv)
    log_info "Downloading nltk data..."
    cd "$INSTALL_DIR/Memento-S"
    uv run python -c "import nltk; nltk.download('punkt_tab', quiet=True)" 2>/dev/null || log_warn "nltk data download skipped"

    # Setup playwright/crawl4ai (optional, may fail)
    log_info "Setting up browser support..."
    uv run crawl4ai-setup -q 2>/dev/null || log_warn "crawl4ai setup skipped"
    uv run python -m playwright install chromium 2>/dev/null || log_warn "Playwright setup skipped (can install later)"

    cd "$INSTALL_DIR"
}

download_router_assets() {
    cd "$INSTALL_DIR/Memento-S"
    local download_flag="${MEMENTO_DOWNLOAD_ROUTER:-1}"
    case "$(printf '%s' "$download_flag" | tr '[:upper:]' '[:lower:]')" in
        0|false|no|off)
            log_warn "Skipping router asset download (MEMENTO_DOWNLOAD_ROUTER=$download_flag)"
            return 0
            ;;
    esac

    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}               Downloading Router Assets                        ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""

    if ! uv run python -c "import huggingface_hub" >/dev/null 2>&1; then
        log_info "Installing huggingface_hub..."
        uv pip install huggingface_hub >/dev/null 2>&1 || {
            log_warn "Failed to install huggingface_hub; skipping router asset download"
            return 0
        }
    fi

    local download_embeddings_flag="${MEMENTO_DOWNLOAD_ROUTER_EMBEDDINGS:-0}"
    local emb_flag_lc
    emb_flag_lc="$(printf '%s' "$download_embeddings_flag" | tr '[:upper:]' '[:lower:]')"

    log_info "Downloading router dataset index: $ROUTER_DATASET_REPO (skills_catalog.jsonl)"

    if MEMENTO_ROUTER_DATASET_REPO="$ROUTER_DATASET_REPO" \
       MEMENTO_DOWNLOAD_ROUTER_EMBEDDINGS="$download_embeddings_flag" \
       uv run python - <<'PY'
import os
import shutil
from pathlib import Path
from huggingface_hub import hf_hub_download, snapshot_download


def as_bool(value: str) -> bool:
    return str(value or "").strip().lower() not in {"", "0", "false", "no", "off"}


root = Path.cwd()
router_root = root / "router_data"
router_root.mkdir(parents=True, exist_ok=True)
token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN") or None
dataset_repo = str(os.getenv("MEMENTO_ROUTER_DATASET_REPO") or "").strip()
download_embeddings = as_bool(os.getenv("MEMENTO_DOWNLOAD_ROUTER_EMBEDDINGS", "0"))

# Always fetch skills catalog first (fast, required).
catalog_src = hf_hub_download(
    repo_id=dataset_repo,
    repo_type="dataset",
    filename="skills_catalog.jsonl",
    token=token,
)
shutil.copy2(catalog_src, router_root / "skills_catalog.jsonl")

# Optional: fetch embeddings only when explicitly enabled.
if download_embeddings and dataset_repo:
    snapshot_download(
        repo_id=dataset_repo,
        repo_type="dataset",
        local_dir=str(router_root),
        allow_patterns=["embeddings/*"],
        token=token,
    )

print(f"router_data_dir={router_root}")
print(f"skills_catalog_exists={(router_root / 'skills_catalog.jsonl').exists()}")
print(f"embeddings_downloaded={download_embeddings}")
PY
    then
        log_success "Router assets downloaded to: $INSTALL_DIR/Memento-S/router_data"
        if [ "$emb_flag_lc" = "0" ] || [ "$emb_flag_lc" = "false" ] || [ "$emb_flag_lc" = "no" ] || [ "$emb_flag_lc" = "off" ] || [ -z "$emb_flag_lc" ]; then
            log_info "Skipped dataset embeddings by default. Set MEMENTO_DOWNLOAD_ROUTER_EMBEDDINGS=1 to download."
        fi
    else
        log_warn "Router asset download failed (network/auth). You can retry later manually."
    fi

    cd "$INSTALL_DIR"
}

configure_env() {
    cd "$INSTALL_DIR"
    local env_file="$INSTALL_DIR/.env"
    local memento_s_env="$INSTALL_DIR/Memento-S/.env"
    local have_tty=0
    if [ -e /dev/tty ] && [ -r /dev/tty ]; then
        have_tty=1
    fi

    local existing_api_key existing_model existing_serper
    existing_api_key="$(_read_env_value "$env_file" "OPENROUTER_API_KEY")"
    existing_model="$(_read_env_value "$env_file" "OPENROUTER_MODEL")"
    existing_serper="$(_read_env_value "$env_file" "SERPER_API_KEY")"

    local api_key model serper_key
    api_key="${OPENROUTER_API_KEY:-$existing_api_key}"
    model="${OPENROUTER_MODEL:-$existing_model}"
    serper_key="${SERPER_API_KEY:-$existing_serper}"

    if [ "$have_tty" -eq 1 ]; then
        echo ""
        echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
        echo -e "${CYAN}               Configure Required API Keys                      ${NC}"
        echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
        echo ""
        api_key="$(_prompt_required "OPENROUTER_API_KEY" "$api_key" "1" "")"
        model="$(_prompt_required "OPENROUTER_MODEL" "$model" "0" "$DEFAULT_OPENROUTER_MODEL")"
        serper_key="$(_prompt_required "SERPER_API_KEY" "$serper_key" "1" "")"
    else
        if [ -z "$api_key" ] || [ -z "$model" ] || [ -z "$serper_key" ]; then
            log_error "Missing required configuration in non-interactive mode."
            log_error "Set env vars before install: OPENROUTER_API_KEY OPENROUTER_MODEL SERPER_API_KEY"
            exit 1
        fi
    fi

    # Write root .env (used by orchestrator / TUI)
    _upsert_env_value "$env_file" "OPENROUTER_API_KEY" "$api_key"
    _upsert_env_value "$env_file" "OPENROUTER_BASE_URL" "$DEFAULT_OPENROUTER_BASE_URL"
    _upsert_env_value "$env_file" "OPENROUTER_MODEL" "$model"
    _upsert_env_value "$env_file" "SERPER_API_KEY" "$serper_key"

    chmod 600 "$env_file" 2>/dev/null || true
    log_success "Configured root .env"

    # Symlink into Memento-S so workers inherit the same config
    if [ -L "$memento_s_env" ] || [ ! -e "$memento_s_env" ]; then
        ln -sf "$env_file" "$memento_s_env"
        log_success "Symlinked .env → Memento-S/.env"
    else
        # Memento-S has its own .env — update it in place
        _upsert_env_value "$memento_s_env" "LLM_API" "openrouter"
        _upsert_env_value "$memento_s_env" "OPENROUTER_API_KEY" "$api_key"
        _upsert_env_value "$memento_s_env" "OPENROUTER_BASE_URL" "$DEFAULT_OPENROUTER_BASE_URL"
        _upsert_env_value "$memento_s_env" "OPENROUTER_MODEL" "$model"
        _upsert_env_value "$memento_s_env" "SERPER_API_KEY" "$serper_key"
        _upsert_env_value "$memento_s_env" "SKILLS_DIR" "./skills"
        _upsert_env_value "$memento_s_env" "SKILLS_EXTRA_DIRS" "./skills-extra"
        _upsert_env_value "$memento_s_env" "WORKSPACE_DIR" "./workspace"
        _upsert_env_value "$memento_s_env" "SEMANTIC_ROUTER_CATALOG_JSONL" "router_data/skills_catalog.jsonl"
        _upsert_env_value "$memento_s_env" "SKILL_DYNAMIC_FETCH_CATALOG_JSONL" "router_data/skills_catalog.jsonl"
        chmod 600 "$memento_s_env" 2>/dev/null || true
        log_success "Updated Memento-S/.env with shared keys"
    fi
}

# Add directory to PATH
add_to_path() {
    local dir="$1"
    echo "$PATH" | grep -q "$dir" && return

    local shell_rc="$HOME/.zshrc"
    [ -f "$HOME/.bashrc" ] && [ "$SHELL" = *bash* ] && shell_rc="$HOME/.bashrc"

    if [ -f "$shell_rc" ] && ! grep -q "$dir" "$shell_rc" 2>/dev/null; then
        echo "" >> "$shell_rc"
        echo "# Added by Web2BigTable installer" >> "$shell_rc"
        echo "export PATH=\"$dir:\$PATH\"" >> "$shell_rc"
        log_success "Added to $shell_rc"
    fi

    export PATH="$dir:$PATH"
    log_warn "Restart terminal or run: source $shell_rc"
}

# Create launcher script
create_launcher() {
    log_info "Creating launcher script..."

    LAUNCHER="$INSTALL_DIR/web2bigtable"
    cat > "$LAUNCHER" << 'EOF'
#!/usr/bin/env bash
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"

cd "$SCRIPT_DIR"

# Use uv run — it handles the venv automatically
uv run python -c "from tui_app import Web2BigTable; Web2BigTable().run()"
EOF
    chmod +x "$LAUNCHER"

    # Create command link with robust fallback
    local installed_link=""
    if [ -w "/usr/local/bin" ]; then
        if ln -sf "$LAUNCHER" /usr/local/bin/web2bigtable 2>/dev/null; then
            installed_link="/usr/local/bin/web2bigtable"
            log_success "Symlink: $installed_link"
        fi
    elif [ -d "/usr/local/bin" ]; then
        if sudo ln -sf "$LAUNCHER" /usr/local/bin/web2bigtable 2>/dev/null; then
            installed_link="/usr/local/bin/web2bigtable"
            log_success "Symlink: $installed_link (sudo)"
        else
            log_warn "Could not write /usr/local/bin/web2bigtable, falling back to ~/.local/bin"
        fi
    fi

    if [ -z "$installed_link" ]; then
        mkdir -p "$HOME/.local/bin"
        ln -sf "$LAUNCHER" "$HOME/.local/bin/web2bigtable"
        installed_link="$HOME/.local/bin/web2bigtable"
        add_to_path "$HOME/.local/bin"
        log_success "Symlink: $installed_link"
    fi

    # Refresh shell command cache
    hash -r 2>/dev/null || true

    local resolved_cmd=""
    resolved_cmd="$(command -v web2bigtable 2>/dev/null || true)"
    if [ -n "$resolved_cmd" ]; then
        log_success "Command available: web2bigtable -> $resolved_cmd"
    else
        log_warn "Command not yet in PATH for this shell. Reopen terminal, then run: web2bigtable"
    fi

    log_success "Launcher created: $LAUNCHER"
}

print_success() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}                 Installation Complete!                        ${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${CYAN}Install directory:${NC} $INSTALL_DIR"
    echo ""
    echo -e "  ${YELLOW}To start Web2BigTable:${NC}"
    echo ""
    echo -e "    ${GREEN}web2bigtable${NC}            # Launch TUI"
    echo ""
    echo -e "  ${CYAN}Or run directly:${NC}"
    echo -e "    ${GREEN}cd $INSTALL_DIR && uv run python -c \"from tui_app import Web2BigTable; Web2BigTable().run()\"${NC}"
    echo ""
    echo -e "  ${YELLOW}Note:${NC} If 'web2bigtable' not found, restart terminal or run:"
    echo -e "        ${CYAN}source ~/.zshrc${NC} (or ~/.bashrc)"
    echo ""
}

# Main
main() {
    print_banner

    # Check git
    if ! check_command git; then
        log_error "git is required. Please install git first."
        exit 1
    fi

    install_uv
    setup_repository
    install_dependencies
    download_router_assets
    configure_env
    create_launcher
    print_success
}

main "$@"