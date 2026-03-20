from __future__ import annotations

import serial.tools.list_ports


class PortService:
    @staticmethod
    def list_ports() -> list[str]:
        return [p.device for p in serial.tools.list_ports.comports()]
