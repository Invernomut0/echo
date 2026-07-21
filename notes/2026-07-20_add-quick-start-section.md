# Aggiunge sezione 'Quick Start' con esempio di avvio

**Date:** 2026-07-20 22:29 UTC
**File:** `README.md`

## Rationale
Fornisce agli utenti un esempio immediato su come avviare ECHO, riducendo confusione e migliorando l'esperienza

## Change
**Removed:**
```python

```

**Added:**
```python

## Quick Start

```bash
# Clona il repository
git clone https://github.com/your-org/echo.git
cd echo

# Installa le dipendenze
pip install -r requirements.txt

# Configura le variabili d'ambiente (esempio)
export LOG_LEVEL=info
export TELEGRAM_BOT_TOKEN=your_bot_token
export TELEGRAM_CHAT_ID=your_chat_id

# Avvia il server principale
./start.sh
```

Questa sequenza avvia ECHO con le impostazioni di base. Assicurati di impostare le variabili d'ambiente richieste prima di eseguire `start.sh`.
```
