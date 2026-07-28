# Aggiungi sezione di sicurezza per l'auto-modifica al README

**Date:** 2026-07-28 20:28 UTC
**File:** `README.md`

## Rationale
Fornisce un promemoria chiaro su quali file non devono essere modificati, riducendo il rischio di errori critici e migliorando la manutenzione del progetto

## Change
**Removed:**
```python

```

**Added:**
```python

## Self‑Modification Safety

- **Non modificare** `src/echo/self_modification/engine.py` né alcun file sotto `data/` che contiene stato persistente.
- Tutte le modifiche devono rispettare l'integrità del repository e superare i test esistenti.

```
