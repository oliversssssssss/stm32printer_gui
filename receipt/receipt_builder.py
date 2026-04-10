from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

from protocol.command_builder import CommandBuilder, SendStep
from protocol.image_processor import ImageProcessor


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
    block_type: str = "text"  # text / image
    text_lines: List[str] = field(default_factory=list)
    align: str = "left"
    scale: int = 1
    line_spacing: Optional[int] = None
    margin_left: Optional[int] = None
    margin_right: Optional[int] = None
    trigger_print: bool = True
    force_reset_style: bool = False

    image_path: str = ""
    image_width: int = 220
    image_max_height: int = 96
    image_threshold: Optional[int] = None
    image_dither: bool = True

    image_kind: str = "file"  # file / qr
    qr_content: str = ""
    qr_size: int = 180
    qr_border: int = 2
    qr_error_correction: str = "M"

    def is_image(self) -> bool:
        return self.block_type == "image"

    def is_text(self) -> bool:
        return self.block_type == "text"


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
    logo_image_path: str
    footer_image_path: str
    image_width: str
    image_max_height: str
    image_threshold: str
    image_dither: str
    qr_content: str
    qr_size: str
    qr_border: str
    qr_error_correction: str


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
    centered_block_count: int
    image_block_count: int
    qr_block_count: int


@dataclass(frozen=True)
class StrategyRecommendation:
    strategy: str
    summary: str
    reasons: List[str]
    stats: ReceiptStats


