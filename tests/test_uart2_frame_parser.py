import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from protocol.uart2_frame_parser import UART2FrameParser, ParseStatus


def test_valid_frame():
    parser = UART2FrameParser()
    parser.feed_line("@FRAME_BEGIN")
    parser.feed_line("TYPE=DOTMATRIX")
    parser.feed_line("MODE=NORMAL")
    parser.feed_line("WIDTH=384")
    parser.feed_line("HEIGHT=2")
    parser.feed_line("ROW=111000")
    parser.feed_line("ROW=000111")
    result = parser.feed_line("@FRAME_END")
    assert result.is_success()
    assert result.frame is not None
    assert result.frame["TYPE"] == "DOTMATRIX"
    assert result.frame["MODE"] == "NORMAL"
    assert result.frame["WIDTH"] == 384
    assert result.frame["HEIGHT"] == 2
    assert len(result.frame["ROWS"]) == 2


def test_incomplete_frame():
    parser = UART2FrameParser()
    result = parser.feed_line("@FRAME_BEGIN")
    assert result.is_incomplete()
    result = parser.feed_line("TYPE=DOTMATRIX")
    assert result.is_incomplete()


def test_missing_type():
    parser = UART2FrameParser()
    parser.feed_line("@FRAME_BEGIN")
    parser.feed_line("MODE=NORMAL")
    parser.feed_line("WIDTH=384")
    parser.feed_line("HEIGHT=2")
    parser.feed_line("ROW=111000")
    parser.feed_line("ROW=000111")
    result = parser.feed_line("@FRAME_END")
    assert result.is_error()
    assert "TYPE" in (result.error_msg or "")


def test_unsupported_type():
    parser = UART2FrameParser()
    parser.feed_line("@FRAME_BEGIN")
    parser.feed_line("TYPE=UNKNOWN")
    parser.feed_line("MODE=NORMAL")
    parser.feed_line("WIDTH=384")
    parser.feed_line("HEIGHT=2")
    parser.feed_line("ROW=111000")
    parser.feed_line("ROW=000111")
    result = parser.feed_line("@FRAME_END")
    assert result.is_error()
    assert "不支持的 TYPE" in (result.error_msg or "")


def test_invalid_dimensions():
    parser = UART2FrameParser()
    parser.feed_line("@FRAME_BEGIN")
    parser.feed_line("TYPE=DOTMATRIX")
    parser.feed_line("MODE=NORMAL")
    parser.feed_line("WIDTH=0")
    parser.feed_line("HEIGHT=0")
    parser.feed_line("ROW=111000")
    result = parser.feed_line("@FRAME_END")
    assert result.is_error()
    assert "WIDTH/HEIGHT" in (result.error_msg or "")


def test_missing_rows():
    parser = UART2FrameParser()
    parser.feed_line("@FRAME_BEGIN")
    parser.feed_line("TYPE=DOTMATRIX")
    parser.feed_line("MODE=NORMAL")
    parser.feed_line("WIDTH=384")
    parser.feed_line("HEIGHT=2")
    result = parser.feed_line("@FRAME_END")
    assert result.is_error()
    assert "ROW" in (result.error_msg or "")


def test_row_width_correction():
    parser = UART2FrameParser()
    parser.feed_line("@FRAME_BEGIN")
    parser.feed_line("TYPE=DOTMATRIX")
    parser.feed_line("MODE=NORMAL")
    parser.feed_line("WIDTH=10")
    parser.feed_line("HEIGHT=1")
    parser.feed_line("ROW=111")
    result = parser.feed_line("@FRAME_END")
    assert result.is_success()
    assert len(result.frame["ROWS"][0]) == 10
    assert result.frame["ROWS"][0] == "1110000000"


def test_row_count_mismatch():
    parser = UART2FrameParser()
    parser.feed_line("@FRAME_BEGIN")
    parser.feed_line("TYPE=DOTMATRIX")
    parser.feed_line("MODE=NORMAL")
    parser.feed_line("WIDTH=6")
    parser.feed_line("HEIGHT=2")
    parser.feed_line("ROW=111000")
    parser.feed_line("ROW=000111")
    parser.feed_line("ROW=101010")
    result = parser.feed_line("@FRAME_END")
    assert result.is_success()
    assert result.frame["HEIGHT"] == 3


def test_reset():
    parser = UART2FrameParser()
    parser.feed_line("@FRAME_BEGIN")
    parser.feed_line("TYPE=DOTMATRIX")
    parser.reset()
    assert parser.frame_active is False
    assert parser.frame_lines == []
