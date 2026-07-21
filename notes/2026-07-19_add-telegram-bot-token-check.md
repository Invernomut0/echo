# Aggiunge controllo per la variabile d'ambiente TELEGRAM_BOT_TOKEN

**Date:** 2026-07-19 08:54 UTC
**File:** `start.sh`

## Rationale
Garantisce che il bot Telegram abbia il token necessario prima di avviarsi, evitando errori di runtime e migliorando la robustezza del sistema

## Change
**Removed:**
```python

```

**Added:**
```python
# Verify required Telegram bot token
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
  echo "Error: TELEGRAM_BOT_TOKEN environment variable is not set."
  exit 1
fi

```
