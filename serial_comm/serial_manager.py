from __future__ import annotations

import threading
from typing import Callable, Optional

import serial


LineCallback = Callable[[str, str], None]


class SerialManager:
    def __init__(self, line_callback: LineCallback):
        self._line_callback = line_callback

        self.ser_uart1: Optional[serial.Serial] = None
        self.ser_uart2: Optional[serial.Serial] = None

        self._stop_uart1 = threading.Event()
        self._stop_uart2 = threading.Event()
        self._uart1_thread: Optional[threading.Thread] = None
        self._uart2_thread: Optional[threading.Thread] = None

    def connect_uart1(self, port: str, baudrate: int) -> None:
        self.disconnect_uart1()
        self.ser_uart1 = serial.Serial(port=port, baudrate=baudrate, timeout=0.1)
        self._stop_uart1.clear()
        self._uart1_thread = threading.Thread(
            target=self._reader_worker,
            args=(self.ser_uart1, self._stop_uart1, "uart1"),
            daemon=True,
        )
        self._uart1_thread.start()

    def disconnect_uart1(self) -> None:
        self._stop_uart1.set()
        if self.ser_uart1 is not None:
            try:
                self.ser_uart1.close()
            except Exception:
                pass
            self.ser_uart1 = None

    def connect_uart2(self, port: str, baudrate: int) -> None:
        self.disconnect_uart2()
        self.ser_uart2 = serial.Serial(port=port, baudrate=baudrate, timeout=0.1)
        self._stop_uart2.clear()
        self._uart2_thread = threading.Thread(
            target=self._reader_worker,
            args=(self.ser_uart2, self._stop_uart2, "uart2"),
            daemon=True,
        )
        self._uart2_thread.start()

    def disconnect_uart2(self) -> None:
        self._stop_uart2.set()
        if self.ser_uart2 is not None:
            try:
                self.ser_uart2.close()
            except Exception:
                pass
            self.ser_uart2 = None

    def disconnect_all(self) -> None:
        self.disconnect_uart1()
        self.disconnect_uart2()

    def uart1_connected(self) -> bool:
        return self.ser_uart1 is not None and self.ser_uart1.is_open

    def uart2_connected(self) -> bool:
        return self.ser_uart2 is not None and self.ser_uart2.is_open

    def send_uart1(self, payload: bytes) -> None:
        if not self.uart1_connected():
            raise RuntimeError("UART1 未连接")
        assert self.ser_uart1 is not None
        self.ser_uart1.write(payload)
        self.ser_uart1.flush()

    def _reader_worker(self, ser: serial.Serial, stop_evt: threading.Event, source: str) -> None:
        buf = b""
        while not stop_evt.is_set():
            try:
                chunk = ser.read(ser.in_waiting or 1)
                if not chunk:
                    continue
                buf += chunk

                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace").rstrip("\r")
                    self._line_callback(source, text)
            except serial.SerialException as e:
                self._line_callback("host", f"[HOST] 串口异常（{source}）：{e}\n")
                break
            except Exception as e:
                self._line_callback("host", f"[HOST] 读取异常（{source}）：{e}\n")
                break
