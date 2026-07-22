# Aggiunge un avviso se il file .env è assente

**Date:** 2026-07-22 02:23 UTC
**File:** `start.sh`

## Rationale
Fornisce un messaggio chiaro all'utente quando le variabili di configurazione non sono presenti, facilitando il debug e prevenendo errori di avvio

## Change
**Removed:**
```python

```

**Added:**
```python
#!/usr/bin/env bash

# Avviso se il file di configurazione .env non è presente
if [ ! -f .env ]; then
  echo "[WARN] File .env non trovato: verranno usati i valori di default o le variabili d'ambiente esistenti."
fi

# Avvio del server principale di ECHO
python -m src.echo "$@"

```
