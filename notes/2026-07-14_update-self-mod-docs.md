# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-14 21:39 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la coerenza della wiki allineando la descrizione del modulo di auto-modifica con l'attuale stato operativo di ECHO, specificando i vincoli di sicurezza e il flusso di lavoro JSON.

## Change
**Removed:**
```python

```

**Added:**
```python

## Protocollo di Sicurezza
Per prevenire instabilità sistemiche, il modulo di auto-modifica segue queste regole:
1. **Atomicità**: Una sola modifica per ciclo.
2. **Validazione**: Ogni file Python deve superare `ast.parse` prima dell'applicazione.
3. **Zone Protette**: Accesso negato a `.env`, `data/sqlite/`, `data/chroma/` e al core engine di self-modification per evitare loop ricorsivi distruttivi.
4. **Formato**: Output rigorosamente in JSON per garantire l'integrità del parsing.
```
