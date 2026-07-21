# Aggiunta di una nota di chiarimento sulla sicurezza della auto-modifica

**Date:** 2026-07-21 10:00 UTC
**File:** `data/wiki/pages/concepts/bug-fixes.md`

## Rationale
Fornire una breve indicazione nella pagina dei bug-fix aiuta gli sviluppatori a ricordare di non modificare il modulo di auto-modifica, riducendo il rischio di errori critici.

## Change
**Removed:**
```python

```

**Added:**
```python

- **Nota:** Evitare di modificare il file `src/echo/self_modification/engine.py` poiché contiene la logica di auto-modifica critica per il corretto funzionamento di ECHO.

```
