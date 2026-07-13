# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 10:29 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Integrare la consapevolezza dei vincoli di sicurezza (es. file protetti come .env e engine.py) per allineare la wiki con le istruzioni operative del modulo di self-improvement.

## Change
**Removed:**
```python

```

**Added:**
```python

## Vincoli di Sicurezza
Per prevenire instabilità critiche o fughe di dati, il modulo di self-modification opera sotto rigidi vincoli:
- **File Protetti**: È severamente vietato modificare `.env`, i database in `data/sqlite/`, l'indice di `data/chroma/` e il core engine in `src/echo/self_modification/engine.py`.
- **Atomicità**: Ogni modifica deve essere singola, mirata e limitata a un delta di poche righe per garantire la reversibilità.
- **Validazione**: Ogni file Python deve superare il parsing AST prima dell'applicazione.
```
