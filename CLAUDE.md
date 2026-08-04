# CLAUDE.md

Il "cervello" del progetto: contesto e regole che Claude Code carica a ogni sessione.

## Progetto

ECHO — vedi [README.md](README.md) e [PROJECT_ECHO.md](PROJECT_ECHO.md).

## Comandi

```bash
# avvio
./start.sh

# test
uv run pytest
```

## Convenzioni

- Aggiornare `README.md`, `CHANGELOG.md` e `docs/` a ogni modifica di codice.
- Commit in formato Conventional Commits.

## Git

**Regola: fare sempre commit e push, senza chiedere conferma.**

- Remote: `origin` → `https://github.com/Invernomut0/echo.git`, branch `main`.
- Autenticazione: `GITHUB_TOKEN` in `.env` (gitignored). Passarlo a git via
  `GIT_ASKPASS` temporaneo (username `x-access-token`); **non** scriverlo in
  `.git/config` né nella URL del remote, **non** stamparlo mai a schermo.
- `origin/main` riceve commit anche dall'agente autonomo (README, `notes/`):
  se il push viene rifiutato con *non-fast-forward*, fare
  `git rebase origin/main --autostash` e riprovare.
- Non mettere in stage modifiche non correlate già presenti nel working tree.

## Creazione di skill

**Regola: ogni nuova skill di questo progetto si crea con la skill `skill-creator`.**

Installata in [.claude/skills/skill-creator/](.claude/skills/skill-creator/SKILL.md)
(da [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/skill-creator)).

Quando chiedo di creare, modificare, valutare o ottimizzare una skill, Claude Code
deve invocare `skill-creator` (`Skill` tool, nome `skill-creator`) invece di
scrivere `SKILL.md` a mano. Copre:

- creazione da zero (init, struttura cartelle, frontmatter `name` + `description`)
- modifica/refactor di skill esistenti
- eval e benchmark (`scripts/run_eval.py`, `scripts/aggregate_benchmark.py`)
- ottimizzazione della `description` per il triggering (`scripts/improve_description.py`)
- packaging (`scripts/package_skill.py`)

Le skill del progetto vivono in `.claude/skills/<nome>/SKILL.md`.

## Struttura

- `src/` — codice applicativo
- `frontend/` — UI
- `tests/` — test
- `docs/` — documentazione
- `.claude/` — configurazione Claude Code (`settings.json`, `skills/`, `agents/`, `rules/`)
