from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any


class ReceiptPrefsStore:
    """保存/读取测试小票模板选择与表单内容。"""

    def __init__(self, path: Path | None = None):
        if path is None:
            # app/receipt_prefs_store.py -> project root / .printer_host_receipt_state.json
            path = Path(__file__).resolve().parents[1] / ".printer_host_receipt_state.json"
        self.path = path

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def save(self, selected_template: str, forms_by_template: Dict[str, Dict[str, str]]) -> None:
        payload = {
            "selected_template": selected_template,
            "forms_by_template": forms_by_template,
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
