# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 21:34 UTC
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
Ogni modifica proposta dal modulo di self-improvement deve seguire un formato JSON rigoroso per evitare errori di parsing. Il sistema applica i seguenti vincoli:
1. **Atomicità**: Una sola modifica per ciclo.
2. **Sicurezza**: Divieto assoluto di modificare `.env` e il core engine di self-modification.
3. **Validazione**: I file Python devono superare `ast.parse` prima dell'applicazione.
4. **Tracciabilità**: Ogni modifica deve includere una rationale chiara e un slug identificativo.
```
