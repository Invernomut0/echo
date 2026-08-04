# Aggiunta di una sezione su come usare il cron scheduler per il monitoraggio delle notizie AI

**Date:** 2026-08-04 07:23 UTC
**File:** `data/wiki/pages/concepts/cron-scheduler.md`

## Rationale
Fornisce una guida pratica per implementare una delle goal attive (monitoraggio notizie AI) migliorando l'usabilità del sistema

## Change
**Removed:**
```python

```

**Added:**
```python
## Integrazione del Cron Scheduler per il monitoraggio delle notizie AI

Il cron scheduler di ECHO può essere configurato per eseguire periodicamente il modulo di ricerca notizie AI.
Aggiungere una voce al file `crontab` (es. `scripts/cron_jobs.sh`):

```bash
# Esegui il monitoraggio notizie AI ogni ora
0 * * * * /usr/bin/python3 /root/echo/scripts/ai_news_monitor.py >> /var/log/echo/ai_news.log 2>&1
```

Assicurarsi che lo script `ai_news_monitor.py` sia presente e che il percorso di log sia scrivibile.
Dopo aver aggiornato il crontab, ricaricare con `crontab -l | crontab -`.
Questo permette a ECHO di raccogliere e sintetizzare le ultime notizie AI in modo autonomo.

```
