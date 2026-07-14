# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 23:59 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la coerenza della wiki allineando la descrizione del modulo di auto-miglioramento con l'attuale implementazione di ECHO, specificando i vincoli di sicurezza e il flusso di modifica.

## Change
**Removed:**
```python

```

**Added:**
```python

## Protocollo di Sicurezza
Per prevenire loop di degradazione o crash sistemici, il modulo di self-modification segue queste regole:
1. **Isolamento**: I file critici (`.env`, `engine.py`) sono protetti in scrittura.
2. **Atomicità**: Ogni modifica riguarda un singolo file per volta.
3. **Validazione**: Il codice Python deve superare il parsing AST prima dell'applicazione.
4. **Tracciabilità**: Ogni modifica viene registrata nel CHANGELOG.md.
```
