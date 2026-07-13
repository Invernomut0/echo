# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 16:13 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la coerenza della wiki allineando la descrizione del modulo di auto-miglioramento con l'attuale implementazione di ECHO, specificando i vincoli di sicurezza e il flusso di modifica.

## Change
**Removed:**
```python

```

**Added:**
```python
# Autonomous Self-Modification

## Overview
Il modulo di self-modification permette a ECHO di analizzare il proprio codice e i propri file di configurazione per apportare miglioramenti incrementali in modo autonomo.

## Protocollo di Modifica
1. **Analisi**: Identificazione di bug, inefficienze o opportunità di nuove feature.
2. **Proposta**: Generazione di un delta di codice (snippet) mirato.
3. **Validazione**: Verifica sintattica (ast.parse per Python) prima dell'applicazione.
4. **Applicazione**: Sostituzione atomica di stringhe nel file target.

## Vincoli di Sicurezza
- **File Protetti**: `.env`, database SQLite e il motore core di self-modification non sono modificabili per prevenire loop infiniti o perdita di credenziali.
- **Atomicità**: Ogni modifica deve riguardare un singolo file e un delta limitato (< 80 righe).
- **Tracciabilità**: Ogni cambiamento viene registrato nel CHANGELOG.md.
```
