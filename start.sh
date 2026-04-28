#!/usr/bin/env bash
set -euo pipefail

# ── PROJECT ECHO — dev launcher ───────────────────────────────────────────────
# Avvia backend (FastAPI :8000) e frontend Vite (:5173) in parallelo.
# Ctrl+C termina entrambi i processi.
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Node v25 (Homebrew) richiesto da Vite 5+
export PATH="/opt/homebrew/bin:$PATH"

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

# ── frontend ─────────────────────────────────────────────────────────────────
echo -e "${CYAN}▶  Frontend${RESET} →  http://localhost:5173"
cd "$PROJECT_ROOT/frontend"
npm run dev 2>&1 | sed 's/^/  [frontend] /' &
FRONTEND_PID=$!

echo ""
echo -e "${GREEN}  Entrambi i servizi avviati.  Premi Ctrl+C per fermarli.${RESET}"
echo ""

# ── attendi che entrambi terminino ───────────────────────────────────────────
wait "$BACKEND_PID" "$FRONTEND_PID"
