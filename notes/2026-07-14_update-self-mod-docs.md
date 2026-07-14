# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-14 20:54 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la coerenza della wiki allineando la descrizione del modulo di auto-modifica con l'attuale stato operativo e i vincoli di sicurezza (es. protezione di .env e engine.py).

## Change
**Removed:**
```python

```

**Added:**
```python

## Vincoli di Sicurezza
Per garantire la stabilità del sistema, il modulo di auto-modifica opera sotto i seguenti vincoli:
- **File Protetti**: È severamente vietata la modifica di `.env` e `src/echo/self_modification/engine.py` per prevenire loop infiniti o perdita di configurazioni critiche.
- **Atomicità**: Ogni modifica deve essere singola, mirata e validata sintatticamente prima dell'applicazione.
- **Tracciabilità**: Ogni cambiamento deve essere registrato nel CHANGELOG.md.
```
