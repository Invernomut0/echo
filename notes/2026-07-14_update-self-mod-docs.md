# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-14 19:09 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la coerenza della wiki allineando la descrizione del modulo di auto-modifica con l'attuale implementazione di ECHO, specificando i vincoli di sicurezza e il flusso di lavoro JSON.

## Change
**Removed:**
```python

```

**Added:**
```python

## Protocollo di Sicurezza
Per prevenire loop infiniti o crash sistemici, il modulo di auto-modifica segue queste regole:
1. **Atomicità**: Una sola modifica per ciclo.
2. **Validazione**: Ogni file Python deve superare `ast.parse` prima dell'applicazione.
3. **Zone Protette**: I file `.env` e il core dell'engine di self-modification sono in sola lettura per l'agente.
4. **Formato**: L'output deve essere esclusivamente un oggetto JSON per garantire l'integrità del parsing.
```
