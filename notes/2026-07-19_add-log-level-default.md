# Aggiunge impostazione predefinita per la variabile d'ambiente LOG_LEVEL

**Date:** 2026-07-19 15:24 UTC
**File:** `start.sh`

## Rationale
Garantisce che il sistema di logging abbia un livello valido anche se l'utente non lo specifica, evitando errori di configurazione e migliorando la leggibilità dei log

## Change
**Removed:**
```python

```

**Added:**
```python
# Set default log level if not provided
if [ -z "$LOG_LEVEL" ]; then
  export LOG_LEVEL="INFO"
fi

```
