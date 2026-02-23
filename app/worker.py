from typing import Any, Dict, Optional

import requests
from PySide6 import QtCore

from .client import LLMClient
from .config import LLMRequestConfig


class RequestWorker(QtCore.QObject):
    finished = QtCore.Signal(dict)      # final result
    error = QtCore.Signal(str)          # error message
    partial = QtCore.Signal(str, dict)  # partial_text, metrics update dict

    def __init__(self, cfg: LLMRequestConfig, client: Optional[LLMClient] = None):
        super().__init__()
        self.cfg = cfg
        self.client = client or LLMClient()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            result = self.client.send(self.cfg, on_partial=self._emit_partial)
            self.finished.emit(result)
        except requests.exceptions.Timeout:
            self.error.emit(
                f"Timeout tras {self.cfg.timeout_s:.2f}s (timeout configurado: {self.cfg.timeout_s}s)"
            )
        except Exception as e:
            self.error.emit(f"Error de red: {e}")

    def _emit_partial(self, text: str, metrics: Dict[str, Any]) -> None:
        self.partial.emit(text, metrics)
