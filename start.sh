#!/usr/bin/env bash
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

# ── backend ──────────────────────────────────────────────────────────────────
echo -e "${CYAN}▶  Backend${RESET}  →  http://localhost:8000"
echo -e "           →  http://localhost:8000/docs  (Swagger)"
cd "$PROJECT_ROOT"
uv run uvicorn echo.api.server:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
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
echo -e "${CYAN}▶  Frontend${RESET} →  http://localhost:5173"
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
