# Aggiunta dello shebang per garantire l'esecuzione corretta dello script di avvio

**Date:** 2026-07-21 12:33 UTC
**File:** `start.sh`

## Rationale
Inserire "#!/usr/bin/env bash" all'inizio di start.sh assicura che lo script venga interpretato dal corretto interprete Bash, evitando errori di avvio su sistemi dove l'associazione file‑script non è predefinita

## Change
**Removed:**
```python

```

**Added:**
```python
#!/usr/bin/env bash

```
