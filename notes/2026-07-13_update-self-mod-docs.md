# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 21:14 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la coerenza della wiki allineando la descrizione del modulo di auto-modifica con l'attuale stato operativo di ECHO, specificando i vincoli di sicurezza e il flusso di validazione JSON.

## Change
**Removed:**
```python

```

**Added:**
```python

## Protocollo di Validazione
Ogni modifica proposta dal modulo di auto-miglioramento deve seguire un formato JSON rigoroso per evitare errori di parsing. Il sistema applica i seguenti vincoli:
1. **Atomicità**: Una sola modifica per file per ogni ciclo.
2. **Sicurezza**: Divieto assoluto di modificare file critici come `.env` o il motore core di self-modification.
3. **Validazione**: I file Python devono superare il controllo `ast.parse` prima dell'applicazione.
4. **Tracciabilità**: Ogni modifica deve essere accompagnata da una razionale chiara e un slug identificativo.
```
