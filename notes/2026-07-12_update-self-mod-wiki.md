# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-12 23:49 UTC
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
Il modulo di self-modification permette a ECHO di evolvere autonomamente modificando il proprio codice sorgente e la propria configurazione.

## Processo di Modifica
1. **Analisi**: Il modulo identifica bug, inefficienze o opportunità di miglioramento.
2. **Proposta**: Generazione di un delta di codice in formato JSON strutturato.
3. **Validazione**: Verifica sintattica (ast.parse per Python) e rispetto dei vincoli di sicurezza.
4. **Applicazione**: Sostituzione atomica di snippet di codice.

## Vincoli di Sicurezza
- **File Protetti**: `.env`, `data/sqlite/`, `data/chroma/` e il motore di self-modification stesso non possono essere modificati per prevenire loop infiniti o perdita di credenziali.
- **Limiti Delta**: Ogni modifica è limitata a un singolo file e a un numero contenuto di righe per garantire la stabilità del sistema.
```
