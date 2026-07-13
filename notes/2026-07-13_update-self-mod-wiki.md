# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 20:29 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la coerenza della wiki allineando la descrizione del modulo di auto-modifica con l'attuale implementazione di ECHO, specificando i vincoli di sicurezza e il flusso di lavoro JSON.

## Change
**Removed:**
```python

```

**Added:**
```python
## Protocollo di Self-Modification

Il modulo di auto-modifica di ECHO permette al sistema di evolvere autonomamente modificando il proprio codice sorgente e la propria base di conoscenza.

### Vincoli di Sicurezza
- **File Protetti**: `.env`, `data/sqlite/`, `data/chroma/` e l'engine di self-modification stesso non possono essere modificati per prevenire loop infiniti o perdita di configurazioni critiche.
- **Validazione**: Ogni modifica deve passare un controllo di sintassi (ast.parse per Python) prima di essere applicata.
- **Atomicità**: Una singola operazione di modifica riguarda un solo file e un delta limitato (< 80 righe).

### Flusso di Esecuzione
1. **Analisi**: Il modulo identifica un bug, un'inefficienza o un'opportunità di miglioramento.
2. **Proposta**: Generazione di un oggetto JSON contenente `old_snippet` e `new_snippet`.
3. **Applicazione**: Sostituzione testuale precisa nel file target.
4. **Verifica**: Validazione del file risultante.
```
