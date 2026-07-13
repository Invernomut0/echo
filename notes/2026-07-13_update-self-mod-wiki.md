# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 07:04 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la coerenza della wiki allineando la descrizione del modulo di auto-miglioramento con l'attuale implementazione di ECHO, specificando i vincoli di sicurezza e il flusso di modifica JSON.

## Change
**Removed:**
```python

```

**Added:**
```python
# Autonomous Self-Modification

## Overview
Il modulo di self-modification permette a ECHO di evolvere il proprio codice e la propria configurazione in modo autonomo.

## Meccanismo di Funzionamento
1. **Analisi**: Il modulo analizza i log, i pattern di errore e i feedback dell'utente.
2. **Proposta**: Genera una modifica specifica (snippet di codice) per risolvere un bug o implementare una feature.
3. **Validazione**: Ogni modifica deve essere formattata come un oggetto JSON rigoroso per evitare l'esecuzione di codice arbitrario non controllato.
4. **Applicazione**: Il sistema applica la modifica al file target e verifica l'integrità sintattica (es. `ast.parse` per Python).

## Vincoli di Sicurezza
- **File Protetti**: I file `.env` e i database core (`data/sqlite/`, `data/chroma/`) sono rigorosamente off-limits.
- **Atomicità**: Una sola modifica per ciclo per prevenire regressioni a cascata.
- **Limitazione Delta**: Le modifiche sono limitate a piccoli delta (< 80 righe) per garantire la revisionabilità.
```
