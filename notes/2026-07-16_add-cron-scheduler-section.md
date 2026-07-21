# Aggiunta sezione Cron Scheduler per avviare il task di consolidazione

**Date:** 2026-07-16 18:28 UTC
**File:** `README.md`

## Rationale
Fornisce indicazioni chiare su come avviare il cron scheduler, riducendo errori di configurazione e migliorando l'esperienza utente

## Change
**Removed:**
```python

```

**Added:**
```python

## Cron Scheduler

Per attivare il ciclo di consolidazione automatica è necessario avviare il **cron scheduler**. Da terminale, nella directory radice del progetto, eseguire:

```bash
python -m echo.cron
```

Il comando avvierà il processo in background che gestisce le attività periodiche (es. sintesi giornaliera di notizie AI, pulizia della memoria, ecc.). È consigliato aggiungere il comando a un servizio di avvio (es. systemd) o a `screen`/`tmux` per mantenerlo attivo anche dopo la chiusura della sessione.

```
