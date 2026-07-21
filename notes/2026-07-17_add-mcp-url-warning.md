# Aggiunta avviso variabile d'ambiente MCP_URL

**Date:** 2026-07-17 13:39 UTC
**File:** `README.md`

## Rationale
Aiuta gli utenti a configurare correttamente la connessione al server MCP, evitando errori di runtime e migliorando l'affidabilità del sistema

## Change
**Removed:**
```python

```

**Added:**
```python

## Configurazione MCP

Assicurati di impostare la variabile d'ambiente `MCP_URL` con l'URL del server MCP prima di avviare ECHO. Esempio:
```bash
export MCP_URL="http://localhost:8000"
```
Se la variabile non è impostata, il sistema terminerà con un errore di connessione.

```
