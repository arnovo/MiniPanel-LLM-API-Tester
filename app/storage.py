import json
import os
from typing import Any, Dict


class ProfileStore:
    def __init__(self, path: str) -> None:
        self._path = path

    def load(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def save(self, profiles: Dict[str, Dict[str, Any]]) -> None:
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._path)
