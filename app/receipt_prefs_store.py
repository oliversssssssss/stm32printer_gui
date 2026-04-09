from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


class ReceiptPrefsStore:
    """测试小票 UI 偏好持久化存储。

    当前持久化内容：
    1. selected_template
    2. forms_by_template
    3. use_recommended_strategy
    4. manual_strategy_choice
    """

    def __init__(self, filepath: Optional[str] = None):
        if filepath:
            self.filepath = Path(filepath)
        else:
            self.filepath = Path(__file__).resolve().parent / "receipt_prefs.json"

    def load(self) -> Dict[str, Any]:
        if not self.filepath.exists():
            return {}

        try:
            raw = self.filepath.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                return {}
            return data
        except Exception:
            return {}

    def save(
        self,
        *,
        selected_template: str,
        forms_by_template: Dict[str, Dict[str, str]],
        use_recommended_strategy: bool = True,
        manual_strategy_choice: str = "block_step_stable",
    ) -> None:
        payload = {
            "selected_template": selected_template,
            "forms_by_template": forms_by_template,
            "use_recommended_strategy": bool(use_recommended_strategy),
            "manual_strategy_choice": str(manual_strategy_choice),
        }

        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.filepath.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )