# Aggiungi avviso di sicurezza sulla modifica del modulo di auto-modifica

**Date:** 2026-07-15 04:24 UTC
**File:** `README.md`

## Rationale
Previene modifiche non intenzionali al core di self‑modification, riducendo il rischio di instabilità del sistema

## Change
**Removed:**
```python

```

**Added:**
```python

## Safety Notice

- **Do not modify** `src/echo/self_modification/engine.py` directly. Use the provided configuration and extension mechanisms to customize behavior. Direct edits may break the self‑modification integrity and cause instability.

```
