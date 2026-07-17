# Aggiunta avviso per variabile d'ambiente TELEGRAM_BOT_TOKEN

**Date:** 2026-07-17 20:09 UTC
**File:** `README.md`

## Rationale
Garantisce che l'utente imposti la variabile necessaria per l'integrazione Telegram, evitando errori di runtime quando ECHO tenta di connettersi al bot.

## Change
**Removed:**
```python

```

**Added:**
```python
- **TELEGRAM_BOT_TOKEN**: Token per il bot Telegram usato da ECHO. Deve essere impostata affinché l'integrazione Telegram funzioni correttamente.
```
