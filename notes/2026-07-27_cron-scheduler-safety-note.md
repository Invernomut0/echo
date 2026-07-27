# Aggiungi una sezione di avviso sulla sicurezza per il cron scheduler

**Date:** 2026-07-27 15:20 UTC
**File:** `data/wiki/pages/concepts/cron-scheduler.md`

## Rationale
Fornisce linee guida chiare per evitare compiti cron pericolosi, migliorando la robustezza e la sicurezza di ECHO

## Change
**Removed:**
```python

```

**Added:**
```python
### Considerazioni di Sicurezza

Quando si definiscono attività cron, assicurarsi di non eseguire operazioni privilegiate o modificare file di sistema critici. Utilizzare i meccanismi di `self_modification` forniti e evitare riferimenti a `.env` o alle directory del database.

```
