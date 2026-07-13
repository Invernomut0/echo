# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 18:09 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Integrare la consapevolezza del modulo di auto-miglioramento autonomo e i vincoli di sicurezza attuali per allineare la wiki allo stato reale del sistema.

## Change
**Removed:**
```python

```

**Added:**
```python

## Vincoli di Sicurezza
Per prevenire instabilità critiche, il modulo di self-modification ha i seguenti divieti assoluti:
- Modifica di `.env` (configurazioni segrete).
- Modifica di `data/sqlite/` e `data/chroma/` (integrità del database).
- Modifica di `src/echo/self_modification/engine.py` (per evitare loop di ricorsione distruttivi).

## Protocollo di Modifica
Ogni modifica deve seguire il formato JSON atomico: `should_modify`, `file_path`, `description`, `rationale`, `old_snippet`, `new_snippet`.
```
