# Aggiungi controllo per la variabile d'ambiente GITHUB_TOKEN

**Date:** 2026-07-17 07:24 UTC
**File:** `start.sh`

## Rationale
Garantisce che lo script di avvio fallisca in modo chiaro se il token GitHub non è impostato, evitando errori silenziosi durante le operazioni di deployment o aggiornamento

## Change
**Removed:**
```python

```

**Added:**
```python
# Ensure required environment variables are set
if [[ -z "$GITHUB_TOKEN" ]]; then
  echo "Error: GITHUB_TOKEN environment variable is not set."
  exit 1
fi
```
