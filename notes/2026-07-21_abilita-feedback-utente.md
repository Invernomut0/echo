# Aggiunta di un flag per abilitare il feedback degli utenti

**Date:** 2026-07-21 10:09 UTC
**File:** `data/mcp.json`

## Rationale
Permette di attivare o disattivare facilmente il meccanismo di rating dei riassunti AI, migliorando l'interazione e la capacità di auto‑miglioramento di ECHO

## Change
**Removed:**
```python
}
```

**Added:**
```python
,
  "feedback_enabled": false
}
```
