# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-14 21:19 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la coerenza della wiki allineando la descrizione del modulo di auto-modifica con l'attuale stato operativo di ECHO, includendo i vincoli di sicurezza e il formato di output JSON richiesto.

## Change
**Removed:**
```python

```

**Added:**
```python

## Vincoli di Sicurezza e Protocollo

Il modulo di auto-modifica opera sotto rigidi vincoli per prevenire l'instabilità del sistema:
1. **File Protetti**: È assolutamente vietato modificare `.env`, i database in `data/sqlite/`, l'indice di `data/chroma/` e il core engine in `src/echo/self_modification/engine.py`.
2. **Atomicità**: Ogni modifica deve riguardare un singolo file e non superare le 80 righe di delta.
3. **Validazione**: I file Python devono superare `ast.parse` e i file TypeScript devono essere sintatticamente validi.
4. **Formato di Output**: Il modulo deve rispondere esclusivamente con un oggetto JSON per garantire l'integrazione automatizzata senza l'intervento umano.
```
