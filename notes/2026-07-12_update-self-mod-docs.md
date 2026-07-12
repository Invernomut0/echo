# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-12 22:01 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la chiarezza della documentazione interna riguardo al modulo di auto-miglioramento autonomo, allineandola alle capacità attuali di modifica dei file tramite JSON.

## Change
**Removed:**
```python

```

**Added:**
```python

## Meccanismo di Modifica
ECHO utilizza un modulo di self-improvement autonomo che opera tramite l'emissione di oggetti JSON strutturati. Ogni modifica è atomica e segue il principio di 'una modifica, un file' per garantire la stabilità del sistema e prevenire regressioni catastrofiche.

### Vincoli di Sicurezza
- Divieto assoluto di modificare `.env` e i core engine di self-modification.
- Validazione sintattica obbligatoria (ast.parse per Python).
- Limite di delta per singola operazione (< 80 righe).
```
