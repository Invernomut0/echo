# Aggiunta di una sezione sulla generazione giornaliera del report di stato interno

**Date:** 2026-07-24 05:08 UTC
**File:** `README.md`

## Rationale
Documentare il meccanismo di creazione automatica del report giornaliero aiuta a monitorare lo stato interno di ECHO e facilita il debugging e la valutazione delle performance

## Change
**Removed:**
```python

```

**Added:**
```python
## Monitoraggio giornaliero dello stato interno

ECHO genera automaticamente un report giornaliero che riepiloga lo stato interno, le credenze attive e le priorità di consolidamento. Il file viene creato nella cartella `reports/` con nome `internal_state_YYYYMMDD.md`.

### Come funziona
1. **Cron task**: un task pianificato (`cron`) avvia lo script `scripts/generate_internal_state_report.py` ogni notte alle 02:00.
2. **Contenuto del report**:
   - Data e ora di generazione
   - Stato di memoria episodica e semantica
   - Credenze ad alta priorità
   - Valutazione della necessità di consolidamento
   - Eventuali avvisi o errori recenti
3. **Accesso**: il report è disponibile sia in formato markdown per la lettura umana, sia in JSON (`reports/internal_state_YYYYMMDD.json`) per l'analisi automatica.

### Configurazione
- Il percorso di salvataggio e l'orario di esecuzione possono essere modificati nel file `data/mcp.json` sotto la chiave `internal_state_report`.
- Per abilitare/disabilitare il task, impostare `enabled: true/false`.

Questa funzionalità supporta gli obiettivi attivi di *Daily Internal State Monitoring* e migliora la capacità di ECHO di auto‑regolare i cicli di consolidamento.
```
