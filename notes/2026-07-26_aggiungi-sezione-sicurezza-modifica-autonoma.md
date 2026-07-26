# Aggiunta sezione di sicurezza per la modifica autonoma

**Date:** 2026-07-26 15:03 UTC
**File:** `README.md`

## Rationale
Fornisce un promemoria chiaro sui limiti di auto‑modifica, riducendo il rischio di alterare componenti critici come engine.py e .env, migliorando la robustezza del sistema.

## Change
**Removed:**
```python

```

**Added:**
```python

## Sicurezza della Modifica Autonoma

- **Limiti di Modifica**: Il modulo di auto‑modifica **non deve** alterare il file `src/echo/self_modification/engine.py` né il file di configurazione `.env`.
- **Verifica**: Prima di ogni modifica, il sistema esegue un controllo di integrità per assicurarsi che questi file rimangano invariati.
- **Log**: Qualsiasi tentativo di modifica non autorizzata viene registrato in `logs/self_modification.log` e genera un avviso all'utente.

```
