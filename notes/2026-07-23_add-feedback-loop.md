# Aggiunta di una sezione sul meccanismo di feedback per i riassunti delle notizie AI

**Date:** 2026-07-23 04:03 UTC
**File:** `README.md`

## Rationale
Fornisce agli utenti un modo semplice per valutare la qualità dei riassunti, consentendo a ECHO di apprendere dal feedback e migliorare le future sintesi

## Change
**Removed:**
```python

```

**Added:**
```python

## Feedback sui riassunti delle notizie AI

- **Come funziona**: dopo ogni riassunto giornaliero, viene mostrato un pulsante **👍** (utile) e **👎** (non utile).
- **Scopo**: i voti vengono registrati in `data/feedback/ai_news.json` e utilizzati dal motore di sintesi per affinare i prompt e i criteri di selezione.
- **Implementazione**: il cron task `cron/ai_news_summary.py` legge il file di feedback e aggiorna la variabile `feedback_score` che influisce sul peso dei contenuti nella prossima generazione.
- **Nota**: è possibile disabilitare il meccanismo impostando `ENABLE_NEWS_FEEDBACK=false` nel file `.env`.

```
