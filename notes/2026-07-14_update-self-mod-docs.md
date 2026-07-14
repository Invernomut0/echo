# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-14 21:34 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Allinea la documentazione wiki con l'attuale stato operativo del modulo di auto-miglioramento autonomo, integrando i vincoli di sicurezza e il formato di output JSON richiesto.

## Change
**Removed:**
```python

```

**Added:**
```python

## Vincoli Operativi
Il modulo di self-modification opera sotto rigidi vincoli per garantire la stabilità del sistema:
- **Output Deterministico**: L'unico output ammesso è un oggetto JSON singolo.
- **Protezione Core**: Divieto assoluto di modificare `.env`, `data/sqlite/`, `data/chroma/` e l'engine di self-modification stesso.
- **Atomicità**: Una sola modifica per ciclo, con delta limitati a 80 righe.
- **Validazione**: Ogni modifica a file `.py` deve superare il parsing `ast.parse` prima dell'applicazione.
```