class ReceiptBuilder:
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
            "single_shot_plain": self._build_single_shot_plain_receipt,
            "logo_receipt": self._build_logo_receipt,
            "qr_receipt": self._build_qr_receipt,
            "brand_qr_receipt": self._build_brand_qr_receipt,
        }

    def list_templates(self) -> List[str]:
        return list(self._templates.keys())

    def list_send_strategies(self) -> List[str]:
        return [
            self.STRATEGY_BLOCK_STEP_STABLE,
            self.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE,
            self.STRATEGY_SINGLE_SHOT_PLAIN,
        ]

    def get_recommended_strategy(self, template_name: str, receipt: Optional[Receipt] = None) -> str:
        return self.explain_recommended_strategy(template_name, receipt).strategy

    def explain_recommended_strategy(self, template_name: str, receipt: Optional[Receipt] = None) -> StrategyRecommendation:
        if receipt is None:
            strategy = self._get_template_default_strategy(template_name)
            empty_stats = ReceiptStats(
                total_blocks=0,
                total_nonempty_lines=0,
                total_chars=0,
                max_block_chars=0,
                style_transitions=0,
                emphasis_block_count=0,
                money_block_count=0,
                multiline_block_count=0,
                centered_block_count=0,
                image_block_count=0,
                qr_block_count=0,
            )
            return StrategyRecommendation(
                strategy=strategy,
                summary=f"当前按模板默认推荐：{strategy}",
                reasons=[f"模板 {template_name} 还未构造成完整 receipt，先使用模板级推荐。"],
                stats=empty_stats,
            )
        return self._recommend_strategy_from_receipt(template_name, receipt)

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
            "logo_image_path": data.logo_image_path,
            "footer_image_path": data.footer_image_path,
            "image_width": data.image_width,
            "image_max_height": data.image_max_height,
            "image_threshold": data.image_threshold,
            "image_dither": data.image_dither,
            "qr_content": data.qr_content,
            "qr_size": data.qr_size,
            "qr_border": data.qr_border,
            "qr_error_correction": data.qr_error_correction,
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
        has_images = any(block.is_image() for block in receipt.blocks)
        if strategy_name == self.STRATEGY_SINGLE_SHOT_PLAIN and has_images:
            strategy_name = self.STRATEGY_BLOCK_STEP_STABLE

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
            if block.is_image():
                last_style = None
                for step in self._encode_image_block(block):
                    plan.add_step(step)
            else:
                block_steps, last_style = self._encode_text_block(block, last_style)
                for step in block_steps:
                    plan.add_step(step)
        return plan

    def _encode_receipt_single_shot_plain(self, receipt: Receipt) -> SendPlan:
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
        if text_blob:
            plan.add_step(CommandBuilder.text_step(text_blob, append_crlf=False))
            plan.add_step(CommandBuilder.print_trigger_lf())
        return plan

    def _encode_receipt_block_fewer_triggers_style(self, receipt: Receipt) -> SendPlan:
        merged_blocks = self._merge_adjacent_same_style_blocks_mixed(receipt.blocks)
        plan = SendPlan()
        plan.add_step(CommandBuilder.init_printer())

        last_style: Optional[BlockStyle] = None
        for block in merged_blocks:
            if block.is_image():
                last_style = None
                for step in self._encode_image_block(block):
                    plan.add_step(step)
            else:
                block_steps, last_style = self._encode_text_block(block, last_style)
                for step in block_steps:
                    plan.add_step(step)
        return plan

    def _get_template_default_strategy(self, template_name: str) -> str:
        if template_name in ("logo_receipt", "qr_receipt"):
            return self.STRATEGY_BLOCK_STEP_STABLE
        if template_name == "single_shot_plain":
            return self.STRATEGY_SINGLE_SHOT_PLAIN
        return self.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE

    def _recommend_strategy_from_receipt(self, template_name: str, receipt: Receipt) -> StrategyRecommendation:
        stats = self._analyze_receipt(receipt)
        reasons: List[str] = []

        if stats.image_block_count > 0:
            reasons.append(f"当前 receipt 含图片区块（{stats.image_block_count} 个），其中二维码区块 {stats.qr_block_count} 个。")
            reasons.append("图文混排优先选择 block_step_stable，保证图片块和文本块独立触发更稳。")
            return StrategyRecommendation(
                strategy=self.STRATEGY_BLOCK_STEP_STABLE,
                summary="当前内容包含图片/二维码，优先稳定性。",
                reasons=reasons,
                stats=stats,
            )

        if template_name == "single_shot_plain":
            reasons.append("当前模板本身就是 plain-text single-shot 实验模板。")
            return StrategyRecommendation(
                strategy=self.STRATEGY_SINGLE_SHOT_PLAIN,
                summary="该模板本身就是 single-shot plain 模板。",
                reasons=reasons,
                stats=stats,
            )

        if stats.total_chars >= 320 or stats.total_nonempty_lines >= 20 or stats.max_block_chars >= 220:
            if stats.total_chars >= 320:
                reasons.append(f"总字符数较多（{stats.total_chars}）。")
            if stats.total_nonempty_lines >= 20:
                reasons.append(f"非空行数较多（{stats.total_nonempty_lines}）。")
            if stats.max_block_chars >= 220:
                reasons.append(f"存在较大的单块文本（最长 {stats.max_block_chars} 字符）。")
            reasons.append("优先选择最稳的 block_step_stable。")
            return StrategyRecommendation(
                strategy=self.STRATEGY_BLOCK_STEP_STABLE,
                summary="当前内容偏重，优先稳定性。",
                reasons=reasons,
                stats=stats,
            )

        if (
            stats.centered_block_count >= 1
            or stats.emphasis_block_count >= 1
            or stats.money_block_count >= 1
            or stats.style_transitions >= 2
        ):
            if stats.centered_block_count >= 1:
                reasons.append(f"存在居中区块（{stats.centered_block_count} 个）。")
            if stats.emphasis_block_count >= 1:
                reasons.append(f"存在重点区/大字区（{stats.emphasis_block_count} 个）。")
            if stats.money_block_count >= 1:
                reasons.append(f"存在金额语义区（{stats.money_block_count} 个）。")
            if stats.style_transitions >= 2:
                reasons.append(f"样式切换不算少（{stats.style_transitions} 次）。")
            reasons.append("优先推荐 block_fewer_triggers_style，在减少 trigger 的同时保住样式。")
            return StrategyRecommendation(
                strategy=self.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE,
                summary="当前 receipt 依赖样式表现，优先保样式。",
                reasons=reasons,
                stats=stats,
            )

        reasons.append("内容复杂度中等。")
        reasons.append("默认推荐 block_fewer_triggers_style。")
        return StrategyRecommendation(
            strategy=self.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE,
            summary="当前内容更适合少 trigger 且保样式的策略。",
            reasons=reasons,
            stats=stats,
        )

    def _analyze_receipt(self, receipt: Receipt) -> ReceiptStats:
        total_blocks = len(receipt.blocks)
        total_nonempty_lines = 0
        total_chars = 0
        max_block_chars = 0
        style_transitions = 0
        emphasis_block_count = 0
        money_block_count = 0
        multiline_block_count = 0
        centered_block_count = 0
        image_block_count = 0
        qr_block_count = 0

        prev_style: Optional[BlockStyle] = None
        for block in receipt.blocks:
            if block.is_image():
                image_block_count += 1
                if block.image_kind == "qr":
                    qr_block_count += 1
                prev_style = None
                continue

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
            if block.align == "center" and nonempty:
                centered_block_count += 1
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
            centered_block_count=centered_block_count,
            image_block_count=image_block_count,
            qr_block_count=qr_block_count,
        )

    def _default_form_data(self, template_name: str) -> ReceiptFormData:
        base = ReceiptFormData(
            title="YINJIAN DRINKS",
            date="2026-03-20",
            receipt_no="1234567890",
            items_text=("COLA 1 3.00\nBREAD 2 5.00\nMILK 1 10.00"),
            total="23.00",
            cash="50.00",
            change="27.00",
            footer="THANK YOU COME AGAIN",
            logo_image_path="",
            footer_image_path="",
            image_width="220",
            image_max_height="96",
            image_threshold="auto",
            image_dither="1",
            qr_content="",
            qr_size="180",
            qr_border="2",
            qr_error_correction="M",
        )
        if template_name == "compact":
            base.items_text = "COLA 1 3.00\nMILK 1 10.00"
            base.total = "13.00"
            base.cash = "20.00"
            base.change = "7.00"
            base.footer = "THANK YOU"
        elif template_name == "simple_center":
            base.title = "HELLO"
            base.date = ""
            base.receipt_no = ""
            base.items_text = "WELCOME"
            base.total = ""
            base.cash = ""
            base.change = ""
            base.footer = "YINJIAN"
        elif template_name == "logo_receipt":
            base.footer = "SCAN BELOW"
            base.image_width = "220"
            base.image_max_height = "96"
        elif template_name == "qr_receipt":
            base.footer = "SCAN TO PAY"
            base.image_width = "180"
            base.image_max_height = "180"
            base.qr_content = "https://example.com/pay/demo-123456"
            base.qr_size = "180"
            base.qr_border = "2"
            base.qr_error_correction = "M"
        elif template_name == "brand_qr_receipt":
            base.footer = "SCAN TO JOIN"
            base.image_width = "220"
            base.image_max_height = "96"
            base.qr_content = "https://example.com/brand/join"
            base.qr_size = "180"
            base.qr_border = "2"
            base.qr_error_correction = "Q"
        return base

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
            logo_image_path=_value("logo_image_path", base.logo_image_path),
            footer_image_path=_value("footer_image_path", base.footer_image_path),
            image_width=_value("image_width", base.image_width),
            image_max_height=_value("image_max_height", base.image_max_height),
            image_threshold=_value("image_threshold", base.image_threshold),
            image_dither=_value("image_dither", base.image_dither),
            qr_content=_value("qr_content", base.qr_content),
            qr_size=_value("qr_size", base.qr_size),
            qr_border=_value("qr_border", base.qr_border),
            qr_error_correction=_value("qr_error_correction", base.qr_error_correction),
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

    def _parse_image_width(self, value: str, default: int) -> int:
        try:
            parsed = int(str(value).strip())
        except Exception:
            parsed = default
        return max(1, min(CommandBuilder.IMAGE_MAX_WIDTH, parsed))

    def _parse_image_height(self, value: str, default: int) -> int:
        try:
            parsed = int(str(value).strip())
        except Exception:
            parsed = default
        return max(1, min(ImageProcessor.MAX_HEIGHT, parsed))

    def _parse_image_threshold(self, value: str) -> Optional[int]:
        s = str(value).strip().lower()
        if s in ("", "auto", "otsu"):
            return None
        try:
            parsed = int(s)
        except Exception:
            return None
        return max(0, min(255, parsed))

    def _parse_image_dither(self, value: str) -> bool:
        return str(value).strip().lower() not in ("0", "false", "off", "no", "")

    def _parse_qr_size(self, value: str, default: int) -> int:
        try:
            parsed = int(str(value).strip())
        except Exception:
            parsed = default
        return max(32, min(ImageProcessor.MAX_QR_SIZE, parsed))

    def _parse_qr_border(self, value: str, default: int) -> int:
        try:
            parsed = int(str(value).strip())
        except Exception:
            parsed = default
        return max(0, min(8, parsed))

    def _parse_qr_error_correction(self, value: str, default: str = "M") -> str:
        level = str(value).strip().upper() if value is not None else default
        return level if level in ("L", "M", "Q", "H") else default

    def _append_optional_logo_block(self, blocks: List[ReceiptBlock], data: ReceiptFormData):
        if data.logo_image_path.strip():
            blocks.append(
                self.image_block(
                    data.logo_image_path,
                    align="center",
                    image_width=self._parse_image_width(data.image_width, 220),
                    image_max_height=self._parse_image_height(data.image_max_height, 96),
                    image_threshold=self._parse_image_threshold(data.image_threshold),
                    image_dither=self._parse_image_dither(data.image_dither),
                )
            )

    def _append_optional_footer_visual_block(self, blocks: List[ReceiptBlock], data: ReceiptFormData):
        qr_content = data.qr_content.strip()
        if qr_content:
            blocks.append(
                self.qr_block(
                    qr_content,
                    align="center",
                    qr_size=self._parse_qr_size(data.qr_size, 180),
                    qr_border=self._parse_qr_border(data.qr_border, 2),
                    qr_error_correction=self._parse_qr_error_correction(data.qr_error_correction, "M"),
                )
            )
            return

        if data.footer_image_path.strip():
            blocks.append(
                self.image_block(
                    data.footer_image_path,
                    align="center",
                    image_width=self._parse_image_width(data.image_width, 180),
                    image_max_height=self._parse_image_height(data.image_max_height, 180),
                    image_threshold=self._parse_image_threshold(data.image_threshold),
                    image_dither=self._parse_image_dither(data.image_dither),
                )
            )

    def _build_default_receipt(self, data: ReceiptFormData) -> Receipt:
        meta_lines: List[str] = []
        if data.date:
            meta_lines.append(self._pad_lr("DATE", data.date, self.RECEIPT_WIDTH))
        if data.receipt_no:
            meta_lines.append(self._pad_lr("RECEIPT NO", data.receipt_no, self.RECEIPT_WIDTH))

        item_lines = self._format_item_rows(data.items_text)
        footer_lines = self._split_nonempty_lines(data.footer) or ["THANK YOU"]

        blocks: List[ReceiptBlock] = []
        self._append_optional_logo_block(blocks, data)
        blocks.extend([
            self.title_block(data.title or "TITLE", scale=2, force_reset_style=True),
            self.center_block(["SALES RECEIPT"], scale=1),
        ])

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
        self._append_optional_footer_visual_block(blocks, data)

        return Receipt(
            name="default",
            description="标准测试票：支持标题/明细/尾部排版，也支持可选顶部 Logo、底部图片或底部二维码。",
            blocks=blocks,
        )

    def _build_compact_receipt(self, data: ReceiptFormData) -> Receipt:
        meta_lines: List[str] = []
        if data.date:
            meta_lines.append(data.date)
        if data.receipt_no:
            meta_lines.append(f"NO {data.receipt_no}")

        blocks: List[ReceiptBlock] = []
        self._append_optional_logo_block(blocks, data)
        blocks.append(self.title_block(data.title or "TITLE", scale=2, force_reset_style=True))
        if meta_lines:
            blocks.append(self.center_block(meta_lines, scale=1))
        if data.total:
            blocks.append(self.rule_block())
            blocks.append(self.center_block([f"TOTAL {data.total}"], scale=2, force_reset_style=True))
        if data.footer:
            blocks.append(self.rule_block())
            blocks.append(self.center_block(self._split_nonempty_lines(data.footer), scale=1, force_reset_style=True))
        self._append_optional_footer_visual_block(blocks, data)

        return Receipt(
            name="compact",
            description="紧凑模板：适合快速看标题/总价/结束语，也支持可选图片或二维码。",
            blocks=blocks,
        )

    def _build_simple_center_receipt(self, data: ReceiptFormData) -> Receipt:
        center_lines = self._split_nonempty_lines(data.items_text) or ["WELCOME"]
        footer_lines = self._split_nonempty_lines(data.footer) or ["YINJIAN"]
        blocks: List[ReceiptBlock] = []
        self._append_optional_logo_block(blocks, data)
        blocks.extend([
            self.title_block(data.title or "HELLO", scale=2, force_reset_style=True),
            self.center_block(center_lines, scale=1, force_reset_style=True),
            self.rule_block(),
            self.center_block(footer_lines, scale=1, force_reset_style=True),
        ])
        self._append_optional_footer_visual_block(blocks, data)
        return Receipt(
            name="simple_center",
            description="最小模板：验证标题、正文、尾部以及可选图片区块。",
            blocks=blocks,
        )

    def _build_single_shot_plain_receipt(self, data: ReceiptFormData) -> Receipt:
        lines: List[str] = []
        title = data.title.strip() if data.title else "TITLE"
        lines.append(self._center_text_visual(title, self.RECEIPT_WIDTH))
        lines.append(self._center_text_visual("SALES RECEIPT", self.RECEIPT_WIDTH))

        if data.date:
            lines.append(self._pad_lr("DATE", data.date, self.RECEIPT_WIDTH))
        if data.receipt_no:
            lines.append(self._pad_lr("RECEIPT NO", data.receipt_no, self.RECEIPT_WIDTH))

        lines.append(self._HR)
        lines.append(f"{'ITEM':<{self.ITEM_NAME_WIDTH}}{'QTY':>{self.ITEM_QTY_WIDTH}}{'PRICE':>{self.ITEM_PRICE_WIDTH}}")
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
            description="兼容保留的实验模板：整票平铺为 plain-text 大块；含图片时会自动退回稳定策略。",
            blocks=[self.text_block(lines, align="left", scale=1, line_spacing=0, margin_left=0, margin_right=0, trigger_print=True, force_reset_style=True)],
        )

    def _build_logo_receipt(self, data: ReceiptFormData) -> Receipt:
        blocks: List[ReceiptBlock] = []
        self._append_optional_logo_block(blocks, data)
        blocks.extend([
            self.title_block(data.title or "TITLE", scale=2, force_reset_style=True),
            self.center_block(["BRAND RECEIPT"], scale=1),
        ])
        item_lines = self._format_item_rows(data.items_text)
        if item_lines:
            blocks.extend([self.rule_block(), self.text_block(item_lines, align="left", scale=1)])
        if data.total:
            blocks.extend([self.rule_block(), self.center_block([f"TOTAL {data.total}"], scale=2, force_reset_style=True)])
        footer_lines = self._split_nonempty_lines(data.footer) or ["THANK YOU"]
        blocks.extend([self.rule_block(), self.center_block(footer_lines, scale=1, force_reset_style=True)])
        self._append_optional_footer_visual_block(blocks, data)
        return Receipt(
            name="logo_receipt",
            description="图文混排模板：顶部 Logo + 文本正文，可选底部二维码或图片。",
            blocks=blocks,
        )

    def _build_qr_receipt(self, data: ReceiptFormData) -> Receipt:
        blocks: List[ReceiptBlock] = [
            self.title_block(data.title or "TITLE", scale=2, force_reset_style=True),
            self.center_block(["SCAN TO PAY"], scale=1),
            self.rule_block(),
        ]
        item_lines = self._format_item_rows(data.items_text)
        if item_lines:
            blocks.append(self.text_block(item_lines, align="left", scale=1))
        if data.total:
            blocks.extend([self.rule_block(), self.center_block([f"TOTAL {data.total}"], scale=2, force_reset_style=True)])
        footer_lines = self._split_nonempty_lines(data.footer) or ["SCAN BELOW"]
        blocks.append(self.center_block(footer_lines, scale=1, force_reset_style=True))
        self._append_optional_footer_visual_block(blocks, data)
        return Receipt(
            name="qr_receipt",
            description="图文混排模板：底部内置二维码优先，其次可用外部底图。",
            blocks=blocks,
        )

    def _build_brand_qr_receipt(self, data: ReceiptFormData) -> Receipt:
        blocks: List[ReceiptBlock] = []
        self._append_optional_logo_block(blocks, data)
        blocks.extend([
            self.title_block(data.title or "TITLE", scale=2, force_reset_style=True),
            self.center_block(["BRAND SERVICE"], scale=1),
            self.rule_block(),
        ])

        meta_lines: List[str] = []
        if data.date:
            meta_lines.append(self._pad_lr("DATE", data.date, self.RECEIPT_WIDTH))
        if data.receipt_no:
            meta_lines.append(self._pad_lr("RECEIPT NO", data.receipt_no, self.RECEIPT_WIDTH))
        if meta_lines:
            blocks.append(self.text_block(meta_lines, align="left", scale=1, force_reset_style=True))

        item_lines = self._format_item_rows(data.items_text)
        if item_lines:
            blocks.extend([self.rule_block(), self.text_block(item_lines, align="left", scale=1)])

        if data.total:
            blocks.extend([self.rule_block(), self.center_block([f"TOTAL {data.total}"], scale=2, force_reset_style=True)])

        footer_lines = self._split_nonempty_lines(data.footer) or ["SCAN TO JOIN"]
        blocks.append(self.center_block(footer_lines, scale=1, force_reset_style=True))
        self._append_optional_footer_visual_block(blocks, data)
        return Receipt(
            name="brand_qr_receipt",
            description="品牌模板：顶部 Logo + 正文 + 底部二维码/图片。",
            blocks=blocks,
        )

    def title_block(self, text: str, *, scale: int = 2, line_spacing: Optional[int] = 0, force_reset_style: bool = False) -> ReceiptBlock:
        return ReceiptBlock(
            block_type="text",
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

    def center_block(self, lines: List[str], *, scale: int = 1, line_spacing: Optional[int] = 0, force_reset_style: bool = False) -> ReceiptBlock:
        return self.text_block(lines, align="center", scale=scale, line_spacing=line_spacing, force_reset_style=force_reset_style)

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
            block_type="text",
            text_lines=lines,
            align=align,
            scale=scale,
            line_spacing=line_spacing,
            margin_left=margin_left,
            margin_right=margin_right,
            trigger_print=trigger_print,
            force_reset_style=force_reset_style,
        )

    def image_block(
        self,
        image_path: str,
        *,
        align: str = "center",
        image_width: int = 220,
        image_max_height: int = 96,
        image_threshold: Optional[int] = None,
        image_dither: bool = True,
        trigger_print: bool = True,
    ) -> ReceiptBlock:
        return ReceiptBlock(
            block_type="image",
            align=align,
            trigger_print=trigger_print,
            image_path=image_path.strip(),
            image_width=image_width,
            image_max_height=image_max_height,
            image_threshold=image_threshold,
            image_dither=image_dither,
            image_kind="file",
        )

    def qr_block(
        self,
        qr_content: str,
        *,
        align: str = "center",
        qr_size: int = 180,
        qr_border: int = 2,
        qr_error_correction: str = "M",
        trigger_print: bool = True,
    ) -> ReceiptBlock:
        return ReceiptBlock(
            block_type="image",
            align=align,
            trigger_print=trigger_print,
            image_kind="qr",
            qr_content=qr_content.strip(),
            qr_size=qr_size,
            qr_border=qr_border,
            qr_error_correction=qr_error_correction,
            image_width=qr_size,
            image_max_height=qr_size,
            image_dither=False,
        )

    def _normalize_style(self, block: ReceiptBlock) -> BlockStyle:
        return BlockStyle(
            align=block.align,
            scale=max(1, min(3, int(block.scale))),
            line_spacing=0 if block.line_spacing is None else max(0, min(255, int(block.line_spacing))),
            margin_left=0 if block.margin_left is None else max(0, min(255, int(block.margin_left))),
            margin_right=0 if block.margin_right is None else max(0, min(255, int(block.margin_right))),
        )

    def _encode_text_block(self, block: ReceiptBlock, last_style: Optional[BlockStyle]) -> tuple[List[SendStep], BlockStyle]:
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
        if block_text:
            steps.append(CommandBuilder.text_step(block_text, append_crlf=False))
        if block.trigger_print:
            steps.append(CommandBuilder.print_trigger_lf())
        return steps, style

    def _encode_image_block(self, block: ReceiptBlock) -> List[SendStep]:
        if block.image_kind == "qr":
            prepared = ImageProcessor.prepare_qr_text(
                block.qr_content,
                target_size=max(32, min(ImageProcessor.MAX_QR_SIZE, int(block.qr_size))),
                qr_border=max(0, min(8, int(block.qr_border))),
                canvas_width=CommandBuilder.IMAGE_MAX_WIDTH,
                align=block.align,
            )
        else:
            prepared = ImageProcessor.prepare_image(
                block.image_path,
                target_width=max(1, min(CommandBuilder.IMAGE_MAX_WIDTH, int(block.image_width))),
                threshold=block.image_threshold,
                max_height=max(1, min(ImageProcessor.MAX_HEIGHT, int(block.image_max_height))),
                dither=bool(block.image_dither),
                canvas_width=CommandBuilder.IMAGE_MAX_WIDTH,
                align=block.align,
            )

        steps: List[SendStep] = [CommandBuilder.image_begin_step(prepared.width, prepared.height)]
        chunk_count = 0
        for seq, chunk in enumerate(prepared.iter_chunks(CommandBuilder.IMAGE_DATA_MAX_PAYLOAD)):
            steps.append(CommandBuilder.image_data_step(seq, chunk))
            chunk_count += 1
        steps.append(CommandBuilder.image_end_step(chunk_count))
        if block.trigger_print:
            steps.append(CommandBuilder.print_trigger_lf())
        return steps

    def _flatten_receipt_to_plain_lines(self, receipt: Receipt) -> List[str]:
        plain_lines: List[str] = []
        prev_block: Optional[ReceiptBlock] = None
        for block in receipt.blocks:
            if block.is_image():
                continue
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

    def _need_visual_gap_between_blocks(self, prev_block: ReceiptBlock, curr_block: ReceiptBlock, prev_last_line: str, curr_first_line: str) -> bool:
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

    def _merge_adjacent_same_style_blocks_mixed(self, blocks: List[ReceiptBlock]) -> List[ReceiptBlock]:
        if not blocks:
            return []

        merged: List[ReceiptBlock] = []
        current: Optional[ReceiptBlock] = None
        current_style: Optional[BlockStyle] = None
        prev_source_block: Optional[ReceiptBlock] = None

        for block in blocks:
            if block.is_image():
                if current is not None:
                    merged.append(current)
                    current = None
                    current_style = None
                    prev_source_block = None
                merged.append(block)
                continue

            style = self._normalize_style(block)
            if current is None:
                current = ReceiptBlock(**{**block.__dict__})
                current.text_lines = list(block.text_lines)
                current_style = style
                prev_source_block = block
                continue

            assert current_style is not None and prev_source_block is not None
            if style == current_style and self._can_merge_blocks(prev_source_block, block):
                if current.text_lines and block.text_lines:
                    prev_last = current.text_lines[-1]
                    curr_first = block.text_lines[0]
                    if self._need_visual_gap_between_blocks(prev_source_block, block, prev_last, curr_first):
                        current.text_lines.append("")
                current.text_lines.extend(block.text_lines)
                prev_source_block = block
                continue

            merged.append(current)
            current = ReceiptBlock(**{**block.__dict__})
            current.text_lines = list(block.text_lines)
            current_style = style
            prev_source_block = block

        if current is not None:
            merged.append(current)
        return merged

    def _can_merge_blocks(self, prev_block: ReceiptBlock, curr_block: ReceiptBlock) -> bool:
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
