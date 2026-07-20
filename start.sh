#!/usr/bin/env bash
set -e
set -euo pipefail

# ── PROJECT ECHO — dev launcher ───────────────────────────────────────────────
# Avvia backend (FastAPI :8000) e frontend Vite (:5173) in parallelo.
# Ctrl+C termina entrambi i processi.
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Node v25 (Homebrew) richiesto da Vite 5+
export PATH="/opt/homebrew/bin:$PATH"
export BROWSER=none

# ── colori ────────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'

echo -e "${CYAN}"
echo "  ███████╗ ██████╗██╗  ██╗ ██████╗ "
echo "  ██╔════╝██╔════╝██║  ██║██╔═══██╗"
echo "  █████╗  ██║     ███████║██║   ██║"
echo "  ██╔══╝  ██║     ██╔══██║██║   ██║"
echo "  ███████╗╚██████╗██║  ██║╚██████╔╝"
echo "  ╚══════╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ "
echo -e "${RESET}"
echo -e "${GREEN}  Persistent Cognitive Architecture — dev mode${RESET}"
echo ""

# ── gestione segnali ─────────────────────────────────────────────────────────
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    echo -e "${YELLOW}⏹  Arresto processi...${RESET}"
    [[ -n "$BACKEND_PID"  ]] && kill "$BACKEND_PID"  2>/dev/null || true
    [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    echo -e "${GREEN}✓  Tutto fermo. Arrivederci.${RESET}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ── kill processi già in ascolto sulle porte ─────────────────────────────────
_kill_port() {
    local port=$1
    local pids
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        echo -e "${YELLOW}  ⚠  Porta $port occupata — termino PID $pids${RESET}"
        echo "$pids" | xargs kill -TERM 2>/dev/null || true
        # aspetta fino a 3s che si liberi, poi forza
        local i=0
        while lsof -ti :"$port" &>/dev/null && (( i < 6 )); do
            sleep 0.5; (( i++ ))
        done
        if lsof -ti :"$port" &>/dev/null; then
            echo "$pids" | xargs kill -9 2>/dev/null || true
        fi
    fi
}

_kill_port 8000
_kill_port 5173

# ── aggiorna lock (rigenera se pyproject.toml è cambiato) ───────────────────
# Su Linux usa automaticamente il pytorch-cpu index (CPU-only, ~200 MB)
# definito in [tool.uv.sources] — torch deve essere dep diretta per questo.
cd "$PROJECT_ROOT"
echo -e "  Risoluzione dipendenze..."
uv lock --quiet

# ── opencode-mcp needs OPENCODE_SERVER_PASSWORD in env to suppress ServeError ──
# Generate a stable token from the hostname if not already set
if [[ -z "${OPENCODE_SERVER_PASSWORD:-}" ]]; then
    export OPENCODE_SERVER_PASSWORD="echo-$(hostname | md5sum | cut -c1-16)"
fi

# ── backend ──────────────────────────────────────────────────────────────────
echo -e "${CYAN}▶  Backend${RESET}  →  http://localhost:8000"
echo -e "           →  http://localhost:8000/docs  (Swagger)"
cd "$PROJECT_ROOT"
uv run uvicorn echo.api.server:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --reload-dir src/echo \
    --log-level info \
    2>&1 | sed 's/^/  [backend] /' &
BACKEND_PID=$!

# ── attendi che il backend sia pronto (max 15 s) ─────────────────────────────
echo -n "  Attendo backend"
for _i in $(seq 1 15); do
    curl -sf http://localhost:8000/health >/dev/null 2>&1 && { echo " ✓"; break; }
    echo -n "."
    sleep 1
done
echo ""

# ── frontend ─────────────────────────────────────────────────────────────────
echo -e "${CYAN}▶  Frontend${RESET} →  http://0.0.0.0:5173  (LAN: check Vite output for your IP)"
cd "$PROJECT_ROOT/frontend"
# Installa dipendenze se mancanti (es. primo avvio su server)
[[ ! -d node_modules ]] && echo '  [frontend] npm install…' && npm install --silent
npm run dev 2>&1 | sed 's/^/  [frontend] /' &
FRONTEND_PID=$!

echo ""
echo -e "${GREEN}  Entrambi i servizi avviati.  Premi Ctrl+C per fermarli.${RESET}"
echo ""

# ── attendi che entrambi terminino ───────────────────────────────────────────
wait "$BACKEND_PID" "$FRONTEND_PID"

if [ -z "$ECHO_MCP_URL" ]; then
  echo "Warning: ECHO_MCP_URL is not set. Some features may not work."
fi

# Ensure required environment variables are set
if [[ -z "$GITHUB_TOKEN" ]]; then
  echo "Error: GITHUB_TOKEN environment variable is not set."
  exit 1
fi

# Verify OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
  echo "Warning: OPENAI_API_KEY environment variable is not set. Some functionalities may be limited."
fi

# Verify MCP server URL is set
if [ -z "$MCP_SERVER_URL" ]; then
  echo "Warning: MCP_SERVER_URL environment variable is not set. MCP integration may fail."
fi

# Verify required Telegram bot token
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
  echo "Error: TELEGRAM_BOT_TOKEN environment variable is not set."
  exit 1
fi

# Set default log level if not provided
if [ -z "$LOG_LEVEL" ]; then
  export LOG_LEVEL="INFO"
fi


# Ensure TELEGRAM_CHAT_ID is set for Telegram notifications
if [ -z "$TELEGRAM_CHAT_ID" ]; then
  echo "Warning: TELEGRAM_CHAT_ID is not set. Telegram notifications will be disabled."
fi

