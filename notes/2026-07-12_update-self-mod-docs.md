# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-12 22:39 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la chiarezza della documentazione interna riguardo al modulo di auto-miglioramento autonomo, allineandola alle capacità attuali di modifica dei file e vincoli di sicurezza.

## Change
**Removed:**
```python

```

**Added:**
```python

## Protocollo di Sicurezza
Per prevenire loop infiniti o corruzione del sistema, il modulo di self-modification segue queste regole:
1. **Isolamento**: Non può modificare il proprio motore di esecuzione (`engine.py`).
2. **Protezione Dati**: Accesso in sola lettura a `.env` e database SQLite/Chroma.
3. **Atomicità**: Una sola modifica per ciclo di iterazione.
4. **Validazione**: Ogni modifica al codice Python deve superare il parsing AST prima dell'applicazione.
```
