# Aggiunge controllo per la variabile d'ambiente OPENAI_API_KEY

**Date:** 2026-07-18 08:24 UTC
**File:** `start.sh`

## Rationale
Garantisce che l'utente sia avvisato se la chiave API di OpenAI non è impostata, evitando errori di runtime durante le chiamate LLM

## Change
**Removed:**
```python

```

**Added:**
```python
# Verify OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
  echo "Warning: OPENAI_API_KEY environment variable is not set. Some functionalities may be limited."
fi

```
