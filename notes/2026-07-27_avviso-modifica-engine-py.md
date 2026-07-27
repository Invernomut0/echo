# Aggiunta di avviso su modifica del motore di auto-modifica

**Date:** 2026-07-27 15:05 UTC
**File:** `data/wiki/pages/concepts/bug-fixes.md`

## Rationale
Previene modifiche accidentali al file critico engine.py, migliorando la stabilità del sistema

## Change
**Removed:**
```python

```

**Added:**
```python

---

⚠️ **Nota:** Non modificare direttamente `src/echo/self_modification/engine.py`. Utilizza l'interfaccia di auto‑modifica fornita per garantire la coerenza e la sicurezza del sistema.

```
