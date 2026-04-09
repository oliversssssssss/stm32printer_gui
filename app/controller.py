from __future__ import annotations

import queue
import time
import uuid
from typing import Optional
from tkinter import messagebox

from app.app_state import AppState
from protocol.command_builder import CommandBuilder, SendStep
from protocol.uart2_frame_parser import UART2FrameParser
from receipt.receipt_builder import ReceiptBuilder, SendPlan, Receipt
from app.receipt_prefs_store import ReceiptPrefsStore
from render.frame_renderer import FrameRenderer
from serial_comm.port_service import PortService
from serial_comm.serial_manager import SerialManager
from ui.main_window import MainWindow


class PrinterHostController:
    """GUI 宿主控制器。

    当前这一版重点：
    1. 支持测试小票模板选择
    2. 支持发送策略选择：
       - block_step_stable
       - block_fewer_triggers_style
       - single_shot_plain
    3. 普通模式下使用模板推荐策略
    4. 推荐策略按实际 receipt 内容动态判定
    5. 高级模式下允许手动覆盖策略
    6. UI 中展示“为什么推荐这个策略”
    7. 表单变化时自动刷新推荐说明
    8. 策略模式与手动策略选择可持久化
    9. 支持更稳健的按 step 节奏执行发送
    10. 在 trigger(0A 00 / 0C 00) 后，优先等待 UART2 返回打印帧再继续
    11. 对不同发送策略应用不同的节拍与等待参数
    12. 适配 PreviewState 的 session 模型
    """

    NORMAL_STEP_DELAY_MS = 90
    RESET_STEP_DELAY_MS = 220

    TEXT_BASE_DELAY_MS = 120
    TEXT_PER_BYTE_DELAY_MS = 3
    TEXT_NEWLINE_EXTRA_DELAY_MS = 120

    # 各策略的发送节拍参数
    STRATEGY_TEXT_DELAY_MULTIPLIER = {
        ReceiptBuilder.STRATEGY_BLOCK_STEP_STABLE: 1.00,
        ReceiptBuilder.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE: 1.20,
        ReceiptBuilder.STRATEGY_SINGLE_SHOT_PLAIN: 1.45,
    }

    STRATEGY_TEXT_MAX_DELAY_MS = {
        ReceiptBuilder.STRATEGY_BLOCK_STEP_STABLE: 900,
        ReceiptBuilder.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE: 1300,
        ReceiptBuilder.STRATEGY_SINGLE_SHOT_PLAIN: 2200,
    }

    # 大文本后紧跟 trigger 时，额外保护等待
    STRATEGY_PRE_TRIGGER_GUARD_MS = {
        ReceiptBuilder.STRATEGY_BLOCK_STEP_STABLE: 0,
        ReceiptBuilder.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE: 160,
        ReceiptBuilder.STRATEGY_SINGLE_SHOT_PLAIN: 380,
    }

    STRATEGY_TRIGGER_FALLBACK_DELAY_MS = {
        ReceiptBuilder.STRATEGY_BLOCK_STEP_STABLE: 650,
        ReceiptBuilder.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE: 900,
        ReceiptBuilder.STRATEGY_SINGLE_SHOT_PLAIN: 1400,
    }

    STRATEGY_TRIGGER_WAIT_TIMEOUT_MS = {
        ReceiptBuilder.STRATEGY_BLOCK_STEP_STABLE: 1800,
        ReceiptBuilder.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE: 2600,
        ReceiptBuilder.STRATEGY_SINGLE_SHOT_PLAIN: 4200,
    }

    STRATEGY_POST_TRIGGER_SETTLE_MS = {
        ReceiptBuilder.STRATEGY_BLOCK_STEP_STABLE: 80,
        ReceiptBuilder.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE: 140,
        ReceiptBuilder.STRATEGY_SINGLE_SHOT_PLAIN: 260,
    }

    TRIGGER_POLL_INTERVAL_MS = 40

    def __init__(self):
        self.window = MainWindow()
        self.state = AppState()
        self.gui_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.parser = UART2FrameParser()
        self.receipt_builder = ReceiptBuilder()
        self.serial_manager = SerialManager(self._queue_line)
        self.receipt_prefs_store = ReceiptPrefsStore()

        self._current_send_plan: Optional[SendPlan] = None
        self._current_send_strategy_name: str = ReceiptBuilder.STRATEGY_BLOCK_STEP_STABLE
        self._manual_strategy_choice: str = ReceiptBuilder.STRATEGY_BLOCK_STEP_STABLE
        self._receipt_send_after_id: Optional[str] = None
        self._receipt_send_active: bool = False
        self._receipt_forms_by_template: dict[str, dict[str, str]] = {}
        self._current_template_name: str = "default"

        # trigger 等待状态
        self._trigger_wait_after_id: Optional[str] = None
        self._pending_trigger_next_idx: Optional[int] = None
        self._pending_trigger_expected_frame_count: Optional[int] = None
        self._pending_trigger_deadline_monotonic: float = 0.0

        self._bind_window_actions()

        self.state.preview.create_session(f"session_init_{uuid.uuid4().hex[:8]}")
        templates = self.receipt_builder.list_templates()
        self.window.set_receipt_templates(templates, default_template="default")
        self.window.set_send_strategies(
            self.receipt_builder.list_send_strategies(),
            default_strategy=ReceiptBuilder.STRATEGY_BLOCK_FEWER_TRIGGERS_STYLE,
        )
        self._restore_receipt_ui_state(templates)
        self._refresh_strategy_mode_ui(write_log=False)
        self._update_recommendation_panel()

        self.refresh_ports()
        self.window.after(50, self._process_gui_queue)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

    def run(self):
        self.window.mainloop()

    def _bind_window_actions(self):
        self.window.on_refresh_ports = self.refresh_ports
        self.window.on_toggle_uart1 = self.toggle_uart1
        self.window.on_toggle_uart2 = self.toggle_uart2
        self.window.on_send_text = self.send_text
        self.window.on_send_hex = self.send_hex
        self.window.on_send_init = lambda: self.send_step(CommandBuilder.init_printer())
        self.window.on_send_align_left = lambda: self.send_step(CommandBuilder.align_left())
        self.window.on_send_align_center = lambda: self.send_step(CommandBuilder.align_center())
        self.window.on_send_align_right = lambda: self.send_step(CommandBuilder.align_right())
        self.window.on_send_trigger_lf = lambda: self.send_step(CommandBuilder.print_trigger_lf())
        self.window.on_send_trigger_ff = lambda: self.send_step(CommandBuilder.print_trigger_ff())
        self.window.on_send_line_spacing = self.send_line_spacing
        self.window.on_send_left_margin = self.send_left_margin
        self.window.on_send_right_margin = self.send_right_margin
        self.window.on_send_scale = self.send_scale
        self.window.on_send_test_receipt = self.send_test_receipt
        self.window.on_receipt_template_changed = self.on_receipt_template_changed
        self.window.on_receipt_form_changed = self.on_receipt_form_changed
        self.window.on_send_strategy_mode_changed = self.on_send_strategy_mode_changed
        self.window.on_send_strategy_changed = self.on_send_strategy_changed
        self.window.on_start_new_receipt = self.start_new_receipt
        self.window.on_clear_history_frames = self.clear_history_frames
        self.window.on_preview_option_changed = self.rerender_views

    def _queue_line(self, source: str, text: str):
        self.gui_queue.put((source, text))

    def _process_gui_queue(self):
        try:
            while True:
                source, data = self.gui_queue.get_nowait()

                if source == "uart1":
                    self.window.append_log(data + "\n")

                elif source == "uart2":
                    self.window.append_uart2_raw(data + "\n")
                    result = self.parser.feed_line(data)

                    if result.is_success():
                        frame = result.frame
                        assert frame is not None
                        self.state.preview.current_frame = frame
                        self.state.preview.add_frame_to_current_session(frame)
                        self.rerender_views()
                        self.window.append_log(
                            f"[UART2] 解析成功：{frame['TYPE']} {frame['WIDTH']}x{frame['HEIGHT']} MODE={frame['MODE']}\n"
                        )
                        self._maybe_resume_after_uart2_frame()

                    elif result.is_error():
                        self.window.append_log(f"[UART2 ERROR] {result.error_msg}\n")
                        self.parser.reset()

                elif source == "host":
                    self.window.append_log(data)

        except queue.Empty:
            pass

        self.window.after(50, self._process_gui_queue)

    # ===== 串口 =====
    def refresh_ports(self):
        ports = PortService.list_ports()
        self.window.set_ports(ports)
        self.window.set_status(f"已刷新串口，共 {len(ports)} 个")

    def toggle_uart1(self):
        if self.serial_manager.uart1_connected():
            self.serial_manager.disconnect_uart1()
            self.state.connection.uart1_connected = False
            self.state.connection.uart1_port = ""
            self.window.set_uart1_connected(False)
            self.window.set_status("UART1 已断开")
            self.window.append_log("[HOST] UART1 已断开\n")
            return

        try:
            port = self.window.get_uart1_port()
            if not port:
                messagebox.showerror("错误", "请选择 UART1 端口")
                return

            self.serial_manager.connect_uart1(port, self.window.get_uart1_baud())
            self.state.connection.uart1_connected = True
            self.state.connection.uart1_port = port
            self.window.set_uart1_connected(True)
            self.window.set_status(f"UART1 已连接：{port}")
            self.window.append_log(f"[HOST] UART1 已连接：{port}\n")

        except Exception as e:
            messagebox.showerror("UART1 连接失败", str(e))

    def toggle_uart2(self):
        if self.serial_manager.uart2_connected():
            self.serial_manager.disconnect_uart2()
            self.state.connection.uart2_connected = False
            self.state.connection.uart2_port = ""
            self.window.set_uart2_connected(False)
            self.window.set_status("UART2 已断开")
            self.window.append_log("[HOST] UART2 已断开\n")
            return

        try:
            port = self.window.get_uart2_port()
            if not port:
                messagebox.showerror("错误", "请选择 UART2 端口")
                return

            self.serial_manager.connect_uart2(port, self.window.get_uart2_baud())
            self.state.connection.uart2_connected = True
            self.state.connection.uart2_port = port
            self.window.set_uart2_connected(True)
            self.window.set_status(f"UART2 已连接：{port}")
            self.window.append_log(f"[HOST] UART2 已连接：{port}\n")

        except Exception as e:
            messagebox.showerror("UART2 连接失败", str(e))

    # ===== 模板与策略 =====
    def _apply_template_defaults(self, template_name: str):
        defaults = self.receipt_builder.get_template_form_defaults(template_name)
        self.window.set_receipt_form_defaults(defaults)

    def _save_current_template_form(self):
        template_name = self._current_template_name or (self.window.get_receipt_template() or "default")
        self._receipt_forms_by_template[template_name] = self.window.get_receipt_form_data()

    def _persist_receipt_ui_state(self):
        self.receipt_prefs_store.save(
            selected_template=self._current_template_name or (self.window.get_receipt_template() or "default"),
            forms_by_template=self._receipt_forms_by_template,
            use_recommended_strategy=self.window.get_use_recommended_strategy(),
            manual_strategy_choice=self._manual_strategy_choice,
        )

    def _restore_receipt_ui_state(self, templates: list[str]):
        saved = self.receipt_prefs_store.load()
        selected_template = saved.get("selected_template")
        forms_by_template = saved.get("forms_by_template", {})
        if not isinstance(forms_by_template, dict):
            forms_by_template = {}
        self._receipt_forms_by_template = {
            key: value for key, value in forms_by_template.items()
            if key in templates and isinstance(value, dict)
        }

        if not selected_template or selected_template not in templates:
            selected_template = "default" if "default" in templates else (templates[0] if templates else "")

        self._current_template_name = selected_template
        self.window.set_receipt_template(selected_template)

        saved_form = self._receipt_forms_by_template.get(selected_template)
        if saved_form:
            self.window.set_receipt_form_defaults(saved_form)
            self.window.append_log(f"[RECEIPT] 已恢复上次模板与表单：{selected_template}\n")
        else:
            self._apply_template_defaults(selected_template)

        saved_use_recommended = saved.get("use_recommended_strategy")
        if isinstance(saved_use_recommended, bool):
            self.window.set_use_recommended_strategy(saved_use_recommended)
        else:
            self.window.set_use_recommended_strategy(True)

        saved_manual_strategy = saved.get("manual_strategy_choice")
        allowed = set(self.receipt_builder.list_send_strategies())
        if isinstance(saved_manual_strategy, str) and saved_manual_strategy in allowed:
            self._manual_strategy_choice = saved_manual_strategy
        else:
            self._manual_strategy_choice = ReceiptBuilder.STRATEGY_BLOCK_STEP_STABLE

    def _build_receipt_from_current_ui(self) -> Receipt:
        template_name = self.window.get_receipt_template() or "default"
        form_data = self.window.get_receipt_form_data()
        return self.receipt_builder.build_receipt(template_name, form_data)

    def _compute_recommendation_from_ui(self):
        template_name = self.window.get_receipt_template() or "default"
        try:
            receipt = self._build_receipt_from_current_ui()
            return self.receipt_builder.explain_recommended_strategy(template_name, receipt)
        except Exception:
            return self.receipt_builder.explain_recommended_strategy(template_name, None)

    def _format_recommendation_stats(self, stats) -> str:
        return (
            f"blocks={stats.total_blocks} | "
            f"nonempty_lines={stats.total_nonempty_lines} | "
            f"chars={stats.total_chars} | "
            f"max_block_chars={stats.max_block_chars} | "
            f"style_transitions={stats.style_transitions} | "
            f"emphasis_blocks={stats.emphasis_block_count} | "
            f"money_blocks={stats.money_block_count} | "
            f"multiline_blocks={stats.multiline_block_count}"
        )

    def _update_recommendation_panel(self):
        rec = self._compute_recommendation_from_ui()
        use_recommended = self.window.get_use_recommended_strategy()
        current_selected = self.window.get_send_strategy() or self._manual_strategy_choice

        if use_recommended:
            mode_text = "推荐模式（自动）"
            effective_strategy = rec.strategy
            summary = rec.summary
            reasons = rec.reasons
            self.window.set_send_strategy(rec.strategy)
        else:
            mode_text = "高级模式（手动）"
            effective_strategy = current_selected
            if effective_strategy == rec.strategy:
                summary = f"当前手动策略与系统推荐一致：{rec.strategy}"
            else:
                summary = f"系统推荐：{rec.strategy}；当前手动覆盖为：{effective_strategy}"
            reasons = ["你当前处于高级手动模式。"] + rec.reasons

        stats_text = self._format_recommendation_stats(rec.stats)
        self.window.set_strategy_recommendation_info(
            mode_text=mode_text,
            recommended_strategy=rec.strategy,
            effective_strategy=effective_strategy,
            summary=summary,
            reasons=reasons,
            stats_text=stats_text,
        )

    def _refresh_strategy_mode_ui(self, *, write_log: bool):
        use_recommended = self.window.get_use_recommended_strategy()
        self.window.set_send_strategy_enabled(not use_recommended)

        if use_recommended:
            rec = self._compute_recommendation_from_ui()
            self.window.set_send_strategy(rec.strategy)
            if write_log:
                self.window.append_log(
                    f"[RECEIPT] 已启用动态推荐策略：template={self._current_template_name} -> {rec.strategy}\n"
                )
        else:
            self.window.set_send_strategy(self._manual_strategy_choice)
            if write_log:
                self.window.append_log(
                    f"[RECEIPT] 已切换为高级模式：当前手动策略={self._manual_strategy_choice}\n"
                )

        self._update_recommendation_panel()

    def on_receipt_template_changed(self):
        previous_template = self._current_template_name
        if previous_template:
            self._receipt_forms_by_template[previous_template] = self.window.get_receipt_form_data()

        template_name = self.window.get_receipt_template() or "default"
        self._current_template_name = template_name

        saved_form = self._receipt_forms_by_template.get(template_name)
        if saved_form:
            self.window.set_receipt_form_defaults(saved_form)
        else:
            self._apply_template_defaults(template_name)

        self._persist_receipt_ui_state()
        self._refresh_strategy_mode_ui(write_log=False)
        self.window.append_log(f"[RECEIPT] 已切换模板：{template_name}\n")

    def on_receipt_form_changed(self):
        if self._receipt_send_active:
            return
        self._update_recommendation_panel()

    def on_send_strategy_mode_changed(self):
        if self._receipt_send_active:
            messagebox.showwarning("发送中", "测试小票发送过程中不能切换策略模式")
            self.window.set_use_recommended_strategy(not self.window.get_use_recommended_strategy())
            return

        if self.window.get_use_recommended_strategy():
            current_ui_strategy = self.window.get_send_strategy() or self._manual_strategy_choice
            self._manual_strategy_choice = current_ui_strategy
            self._persist_receipt_ui_state()
            self._refresh_strategy_mode_ui(write_log=True)
            return

        self._persist_receipt_ui_state()
        self._refresh_strategy_mode_ui(write_log=True)

    def on_send_strategy_changed(self):
        if self.window.get_use_recommended_strategy():
            return
        self._manual_strategy_choice = self.window.get_send_strategy() or ReceiptBuilder.STRATEGY_BLOCK_STEP_STABLE
        self._persist_receipt_ui_state()
        self._update_recommendation_panel()

    # ===== 发送 =====
    def send_step(self, step: SendStep):
        if self._receipt_send_active:
            messagebox.showwarning("发送中", "测试小票发送过程中，请勿手动插入单步命令")
            return

        try:
            self.serial_manager.send_uart1(step.payload)
            self.window.append_log(f"[HOST SEND] {step.desc} -> {step.payload.hex(' ').upper()}\n")
        except Exception as e:
            messagebox.showwarning("发送失败", str(e))

    def send_text(self):
        text = self.window.get_send_text()
        if not text:
            return

        try:
            step = CommandBuilder.text_step(text, append_crlf=self.window.get_append_crlf())
            self.send_step(step)
        except Exception as e:
            messagebox.showerror("发送失败", str(e))

    def send_hex(self):
        hex_text = self.window.get_send_hex()
        if not hex_text:
            return

        try:
            step = CommandBuilder.hex_step(hex_text)
            self.send_step(step)
        except Exception as e:
            messagebox.showerror("HEX 发送失败", str(e))

    def send_line_spacing(self):
        try:
            self.send_step(CommandBuilder.line_spacing(int(self.window.get_line_spacing())))
        except Exception as e:
            messagebox.showerror("发送失败", str(e))

    def send_left_margin(self):
        try:
            self.send_step(CommandBuilder.left_margin(int(self.window.get_left_margin())))
        except Exception as e:
            messagebox.showerror("发送失败", str(e))

    def send_right_margin(self):
        try:
            self.send_step(CommandBuilder.right_margin(int(self.window.get_right_margin())))
        except Exception as e:
            messagebox.showerror("发送失败", str(e))

    def send_scale(self):
        try:
            self.send_step(CommandBuilder.scale(int(self.window.get_scale())))
        except Exception as e:
            messagebox.showerror("发送失败", str(e))

    def send_test_receipt(self):
        if self._receipt_send_active:
            messagebox.showwarning("发送中", "已有测试小票发送任务正在执行")
            return

        if not self.serial_manager.uart1_connected():
            messagebox.showerror("发送失败", "UART1 未连接")
            return

        try:
            self._cancel_all_receipt_timers()

            template_name = self.window.get_receipt_template() or "default"
            receipt = self._build_receipt_from_current_ui()

            if self.window.get_use_recommended_strategy():
                strategy_name = self.receipt_builder.get_recommended_strategy(template_name, receipt)
                self.window.set_send_strategy(strategy_name)
            else:
                strategy_name = self.window.get_send_strategy() or ReceiptBuilder.STRATEGY_BLOCK_STEP_STABLE
                self._manual_strategy_choice = strategy_name

            self._current_template_name = template_name
            self._current_send_strategy_name = strategy_name

            form_data = self.window.get_receipt_form_data()
            self._receipt_forms_by_template[template_name] = form_data
            self._persist_receipt_ui_state()

            plan = self.receipt_builder.encode_receipt(receipt, strategy_name=strategy_name)
            self._current_send_plan = plan
            self._receipt_send_active = True

            self.clear_history_frames()
            self.state.preview.create_session(f"session_{uuid.uuid4().hex[:8]}")

            strategy_source = "recommended" if self.window.get_use_recommended_strategy() else "manual"
            self.window.append_log(
                f"[RECEIPT] 开始发送测试小票 template={template_name} strategy={strategy_name} mode={strategy_source} name={receipt.name} 共 {plan.total} 步\n"
            )
            if receipt.description:
                self.window.append_log(f"[RECEIPT] 模板说明：{receipt.description}\n")
            if not self.serial_manager.uart2_connected():
                self.window.append_log("[RECEIPT] UART2 未连接：本轮按固定节拍发送，不等待打印帧\n")

            self._send_receipt_step(0)
        except Exception as e:
            self._receipt_send_active = False
            self._current_send_plan = None
            self._current_send_strategy_name = ReceiptBuilder.STRATEGY_BLOCK_STEP_STABLE
            self._cancel_all_receipt_timers()
            messagebox.showerror("发送测试小票失败", str(e))

    def _send_receipt_step(self, idx: int):
        plan = self._current_send_plan
        if plan is None:
            self._receipt_send_active = False
            return

        if idx >= plan.total:
            self._receipt_send_active = False
            self._current_send_plan = None
            self._current_send_strategy_name = ReceiptBuilder.STRATEGY_BLOCK_STEP_STABLE
            self._cancel_all_receipt_timers()
            self.window.append_log(
                f"[RECEIPT] 发送完成：{plan.sent_count}/{plan.total} 成功\n"
            )
            return

        record = plan.steps[idx]
        try:
            record.mark_sending()
            self.serial_manager.send_uart1(record.step.payload)
            plan.mark_step_sent(record.index)
            self.window.append_log(
                f"[RECEIPT {record.index + 1}/{plan.total}] {record.step.desc} -> {record.step.payload.hex(' ').upper()}\n"
            )
        except Exception as e:
            plan.mark_step_failed(record.index, str(e))
            self.window.append_log(
                f"[RECEIPT ERROR {record.index + 1}/{plan.total}] {str(e)}\n"
            )
            self._receipt_send_active = False
            self._current_send_plan = None
            self._current_send_strategy_name = ReceiptBuilder.STRATEGY_BLOCK_STEP_STABLE
            self._cancel_all_receipt_timers()
            return

        next_idx = idx + 1
        next_step = None
        if next_idx < plan.total:
            next_step = plan.steps[next_idx].step

        if self._is_trigger_step(record.step):
            if self.serial_manager.uart2_connected():
                self._arm_trigger_wait(next_idx)
                return

            next_delay = self._decide_next_step_delay(
                record.step,
                next_step=next_step,
                strategy_name=self._current_send_strategy_name,
            )
            self._receipt_send_after_id = self.window.after(
                next_delay,
                lambda: self._send_receipt_step(next_idx),
            )
            return

        next_delay = self._decide_next_step_delay(
            record.step,
            next_step=next_step,
            strategy_name=self._current_send_strategy_name,
        )
        self._receipt_send_after_id = self.window.after(
            next_delay,
            lambda: self._send_receipt_step(next_idx),
        )

    def _arm_trigger_wait(self, next_idx: int):
        self._cancel_trigger_wait_timer()
        self._pending_trigger_next_idx = next_idx
        self._pending_trigger_expected_frame_count = self._get_total_preview_frame_count() + 1
        timeout_ms = self._get_trigger_wait_timeout_ms(self._current_send_strategy_name)
        self._pending_trigger_deadline_monotonic = (
            time.monotonic() + timeout_ms / 1000.0
        )
        self._trigger_wait_after_id = self.window.after(
            self.TRIGGER_POLL_INTERVAL_MS,
            self._check_trigger_wait,
        )

    def _check_trigger_wait(self):
        self._trigger_wait_after_id = None

        if not self._receipt_send_active:
            self._reset_trigger_wait_state()
            return

        expected = self._pending_trigger_expected_frame_count
        if expected is None or self._pending_trigger_next_idx is None:
            return

        if self._get_total_preview_frame_count() >= expected:
            self._finish_trigger_wait(observed_uart2_frame=True)
            return

        if time.monotonic() >= self._pending_trigger_deadline_monotonic:
            self.window.append_log("[RECEIPT] 等待 UART2 打印帧超时，按兜底节拍继续\n")
            self._finish_trigger_wait(observed_uart2_frame=False)
            return

        self._trigger_wait_after_id = self.window.after(
            self.TRIGGER_POLL_INTERVAL_MS,
            self._check_trigger_wait,
        )

    def _maybe_resume_after_uart2_frame(self):
        if not self._receipt_send_active:
            return

        expected = self._pending_trigger_expected_frame_count
        if expected is None or self._pending_trigger_next_idx is None:
            return

        if self._get_total_preview_frame_count() >= expected:
            self._finish_trigger_wait(observed_uart2_frame=True)

    def _finish_trigger_wait(self, observed_uart2_frame: bool):
        next_idx = self._pending_trigger_next_idx
        self._cancel_trigger_wait_timer()
        self._reset_trigger_wait_state()

        if next_idx is None or not self._receipt_send_active:
            return

        if observed_uart2_frame:
            delay = self._get_post_trigger_settle_ms(self._current_send_strategy_name)
        else:
            delay = self._get_trigger_fallback_delay_ms(self._current_send_strategy_name)

        self._receipt_send_after_id = self.window.after(
            delay,
            lambda: self._send_receipt_step(next_idx),
        )

    def _cancel_receipt_after_timer(self):
        if self._receipt_send_after_id is not None:
            try:
                self.window.after_cancel(self._receipt_send_after_id)
            except Exception:
                pass
            self._receipt_send_after_id = None

    def _cancel_trigger_wait_timer(self):
        if self._trigger_wait_after_id is not None:
            try:
                self.window.after_cancel(self._trigger_wait_after_id)
            except Exception:
                pass
            self._trigger_wait_after_id = None

    def _reset_trigger_wait_state(self):
        self._pending_trigger_next_idx = None
        self._pending_trigger_expected_frame_count = None
        self._pending_trigger_deadline_monotonic = 0.0

    def _cancel_all_receipt_timers(self):
        self._cancel_receipt_after_timer()
        self._cancel_trigger_wait_timer()
        self._reset_trigger_wait_state()

    def _get_total_preview_frame_count(self) -> int:
        return len(self.state.preview.get_all_frames_in_order())

    @staticmethod
    def _is_trigger_step(step: SendStep) -> bool:
        return step.payload in (b"\x0A\x00", b"\x0C\x00")

    @staticmethod
    def _is_text_step(step: SendStep) -> bool:
        return bool(step.payload) and step.payload[:1] != b"\x1B"

    def _get_trigger_wait_timeout_ms(self, strategy_name: str) -> int:
        return self.STRATEGY_TRIGGER_WAIT_TIMEOUT_MS.get(strategy_name, 1800)

    def _get_trigger_fallback_delay_ms(self, strategy_name: str) -> int:
        return self.STRATEGY_TRIGGER_FALLBACK_DELAY_MS.get(strategy_name, 650)

    def _get_post_trigger_settle_ms(self, strategy_name: str) -> int:
        return self.STRATEGY_POST_TRIGGER_SETTLE_MS.get(strategy_name, 80)

    def _decide_next_step_delay(
        self,
        step: SendStep,
        *,
        next_step: Optional[SendStep],
        strategy_name: str,
    ) -> int:
        payload = step.payload

        if payload == b"\x1B\x40":
            return self.RESET_STEP_DELAY_MS

        if payload in (b"\x0A\x00", b"\x0C\x00"):
            return self._get_trigger_fallback_delay_ms(strategy_name)

        if self._is_text_step(step):
            newline_count = payload.count(b"\n") + payload.count(b"\r")
            multiplier = self.STRATEGY_TEXT_DELAY_MULTIPLIER.get(strategy_name, 1.0)
            max_delay = self.STRATEGY_TEXT_MAX_DELAY_MS.get(strategy_name, 900)

            delay = int(
                (
                    self.TEXT_BASE_DELAY_MS
                    + len(payload) * self.TEXT_PER_BYTE_DELAY_MS
                    + newline_count * self.TEXT_NEWLINE_EXTRA_DELAY_MS
                ) * multiplier
            )

            if next_step is not None and self._is_trigger_step(next_step):
                delay += self.STRATEGY_PRE_TRIGGER_GUARD_MS.get(strategy_name, 0)

            return min(delay, max_delay)

        return self.NORMAL_STEP_DELAY_MS

    # ===== 预览 =====
    def rerender_views(self):
        self.state.preview.auto_crop = self.window.get_auto_crop()
        self.state.preview.zoom = self.window.get_zoom()

        if self.state.preview.current_frame:
            if hasattr(self.window, "preview_canvas"):
                width, height, display_width, display_height = FrameRenderer.render_current_frame(
                    self.window.preview_canvas,
                    self.state.preview.current_frame,
                    self.state.preview.zoom,
                    self.state.preview.auto_crop,
                )
            else:
                frame = self.state.preview.current_frame
                width, height = frame['WIDTH'], frame['HEIGHT']
                display_width, display_height = width, height
            frame = self.state.preview.current_frame
            if hasattr(self.window, "preview_info_var"):
                self.window.preview_info_var.set(
                    f"TYPE={frame['TYPE']} | MODE={frame['MODE']} | 原始 {width}x{height} | 显示 {display_width}x{display_height}"
                )
        else:
            if hasattr(self.window, "preview_canvas"):
                self.window.preview_canvas.delete("all")
            if hasattr(self.window, "preview_info_var"):
                self.window.preview_info_var.set("尚未收到打印帧")

        FrameRenderer.render_history_frames(
            self.window.history_canvas,
            self.state.preview.get_all_frames_in_order(),
            self.state.preview.zoom,
            self.state.preview.auto_crop,
        )

    def start_new_receipt(self):
        if self._receipt_send_active:
            messagebox.showwarning("发送中", "测试小票发送过程中不能手动开始新小票")
            return

        self.clear_history_frames()
        self.state.preview.create_session(f"session_{uuid.uuid4().hex[:8]}")
        self.window.append_log("[HOST] 开始新小票，已清空历史预览\n")

    def clear_history_frames(self):
        self.state.preview.current_frame = None
        self.state.preview.clear_sessions()
        if hasattr(self.window, "preview_canvas"):
            self.window.preview_canvas.delete("all")
        if hasattr(self.window, "preview_info_var"):
            self.window.preview_info_var.set("尚未收到打印帧")
        self.window.clear_history_preview()

    def _on_close(self):
        self._cancel_all_receipt_timers()
        self._receipt_send_active = False
        try:
            self._save_current_template_form()
            self._persist_receipt_ui_state()
        except Exception:
            pass
        self.serial_manager.disconnect_all()
        self.window.destroy()