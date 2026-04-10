from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SendStep:
    payload: bytes
    desc: str


class CommandBuilder:
    """构造 UART1 发送字节流。"""

    IMAGE_MAX_WIDTH = 384
    IMAGE_MAX_HEIGHT = 256
    IMAGE_DATA_MAX_PAYLOAD = 192

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

    @staticmethod
    def image_begin_step(width: int, height: int) -> SendStep:
        width = int(width)
        height = int(height)

        if width <= 0 or width > CommandBuilder.IMAGE_MAX_WIDTH:
            raise ValueError(f"图片宽度必须在 1~{CommandBuilder.IMAGE_MAX_WIDTH} 之间")
        if height <= 0 or height > CommandBuilder.IMAGE_MAX_HEIGHT:
            raise ValueError(f"图片高度必须在 1~{CommandBuilder.IMAGE_MAX_HEIGHT} 之间")

        payload = bytes([
            0x1B, 0x49, 0x42,
            (width >> 8) & 0xFF, width & 0xFF,
            (height >> 8) & 0xFF, height & 0xFF,
        ])
        return SendStep(payload=payload, desc=f"IMAGE_BEGIN {width}x{height}")

    @staticmethod
    def image_data_step(seq: int, payload_data: bytes) -> SendStep:
        seq = int(seq)
        if seq < 0 or seq > 0xFFFF:
            raise ValueError("图片块序号必须在 0~65535 之间")
        if not payload_data:
            raise ValueError("图片数据块不能为空")
        if len(payload_data) > CommandBuilder.IMAGE_DATA_MAX_PAYLOAD:
            raise ValueError(
                f"单个图片数据块不能超过 {CommandBuilder.IMAGE_DATA_MAX_PAYLOAD} 字节"
            )

        payload_len = len(payload_data)
        header = bytes([
            0x1B, 0x49, 0x44,
            (seq >> 8) & 0xFF, seq & 0xFF,
            (payload_len >> 8) & 0xFF, payload_len & 0xFF,
        ])
        return SendStep(
            payload=header + payload_data,
            desc=f"IMAGE_DATA seq={seq} len={payload_len}",
        )

    @staticmethod
    def image_end_step(chunk_count: int) -> SendStep:
        chunk_count = int(chunk_count)
        if chunk_count < 0 or chunk_count > 0xFFFF:
            raise ValueError("图片块总数必须在 0~65535 之间")

        payload = bytes([
            0x1B, 0x49, 0x45,
            (chunk_count >> 8) & 0xFF, chunk_count & 0xFF,
        ])
        return SendStep(payload=payload, desc=f"IMAGE_END chunks={chunk_count}")
