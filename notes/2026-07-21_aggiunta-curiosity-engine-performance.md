# Aggiunta di una sezione su considerazioni di performance

**Date:** 2026-07-21 07:00 UTC
**File:** `data/wiki/pages/concepts/curiosity-engine.md`

## Rationale
Fornire indicazioni su come limitare la frequenza del motore di curiosità aiuta a prevenire sovraccarichi di risorse e migliora la stabilità del sistema ECHO

## Change
**Removed:**
```python

```

**Added:**
```python

## Considerazioni di Performance

Il motore di curiosità può generare un gran numero di stimoli in breve tempo. Per evitare un utilizzo eccessivo della CPU e della rete, è consigliato:

- **Rate limiting**: impostare un intervallo minimo (es. 5 minuti) tra due cicli di curiosità consecutivi.
- **Filtraggio dei topic**: limitare i topic a quelli con una soglia di confidenza superiore a 0.5.
- **Cache dei risultati**: memorizzare i risultati recenti per evitare richieste duplicate.

Queste pratiche garantiscono che il motore di curiosità rimanga reattivo senza compromettere le prestazioni complessive del sistema.

```
