# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 07:24 UTC
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
Per prevenire loop di regressione o crash sistemici, il modulo di self-modification segue queste regole:
1. **Isolamento**: Non è possibile modificare i file core dell'engine di self-modification (`engine.py`) o i file di configurazione sensibili (`.env`).
2. **Atomicità**: Ogni modifica riguarda un singolo file per transazione.
3. **Validazione**: I file Python devono superare il parsing AST prima dell'applicazione.
4. **Tracciabilità**: Ogni modifica deve essere registrata nel CHANGELOG.md.
```
