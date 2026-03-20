import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from receipt.receipt_builder import ReceiptBuilder, ReceiptBlock, Receipt, SendPlan, SendStepStatus
from protocol.command_builder import CommandBuilder


def test_receipt_block_creation():
    block = ReceiptBlock(text_lines=["Hello", "World"], align="center", scale=2)
    assert block.text_lines == ["Hello", "World"]
    assert block.align == "center"
    assert block.scale == 2
    assert block.trigger_print is True


def test_receipt_creation():
    receipt = Receipt(blocks=[ReceiptBlock(["Title"]), ReceiptBlock(["Content"])])
    assert len(receipt.blocks) == 2


def test_build_test_receipt():
    builder = ReceiptBuilder()
    receipt = builder.build_test_receipt()
    assert len(receipt.blocks) > 0
    assert receipt.blocks[0].text_lines[0] == "YINJIAN DRINKS"


def test_encode_receipt():
    builder = ReceiptBuilder()
    receipt = builder.build_test_receipt()
    plan = builder.encode_receipt(receipt)
    assert isinstance(plan, SendPlan)
    assert plan.total > 0
    assert len(plan.steps) == plan.total


def test_send_plan_mark_sent():
    plan = SendPlan()
    plan.add_step(CommandBuilder.init_printer())
    plan.add_step(CommandBuilder.align_center())
    assert plan.sent_count == 0
    plan.mark_step_sent(0)
    assert plan.sent_count == 1
    assert plan.steps[0].status == SendStepStatus.SENT


def test_send_plan_mark_failed():
    plan = SendPlan()
    plan.add_step(CommandBuilder.init_printer())
    plan.mark_step_failed(0, "Connection lost")
    assert plan.steps[0].status == SendStepStatus.FAILED
    assert plan.steps[0].error_msg == "Connection lost"


def test_send_plan_all_sent():
    plan = SendPlan()
    plan.add_step(CommandBuilder.init_printer())
    plan.add_step(CommandBuilder.align_center())
    assert not plan.all_sent()
    plan.mark_step_sent(0)
    assert not plan.all_sent()
    plan.mark_step_sent(1)
    assert plan.all_sent()


def test_send_plan_reset():
    plan = SendPlan()
    plan.add_step(CommandBuilder.init_printer())
    plan.mark_step_sent(0)
    assert plan.sent_count == 1
    plan.reset()
    assert plan.sent_count == 0
    assert plan.steps[0].status == SendStepStatus.PENDING


def test_send_plan_get_pending():
    plan = SendPlan()
    plan.add_step(CommandBuilder.init_printer())
    plan.add_step(CommandBuilder.align_center())
    plan.add_step(CommandBuilder.align_left())
    pending = plan.get_pending_steps()
    assert len(pending) == 3
    plan.mark_step_sent(0)
    pending = plan.get_pending_steps()
    assert len(pending) == 2


def test_encode_block_with_parameters():
    builder = ReceiptBuilder()
    block = ReceiptBlock(
        text_lines=["Test"],
        align="center",
        scale=2,
        line_spacing=10,
        margin_left=5,
        margin_right=5,
    )
    steps = builder._encode_block(block)
    assert len(steps) >= 6
