# Aggiungi nota su abilitazione del cron scheduler per il ciclo di consolidazione

**Date:** 2026-07-18 02:19 UTC
**File:** `README.md`

## Rationale
Aiuta gli utenti a ricordare di avviare il servizio cron, garantendo che il heartbeat di consolidazione funzioni regolarmente e migliorando l'affidabilità del sistema

## Change
**Removed:**
```python

```

**Added:**
```python


**Nota:** Assicurati che il servizio cron sia attivo (es. `service cron start` o `systemctl enable --now cron`) affinché il ciclo di consolidazione di ECHO venga eseguito regolarmente.

```
