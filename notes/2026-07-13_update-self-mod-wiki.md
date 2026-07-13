# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 00:54 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la coerenza della wiki allineando la descrizione del modulo di auto-modifica con l'attuale implementazione di ECHO, includendo i vincoli di sicurezza e il formato JSON richiesto.

## Change
**Removed:**
```python

```

**Added:**
```python
# Autonomous Self-Modification

## Overview
Il modulo di auto-modifica permette a ECHO di evolvere il proprio codice e la propria configurazione in modo autonomo.

## Protocollo di Modifica
Ogni modifica deve seguire un formato rigoroso per garantire la stabilità del sistema:
- **Output**: Un singolo oggetto JSON.
- **Vincoli**: Massimo 80 linee di delta per modifica.
- **Sicurezza**: Divieto assoluto di modificare `.env`, database SQLite e il motore core di self-modification (`engine.py`).

## Obiettivi
1. Correzione di bug identificati nei log.
2. Ottimizzazione dei prompt degli agenti specialisti.
3. Implementazione di nuove funzionalità basate sui goal attivi.
4. Raffinamento dell'interfaccia utente React.
```
