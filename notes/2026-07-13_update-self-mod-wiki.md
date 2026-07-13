# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 19:34 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Allinea la documentazione wiki con l'attuale stato operativo del modulo di auto-miglioramento autonomo, integrando i vincoli di sicurezza e il formato di output JSON richiesto.

## Change
**Removed:**
```python

```

**Added:**
```python

## Protocollo di Modifica
Il modulo di self-modification opera seguendo un ciclo di: Analisi Log $\rightarrow$ Identificazione Bug/Miglioramento $\rightarrow$ Proposta JSON $\rightarrow$ Applicazione Atomica.

### Vincoli di Sicurezza
- Divieto assoluto di modificare `.env` e i database in `data/sqlite/` o `data/chroma/`.
- Ogni modifica deve essere limitata a un singolo file per transazione.
- Il delta di codice deve essere inferiore a 80 righe per prevenire regressioni massive.
- I file Python devono superare il controllo `ast.parse` prima dell'applicazione.
```
