# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-12 23:59 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la chiarezza della documentazione interna riguardo al modulo di auto-miglioramento autonomo, allineandola con le capacità attuali di modifica dei file e i vincoli di sicurezza.

## Change
**Removed:**
```python

```

**Added:**
```python

## Protocollo di Sicurezza
Per prevenire loop infiniti o corruzione del sistema, il modulo di self-modification segue queste regole:
1. **Isolamento**: Non può modificare il proprio motore di esecuzione (`engine.py`) o i file di configurazione sensibili (`.env`).
2. **Atomicità**: Ogni modifica riguarda un singolo file per transazione.
3. **Validazione**: I file Python devono superare il parsing AST prima dell'applicazione.
4. **Tracciabilità**: Ogni modifica deve essere documentata con una rationale chiara e un slug identificativo.
```
