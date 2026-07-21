# Aggiunta controllo variabile d'ambiente MCP_SERVER_URL

**Date:** 2026-07-19 02:49 UTC
**File:** `start.sh`

## Rationale
Garantisce che l'utente imposti la variabile MCP_SERVER_URL necessaria per l'integrazione con il server MCP, evitando errori di runtime e migliorando l'affidabilità del sistema.

## Change
**Removed:**
```python

```

**Added:**
```python
# Verify MCP server URL is set
if [ -z "$MCP_SERVER_URL" ]; then
  echo "Warning: MCP_SERVER_URL environment variable is not set. MCP integration may fail."
fi

```
