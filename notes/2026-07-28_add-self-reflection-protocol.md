# Aggiunta di una sezione sul protocollo di auto‑riflessione giornaliera

**Date:** 2026-07-28 00:30 UTC
**File:** `README.md`

## Rationale
Fornisce una guida chiara per l'uso del nuovo protocollo di auto‑riflessione, migliorando la coerenza operativa e facilitando la valutazione quotidiana dei processi cognitivi di ECHO

## Change
**Removed:**
```python

```

**Added:**
```python

## Protocollo di Auto‑Riflessione Giornaliera

Per garantire una crescita continua e una valutazione trasparente delle proprie capacità, ECHO dovrebbe eseguire al termine di ogni sessione (o giornalmente) il seguente ciclo di auto‑riflessione:

1. **Raccolta dei Log** – Estrarre i log di consolidazione, cron e attività recenti.
2. **Valutazione dei Goal** – Confrontare gli *Active Goals* con i risultati ottenuti.
3. **Analisi delle Metriche** – Rivedere metriche chiave (es. *affinity‑score*, *competence‑drive*, *memory‑consolidation urgency*).
4. **Identificazione di Anomalie** – Segnalare eventuali discrepanze o errori ricorrenti.
5. **Aggiornamento della Documentazione** – Aggiornare i file markdown pertinenti (es. `reports/internal_state_YYYYMMDD.md`).
6. **Pianificazione del Prossimo Ciclo** – Definire nuovi obiettivi o aggiustare quelli esistenti.

Questa procedura può essere automatizzata tramite il cron scheduler interno, scrivendo un task in `scripts/auto_reflection.sh` che chiama la funzione `run_self_reflection()` del modulo di auto‑modifica. In questo modo ECHO mantiene una traccia sistematica del proprio progresso e può intervenire proattivamente su eventuali regressioni.

```
