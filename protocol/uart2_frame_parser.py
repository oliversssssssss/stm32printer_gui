from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class ParseStatus(Enum):
    SUCCESS = "success"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"
    ERROR = "error"


@dataclass
class ParseResult:
    status: ParseStatus
    frame: Optional[dict] = None
    error_msg: Optional[str] = None

    def is_success(self) -> bool:
        return self.status == ParseStatus.SUCCESS

    def is_incomplete(self) -> bool:
        return self.status == ParseStatus.INCOMPLETE

    def is_error(self) -> bool:
        return self.status in (ParseStatus.INVALID, ParseStatus.ERROR)


class UART2FrameParser:
    def __init__(self) -> None:
        self.frame_active = False
        self.frame_lines: List[str] = []

    def feed_line(self, line: str) -> ParseResult:
        s = line.strip()
        if not s:
            return ParseResult(status=ParseStatus.INCOMPLETE)

        if s == "@FRAME_BEGIN":
            if self.frame_active and self.frame_lines:
                self._log_warning("上一帧未完成就收到新 @FRAME_BEGIN，丢弃上一帧")
                self.frame_lines = []
            self.frame_active = True
            self.frame_lines = [s]
            return ParseResult(status=ParseStatus.INCOMPLETE)

        if self.frame_active:
            self.frame_lines.append(s)
            if s == "@FRAME_END":
                self.frame_active = False
                frame_list = self.frame_lines[:]
                self.frame_lines = []
                return self._parse_frame(frame_list)
            return ParseResult(status=ParseStatus.INCOMPLETE)

        return ParseResult(status=ParseStatus.INCOMPLETE)

    def reset(self):
        self.frame_active = False
        self.frame_lines = []

    def _parse_frame(self, lines: List[str]) -> ParseResult:
        frame = {
            "TYPE": "",
            "MODE": "",
            "WIDTH": 0,
            "HEIGHT": 0,
            "ROWS": [],
        }

        try:
            for line in lines:
                if line.startswith("TYPE="):
                    frame["TYPE"] = line.split("=", 1)[1].strip()
                elif line.startswith("MODE="):
                    frame["MODE"] = line.split("=", 1)[1].strip()
                elif line.startswith("WIDTH="):
                    frame["WIDTH"] = int(line.split("=", 1)[1].strip())
                elif line.startswith("HEIGHT="):
                    frame["HEIGHT"] = int(line.split("=", 1)[1].strip())
                elif line.startswith("ROW="):
                    frame["ROWS"].append(line.split("=", 1)[1].strip())

            if not frame["TYPE"]:
                return ParseResult(status=ParseStatus.INVALID, error_msg="缺少 TYPE 字段")
            if frame["TYPE"] != "DOTMATRIX":
                return ParseResult(status=ParseStatus.INVALID, error_msg=f"不支持的 TYPE: {frame['TYPE']}")
            if frame["WIDTH"] <= 0 or frame["HEIGHT"] <= 0:
                return ParseResult(status=ParseStatus.INVALID, error_msg=f"WIDTH/HEIGHT 必须 > 0: ({frame['WIDTH']}, {frame['HEIGHT']})")
            if not frame["ROWS"]:
                return ParseResult(status=ParseStatus.INVALID, error_msg="缺少 ROW 数据")

            if len(frame["ROWS"]) != frame["HEIGHT"]:
                self._log_warning(f"ROW 数量 ({len(frame['ROWS'])}) 不等于 HEIGHT ({frame['HEIGHT']})，修正为实际行数")
                frame["HEIGHT"] = len(frame["ROWS"])

            rows = []
            width = frame["WIDTH"]
            for row in frame["ROWS"]:
                if len(row) < width:
                    row = row + ("0" * (width - len(row)))
                elif len(row) > width:
                    row = row[:width]
                rows.append(row)
            frame["ROWS"] = rows

            return ParseResult(status=ParseStatus.SUCCESS, frame=frame)

        except ValueError as e:
            return ParseResult(status=ParseStatus.ERROR, error_msg=f"解析异常：{str(e)}")
        except Exception as e:
            return ParseResult(status=ParseStatus.ERROR, error_msg=f"未知异常：{str(e)}")

    def _log_warning(self, msg: str):
        print(f"[UART2Parser WARNING] {msg}", flush=True)

