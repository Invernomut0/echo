# Aggiungi sezione Cron Tasks per ricordare di avviare il scheduler

**Date:** 2026-07-15 10:54 UTC
**File:** `README.md`

## Rationale
Aiuta gli utenti a ricordare di avviare il cron scheduler, migliorando l'affidabilità delle funzioni di auto‑monitoraggio e consolidamento della memoria

## Change
**Removed:**
```python

```

**Added:**
```python
## Cron Tasks

Per garantire che le funzioni di monitoraggio delle notizie AI e la consolidazione della memoria operino correttamente, è necessario avviare il scheduler cron.

```bash
python -m src.echo.cron
```

Assicurati che questo comando sia in esecuzione (ad esempio tramite un servizio di sistema o un processo di background) per mantenere ECHO aggiornato e reattivo.

```
