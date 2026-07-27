# Aggiunta di una breve sezione di esempio sull'uso del cron scheduler

**Date:** 2026-07-27 16:25 UTC
**File:** `data/wiki/pages/concepts/cron-scheduler.md`

## Rationale
Fornisce agli utenti un esempio pratico su come configurare attività periodiche, facilitando l'adozione della funzionalità di pianificazione automatica

## Change
**Removed:**
```python

```

**Added:**
```python

## Esempio di utilizzo

Per programmare un'attività che esegua una ricerca di notizie AI ogni giorno alle 08:00, aggiungi la seguente voce al file `cron_tasks.yaml`:

```yaml
- name: ai_news_fetch
  schedule: "0 8 * * *"
  command: "python scripts/fetch_ai_news.py"
```

Assicurati che lo script `fetch_ai_news.py` sia presente nella cartella `scripts/` e che abbia i permessi di esecuzione. Dopo aver salvato il file, il cron scheduler di ECHO caricherà automaticamente la nuova attività.

```
