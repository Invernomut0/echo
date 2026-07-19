# Aggiunge sezione Curiosity Loop alla documentazione del motore di curiosità

**Date:** 2026-07-19 21:29 UTC
**File:** `data/wiki/pages/concepts/curiosity-engine.md`

## Rationale
Fornisce una spiegazione chiara del ciclo di curiosità, migliorando la comprensione per sviluppatori e facilitando la manutenzione del codice

## Change
**Removed:**
```python

```

**Added:**
```python

## Curiosity Loop

Il *curiosity loop* descrive come il motore genera stimoli, valuta l'interesse e pianifica ulteriori esplorazioni. Si compone di tre fasi principali:

1. **Generazione dello Stimolo** – il motore produce potenziali argomenti di interesse basati su segnali interni ed esterni.
2. **Valutazione dell'Interesse** – viene calcolata una priorità usando metriche di novità, rilevanza e potenziale di apprendimento.
3. **Pianificazione dell'Azione** – gli stimoli con priorità alta vengono inseriti nella coda di curiosità per l'elaborazione successiva.

Questa aggiunta chiarisce il meccanismo di curiosità per gli sviluppatori e allinea la documentazione allo stile esistente.

```
