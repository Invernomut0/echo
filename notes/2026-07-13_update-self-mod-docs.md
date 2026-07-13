# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 00:41 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Allinea la documentazione wiki con l'attuale implementazione del modulo di auto-miglioramento autonomo, integrando i vincoli di sicurezza e il formato di output JSON richiesto.

## Change
**Removed:**
```python

```

**Added:**
```python
## Vincoli di Sicurezza e Protocollo

Il modulo di self-modification opera sotto rigidi vincoli per prevenire l'instabilità del sistema:
1. **File Protetti**: È severamente vietato modificare `.env`, i database in `data/sqlite/`, l'indice di `data/chroma/` e il core engine `src/echo/self_modification/engine.py`.
2. **Atomicità**: Ogni modifica deve riguardare un singolo file e non superare le 80 righe di delta.
3. **Validazione**: I file Python devono superare `ast.parse` e i file TypeScript devono essere sintatticamente validi.
4. **Output Deterministico**: Il modulo deve rispondere esclusivamente con un oggetto JSON per garantire l'integrazione automatizzata senza l'intervento umano.
```
