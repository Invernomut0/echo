# Aggiunta controllo per la variabile d'ambiente TELEGRAM_BOT_TOKEN

**Date:** 2026-07-21 04:44 UTC
**File:** `start.sh`

## Rationale
Garantisce che l'integrazione Telegram non fallisca silenziosamente se il token non è impostato, migliorando la robustezza e l'esperienza dell'utente

## Change
**Removed:**
```python

```

**Added:**
```python
# Ensure TELEGRAM_BOT_TOKEN is set for Telegram integration
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
  echo "Warning: TELEGRAM_BOT_TOKEN is not set. Telegram integration will be disabled."
fi

```
