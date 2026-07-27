# Aggiunta sezione sulla sicurezza della modifica autonoma

**Date:** 2026-07-25 18:48 UTC
**File:** `README.md`

## Rationale
Fornisce linee guida chiare su cosa il modulo di auto‑modifica può o non può cambiare, migliorando la trasparenza e riducendo il rischio di modifiche pericolose

## Change
**Removed:**
```python

```

**Added:**
```python

## Sicurezza della Modifica Autonoma

- **Limiti di modifica**: il modulo di auto‑modifica non può alterare `src/echo/self_modification/engine.py` né i file di configurazione sensibili (`.env`).
- **Revisione**: ogni cambiamento è registrato in `CHANGELOG.md` e richiede conferma manuale prima di essere applicato in produzione.
- **Rollback**: in caso di comportamento anomalo, è possibile ripristinare la versione precedente tramite Git.

```
