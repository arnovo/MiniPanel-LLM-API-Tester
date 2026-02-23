import json
from typing import Any, Callable, Dict, List, Optional

import requests

from .config import LLMRequestConfig
from .utils import normalize_url, now_perf, safe_json_loads


def build_payload(cfg: LLMRequestConfig) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": cfg.model.strip(),
        "messages": [
            {"role": "system", "content": cfg.system_prompt},
            {"role": "user", "content": cfg.user_prompt},
        ],
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "top_p": cfg.top_p,
    }

    stop_val = safe_json_loads(cfg.stop.strip()) if cfg.stop.strip() else None
    if stop_val is not None:
        payload["stop"] = stop_val

    if cfg.stream:
        payload["stream"] = True

    return payload


def build_headers(cfg: LLMRequestConfig) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
    }
    if cfg.api_key.strip():
        headers["Authorization"] = f"Bearer {cfg.api_key.strip()}"

    extra = safe_json_loads(cfg.extra_headers.strip()) if cfg.extra_headers.strip() else None
    if isinstance(extra, dict):
        for k, v in extra.items():
            headers[str(k)] = str(v)
    return headers


def build_curl(cfg: LLMRequestConfig, reveal_key: bool) -> str:
    url = normalize_url(cfg.base_url, cfg.endpoint)
    payload = build_payload(cfg)
    headers = build_headers(cfg)

    curl_headers: List[str] = []
    for k, v in headers.items():
        if k.lower() == "authorization" and not reveal_key:
            v = "Bearer ***"
        curl_headers.append(f"-H {json.dumps(f'{k}: {v}', ensure_ascii=False)}")

    body = json.dumps(payload, ensure_ascii=False)
    curl = f"curl {' '.join(curl_headers)} {json.dumps(url)} -d {json.dumps(body, ensure_ascii=False)}"
    return curl


class LLMClient:
    def send(
        self,
        cfg: LLMRequestConfig,
        on_partial: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        url = normalize_url(cfg.base_url, cfg.endpoint)
        payload = build_payload(cfg)
        headers = build_headers(cfg)
        t0 = now_perf()

        if cfg.stream:
            return self._send_streaming(url, payload, headers, t0, cfg.timeout_s, on_partial)
        return self._send_non_streaming(url, payload, headers, t0, cfg.timeout_s)

    def _send_streaming(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        t0: float,
        timeout_s: int,
        on_partial: Optional[Callable[[str, Dict[str, Any]], None]],
    ) -> Dict[str, Any]:
        r = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=max(1, int(timeout_s)),
            stream=True,
        )
        status = r.status_code

        if status >= 400:
            raw = r.text
            parsed = safe_json_loads(raw)
            dt = now_perf() - t0
            return {
                "url": url,
                "status_code": status,
                "elapsed_s": dt,
                "ttfb_s": None,
                "headers": dict(r.headers),
                "request_payload": payload,
                "response_text": raw,
                "response_json": parsed,
                "streamed_text": "",
            }

        ttfb_s: Optional[float] = None
        acc_text = ""
        last_emit_t = 0.0

        for raw_line in r.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("data:"):
                data_part = line[len("data:") :].strip()
                if data_part == "[DONE]":
                    break

                obj = safe_json_loads(data_part)
                if isinstance(obj, dict):
                    try:
                        choices = obj.get("choices", [])
                        if choices and isinstance(choices, list):
                            delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
                            if isinstance(delta, dict):
                                piece = delta.get("content") or ""
                                if piece:
                                    if ttfb_s is None:
                                        ttfb_s = now_perf() - t0
                                    acc_text += piece
                    except Exception:
                        pass

            if on_partial:
                t_now = now_perf()
                if t_now - last_emit_t >= 0.05:  # 20fps max
                    elapsed = t_now - t0
                    metrics = {
                        "status_code": status,
                        "elapsed_s": elapsed,
                        "ttfb_s": ttfb_s,
                    }
                    on_partial(acc_text, metrics)
                    last_emit_t = t_now

        dt = now_perf() - t0
        if on_partial:
            metrics = {"status_code": status, "elapsed_s": dt, "ttfb_s": ttfb_s}
            on_partial(acc_text, metrics)

        return {
            "url": url,
            "status_code": status,
            "elapsed_s": dt,
            "ttfb_s": ttfb_s,
            "headers": dict(r.headers),
            "request_payload": payload,
            "response_text": "",
            "response_json": None,
            "streamed_text": acc_text,
        }

    def _send_non_streaming(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        t0: float,
        timeout_s: int,
    ) -> Dict[str, Any]:
        r = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=max(1, int(timeout_s)),
        )
        dt = now_perf() - t0

        content_type = r.headers.get("content-type", "")
        raw_text = r.text
        parsed = None
        if "application/json" in content_type.lower():
            parsed = safe_json_loads(raw_text)

        return {
            "url": url,
            "status_code": r.status_code,
            "elapsed_s": dt,
            "ttfb_s": None,
            "headers": dict(r.headers),
            "request_payload": payload,
            "response_text": raw_text,
            "response_json": parsed,
            "streamed_text": "",
        }
