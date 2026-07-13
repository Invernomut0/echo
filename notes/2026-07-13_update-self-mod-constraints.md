# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 06:29 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Integrare la consapevolezza del modulo di self-improvement autonomo e dei vincoli operativi attuali per migliorare la coerenza della base di conoscenza di ECHO.

## Change
**Removed:**
```python

```

**Added:**
```python

## Vincoli Operativi
Il modulo di self-modification opera sotto rigidi vincoli di sicurezza:
- Modifica di un singolo file per iterazione.
- Delta massimo di 80 righe.
- Divieto assoluto di modificare `.env`, `data/sqlite/`, `data/chroma/` e l'engine di self-modification stesso per prevenire loop di crash catastrofici.
- Validazione sintattica obbligatoria (ast.parse per Python) prima dell'applicazione.
```
