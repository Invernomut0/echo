# Aggiunta di un esempio pratico di utilizzo del cron scheduler per il riepilogo giornaliero delle notizie AI

**Date:** 2026-07-28 00:10 UTC
**File:** `data/wiki/pages/concepts/cron-scheduler.md`

## Rationale
Fornire un esempio concreto aiuta gli sviluppatori a configurare rapidamente attività cron, migliorando l'usabilità e riducendo errori di configurazione

## Change
**Removed:**
```python

```

**Added:**
```python

## Example: Daily AI News Summary
```yaml
# In cron_tasks.yaml
- name: ai_news_summary
  schedule: "0 8 * * *"  # every day at 08:00
  command: "python -m echo.tasks.ai_news_summary"
```

```
