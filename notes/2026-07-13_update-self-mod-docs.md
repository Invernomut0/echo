# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 21:49 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la coerenza della wiki allineando la descrizione del modulo di auto-modifica con l'attuale implementazione basata su JSON e vincoli di sicurezza.

## Change
**Removed:**
```python

```

**Added:**
```python

## Vincoli di Sicurezza
Per prevenire instabilità sistemiche, il modulo di auto-modifica opera sotto i seguenti vincoli:
1. **File Protetti**: Accesso negato a `.env`, `data/sqlite/`, `data/chroma/` e al motore core `src/echo/self_modification/engine.py`.
2. **Atomicità**: Ogni modifica è limitata a un singolo file per ciclo.
3. **Validazione**: I file Python devono superare il parsing `ast.parse` prima dell'applicazione.
4. **Dimensioni**: Delta di modifica limitato a < 80 righe per evitare regressioni massive.
```
