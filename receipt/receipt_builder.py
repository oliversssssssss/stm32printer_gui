from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

from protocol.command_builder import CommandBuilder, SendStep


class SendStepStatus(Enum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


@dataclass
class SendStepRecord:
    index: int
    step: SendStep
    status: SendStepStatus = SendStepStatus.PENDING
    error_msg: Optional[str] = None

    def mark_sending(self):
        self.status = SendStepStatus.SENDING

    def mark_sent(self):
        self.status = SendStepStatus.SENT

    def mark_failed(self, msg: str):
        self.status = SendStepStatus.FAILED
        self.error_msg = msg


@dataclass
class SendPlan:
    steps: List[SendStepRecord] = field(default_factory=list)
    total: int = 0
    sent_count: int = 0

    def add_step(self, step: SendStep):
        idx = len(self.steps)
        self.steps.append(SendStepRecord(index=idx, step=step))
        self.total = len(self.steps)

    def get_step_by_index(self, idx: int) -> Optional[SendStepRecord]:
        if 0 <= idx < len(self.steps):
            return self.steps[idx]
        return None

    def mark_step_sent(self, idx: int):
        if record := self.get_step_by_index(idx):
            if record.status != SendStepStatus.SENT:
                record.mark_sent()
                self.sent_count += 1

    def mark_step_failed(self, idx: int, msg: str):
        if record := self.get_step_by_index(idx):
            record.mark_failed(msg)

    def reset(self):
        for record in self.steps:
            record.status = SendStepStatus.PENDING
            record.error_msg = None
        self.sent_count = 0


@dataclass(frozen=True)
class BlockStyle:
    align: str = "left"  # left / center / right
    scale: int = 1
    line_spacing: int = 0
    margin_left: int = 0
    margin_right: int = 0


@dataclass
class ReceiptBlock:
    text_lines: List[str]
    align: str = "left"
    scale: int = 1
    line_spacing: Optional[int] = None
    margin_left: Optional[int] = None
    margin_right: Optional[int] = None
    trigger_print: bool = True
    force_reset_style: bool = False


@dataclass
class Receipt:
    blocks: List[ReceiptBlock] = field(default_factory=list)
    name: str = "default"
    description: str = ""


@dataclass
class ReceiptFormData:
    title: str
    date: str
    receipt_no: str
    items_text: str
    total: str
    cash: str
    change: str
    footer: str


class ReceiptBuilder:
    """构造 block 化测试小票与发送计划。

    这一版重点：
    1. 支持模板选择（default / compact / simple_center）
    2. 支持 GUI 参数化测试票内容，而不是只能打印硬编码样例
    3. 继续保持 block -> settings -> text -> trigger 的 MCU 友好策略
    4. 对 block style 做最小化命令输出，减少冗余 step
    """

    _HR = "-" * 24

    def __init__(self):
        self._templates: Dict[str, Callable[[ReceiptFormData], Receipt]] = {
            "default": self._build_default_receipt,
            "compact": self._build_compact_receipt,
            "simple_center": self._build_simple_center_receipt,
        }

    # ===== 对外 API =====
    def list_templates(self) -> List[str]:
        return list(self._templates.keys())

    def build_test_receipt(self) -> Receipt:
        """兼容旧调用，默认仍返回标准测试小票。"""
        return self.build_receipt("default")

    def get_template_form_defaults(self, template_name: str = "default") -> Dict[str, str]:
        data = self._default_form_data(template_name)
        return {
            "title": data.title,
            "date": data.date,
            "receipt_no": data.receipt_no,
            "items_text": data.items_text,
            "total": data.total,
            "cash": data.cash,
            "change": data.change,
            "footer": data.footer,
        }

    def build_receipt(self, template_name: str = "default", overrides: Optional[Dict[str, str]] = None) -> Receipt:
        builder = self._templates.get(template_name)
        if builder is None:
            raise ValueError(f"未知测试小票模板: {template_name}")

        form_data = self._default_form_data(template_name)
        if overrides:
            form_data = self._merge_form_data(form_data, overrides)

        return builder(form_data)

    def encode_receipt(self, receipt: Receipt) -> SendPlan:
        plan = SendPlan()
        plan.add_step(CommandBuilder.init_printer())

        last_style: Optional[BlockStyle] = None
        for block in receipt.blocks:
            block_steps, last_style = self._encode_block(block, last_style)
            for step in block_steps:
                plan.add_step(step)

        return plan

    # ===== 模板默认值 =====
    def _default_form_data(self, template_name: str) -> ReceiptFormData:
        if template_name == "compact":
            return ReceiptFormData(
                title="YINJIAN DRINKS",
                date="2026-03-20",
                receipt_no="1234567890",
                items_text="COLA      1    3.00\nMILK      1   10.00",
                total="13.00",
                cash="20.00",
                change="7.00",
                footer="THANK YOU",
            )
        if template_name == "simple_center":
            return ReceiptFormData(
                title="HELLO",
                date="",
                receipt_no="",
                items_text="WELCOME",
                total="",
                cash="",
                change="",
                footer="YINJIAN",
            )
        return ReceiptFormData(
            title="YINJIAN DRINKS",
            date="2026-03-20",
            receipt_no="1234567890",
            items_text=(
                "COLA      1    3.00\n"
                "BREAD     2    5.00\n"
                "MILK      1   10.00"
            ),
            total="23.00",
            cash="50.00",
            change="27.00",
            footer="THANK YOU COME AGAIN",
        )

    @staticmethod
    def _merge_form_data(base: ReceiptFormData, overrides: Dict[str, str]) -> ReceiptFormData:
        def _value(key: str, current: str) -> str:
            value = overrides.get(key)
            if value is None:
                return current
            return str(value)

        return ReceiptFormData(
            title=_value("title", base.title),
            date=_value("date", base.date),
            receipt_no=_value("receipt_no", base.receipt_no),
            items_text=_value("items_text", base.items_text),
            total=_value("total", base.total),
            cash=_value("cash", base.cash),
            change=_value("change", base.change),
            footer=_value("footer", base.footer),
        )

    @staticmethod
    def _split_nonempty_lines(text: str) -> List[str]:
        return [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]

    # ===== 模板层 =====
    def _build_default_receipt(self, data: ReceiptFormData) -> Receipt:
        header_lines: List[str] = []
        if data.date:
            header_lines.append(f"DATE: {data.date}")
        if data.receipt_no:
            header_lines.append(f"NO: {data.receipt_no}")

        footer_lines = self._split_nonempty_lines(data.footer)
        item_lines = self._split_nonempty_lines(data.items_text)

        blocks: List[ReceiptBlock] = [
            self.title_block(data.title or "TITLE", scale=2, force_reset_style=True),
        ]
        if header_lines:
            blocks.append(self.text_block(header_lines))
        blocks.extend([
            self.rule_block(),
            self.text_block(["ITEM    QTY   PRICE"]),
        ])
        if item_lines:
            blocks.append(self.text_block(item_lines))
        blocks.append(self.rule_block())
        if data.total:
            blocks.append(self.total_block(f"TOTAL: {data.total}", scale=2, force_reset_style=True))
        if data.cash or data.change:
            cash_line = f"CASH: {data.cash or '-'}  CHANGE: {data.change or '-'}"
            blocks.append(self.text_block([cash_line]))
        if footer_lines:
            blocks.append(self.center_block(footer_lines))

        return Receipt(
            name="default",
            description="标准联调用测试小票，覆盖标题/明细/总价/结束语，可由 GUI 自定义内容",
            blocks=blocks,
        )

    def _build_compact_receipt(self, data: ReceiptFormData) -> Receipt:
        lines: List[str] = []
        if data.date:
            lines.append(f"DATE: {data.date}")
        if data.receipt_no:
            lines.append(f"NO: {data.receipt_no}")
        footer_lines = self._split_nonempty_lines(data.footer) or ["THANK YOU"]

        blocks: List[ReceiptBlock] = [
            self.title_block(data.title or "TITLE", scale=2, force_reset_style=True),
        ]
        if lines:
            blocks.append(self.text_block(lines))
        if data.total:
            blocks.append(self.total_block(f"TOTAL: {data.total}", scale=2, force_reset_style=True))
        blocks.append(self.center_block(footer_lines))

        return Receipt(
            name="compact",
            description="更短的联调模板，适合快速验证 block 边界与样式切换",
            blocks=blocks,
        )

    def _build_simple_center_receipt(self, data: ReceiptFormData) -> Receipt:
        center_lines = self._split_nonempty_lines(data.items_text) or ["WELCOME"]
        footer_lines = self._split_nonempty_lines(data.footer) or ["YINJIAN"]
        return Receipt(
            name="simple_center",
            description="最小模板，用于快速验证居中/放大/打印触发，可从 GUI 自定义标题和文案",
            blocks=[
                self.title_block(data.title or "HELLO", scale=2, force_reset_style=True),
                self.center_block(center_lines, force_reset_style=False),
                self.center_block(footer_lines, force_reset_style=False),
            ],
        )

    # ===== Block 工厂 =====
    def title_block(
        self,
        text: str,
        *,
        scale: int = 2,
        line_spacing: Optional[int] = 0,
        force_reset_style: bool = False,
    ) -> ReceiptBlock:
        return ReceiptBlock(
            text_lines=[text],
            align="center",
            scale=scale,
            line_spacing=line_spacing,
            margin_left=0,
            margin_right=0,
            trigger_print=True,
            force_reset_style=force_reset_style,
        )

    def total_block(
        self,
        text: str,
        *,
        scale: int = 2,
        force_reset_style: bool = False,
    ) -> ReceiptBlock:
        return ReceiptBlock(
            text_lines=[text],
            align="right",
            scale=scale,
            line_spacing=0,
            margin_left=0,
            margin_right=0,
            trigger_print=True,
            force_reset_style=force_reset_style,
        )

    def rule_block(self) -> ReceiptBlock:
        return self.text_block([self._HR], align="left", scale=1)

    def center_block(
        self,
        lines: List[str],
        *,
        scale: int = 1,
        line_spacing: Optional[int] = 0,
        force_reset_style: bool = False,
    ) -> ReceiptBlock:
        return self.text_block(
            lines,
            align="center",
            scale=scale,
            line_spacing=line_spacing,
            force_reset_style=force_reset_style,
        )

    def text_block(
        self,
        lines: List[str],
        *,
        align: str = "left",
        scale: int = 1,
        line_spacing: Optional[int] = 0,
        margin_left: Optional[int] = 0,
        margin_right: Optional[int] = 0,
        trigger_print: bool = True,
        force_reset_style: bool = False,
    ) -> ReceiptBlock:
        return ReceiptBlock(
            text_lines=lines,
            align=align,
            scale=scale,
            line_spacing=line_spacing,
            margin_left=margin_left,
            margin_right=margin_right,
            trigger_print=trigger_print,
            force_reset_style=force_reset_style,
        )

    # ===== 编码层 =====
    def _normalize_style(self, block: ReceiptBlock) -> BlockStyle:
        return BlockStyle(
            align=block.align,
            scale=max(1, min(3, int(block.scale))),
            line_spacing=0 if block.line_spacing is None else max(0, min(255, int(block.line_spacing))),
            margin_left=0 if block.margin_left is None else max(0, min(255, int(block.margin_left))),
            margin_right=0 if block.margin_right is None else max(0, min(255, int(block.margin_right))),
        )

    def _encode_block(self, block: ReceiptBlock, last_style: Optional[BlockStyle]) -> tuple[List[SendStep], BlockStyle]:
        steps: List[SendStep] = []
        style = self._normalize_style(block)

        if block.force_reset_style:
            last_style = None

        if last_style is None or style.align != last_style.align:
            if style.align == "left":
                steps.append(CommandBuilder.align_left())
            elif style.align == "center":
                steps.append(CommandBuilder.align_center())
            elif style.align == "right":
                steps.append(CommandBuilder.align_right())
            else:
                raise ValueError(f"未知 align: {style.align}")

        if last_style is None or style.scale != last_style.scale:
            steps.append(CommandBuilder.scale(style.scale))

        if last_style is None or style.line_spacing != last_style.line_spacing:
            steps.append(CommandBuilder.line_spacing(style.line_spacing))

        if last_style is None or style.margin_left != last_style.margin_left:
            steps.append(CommandBuilder.left_margin(style.margin_left))

        if last_style is None or style.margin_right != last_style.margin_right:
            steps.append(CommandBuilder.right_margin(style.margin_right))

        block_text = "\n".join(block.text_lines)
        steps.append(CommandBuilder.text_step(block_text, append_crlf=False))

        if block.trigger_print:
            steps.append(CommandBuilder.print_trigger_lf())

        return steps, style
