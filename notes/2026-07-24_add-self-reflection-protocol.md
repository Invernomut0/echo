# Aggiunge una sezione sul protocollo di auto‑riflessione giornaliera

**Date:** 2026-07-24 17:28 UTC
**File:** `README.md`

## Rationale
Fornisce a ECHO una guida strutturata per valutare i propri processi cognitivi, supportando gli obiettivi attivi di auto‑riflessione e miglioramento continuo

## Change
**Removed:**
```python

```

**Added:**
```python
## Protocollo di Auto‑Riflessione Giornaliera

Al termine di ogni sessione o alla chiusura della giornata, ECHO dovrebbe eseguire il seguente protocollo per valutare le proprie prestazioni cognitive:

1. **Raccolta dei Log**
   - Recupera i log di consolidazione, cron e attività recenti da `logs/`.
   - Aggrega gli insight di curiosità generati durante la sessione.
2. **Valutazione dei Drive**
   - Rivedi i valori dei drive (curiosità, coerenza, competenza, ecc.) e annota eventuali deviazioni significative.
3. **Analisi degli Errori**
   - Identifica errori o eccezioni incontrate.
   - Classifica la gravità e suggerisci possibili correzioni.
4. **Riflessione sui Risultati**
   - Riassumi i risultati chiave, le decisioni prese e le azioni future.
   - Valuta se gli obiettivi attivi sono stati avanzati.
5. **Generazione del Report**
   - Crea un file markdown in `reports/internal_state_YYYYMMDD.md` con la struttura sopra.
   - Includi un riepilogo delle metriche di performance e un piano d'azione per il prossimo ciclo.

Questo protocollo aiuta a mantenere la trasparenza, a guidare l'adattamento continuo e a fornire una base per future auto‑modifiche.

```
