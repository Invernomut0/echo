# Aggiunta documentazione per il task cron di monitoraggio stato interno giornaliero

**Date:** 2026-07-23 16:23 UTC
**File:** `data/wiki/pages/concepts/cron-tasks.md`

## Rationale
Fornisce una guida chiara su come configurare il cron che genera report giornalieri sullo stato interno di ECHO, facilitando il monitoraggio e la diagnostica

## Change
**Removed:**
```python

```

**Added:**
```python

## Task Cron: Monitoraggio Stato Interno Giornaliero

- **Nome**: `daily_internal_state_report`
- **Frequenza**: `0 6 * * *` (ogni giorno alle 06:00)
- **Descrizione**: Genera un report markdown in `reports/internal_state_YYYYMMDD.md` che sintetizza lo stato attuale di memoria, curiosità, obiettivi attivi e pattern recenti.
- **Implementazione**: Utilizza lo script `scripts/generate_internal_state_report.py` (da creare) che raccoglie le informazioni dal modulo di memoria e le formatta in un documento leggibile.
- **Esempio di utilizzo**:
  ```bash
  echo "0 6 * * * /usr/bin/python3 /root/echo/scripts/generate_internal_state_report.py" | crontab -
  ```
- **Nota**: Assicurarsi che il percorso di output `reports/` esista e sia scrivibile dal processo cron.

```
