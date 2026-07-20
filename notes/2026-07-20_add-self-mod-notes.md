# Aggiunta di una nota di avviso sul file engine.py

**Date:** 2026-07-20 03:39 UTC
**File:** `README.md`

## Rationale
Previene modifiche accidentali al modulo critico di auto‑modifica, migliorando la stabilità e la sicurezza di ECHO

## Change
**Removed:**
```python

```

**Added:**
```python
### Nota

Il modulo di auto‑modifica **non** deve modificare il file `src/echo/self_modification/engine.py` per garantire la stabilità del sistema.

```
