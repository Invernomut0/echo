# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 10:24 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la coerenza della wiki allineando la descrizione del modulo di auto-miglioramento con l'attuale stato operativo e i vincoli di sicurezza (es. protezione di engine.py).

## Change
**Removed:**
```python

```

**Added:**
```python

## Vincoli di Sicurezza
Per prevenire loop di instabilità o crash sistemici, il modulo di self-modification opera sotto i seguenti vincoli:
- **File Protetti**: L'accesso in scrittura a `src/echo/self_modification/engine.py` e ai file `.env` è rigorosamente vietato.
- **Atomicità**: Ogni modifica deve riguardare un singolo file per transazione.
- **Validazione**: I file Python devono superare il parsing AST prima dell'applicazione della modifica.
- **Limitazione Delta**: Le modifiche sono limitate a piccoli incrementi (< 80 righe) per garantire la tracciabilità.
```
