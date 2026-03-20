from __future__ import annotations

import queue
import uuid
from typing import Optional
from tkinter import messagebox

from app.app_state import AppState
from protocol.command_builder import CommandBuilder, SendStep
from protocol.uart2_frame_parser import UART2FrameParser
from receipt.receipt_builder import ReceiptBuilder, SendPlan
from app.receipt_prefs_store import ReceiptPrefsStore
from render.frame_renderer import FrameRenderer
from serial_comm.port_service import PortService
from serial_comm.serial_manager import SerialManager
from ui.main_window import MainWindow


class PrinterHostController:
    """GUI 宿主控制器。

    当前这一版重点：
    1. 支持测试小票模板选择
    2. 支持 GUI 参数化测试票内容
    3. 使用按 step 节奏执行的发送策略，降低 MCU 接收压力
    4. 适配 PreviewState 的 session 模型
    """

    NORMAL_STEP_DELAY_MS = 80
    RESET_STEP_DELAY_MS = 180
    SINGLELINE_TEXT_STEP_DELAY_MS = 150
    MULTILINE_TEXT_STEP_DELAY_MS = 260
    TRIGGER_STEP_DELAY_MS = 380

    def __init__(self):
        self.window = MainWindow()
        self.state = AppState()
        self.gui_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.parser = UART2FrameParser()
        self.receipt_builder = ReceiptBuilder()
        self.serial_manager = SerialManager(self._queue_line)
        self.receipt_prefs_store = ReceiptPrefsStore()

        self._current_send_plan: Optional[SendPlan] = None
        self._receipt_send_after_id: Optional[str] = None
        self._receipt_send_active: bool = False
        self._receipt_forms_by_template: dict[str, dict[str, str]] = {}
        self._current_template_name: str = "default"

        self._bind_window_actions()

        self.state.preview.create_session(f"session_init_{uuid.uuid4().hex[:8]}")
        templates = self.receipt_builder.list_templates()
        self.window.set_receipt_templates(templates, default_template="default")
        self._restore_receipt_ui_state(templates)

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

    # ===== 模板 =====
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
        )

    def _restore_receipt_ui_state(self, templates: list[str]):
        saved = self.receipt_prefs_store.load()
        selected_template = saved.get("selected_template")
        forms_by_template = saved.get("forms_by_template", {})
        if not isinstance(forms_by_template, dict):
            forms_by_template = {}
        # 仅保留有效模板项且表单必须是字典
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
        self.window.append_log(f"[RECEIPT] 已切换模板：{template_name}\n")

    # ===== 发送 =====
    def send_step(self, step: SendStep):
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

        try:
            template_name = self.window.get_receipt_template() or "default"
            self._current_template_name = template_name
            form_data = self.window.get_receipt_form_data()
            self._receipt_forms_by_template[template_name] = form_data
            self._persist_receipt_ui_state()
            receipt = self.receipt_builder.build_receipt(template_name, form_data)
            plan = self.receipt_builder.encode_receipt(receipt)
            self._current_send_plan = plan
            self._receipt_send_active = True

            self.clear_history_frames()
            self.state.preview.create_session(f"session_{uuid.uuid4().hex[:8]}")

            self.window.append_log(
                f"[RECEIPT] 开始发送测试小票 template={template_name} name={receipt.name} 共 {plan.total} 步\n"
            )
            if receipt.description:
                self.window.append_log(f"[RECEIPT] 模板说明：{receipt.description}\n")
            self._send_receipt_step(0)
        except Exception as e:
            self._receipt_send_active = False
            self._current_send_plan = None
            messagebox.showerror("发送测试小票失败", str(e))

    def _send_receipt_step(self, idx: int):
        plan = self._current_send_plan
        if plan is None:
            self._receipt_send_active = False
            return

        if idx >= plan.total:
            self._receipt_send_active = False
            self._receipt_send_after_id = None
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

        next_delay = self._decide_next_step_delay(record.step)
        self._receipt_send_after_id = self.window.after(next_delay, lambda: self._send_receipt_step(idx + 1))

    @staticmethod
    def _decide_next_step_delay(step: SendStep) -> int:
        payload = step.payload
        if payload == b"\x1B\x40":
            return PrinterHostController.RESET_STEP_DELAY_MS
        if payload in (b"\x0A\x00", b"\x0C\x00"):
            return PrinterHostController.TRIGGER_STEP_DELAY_MS
        if payload and payload[:1] != b"\x1B":
            if b"\n" in payload or b"\r" in payload:
                return PrinterHostController.MULTILINE_TEXT_STEP_DELAY_MS
            return PrinterHostController.SINGLELINE_TEXT_STEP_DELAY_MS
        return PrinterHostController.NORMAL_STEP_DELAY_MS

    # ===== 预览 =====
    def rerender_views(self):
        self.state.preview.auto_crop = self.window.get_auto_crop()
        self.state.preview.zoom = self.window.get_zoom()

        if self.state.preview.current_frame:
            width, height, display_width, display_height = FrameRenderer.render_current_frame(
                self.window.preview_canvas,
                self.state.preview.current_frame,
                self.state.preview.zoom,
                self.state.preview.auto_crop,
            )
            frame = self.state.preview.current_frame
            self.window.preview_info_var.set(
                f"TYPE={frame['TYPE']} | MODE={frame['MODE']} | 原始 {width}x{height} | 显示 {display_width}x{display_height}"
            )
        else:
            self.window.preview_canvas.delete("all")
            self.window.preview_info_var.set("尚未收到打印帧")

        FrameRenderer.render_history_frames(
            self.window.history_canvas,
            self.state.preview.get_all_frames_in_order(),
            self.state.preview.zoom,
            self.state.preview.auto_crop,
        )

    def start_new_receipt(self):
        self.clear_history_frames()
        self.state.preview.create_session(f"session_{uuid.uuid4().hex[:8]}")
        self.window.append_log("[HOST] 开始新小票，已清空历史预览\n")

    def clear_history_frames(self):
        self.state.preview.current_frame = None
        self.state.preview.clear_sessions()
        self.window.preview_canvas.delete("all")
        self.window.preview_info_var.set("尚未收到打印帧")
        self.window.clear_history_preview()

    def _on_close(self):
        if self._receipt_send_after_id is not None:
            try:
                self.window.after_cancel(self._receipt_send_after_id)
            except Exception:
                pass
            self._receipt_send_after_id = None
        self._receipt_send_active = False
        try:
            self._save_current_template_form()
            self._persist_receipt_ui_state()
        except Exception:
            pass
        self.serial_manager.disconnect_all()
        self.window.destroy()
