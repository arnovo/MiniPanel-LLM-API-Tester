import json
import time
from typing import Any, Dict, Optional, Tuple


def pretty_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


def safe_json_loads(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except Exception:
        return None


def normalize_url(base_url: str, endpoint: str) -> str:
    base = base_url.strip().rstrip("/")
    ep = endpoint.strip()
    if not ep.startswith("/"):
        ep = "/" + ep
    return base + ep


def now_perf() -> float:
    return time.perf_counter()


def extract_text_and_usage(resp_json: Any) -> Tuple[str, Dict[str, Any]]:
    """Best-effort extraction for OpenAI-compatible responses."""
    text = ""
    usage: Dict[str, Any] = {}
    if isinstance(resp_json, dict):
        usage = resp_json.get("usage") or {}
        choices = resp_json.get("choices")
        if isinstance(choices, list) and choices:
            c0 = choices[0]
            if isinstance(c0, dict):
                msg = c0.get("message")
                if isinstance(msg, dict):
                    text = msg.get("content") or ""
                if not text and isinstance(c0.get("text"), str):
                    text = c0["text"]
    return text, usage


def estimate_tokens(text: str) -> int:
    """
    Heuristica simple (no exacta). Util para comparar rendimiento.
    Aproximacion comun: ~4 chars/token en ingles; en ES suele ser similar.
    """
    if not text:
        return 0
    return max(1, int(len(text) / 4))
