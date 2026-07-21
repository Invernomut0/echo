# Aggiungi una sezione di troubleshooting per avvisare gli utenti quando la consolidazione della memoria è alta

**Date:** 2026-07-16 05:19 UTC
**File:** `README.md`

## Rationale
Fornire un'indicazione chiara su come reagire a un'alta urgenza di consolidamento aiuta a mantenere le prestazioni di ECHO e riduce i cicli di sonno non necessari

## Change
**Removed:**
```python

```

**Added:**
```python

## Troubleshooting

- **Consolidazione della memoria alta**: se vedi un avviso di "Memory consolidation urgency high" (valore > 0.7), considera di avviare un ciclo di *light‑sleep* manualmente. Puoi farlo eseguendo:
  ```bash
  ./scripts/run_light_sleep.sh
  ```
  Questo aiuta a processare i dati recenti senza attendere il ciclo di consolidazione programmato.

```
