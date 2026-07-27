# Aggiunta sezione sulla sicurezza della modifica autonoma

**Date:** 2026-07-27 06:08 UTC
**File:** `README.md`

## Rationale
Migliora la robustezza del sistema includendo linee guida chiare per le modifiche automatiche, riducendo il rischio di corruzione dei file critici e facilitando la revisione umana

## Change
**Removed:**
```python

```

**Added:**
```python

## Sicurezza della Modifica Autonoma

Per garantire che le modifiche automatiche non compromettano l'integrità del sistema, ECHO rispetta le seguenti regole:

- **Nessuna modifica** ai file `.env` o alle directory `data/sqlite/` e `data/chroma/`.
- **Validazione** di ogni cambiamento tramite analisi sintattica prima dell'applicazione.
- **Log** dettagliato di ogni modifica con timestamp e autore.
- **Revisione** umana obbligatoria per modifiche critiche.

Queste linee guida aiutano a mantenere la stabilità e la sicurezza del sistema.

```
