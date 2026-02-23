# MiniPanel LLM API Tester

Desktop panel built with PySide6 to test OpenAI-style endpoints (chat/completions) with streaming, profiles, and basic metrics.

## Features
- Quick connection setup (base URL, endpoint, API key, extra headers).
- Request editor (model, system/user prompt, parameters, streaming).
- Response views for text, JSON, and metadata.
- Metrics: status, total time, TTFB, approximate tokens/sec.
- Locally saved profiles.
- Accordion sections to collapse Connection and Request.

## Requirements
- Python 3.9+
- Dependencies: `PySide6`, `requests`

## Install
```bash
pip install PySide6 requests
```

## Run
```bash
python main.py
```

You can also run:
```bash
python llm_panel.py
```

## Notes
- Profiles are saved to `~/.llm_panel_profiles.json`.
- `Copy cURL (reveal key)` exposes the API key. Use with care.
- Token calculation is a simple heuristic, not exact.

## Structure
- `main.py`: entrypoint.
- `llm_panel.py`: legacy wrapper entrypoint.
- `app/config.py`: constants and config dataclass.
- `app/utils.py`: helpers.
- `app/storage.py`: profiles persistence.
- `app/client.py`: HTTP client and request builders.
- `app/worker.py`: Qt worker.
- `app/ui.py`: UI and app startup.
