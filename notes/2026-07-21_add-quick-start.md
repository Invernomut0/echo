# Aggiunta di una sezione "Quick Start" per facilitare l'avvio rapido di ECHO

**Date:** 2026-07-21 20:13 UTC
**File:** `README.md`

## Rationale
Fornire istruzioni concise aiuta gli utenti a configurare e lanciare il sistema senza dover cercare tra la documentazione, migliorando l'esperienza d'uso

## Change
**Removed:**
```python

```

**Added:**
```python

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/echo.git
   cd echo
   ```
2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure environment variables**
   - Copy the example file:
     ```bash
     cp .env.example .env
     ```
   - Edit `.env` with your API keys and preferences.
4. **Run the startup script**
   ```bash
   ./start.sh
   ```
   This will launch the backend, the React frontend, and schedule cron tasks.
5. **Access the UI**
   Open your browser and navigate to `http://localhost:3000`.

Feel free to explore the documentation for advanced configuration and customization.

```
