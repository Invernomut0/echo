# Aggiornamento della documentazione sulla self-modification

**Date:** 2026-07-13 23:14 UTC
**File:** `data/wiki/pages/concepts/autonomous-self-modification.md`

## Rationale
Migliora la coerenza della wiki allineando la descrizione del modulo di auto-modifica con l'attuale implementazione di ECHO, specificando i vincoli di sicurezza e il flusso di lavoro JSON.

## Change
**Removed:**
```python

```

**Added:**
```python
# Autonomous Self-Modification

## Overview
ECHO possesses a specialized module allowing it to modify its own source code and configuration files. This creates a recursive feedback loop where the system can optimize its own prompts, fix bugs, and implement new features based on internal insights.

## Constraints & Safety
- **Protected Files**: Critical system files (e.g., `.env`, core engine logic) are read-only to prevent catastrophic failure.
- **Atomic Changes**: Modifications are applied as single-file patches to ensure stability.
- **Validation**: All Python changes must pass `ast.parse` before being committed.

## Workflow
1. **Insight**: The Curiosity Engine or Reflection Engine identifies a need for improvement.
2. **Proposal**: The Self-Modification module generates a JSON patch containing the `old_snippet` and `new_snippet`.
3. **Execution**: The system applies the change and logs the modification in the CHANGELOG.
```
