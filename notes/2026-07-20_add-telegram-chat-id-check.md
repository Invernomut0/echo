# Aggiunge controllo per la variabile d'ambiente TELEGRAM_CHAT_ID

**Date:** 2026-07-20 16:14 UTC
**File:** `start.sh`

## Rationale
Previene errori di runtime quando il bot tenta di inviare messaggi su Telegram senza un ID chat configurato, migliorando la robustezza del sistema.

## Change
**Removed:**
```python

```

**Added:**
```python

# Ensure TELEGRAM_CHAT_ID is set for Telegram notifications
if [ -z "$TELEGRAM_CHAT_ID" ]; then
  echo "Warning: TELEGRAM_CHAT_ID is not set. Telegram notifications will be disabled."
fi

```
