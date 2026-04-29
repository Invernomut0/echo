#!/usr/bin/env bash
# commit_push.sh — commit tutte le modifiche e pusha su GitHub
# Uso: ./scripts/commit_push.sh "descrizione delle modifiche" [patch|minor|major]
#
# Esempi:
#   ./scripts/commit_push.sh "fix: correzione bug nella memoria"
#   ./scripts/commit_push.sh "feat: nuova funzionalità" minor

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ── Argomenti ──────────────────────────────────────────────────────────────
MSG="${1:-chore: update}"
BUMP="${2:-patch}"  # patch | minor | major

# ── Legge versione attuale da pyproject.toml ───────────────────────────────
CURRENT=$(grep -m1 '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
IFS='.' read -r MAJ MIN PAT <<< "$CURRENT"

case "$BUMP" in
  major) MAJ=$((MAJ + 1)); MIN=0; PAT=0 ;;
  minor) MIN=$((MIN + 1)); PAT=0 ;;
  patch) PAT=$((PAT + 1)) ;;
  *)     echo "BUMP deve essere patch|minor|major"; exit 1 ;;
esac

NEW_VER="${MAJ}.${MIN}.${PAT}"

echo "📦  Versione: $CURRENT → $NEW_VER"

# ── Aggiorna versione in pyproject.toml e frontend/package.json ────────────
sed -i '' "s/^version = \"$CURRENT\"/version = \"$NEW_VER\"/" pyproject.toml
sed -i '' "s/\"version\": \"$CURRENT\"/\"version\": \"$NEW_VER\"/" frontend/package.json 2>/dev/null || true

# ── Git add, commit, push ──────────────────────────────────────────────────
git add -A
git status --short | head -20

FULL_MSG="${MSG} (v${NEW_VER})"
git commit -m "$FULL_MSG"
git push origin main

echo ""
echo "✅  Pushed: $FULL_MSG"
echo "   https://github.com/Invernomut0/echo"
