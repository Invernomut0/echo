# Aggiunta sezione feedback per i riassunti delle notizie AI

**Date:** 2026-07-24 11:13 UTC
**File:** `README.md`

## Rationale
Permette agli utenti di valutare la qualità dei riassunti giornalieri, fornendo dati di feedback che il sistema può utilizzare per migliorare i futuri riassunti e affinare il modello di sintesi.

## Change
**Removed:**
```python

```

**Added:**
```python

## Feedback per i Riassunti delle Notizie AI

Per migliorare la qualità dei riassunti giornalieri delle notizie AI, è stato introdotto un semplice meccanismo di valutazione da parte dell'utente.

- **Come funziona**: dopo aver ricevuto il riassunto, l'utente può cliccare su un'icona **👍** (positivo) o **👎** (negativo).
- **Raccolta dati**: le valutazioni vengono registrate in `data/feedback/ai_news_summary.json` e sono disponibili per l'analisi.
- **Utilizzo**: i dati di feedback alimentano un processo di *reinforcement learning* che adatta i prompt di sintesi per massimizzare il punteggio medio.

### Esempio di utilizzo
```bash
# Dopo aver visualizzato il riassunto
curl -X POST https://your-echo-instance/api/feedback \
    -H "Content-Type: application/json" \
    -d '{"summary_id": "2023-09-15", "rating": "up"}'
```

Questa semplice interfaccia permette di chiudere il ciclo di feedback, rendendo il sistema più reattivo alle esigenze degli utenti.

```
