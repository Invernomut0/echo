# Aggiunta sezione sul meccanismo di feedback per i riassunti delle notizie AI

**Date:** 2026-07-23 16:33 UTC
**File:** `README.md`

## Rationale
Documentare il meccanismo di feedback consente agli sviluppatori e agli utenti di capire come le valutazioni (pollice su/giù) vengano raccolte e utilizzate per migliorare la qualità dei riassunti, facilitando ulteriori iterazioni e manutenzione.

## Change
**Removed:**
```python

```

**Added:**
```python

## User Feedback Loop for AI News Summaries

To collect user feedback on the quality of daily AI news summaries, a simple thumbs up/down rating is integrated into the Telegram bot. The rating is stored in `data/feedback/ai_news.json` and used by the cron task `scripts/collect_feedback.py` to adjust summarization parameters.

```
