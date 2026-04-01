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
    align: str = "left"
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


@dataclass(frozen=True)
class ReceiptStats:
    total_blocks: int
    total_nonempty_lines: int
    total_chars: int
    max_block_chars: int
    style_transitions: int
    emphasis_block_count: int
    money_block_count: int
    multiline_block_count: int


class ReceiptBuilder:
    """构造测试小票与发送计划。

    当前支持三类发送策略：

    1. block_step_stable
       - 当前稳定策略
       - 每个 block 按现有样式命令 + TEXT + trigger 发送
       - 兼容现有稳定 MCU 主链

    2. single_shot_plain
       - 将同一张 receipt 平铺成一个 plain-text 大块
       - 最后只发送一次 trigger
       - 不保留真正的块内样式，仅保留“视觉上的”左右/居中排版

    3. block_fewer_triggers_style
       - 保留 block 样式分组
       - 将“相邻且样式相同”的 block 合并
       - 在尽量保留样式的前提下，减少 trigger 次数

    当前这一轮新增：
    - 推荐策略可按实际 receipt 内容动态判定，而不仅仅按模板名固定映射。
    """

    STRATEGY_BLOCK_STEP_STABLE = "block_step_stable"
    STRATEGY_SINGLE_SHOT_PLAIN = "single_shot_plain"
    STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE = "block_fewer_triggers_style"

    RECEIPT_WIDTH = 24
    ITEM_NAME_WIDTH = 12
    ITEM_QTY_WIDTH = 5
    ITEM_PRICE_WIDTH = 7
    _HR = "-" * RECEIPT_WIDTH

    MONEY_KEYWORDS = ("TOTAL", "CASH", "CHANGE")

    def __init__(self):
        self._templates: Dict[str, Callable[[ReceiptFormData], Receipt]] = {
            "default": self._build_default_receipt,
            "compact": self._build_compact_receipt,
            "simple_center": self._build_simple_center_receipt,
            # 兼容保留原实验模板
            "single_shot_plain": self._build_single_shot_plain_receipt,
        }

    def list_templates(self) -> List[str]:
        return list(self._templates.keys())

    def list_send_strategies(self) -> List[str]:
        return [
            self.STRATEGY_BLOCK_STEP_STABLE,
            self.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE,
            self.STRATEGY_SINGLE_SHOT_PLAIN,
        ]

    def get_recommended_strategy(
        self,
        template_name: str,
        receipt: Optional[Receipt] = None,
    ) -> str:
        """推荐策略。

        优先级：
        1. 如果提供了 receipt，则按当前实际内容动态判定
        2. 否则退回模板级默认推荐
        """
        if receipt is not None:
            return self._recommend_strategy_from_receipt(template_name, receipt)
        return self._get_template_default_strategy(template_name)

    def build_test_receipt(self) -> Receipt:
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

    def encode_receipt(self, receipt: Receipt, strategy_name: str = STRATEGY_BLOCK_STEP_STABLE) -> SendPlan:
        if strategy_name == self.STRATEGY_BLOCK_STEP_STABLE:
            return self._encode_receipt_block_step_stable(receipt)

        if strategy_name == self.STRATEGY_SINGLE_SHOT_PLAIN:
            return self._encode_receipt_single_shot_plain(receipt)

        if strategy_name == self.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE:
            return self._encode_receipt_block_fewer_triggers_style(receipt)

        raise ValueError(f"未知发送策略: {strategy_name}")

    def _encode_receipt_block_step_stable(self, receipt: Receipt) -> SendPlan:
        plan = SendPlan()
        plan.add_step(CommandBuilder.init_printer())

        last_style: Optional[BlockStyle] = None
        for block in receipt.blocks:
            block_steps, last_style = self._encode_block(block, last_style)
            for step in block_steps:
                plan.add_step(step)

        return plan

    def _encode_receipt_single_shot_plain(self, receipt: Receipt) -> SendPlan:
        """将任意 receipt 平铺为一个大文本块，最后只触发一次打印。"""
        plan = SendPlan()

        plain_lines = self._flatten_receipt_to_plain_lines(receipt)
        plain_lines = self._refine_plain_money_section(plain_lines)
        text_blob = "\n".join(plain_lines).strip("\n")

        plan.add_step(CommandBuilder.init_printer())
        plan.add_step(CommandBuilder.align_left())
        plan.add_step(CommandBuilder.scale(1))
        plan.add_step(CommandBuilder.line_spacing(0))
        plan.add_step(CommandBuilder.left_margin(0))
        plan.add_step(CommandBuilder.right_margin(0))
        plan.add_step(CommandBuilder.text_step(text_blob, append_crlf=False))
        plan.add_step(CommandBuilder.print_trigger_lf())

        return plan

    def _encode_receipt_block_fewer_triggers_style(self, receipt: Receipt) -> SendPlan:
        """保留样式分组，但合并相邻且样式相同的 block，减少 trigger 次数。"""
        merged_blocks = self._merge_adjacent_same_style_blocks(receipt.blocks)

        plan = SendPlan()
        plan.add_step(CommandBuilder.init_printer())

        last_style: Optional[BlockStyle] = None
        for block in merged_blocks:
            block_steps, last_style = self._encode_block(block, last_style)
            for step in block_steps:
                plan.add_step(step)

        return plan

    def _get_template_default_strategy(self, template_name: str) -> str:
        """模板级兜底推荐。"""
        if template_name == "default":
            return self.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE
        if template_name == "compact":
            return self.STRATEGY_SINGLE_SHOT_PLAIN
        if template_name == "simple_center":
            return self.STRATEGY_SINGLE_SHOT_PLAIN
        if template_name == "single_shot_plain":
            return self.STRATEGY_SINGLE_SHOT_PLAIN
        return self.STRATEGY_BLOCK_STEP_STABLE

    def _recommend_strategy_from_receipt(self, template_name: str, receipt: Receipt) -> str:
        """按当前实际 receipt 内容动态推荐策略。"""
        # 很小的居中欢迎类模板，直接 single-shot plain
        if template_name == "simple_center":
            return self.STRATEGY_SINGLE_SHOT_PLAIN

        stats = self._analyze_receipt(receipt)

        # 特别长、特别多行、或者存在超长大块文本时，稳定优先
        if (
            stats.total_chars >= 320
            or stats.total_nonempty_lines >= 20
            or stats.max_block_chars >= 220
        ):
            return self.STRATEGY_BLOCK_STEP_STABLE

        # 非常短、非常简单的小票，直接 single-shot plain
        if (
            stats.total_nonempty_lines <= 6
            and stats.total_chars <= 90
            and stats.style_transitions <= 2
        ):
            return self.STRATEGY_SINGLE_SHOT_PLAIN

        # compact 模板：中短内容优先 single-shot plain，过长则退回 fewer-triggers
        if template_name == "compact":
            if stats.total_chars <= 150 and stats.total_nonempty_lines <= 10:
                return self.STRATEGY_SINGLE_SHOT_PLAIN
            return self.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE

        # 有明显样式分区/重点区/金额区时，更适合 fewer-triggers
        if (
            stats.style_transitions >= 4
            or stats.emphasis_block_count >= 2
            or stats.money_block_count >= 2
        ):
            return self.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE

        # block 不多、内容不长，也可以 single-shot plain
        if (
            stats.total_blocks <= 4
            and stats.total_chars <= 150
            and stats.max_block_chars <= 120
        ):
            return self.STRATEGY_SINGLE_SHOT_PLAIN

        # 默认偏向较实用的 fewer-triggers
        return self.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE

    def _analyze_receipt(self, receipt: Receipt) -> ReceiptStats:
        total_blocks = len(receipt.blocks)
        total_nonempty_lines = 0
        total_chars = 0
        max_block_chars = 0
        style_transitions = 0
        emphasis_block_count = 0
        money_block_count = 0
        multiline_block_count = 0

        prev_style: Optional[BlockStyle] = None

        for block in receipt.blocks:
            style = self._normalize_style(block)
            if prev_style is not None and style != prev_style:
                style_transitions += 1
            prev_style = style

            joined = "\n".join(block.text_lines)
            max_block_chars = max(max_block_chars, len(joined))
            total_chars += len(joined)

            nonempty = [line.strip() for line in block.text_lines if line.strip()]
            total_nonempty_lines += len(nonempty)

            if len(nonempty) > 1:
                multiline_block_count += 1

            if self._is_large_or_emphasis_block(block):
                emphasis_block_count += 1

            if self._contains_money_semantic(block):
                money_block_count += 1

        return ReceiptStats(
            total_blocks=total_blocks,
            total_nonempty_lines=total_nonempty_lines,
            total_chars=total_chars,
            max_block_chars=max_block_chars,
            style_transitions=style_transitions,
            emphasis_block_count=emphasis_block_count,
            money_block_count=money_block_count,
            multiline_block_count=multiline_block_count,
        )

    def _default_form_data(self, template_name: str) -> ReceiptFormData:
        if template_name == "compact":
            return ReceiptFormData(
                title="YINJIAN DRINKS",
                date="2026-03-20",
                receipt_no="1234567890",
                items_text="COLA 1 3.00\nMILK 1 10.00",
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
        if template_name == "single_shot_plain":
            return ReceiptFormData(
                title="YINJIAN DRINKS",
                date="2026-03-20",
                receipt_no="1234567890",
                items_text=(
                    "COLA 1 3.00\n"
                    "BREAD 2 5.00\n"
                    "MILK 1 10.00"
                ),
                total="23.00",
                cash="50.00",
                change="27.00",
                footer="THANK YOU COME AGAIN",
            )
        return ReceiptFormData(
            title="YINJIAN DRINKS",
            date="2026-03-20",
            receipt_no="1234567890",
            items_text=(
                "COLA 1 3.00\n"
                "BREAD 2 5.00\n"
                "MILK 1 10.00"
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

    def _fit_text(self, text: str, width: int) -> str:
        text = (text or "").strip()
        if len(text) <= width:
            return text
        if width <= 1:
            return text[:width]
        return text[: width - 1] + "~"

    def _pad_lr(self, left: str, right: str, width: int) -> str:
        left = (left or "").strip()
        right = (right or "").strip()
        if len(left) + len(right) >= width:
            available_left = max(0, width - len(right) - 1)
            left = self._fit_text(left, available_left)
        spaces = max(1, width - len(left) - len(right))
        return f"{left}{' ' * spaces}{right}"

    def _center_text_visual(self, text: str, width: int) -> str:
        text = self._fit_text((text or "").strip(), width)
        if len(text) >= width:
            return text[:width]
        left_pad = max(0, (width - len(text)) // 2)
        right_pad = max(0, width - len(text) - left_pad)
        return (" " * left_pad) + text + (" " * right_pad)

    def _right_text_visual(self, text: str, width: int) -> str:
        text = self._fit_text((text or "").strip(), width)
        if len(text) >= width:
            return text[:width]
        return (" " * (width - len(text))) + text

    def _wrap_name(self, name: str, width: int) -> List[str]:
        name = (name or "").strip()
        if not name:
            return [""]
        return [name[i:i + width] for i in range(0, len(name), width)]

    def _parse_item_line(self, line: str) -> tuple[str, str, str]:
        s = line.strip()
        if not s:
            return "", "", ""

        for sep in ("|", "\t", ","):
            if sep in s:
                parts = [p.strip() for p in s.split(sep) if p.strip()]
                if len(parts) >= 3:
                    return parts[0], parts[1], parts[2]

        parts = s.split()
        if len(parts) >= 3:
            price = parts[-1]
            qty = parts[-2]
            name = " ".join(parts[:-2])
            return name, qty, price

        return s, "", ""

    def _format_item_rows(self, items_text: str) -> List[str]:
        rows: List[str] = []
        for raw_line in self._split_nonempty_lines(items_text):
            name, qty, price = self._parse_item_line(raw_line)
            name_lines = self._wrap_name(name, self.ITEM_NAME_WIDTH)
            first_name = self._fit_text(name_lines[0], self.ITEM_NAME_WIDTH)
            rows.append(
                f"{first_name:<{self.ITEM_NAME_WIDTH}}"
                f"{qty:>{self.ITEM_QTY_WIDTH}}"
                f"{price:>{self.ITEM_PRICE_WIDTH}}"
            )
            for extra_name in name_lines[1:]:
                rows.append(f"{extra_name:<{self.ITEM_NAME_WIDTH}}")
        return rows

    def _format_money_line(self, label: str, value: str) -> str:
        return self._pad_lr(label, value, self.RECEIPT_WIDTH)

    def _build_default_receipt(self, data: ReceiptFormData) -> Receipt:
        meta_lines: List[str] = []
        if data.date:
            meta_lines.append(self._pad_lr("DATE", data.date, self.RECEIPT_WIDTH))
        if data.receipt_no:
            meta_lines.append(self._pad_lr("RECEIPT NO", data.receipt_no, self.RECEIPT_WIDTH))

        item_lines = self._format_item_rows(data.items_text)
        footer_lines = self._split_nonempty_lines(data.footer) or ["THANK YOU"]

        blocks: List[ReceiptBlock] = [
            self.title_block(data.title or "TITLE", scale=2, force_reset_style=True),
            self.center_block(["SALES RECEIPT"], scale=1),
        ]

        if meta_lines:
            blocks.append(self.text_block(meta_lines, align="left", scale=1, force_reset_style=True))

        blocks.extend([
            self.rule_block(),
            self.text_block([
                f"{'ITEM':<{self.ITEM_NAME_WIDTH}}{'QTY':>{self.ITEM_QTY_WIDTH}}{'PRICE':>{self.ITEM_PRICE_WIDTH}}"
            ], align="left", scale=1, force_reset_style=True),
            self.rule_block(),
        ])

        if item_lines:
            blocks.append(self.text_block(item_lines, align="left", scale=1))

        blocks.append(self.rule_block())

        if data.total:
            blocks.append(self.center_block([f"TOTAL {data.total}"], scale=2, force_reset_style=True))

        money_lines: List[str] = []
        if data.cash:
            money_lines.append(self._format_money_line("CASH", data.cash))
        if data.change:
            money_lines.append(self._format_money_line("CHANGE", data.change))
        if money_lines:
            blocks.append(self.text_block(money_lines, align="left", scale=1, force_reset_style=True))

        blocks.append(self.rule_block())
        blocks.append(self.center_block(footer_lines, scale=1, force_reset_style=True))

        return Receipt(
            name="default",
            description="标准测试票：标题、票据信息、表头、商品明细、合计和尾部都做了分区排版",
            blocks=blocks,
        )

    def _build_compact_receipt(self, data: ReceiptFormData) -> Receipt:
        meta_lines: List[str] = []
        if data.date:
            meta_lines.append(data.date)
        if data.receipt_no:
            meta_lines.append(f"NO {data.receipt_no}")

        blocks: List[ReceiptBlock] = [
            self.title_block(data.title or "TITLE", scale=2, force_reset_style=True),
        ]
        if meta_lines:
            blocks.append(self.center_block(meta_lines, scale=1))
        if data.total:
            blocks.append(self.rule_block())
            blocks.append(self.center_block([f"TOTAL {data.total}"], scale=2, force_reset_style=True))
        if data.footer:
            blocks.append(self.rule_block())
            blocks.append(self.center_block(self._split_nonempty_lines(data.footer), scale=1, force_reset_style=True))

        return Receipt(
            name="compact",
            description="紧凑模板：适合快速看标题/总价/结束语的样式区分",
            blocks=blocks,
        )

    def _build_simple_center_receipt(self, data: ReceiptFormData) -> Receipt:
        center_lines = self._split_nonempty_lines(data.items_text) or ["WELCOME"]
        footer_lines = self._split_nonempty_lines(data.footer) or ["YINJIAN"]
        return Receipt(
            name="simple_center",
            description="最小模板：只验证标题、正文和尾部三段的样式区分",
            blocks=[
                self.title_block(data.title or "HELLO", scale=2, force_reset_style=True),
                self.center_block(center_lines, scale=1, force_reset_style=True),
                self.rule_block(),
                self.center_block(footer_lines, scale=1, force_reset_style=True),
            ],
        )

    def _build_single_shot_plain_receipt(self, data: ReceiptFormData) -> Receipt:
        """兼容保留的旧实验模板。"""
        lines: List[str] = []

        title = data.title.strip() if data.title else "TITLE"
        lines.append(self._center_text_visual(title, self.RECEIPT_WIDTH))
        lines.append(self._center_text_visual("SALES RECEIPT", self.RECEIPT_WIDTH))

        if data.date:
            lines.append(self._pad_lr("DATE", data.date, self.RECEIPT_WIDTH))
        if data.receipt_no:
            lines.append(self._pad_lr("RECEIPT NO", data.receipt_no, self.RECEIPT_WIDTH))

        lines.append(self._HR)
        lines.append(
            f"{'ITEM':<{self.ITEM_NAME_WIDTH}}{'QTY':>{self.ITEM_QTY_WIDTH}}{'PRICE':>{self.ITEM_PRICE_WIDTH}}"
        )
        lines.append(self._HR)

        item_rows = self._format_item_rows(data.items_text)
        if item_rows:
            lines.extend(item_rows)

        lines.append(self._HR)

        if data.total:
            lines.append(self._center_text_visual(f"TOTAL {data.total}", self.RECEIPT_WIDTH))

        if data.cash:
            lines.append(self._format_money_line("CASH", data.cash))
        if data.change:
            lines.append(self._format_money_line("CHANGE", data.change))

        lines.append(self._HR)

        footer_lines = self._split_nonempty_lines(data.footer)
        if footer_lines:
            for line in footer_lines:
                lines.append(self._center_text_visual(line, self.RECEIPT_WIDTH))

        lines = self._refine_plain_money_section(lines)

        return Receipt(
            name="single_shot_plain",
            description="兼容保留的实验模板：整票平铺为 plain-text 大块",
            blocks=[
                self.text_block(
                    lines,
                    align="left",
                    scale=1,
                    line_spacing=0,
                    margin_left=0,
                    margin_right=0,
                    trigger_print=True,
                    force_reset_style=True,
                )
            ],
        )

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

    def rule_block(self) -> ReceiptBlock:
        return self.text_block([self._HR], align="left", scale=1, force_reset_style=True)

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

    def _flatten_receipt_to_plain_lines(self, receipt: Receipt) -> List[str]:
        plain_lines: List[str] = []
        prev_block: Optional[ReceiptBlock] = None

        for block in receipt.blocks:
            rendered = self._render_block_as_plain_lines(block)
            if not rendered:
                prev_block = block
                continue

            if prev_block is not None and plain_lines:
                if self._need_visual_gap_between_blocks(prev_block, block, plain_lines[-1], rendered[0]):
                    plain_lines.append("")

            plain_lines.extend(rendered)
            prev_block = block

        return plain_lines

    def _render_block_as_plain_lines(self, block: ReceiptBlock) -> List[str]:
        lines: List[str] = []

        for raw_line in block.text_lines:
            line = raw_line.rstrip()

            if block.scale >= 2:
                line = line.upper()

            if block.align == "center":
                lines.append(self._center_text_visual(line, self.RECEIPT_WIDTH))
            elif block.align == "right":
                lines.append(self._right_text_visual(line, self.RECEIPT_WIDTH))
            else:
                lines.append(self._fit_text(line, self.RECEIPT_WIDTH))

        return lines

    def _need_visual_gap_between_blocks(
        self,
        prev_block: ReceiptBlock,
        curr_block: ReceiptBlock,
        prev_last_line: str,
        curr_first_line: str,
    ) -> bool:
        prev_last = prev_last_line.strip()
        curr_first = curr_first_line.strip()

        if not prev_last or not curr_first:
            return False

        if prev_last == self._HR or curr_first == self._HR:
            return False

        if prev_block.align != curr_block.align:
            return True

        if prev_block.scale != curr_block.scale:
            return True

        if curr_block.force_reset_style:
            return True

        return False

    def _merge_adjacent_same_style_blocks(self, blocks: List[ReceiptBlock]) -> List[ReceiptBlock]:
        """将相邻且样式相同的 block 合并，减少 trigger 次数。
        当前版本会避开金额区、横线区和大字区的危险边界。
        """
        if not blocks:
            return []

        merged_blocks: List[ReceiptBlock] = []

        current_block = blocks[0]
        current_style = self._normalize_style(current_block)
        current_lines = list(current_block.text_lines)
        current_force_reset = current_block.force_reset_style
        prev_source_block = current_block

        for block in blocks[1:]:
            style = self._normalize_style(block)

            if style == current_style and self._can_merge_blocks(prev_source_block, block):
                if current_lines and block.text_lines:
                    prev_last = current_lines[-1]
                    curr_first = block.text_lines[0]
                    if self._need_visual_gap_between_blocks(prev_source_block, block, prev_last, curr_first):
                        current_lines.append("")
                current_lines.extend(block.text_lines)
                prev_source_block = block
                continue

            merged_blocks.append(
                ReceiptBlock(
                    text_lines=current_lines,
                    align=current_style.align,
                    scale=current_style.scale,
                    line_spacing=current_style.line_spacing,
                    margin_left=current_style.margin_left,
                    margin_right=current_style.margin_right,
                    trigger_print=True,
                    force_reset_style=current_force_reset,
                )
            )

            current_block = block
            current_style = style
            current_lines = list(block.text_lines)
            current_force_reset = block.force_reset_style
            prev_source_block = block

        merged_blocks.append(
            ReceiptBlock(
                text_lines=current_lines,
                align=current_style.align,
                scale=current_style.scale,
                line_spacing=current_style.line_spacing,
                margin_left=current_style.margin_left,
                margin_right=current_style.margin_right,
                trigger_print=True,
                force_reset_style=current_force_reset,
            )
        )

        return merged_blocks

    def _can_merge_blocks(self, prev_block: ReceiptBlock, curr_block: ReceiptBlock) -> bool:
        """判断两个相邻同样式 block 是否适合合并。"""
        if prev_block.force_reset_style or curr_block.force_reset_style:
            return False

        if self._is_large_or_emphasis_block(prev_block) or self._is_large_or_emphasis_block(curr_block):
            return False

        if self._contains_money_semantic(prev_block) or self._contains_money_semantic(curr_block):
            return False

        if self._is_rule_block(prev_block) or self._is_rule_block(curr_block):
            return False

        return True

    def _is_rule_block(self, block: ReceiptBlock) -> bool:
        stripped = [line.strip() for line in block.text_lines if line.strip()]
        return bool(stripped) and all(line == self._HR for line in stripped)

    def _contains_money_semantic(self, block: ReceiptBlock) -> bool:
        for line in block.text_lines:
            s = line.strip().upper()
            if any(s.startswith(keyword) for keyword in self.MONEY_KEYWORDS):
                return True
        return False

    def _is_large_or_emphasis_block(self, block: ReceiptBlock) -> bool:
        if block.scale >= 2:
            return True

        nonempty = [line.strip() for line in block.text_lines if line.strip()]
        if block.align == "center" and 0 < len(nonempty) <= 2:
            return True

        return False

    def _refine_plain_money_section(self, lines: List[str]) -> List[str]:
        """对 plain-text 输出中的金额区做空行和边界微调。"""
        if not lines:
            return lines

        result: List[str] = []

        for idx, line in enumerate(lines):
            stripped = line.strip().upper()

            if stripped.startswith("TOTAL "):
                if result and result[-1].strip() != "" and result[-1].strip() != self._HR:
                    result.append("")
                result.append(line)
                if idx + 1 < len(lines):
                    result.append("")
                continue

            if stripped.startswith("CASH"):
                if result and result[-1].strip() not in ("", self._HR):
                    result.append("")
                result.append(line)
                continue

            result.append(line)

        compact: List[str] = []
        blank_run = 0
        for line in result:
            if line.strip() == "":
                blank_run += 1
                if blank_run <= 1:
                    compact.append("")
            else:
                blank_run = 0
                compact.append(line)

        while compact and compact[0].strip() == "":
            compact.pop(0)
        while compact and compact[-1].strip() == "":
            compact.pop()

        return compact