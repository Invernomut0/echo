# aggiungere nota su sicurezza della self-modification

**Date:** 2026-07-28 12:03 UTC
**File:** `data/wiki/pages/concepts/bug-fixes.md`

## Rationale
ricorda agli sviluppatori di escludere il motore di self-modification dalle modifiche automatiche, prevenendo potenziali corruzioni del codice

## Change
**Removed:**
```python

```

**Added:**
```python

- **Nota di sicurezza**: il modulo `src/echo/self_modification/engine.py` è deliberatamente escluso dalle modifiche automatiche per preservare l'integrità del meccanismo di auto-modifica.

```
