from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SendStep:
    payload: bytes
    desc: str


class CommandBuilder:
    """构造 UART1 发送字节流。

    说明：
    - 标准 / 近标准：ESC @ / ESC a n / ESC 3 n
    - 项目扩展：ESC L n / ESC r n / ESC E n / 0A 00 / 0C 00
    """

    @staticmethod
    def text_step(text: str, append_crlf: bool = False) -> SendStep:
        payload = text.encode("ascii", errors="replace")
        if append_crlf:
            payload += b"\r\n"
        return SendStep(payload=payload, desc=f"TEXT: {text}")

    @staticmethod
    def hex_step(hex_text: str) -> SendStep:
        hex_str = hex_text.replace(" ", "").replace(",", "").replace("0x", "").replace("0X", "")
        if len(hex_str) % 2 != 0:
            raise ValueError("HEX 长度必须为偶数")
        payload = bytes.fromhex(hex_str)
        return SendStep(payload=payload, desc=f"HEX: {hex_text}")

    @staticmethod
    def init_printer() -> SendStep:
        return SendStep(bytes([0x1B, 0x40]), "ESC @")

    @staticmethod
    def align_left() -> SendStep:
        return SendStep(bytes([0x1B, 0x61, 0x00]), "ESC a 0")

    @staticmethod
    def align_center() -> SendStep:
        return SendStep(bytes([0x1B, 0x61, 0x01]), "ESC a 1")

    @staticmethod
    def align_right() -> SendStep:
        return SendStep(bytes([0x1B, 0x61, 0x02]), "ESC a 2")

    @staticmethod
    def line_spacing(n: int) -> SendStep:
        n = max(0, min(255, int(n)))
        return SendStep(bytes([0x1B, 0x33, n]), f"ESC 3 {n}")

    @staticmethod
    def left_margin(n: int) -> SendStep:
        n = max(0, min(255, int(n)))
        return SendStep(bytes([0x1B, 0x4C, n]), f"ESC L {n}")

    @staticmethod
    def right_margin(n: int) -> SendStep:
        n = max(0, min(255, int(n)))
        return SendStep(bytes([0x1B, 0x72, n]), f"ESC r {n}")

    @staticmethod
    def scale(n: int) -> SendStep:
        n = max(1, min(3, int(n)))
        return SendStep(bytes([0x1B, 0x45, n]), f"ESC E {n}")

    @staticmethod
    def print_trigger_lf() -> SendStep:
        return SendStep(bytes([0x0A, 0x00]), "0A 00")

    @staticmethod
    def print_trigger_ff() -> SendStep:
        return SendStep(bytes([0x0C, 0x00]), "0C 00")
