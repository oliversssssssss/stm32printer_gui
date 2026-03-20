import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from protocol.command_builder import CommandBuilder, SendStep


def test_text_step():
    step = CommandBuilder.text_step("Hello")
    assert isinstance(step, SendStep)
    assert step.payload == b"Hello"
    assert step.desc == "TEXT: Hello"


def test_text_step_with_crlf():
    step = CommandBuilder.text_step("Hello", append_crlf=True)
    assert step.payload == b"Hello\r\n"


def test_hex_step():
    step = CommandBuilder.hex_step("1B 40")
    assert step.payload == bytes([0x1B, 0x40])
    assert "HEX" in step.desc


def test_hex_step_various_formats():
    step1 = CommandBuilder.hex_step("1B 40")
    step2 = CommandBuilder.hex_step("1B,40")
    step3 = CommandBuilder.hex_step("1B40")
    assert step1.payload == step2.payload == step3.payload


def test_init_printer():
    step = CommandBuilder.init_printer()
    assert step.payload == bytes([0x1B, 0x40])


def test_align_commands():
    left = CommandBuilder.align_left()
    assert left.payload == bytes([0x1B, 0x61, 0x00])

    center = CommandBuilder.align_center()
    assert center.payload == bytes([0x1B, 0x61, 0x01])

    right = CommandBuilder.align_right()
    assert right.payload == bytes([0x1B, 0x61, 0x02])


def test_line_spacing():
    step = CommandBuilder.line_spacing(8)
    assert step.payload == bytes([0x1B, 0x33, 8])
    step_min = CommandBuilder.line_spacing(-1)
    assert step_min.payload == bytes([0x1B, 0x33, 0])
    step_max = CommandBuilder.line_spacing(300)
    assert step_max.payload == bytes([0x1B, 0x33, 255])


def test_margin_commands():
    left = CommandBuilder.left_margin(10)
    assert left.payload == bytes([0x1B, 0x4C, 10])
    right = CommandBuilder.right_margin(20)
    assert right.payload == bytes([0x1B, 0x72, 20])


def test_scale_command():
    step = CommandBuilder.scale(2)
    assert step.payload == bytes([0x1B, 0x45, 2])
    step_min = CommandBuilder.scale(0)
    assert step_min.payload == bytes([0x1B, 0x45, 1])
    step_max = CommandBuilder.scale(10)
    assert step_max.payload == bytes([0x1B, 0x45, 3])


def test_print_triggers():
    lf = CommandBuilder.print_trigger_lf()
    assert lf.payload == bytes([0x0A, 0x00])
    ff = CommandBuilder.print_trigger_ff()
    assert ff.payload == bytes([0x0C, 0x00])
