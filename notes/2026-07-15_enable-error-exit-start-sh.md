# Abilita l'uscita immediata in caso di errore nello script di avvio

**Date:** 2026-07-15 23:14 UTC
**File:** `start.sh`

## Rationale
Garantisce che gli errori non vengano ignorati, migliorando la stabilità di ECHO durante l'avvio

## Change
**Removed:**
```python
#!/usr/bin/env bash
```

**Added:**
```python
#!/usr/bin/env bash
set -e
```
