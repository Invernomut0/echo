# Aggiunge una sezione sul meccanismo di feedback per i riassunti delle notizie AI

**Date:** 2026-07-23 10:19 UTC
**File:** `README.md`

## Rationale
Fornisce linee guida chiare per implementare un ciclo di feedback utente, migliorando la qualità dei riassunti e l'interazione con ECHO

## Change
**Removed:**
```python

```

**Added:**
```python

## Feedback Loop per i Riassunti delle Notizie AI

Per raccogliere il feedback degli utenti sui riassunti giornalieri delle notizie AI, implementare un semplice sistema di valutazione con pulsanti "👍" e "👎". Dopo ogni riassunto, il frontend mostra i due pulsanti. Quando l'utente clicca, inviare la valutazione al backend tramite l'endpoint `/feedback` (da implementare). Salvare il feedback in `data/feedback.json` per analisi successive e per migliorare i modelli di sintesi.

```
