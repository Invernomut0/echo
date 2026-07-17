# aggiunge avviso per variabile d'ambiente MCP

**Date:** 2026-07-17 01:04 UTC
**File:** `start.sh`

## Rationale
se ECHO_MCP_URL non è impostata, l'AI non può comunicare con il server MCP; avvisare l'utente previene errori silenziosi e migliora l'affidabilità del sistema

## Change
**Removed:**
```python

```

**Added:**
```python
if [ -z "$ECHO_MCP_URL" ]; then
  echo "Warning: ECHO_MCP_URL is not set. Some features may not work."
fi

```
