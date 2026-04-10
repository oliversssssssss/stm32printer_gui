from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog
from tkinter.scrolledtext import ScrolledText
from typing import Callable, Optional


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("STM32U575 模拟打印上位机")
        self.geometry("1560x980")
        self.minsize(1320, 860)

        self.on_refresh_ports: Optional[Callable[[], None]] = None
        self.on_toggle_uart1: Optional[Callable[[], None]] = None
        self.on_toggle_uart2: Optional[Callable[[], None]] = None
        self.on_send_text: Optional[Callable[[], None]] = None
        self.on_send_hex: Optional[Callable[[], None]] = None
        self.on_send_init: Optional[Callable[[], None]] = None
        self.on_send_align_left: Optional[Callable[[], None]] = None
        self.on_send_align_center: Optional[Callable[[], None]] = None
        self.on_send_align_right: Optional[Callable[[], None]] = None
        self.on_send_trigger_lf: Optional[Callable[[], None]] = None
        self.on_send_trigger_ff: Optional[Callable[[], None]] = None
        self.on_send_line_spacing: Optional[Callable[[], None]] = None
        self.on_send_left_margin: Optional[Callable[[], None]] = None
        self.on_send_right_margin: Optional[Callable[[], None]] = None
        self.on_send_scale: Optional[Callable[[], None]] = None
        self.on_send_test_receipt: Optional[Callable[[], None]] = None
        self.on_receipt_template_changed: Optional[Callable[[], None]] = None
        self.on_receipt_form_changed: Optional[Callable[[], None]] = None
        self.on_send_strategy_mode_changed: Optional[Callable[[], None]] = None
        self.on_send_strategy_changed: Optional[Callable[[], None]] = None
        self.on_start_new_receipt: Optional[Callable[[], None]] = None
        self.on_clear_history_frames: Optional[Callable[[], None]] = None
        self.on_preview_option_changed: Optional[Callable[[], None]] = None
        self.on_browse_image: Optional[Callable[[], None]] = None
        self.on_send_image: Optional[Callable[[], None]] = None

        self._build_vars()
        self._build_ui()
        self._bind_receipt_form_watchers()

    def _build_vars(self):
        self.port1_var = tk.StringVar()
        self.port2_var = tk.StringVar()
        self.baud1_var = tk.StringVar(value="115200")
        self.baud2_var = tk.StringVar(value="115200")
        self.status_var = tk.StringVar(value="就绪")
        self.text_to_send = tk.StringVar()
        self.hex_to_send = tk.StringVar()
        self.append_crlf_var = tk.BooleanVar(value=False)
        self.line_spacing_var = tk.StringVar(value="8")
        self.left_margin_var = tk.StringVar(value="0")
        self.right_margin_var = tk.StringVar(value="0")
        self.scale_var = tk.StringVar(value="1")
        self.preview_info_var = tk.StringVar(value="尚未收到打印帧")
        self.auto_crop_var = tk.BooleanVar(value=False)
        self.zoom_var = tk.IntVar(value=4)

        self.image_path_var = tk.StringVar(value="")
        self.image_width_var = tk.StringVar(value="384")
        self.image_max_height_var = tk.StringVar(value="256")
        self.image_threshold_var = tk.StringVar(value="auto")
        self.image_dither_var = tk.BooleanVar(value=True)

        self.receipt_template_var = tk.StringVar(value="default")
        self.send_strategy_var = tk.StringVar(value="block_fewer_triggers_style")
        self.use_recommended_strategy_var = tk.BooleanVar(value=True)

        self.receipt_title_var = tk.StringVar(value="YINJIAN DRINKS")
        self.receipt_date_var = tk.StringVar(value="2026-03-20")
        self.receipt_no_var = tk.StringVar(value="1234567890")
        self.receipt_total_var = tk.StringVar(value="23.00")
        self.receipt_cash_var = tk.StringVar(value="50.00")
        self.receipt_change_var = tk.StringVar(value="27.00")

        self.receipt_logo_image_path_var = tk.StringVar(value="")
        self.receipt_footer_image_path_var = tk.StringVar(value="")
        self.receipt_image_width_var = tk.StringVar(value="220")
        self.receipt_image_max_height_var = tk.StringVar(value="96")
        self.receipt_image_threshold_var = tk.StringVar(value="auto")
        self.receipt_image_dither_var = tk.BooleanVar(value=True)

        self.receipt_qr_content_var = tk.StringVar(value="")
        self.receipt_qr_size_var = tk.StringVar(value="180")
        self.receipt_qr_border_var = tk.StringVar(value="2")
        self.receipt_qr_error_correction_var = tk.StringVar(value="M")

        self.receipt_barcode_content_var = tk.StringVar(value="")
        self.receipt_barcode_width_var = tk.StringVar(value="260")
        self.receipt_barcode_height_var = tk.StringVar(value="72")

        self.recommend_mode_var = tk.StringVar(value="推荐模式（自动）")
        self.recommend_system_var = tk.StringVar(value="-")
        self.recommend_effective_var = tk.StringVar(value="-")
        self.recommend_summary_var = tk.StringVar(value="尚未生成推荐说明")
        self.recommend_stats_var = tk.StringVar(value="-")

    def _build_ui(self):
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left_container = ttk.Frame(self)
        left_container.grid(row=0, column=0, sticky="ns")

        self.left_canvas = tk.Canvas(left_container, highlightthickness=0, width=600)
        left_scrollbar = ttk.Scrollbar(left_container, orient="vertical", command=self.left_canvas.yview)
        self.left_canvas.configure(yscrollcommand=left_scrollbar.set)
        self.left_canvas.grid(row=0, column=0, sticky="ns")
        left_scrollbar.grid(row=0, column=1, sticky="ns")

        left_container.rowconfigure(0, weight=1)
        left_container.columnconfigure(0, weight=1)

        self.left_inner = ttk.Frame(self.left_canvas, padding=10)
        self.left_window = self.left_canvas.create_window((0, 0), window=self.left_inner, anchor="nw")

        def _sync_left_scrollregion(event=None):
            self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))

        def _resize_left_inner(event):
            self.left_canvas.itemconfigure(self.left_window, width=event.width)

        self.left_inner.bind("<Configure>", _sync_left_scrollregion)
        self.left_canvas.bind("<Configure>", _resize_left_inner)
        self._bind_left_canvas_mousewheel(self.left_canvas, self.left_inner)

        right = ttk.Frame(self, padding=10)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=4)
        right.rowconfigure(2, weight=2)

        serial_frame = ttk.LabelFrame(self.left_inner, text="串口连接", padding=10)
        serial_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(serial_frame, text="UART1 端口").grid(row=0, column=0, sticky="w")
        ttk.Label(serial_frame, text="UART2 端口").grid(row=1, column=0, sticky="w")
        self.port1_combo = ttk.Combobox(serial_frame, textvariable=self.port1_var, width=18, state="readonly")
        self.port2_combo = ttk.Combobox(serial_frame, textvariable=self.port2_var, width=18, state="readonly")
        self.port1_combo.grid(row=0, column=1, padx=5, pady=2)
        self.port2_combo.grid(row=1, column=1, padx=5, pady=2)
        ttk.Label(serial_frame, text="波特率").grid(row=0, column=2, sticky="w")
        ttk.Label(serial_frame, text="波特率").grid(row=1, column=2, sticky="w")
        ttk.Entry(serial_frame, textvariable=self.baud1_var, width=10).grid(row=0, column=3, padx=5, pady=2)
        ttk.Entry(serial_frame, textvariable=self.baud2_var, width=10).grid(row=1, column=3, padx=5, pady=2)
        ttk.Button(serial_frame, text="刷新端口", command=self._safe_call(lambda: self.on_refresh_ports)).grid(row=0, column=4, rowspan=2, padx=8)
        self.btn_connect1 = ttk.Button(serial_frame, text="连接 UART1", command=self._safe_call(lambda: self.on_toggle_uart1))
        self.btn_connect2 = ttk.Button(serial_frame, text="连接 UART2", command=self._safe_call(lambda: self.on_toggle_uart2))
        self.btn_connect1.grid(row=2, column=1, pady=(8, 0), sticky="ew")
        self.btn_connect2.grid(row=2, column=3, pady=(8, 0), sticky="ew")
        ttk.Label(serial_frame, textvariable=self.status_var, foreground="#0066cc").grid(row=3, column=0, columnspan=5, sticky="w", pady=(8, 0))

        image_frame = ttk.LabelFrame(self.left_inner, text="图片打印（单图）", padding=10)
        image_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(image_frame, text="图片路径").grid(row=0, column=0, sticky="w")
        ttk.Entry(image_frame, textvariable=self.image_path_var, width=42).grid(row=0, column=1, columnspan=2, sticky="ew", padx=4, pady=2)
        ttk.Button(image_frame, text="选择图片", command=self._safe_call(lambda: self.on_browse_image)).grid(row=0, column=3, padx=(6, 0))
        ttk.Label(image_frame, text="目标宽度").grid(row=1, column=0, sticky="w")
        ttk.Entry(image_frame, textvariable=self.image_width_var, width=10).grid(row=1, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(image_frame, text="最大高度").grid(row=1, column=2, sticky="e")
        ttk.Entry(image_frame, textvariable=self.image_max_height_var, width=10).grid(row=1, column=3, sticky="w", padx=4, pady=2)
        ttk.Label(image_frame, text="阈值").grid(row=2, column=0, sticky="w")
        ttk.Entry(image_frame, textvariable=self.image_threshold_var, width=10).grid(row=2, column=1, sticky="w", padx=4, pady=2)
        ttk.Checkbutton(image_frame, text="抖动优化（推荐）", variable=self.image_dither_var).grid(row=2, column=2, columnspan=2, sticky="w")
        ttk.Button(image_frame, text="发送图片", command=self._safe_call(lambda: self.on_send_image)).grid(row=3, column=3, sticky="e", pady=(6, 0))
        ttk.Label(
            image_frame,
            text="支持普通彩色图片/灰度图/黑白图直接输入；阈值可填 auto。",
            foreground="#555555",
            wraplength=500,
            justify="left",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        image_frame.columnconfigure(1, weight=1)
        image_frame.columnconfigure(2, weight=1)

        send_text_frame = ttk.LabelFrame(self.left_inner, text="发送普通文本（UART1）", padding=10)
        send_text_frame.pack(fill="x", pady=(0, 10))
        ttk.Entry(send_text_frame, textvariable=self.text_to_send, width=40).grid(row=0, column=0, columnspan=3, sticky="ew")
        ttk.Checkbutton(send_text_frame, text="追加 CRLF", variable=self.append_crlf_var).grid(row=1, column=0, sticky="w", pady=5)
        ttk.Button(send_text_frame, text="发送文本", command=self._safe_call(lambda: self.on_send_text)).grid(row=1, column=2, sticky="e")
        ttk.Label(send_text_frame, text="说明：建议按“段”发送文本，再触发打印。").grid(row=2, column=0, columnspan=3, sticky="w")

        send_hex_frame = ttk.LabelFrame(self.left_inner, text="发送十六进制命令（UART1）", padding=10)
        send_hex_frame.pack(fill="x", pady=(0, 10))
        ttk.Entry(send_hex_frame, textvariable=self.hex_to_send, width=40).grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Button(send_hex_frame, text="发送 HEX", command=self._safe_call(lambda: self.on_send_hex)).grid(row=0, column=2, padx=(8, 0))
        ttk.Label(send_hex_frame, text="示例：0A 00 / 1B 40 / 1B 61 01 / 1B 33 08").grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))

        quick_frame = ttk.LabelFrame(self.left_inner, text="标准 / 近标准命令", padding=10)
        quick_frame.pack(fill="x", pady=(0, 10))
        ttk.Button(quick_frame, text="ESC @ (初始化)", command=self._safe_call(lambda: self.on_send_init)).grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(quick_frame, text="左对齐 ESC a 0", command=self._safe_call(lambda: self.on_send_align_left)).grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(quick_frame, text="居中 ESC a 1", command=self._safe_call(lambda: self.on_send_align_center)).grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(quick_frame, text="右对齐 ESC a 2", command=self._safe_call(lambda: self.on_send_align_right)).grid(row=1, column=2, sticky="ew", padx=2, pady=2)
        ttk.Button(quick_frame, text="打印 0A 00", command=self._safe_call(lambda: self.on_send_trigger_lf)).grid(row=2, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(quick_frame, text="打印 0C 00", command=self._safe_call(lambda: self.on_send_trigger_ff)).grid(row=2, column=1, sticky="ew", padx=2, pady=2)
        ttk.Label(quick_frame, text="说明：0A 00 / 0C 00 为当前项目触发命令。").grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

        receipt_frame = ttk.LabelFrame(self.left_inner, text="测试小票模板", padding=10)
        receipt_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(receipt_frame, text="模板").grid(row=0, column=0, sticky="w")
        self.receipt_template_combo = ttk.Combobox(receipt_frame, textvariable=self.receipt_template_var, state="readonly", width=20)
        self.receipt_template_combo.grid(row=0, column=1, padx=6, sticky="ew")
        self.receipt_template_combo.bind("<<ComboboxSelected>>", self._on_receipt_template_selected)

        self.use_recommended_strategy_check = ttk.Checkbutton(
            receipt_frame,
            text="使用模板推荐策略（默认）",
            variable=self.use_recommended_strategy_var,
            command=self._safe_call(lambda: self.on_send_strategy_mode_changed),
        )
        self.use_recommended_strategy_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        ttk.Label(receipt_frame, text="高级手动策略").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.send_strategy_combo = ttk.Combobox(receipt_frame, textvariable=self.send_strategy_var, state="readonly", width=20)
        self.send_strategy_combo.grid(row=2, column=1, padx=6, pady=(6, 0), sticky="ew")
        self.send_strategy_combo.bind("<<ComboboxSelected>>", self._on_send_strategy_selected)
        ttk.Button(receipt_frame, text="打印测试小票", command=self._safe_call(lambda: self.on_send_test_receipt)).grid(row=0, column=2, rowspan=3, sticky="nsew")
        ttk.Label(receipt_frame, text="普通模式自动选策略；关闭推荐后可手动切换。", foreground="#555555").grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        receipt_frame.columnconfigure(1, weight=1)

        recommend_frame = ttk.LabelFrame(self.left_inner, text="策略推荐说明", padding=10)
        recommend_frame.pack(fill="x", pady=(0, 10))
        recommend_frame.columnconfigure(1, weight=1)
        ttk.Label(recommend_frame, text="当前模式").grid(row=0, column=0, sticky="nw")
        ttk.Label(recommend_frame, textvariable=self.recommend_mode_var, foreground="#0066cc").grid(row=0, column=1, sticky="w")
        ttk.Label(recommend_frame, text="系统推荐").grid(row=1, column=0, sticky="nw", pady=(4, 0))
        ttk.Label(recommend_frame, textvariable=self.recommend_system_var).grid(row=1, column=1, sticky="w", pady=(4, 0))
        ttk.Label(recommend_frame, text="当前生效").grid(row=2, column=0, sticky="nw", pady=(4, 0))
        ttk.Label(recommend_frame, textvariable=self.recommend_effective_var).grid(row=2, column=1, sticky="w", pady=(4, 0))
        ttk.Label(recommend_frame, text="摘要").grid(row=3, column=0, sticky="nw", pady=(6, 0))
        ttk.Label(recommend_frame, textvariable=self.recommend_summary_var, wraplength=430, justify="left", foreground="#333333").grid(row=3, column=1, sticky="w", pady=(6, 0))
        ttk.Label(recommend_frame, text="依据").grid(row=4, column=0, sticky="nw", pady=(6, 0))
        self.recommend_reasons_text = ScrolledText(recommend_frame, height=5, width=52, font=("Consolas", 9))
        self.recommend_reasons_text.grid(row=4, column=1, sticky="ew", pady=(6, 0))
        self.recommend_reasons_text.configure(state="disabled")
        ttk.Label(recommend_frame, text="统计").grid(row=5, column=0, sticky="nw", pady=(6, 0))
        ttk.Label(recommend_frame, textvariable=self.recommend_stats_var, wraplength=430, justify="left", foreground="#666666").grid(row=5, column=1, sticky="w", pady=(6, 0))

        receipt_param_frame = ttk.LabelFrame(self.left_inner, text="测试票参数", padding=10)
        receipt_param_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(receipt_param_frame, text="标题").grid(row=0, column=0, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_title_var).grid(row=0, column=1, columnspan=3, sticky="ew", padx=4, pady=2)

        ttk.Label(receipt_param_frame, text="日期").grid(row=1, column=0, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_date_var, width=18).grid(row=1, column=1, sticky="ew", padx=4, pady=2)
        ttk.Label(receipt_param_frame, text="编号").grid(row=1, column=2, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_no_var, width=18).grid(row=1, column=3, sticky="ew", padx=4, pady=2)

        ttk.Label(receipt_param_frame, text="总价").grid(row=2, column=0, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_total_var, width=18).grid(row=2, column=1, sticky="ew", padx=4, pady=2)
        ttk.Label(receipt_param_frame, text="现金").grid(row=2, column=2, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_cash_var, width=18).grid(row=2, column=3, sticky="ew", padx=4, pady=2)

        ttk.Label(receipt_param_frame, text="找零").grid(row=3, column=0, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_change_var, width=18).grid(row=3, column=1, sticky="ew", padx=4, pady=2)

        ttk.Label(receipt_param_frame, text="顶部 Logo 图").grid(row=4, column=0, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_logo_image_path_var).grid(row=4, column=1, columnspan=2, sticky="ew", padx=4, pady=2)
        ttk.Button(receipt_param_frame, text="选择", command=lambda: self._browse_path_into_var(self.receipt_logo_image_path_var)).grid(row=4, column=3, sticky="ew", padx=4, pady=2)

        ttk.Label(receipt_param_frame, text="底部图片").grid(row=5, column=0, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_footer_image_path_var).grid(row=5, column=1, columnspan=2, sticky="ew", padx=4, pady=2)
        ttk.Button(receipt_param_frame, text="选择", command=lambda: self._browse_path_into_var(self.receipt_footer_image_path_var)).grid(row=5, column=3, sticky="ew", padx=4, pady=2)

        ttk.Label(receipt_param_frame, text="嵌图宽度").grid(row=6, column=0, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_image_width_var, width=18).grid(row=6, column=1, sticky="ew", padx=4, pady=2)
        ttk.Label(receipt_param_frame, text="嵌图最大高").grid(row=6, column=2, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_image_max_height_var, width=18).grid(row=6, column=3, sticky="ew", padx=4, pady=2)

        ttk.Label(receipt_param_frame, text="嵌图阈值").grid(row=7, column=0, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_image_threshold_var, width=18).grid(row=7, column=1, sticky="ew", padx=4, pady=2)
        ttk.Checkbutton(receipt_param_frame, text="嵌图抖动优化", variable=self.receipt_image_dither_var, command=self._notify_receipt_form_changed).grid(row=7, column=2, columnspan=2, sticky="w", padx=4, pady=2)

        ttk.Label(receipt_param_frame, text="内置二维码内容").grid(row=8, column=0, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_qr_content_var).grid(row=8, column=1, columnspan=3, sticky="ew", padx=4, pady=2)

        ttk.Label(receipt_param_frame, text="二维码尺寸").grid(row=9, column=0, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_qr_size_var, width=18).grid(row=9, column=1, sticky="ew", padx=4, pady=2)
        ttk.Label(receipt_param_frame, text="二维码边距").grid(row=9, column=2, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_qr_border_var, width=18).grid(row=9, column=3, sticky="ew", padx=4, pady=2)

        ttk.Label(receipt_param_frame, text="二维码纠错").grid(row=10, column=0, sticky="w")
        qr_ec_combo = ttk.Combobox(
            receipt_param_frame,
            textvariable=self.receipt_qr_error_correction_var,
            state="readonly",
            values=["L", "M", "Q", "H"],
            width=16,
        )
        qr_ec_combo.grid(row=10, column=1, sticky="ew", padx=4, pady=2)
        qr_ec_combo.bind("<<ComboboxSelected>>", lambda _e: self._notify_receipt_form_changed())

        ttk.Label(receipt_param_frame, text="内置条形码内容").grid(row=11, column=0, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_barcode_content_var).grid(row=11, column=1, columnspan=3, sticky="ew", padx=4, pady=2)

        ttk.Label(receipt_param_frame, text="条形码宽度").grid(row=12, column=0, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_barcode_width_var, width=18).grid(row=12, column=1, sticky="ew", padx=4, pady=2)
        ttk.Label(receipt_param_frame, text="条形码高度").grid(row=12, column=2, sticky="w")
        ttk.Entry(receipt_param_frame, textvariable=self.receipt_barcode_height_var, width=18).grid(row=12, column=3, sticky="ew", padx=4, pady=2)

        ttk.Label(receipt_param_frame, text="明细（多行）").grid(row=13, column=0, sticky="nw", pady=(6, 0))
        self.receipt_items_text = ScrolledText(receipt_param_frame, height=6, width=44, font=("Consolas", 10))
        self.receipt_items_text.grid(row=13, column=1, columnspan=3, sticky="ew", padx=4, pady=(6, 2))

        ttk.Label(receipt_param_frame, text="尾部文案（多行）").grid(row=14, column=0, sticky="nw", pady=(6, 0))
        self.receipt_footer_text = ScrolledText(receipt_param_frame, height=3, width=44, font=("Consolas", 10))
        self.receipt_footer_text.grid(row=14, column=1, columnspan=3, sticky="ew", padx=4, pady=(6, 2))

        ttk.Label(
            receipt_param_frame,
            text="提示：支持顶部 Logo、底部图片、二维码、条形码。若二维码/条形码内容不为空，会优先使用内置生成结果。",
            foreground="#555555",
            wraplength=500,
            justify="left",
        ).grid(row=15, column=0, columnspan=4, sticky="w", pady=(6, 0))

        for i in range(4):
            receipt_param_frame.columnconfigure(i, weight=1 if i else 0)

        param_frame = ttk.LabelFrame(self.left_inner, text="项目自定义参数命令", padding=10)
        param_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(param_frame, text="行距 n").grid(row=0, column=0, sticky="w")
        ttk.Entry(param_frame, textvariable=self.line_spacing_var, width=8).grid(row=0, column=1, sticky="w")
        ttk.Button(param_frame, text="发送 ESC 3 n", command=self._safe_call(lambda: self.on_send_line_spacing)).grid(row=0, column=2, padx=4)
        ttk.Label(param_frame, text="左边距 n").grid(row=1, column=0, sticky="w")
        ttk.Entry(param_frame, textvariable=self.left_margin_var, width=8).grid(row=1, column=1, sticky="w")
        ttk.Button(param_frame, text="发送 ESC L n", command=self._safe_call(lambda: self.on_send_left_margin)).grid(row=1, column=2, padx=4)
        ttk.Label(param_frame, text="右边距 n").grid(row=2, column=0, sticky="w")
        ttk.Entry(param_frame, textvariable=self.right_margin_var, width=8).grid(row=2, column=1, sticky="w")
        ttk.Button(param_frame, text="发送 ESC r n", command=self._safe_call(lambda: self.on_send_right_margin)).grid(row=2, column=2, padx=4)
        ttk.Label(param_frame, text="放大倍数").grid(row=3, column=0, sticky="w")
        ttk.Entry(param_frame, textvariable=self.scale_var, width=8).grid(row=3, column=1, sticky="w")
        ttk.Button(param_frame, text="发送 ESC E n", command=self._safe_call(lambda: self.on_send_scale)).grid(row=3, column=2, padx=4)
        ttk.Label(param_frame, text="说明：ESC L / ESC r / ESC E 为当前项目自定义语义。").grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))

        log_frame = ttk.LabelFrame(self.left_inner, text="UART1 日志", padding=8)
        log_frame.pack(fill="both", expand=True)
        self.log_text = ScrolledText(log_frame, width=60, height=22, font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")
        self._bind_text_mousewheel(self.log_text)

        info_frame = ttk.Frame(right)
        info_frame.grid(row=0, column=0, sticky="ew")
        info_frame.columnconfigure(0, weight=1)
        ttk.Checkbutton(
            info_frame,
            text="SETTINGS 自动裁边（会隐藏对齐效果，仅调试时使用）",
            variable=self.auto_crop_var,
            command=self._safe_call(lambda: self.on_preview_option_changed),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(info_frame, text="缩放").grid(row=0, column=1, padx=(20, 2))
        zoom_spin = ttk.Spinbox(info_frame, from_=1, to=20, textvariable=self.zoom_var, width=6, command=self._safe_call(lambda: self.on_preview_option_changed))
        zoom_spin.grid(row=0, column=2)
        ttk.Button(info_frame, text="开始新小票", command=self._safe_call(lambda: self.on_start_new_receipt)).grid(row=0, column=3, padx=(16, 4))
        ttk.Button(info_frame, text="清空历史预览", command=self._safe_call(lambda: self.on_clear_history_frames)).grid(row=0, column=4, padx=(4, 0))

        history_frame = ttk.LabelFrame(right, text="小票历史累计预览", padding=8)
        history_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 8))
        history_frame.rowconfigure(0, weight=1)
        history_frame.columnconfigure(0, weight=1)
        self.history_canvas = tk.Canvas(history_frame, bg="#fafafa", highlightthickness=1, highlightbackground="#d0d0d0")
        self.history_canvas.grid(row=0, column=0, sticky="nsew")
        history_scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.history_canvas.yview)
        history_scrollbar.grid(row=0, column=1, sticky="ns")
        self.history_canvas.configure(yscrollcommand=history_scrollbar.set)
        self._bind_text_mousewheel(self.history_canvas)

        raw_frame = ttk.LabelFrame(right, text="UART2 原始文本", padding=8)
        raw_frame.grid(row=2, column=0, sticky="nsew")
        raw_frame.rowconfigure(0, weight=1)
        raw_frame.columnconfigure(0, weight=1)
        self.raw_uart2_text = ScrolledText(raw_frame, width=90, height=10, font=("Consolas", 9))
        self.raw_uart2_text.grid(row=0, column=0, sticky="nsew")
        self.raw_uart2_text.configure(state="disabled")
        self._bind_text_mousewheel(self.raw_uart2_text)

    def _bind_receipt_form_watchers(self):
        watched_vars = [
            self.receipt_title_var,
            self.receipt_date_var,
            self.receipt_no_var,
            self.receipt_total_var,
            self.receipt_cash_var,
            self.receipt_change_var,
            self.receipt_logo_image_path_var,
            self.receipt_footer_image_path_var,
            self.receipt_image_width_var,
            self.receipt_image_max_height_var,
            self.receipt_image_threshold_var,
            self.receipt_qr_content_var,
            self.receipt_qr_size_var,
            self.receipt_qr_border_var,
            self.receipt_qr_error_correction_var,
            self.receipt_barcode_content_var,
            self.receipt_barcode_width_var,
            self.receipt_barcode_height_var,
        ]

        for var in watched_vars:
            var.trace_add("write", lambda *_: self._notify_receipt_form_changed())

        self.receipt_items_text.bind("<<Modified>>", self._on_multiline_text_modified)
        self.receipt_footer_text.bind("<<Modified>>", self._on_multiline_text_modified)

    def _on_multiline_text_modified(self, event):
        widget = event.widget
        if widget.edit_modified():
            widget.edit_modified(False)
            self._notify_receipt_form_changed()

    def _notify_receipt_form_changed(self):
        if self.on_receipt_form_changed:
            self.on_receipt_form_changed()

    def _on_receipt_template_selected(self, _event=None):
        if self.on_receipt_template_changed:
            self.on_receipt_template_changed()

    def _on_send_strategy_selected(self, _event=None):
        if self.on_send_strategy_changed:
            self.on_send_strategy_changed()

    def _browse_path_into_var(self, var: tk.StringVar):
        path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif"), ("所有文件", "*.*")],
        )
        if path:
            var.set(path)
            self._notify_receipt_form_changed()

    def _safe_call(self, cb_getter: Callable[[], Optional[Callable[[], None]]]):
        def _wrapped():
            cb = cb_getter()
            if cb:
                cb()
        return _wrapped

    def _bind_text_mousewheel(self, widget):
        def _on_mousewheel(event):
            widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        def _on_linux_up(event):
            widget.yview_scroll(-1, "units")
            return "break"

        def _on_linux_down(event):
            widget.yview_scroll(1, "units")
            return "break"

        widget.bind("<MouseWheel>", _on_mousewheel)
        widget.bind("<Button-4>", _on_linux_up)
        widget.bind("<Button-5>", _on_linux_down)

    def _bind_left_canvas_mousewheel(self, canvas, inner_widget):
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        def _on_linux_up(event):
            canvas.yview_scroll(-1, "units")
            return "break"

        def _on_linux_down(event):
            canvas.yview_scroll(1, "units")
            return "break"

        def _bind_all_handlers(_event=None):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>", _on_linux_up)
            canvas.bind_all("<Button-5>", _on_linux_down)

        def _unbind_all_handlers(_event=None):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind_all_handlers)
        inner_widget.bind("<Enter>", _bind_all_handlers)
        canvas.bind("<Leave>", _unbind_all_handlers)
        inner_widget.bind("<Leave>", _unbind_all_handlers)

    def set_ports(self, ports: list[str]):
        self.port1_combo["values"] = ports
        self.port2_combo["values"] = ports
        if ports:
            if not self.port1_var.get():
                self.port1_var.set(ports[0])
            if not self.port2_var.get():
                self.port2_var.set(ports[0])

    def set_receipt_templates(self, templates: list[str], default_template: str = "default"):
        self.receipt_template_combo["values"] = templates
        if default_template in templates:
            self.receipt_template_var.set(default_template)
        elif templates:
            self.receipt_template_var.set(templates[0])
        else:
            self.receipt_template_var.set("")

    def set_send_strategies(self, strategies: list[str], default_strategy: str = "block_step_stable"):
        self.send_strategy_combo["values"] = strategies
        if default_strategy in strategies:
            self.send_strategy_var.set(default_strategy)
        elif strategies:
            self.send_strategy_var.set(strategies[0])
        else:
            self.send_strategy_var.set("")

    def set_send_strategy(self, strategy_name: str):
        self.send_strategy_var.set(strategy_name)

    def set_send_strategy_enabled(self, enabled: bool):
        self.send_strategy_combo.config(state="readonly" if enabled else "disabled")

    def set_use_recommended_strategy(self, use_recommended: bool):
        self.use_recommended_strategy_var.set(use_recommended)

    def set_receipt_template(self, template_name: str):
        self.receipt_template_var.set(template_name)

    def set_receipt_form_defaults(self, data: dict[str, str]):
        self.receipt_title_var.set(data.get("title", ""))
        self.receipt_date_var.set(data.get("date", ""))
        self.receipt_no_var.set(data.get("receipt_no", ""))
        self.receipt_total_var.set(data.get("total", ""))
        self.receipt_cash_var.set(data.get("cash", ""))
        self.receipt_change_var.set(data.get("change", ""))

        self.receipt_logo_image_path_var.set(data.get("logo_image_path", ""))
        self.receipt_footer_image_path_var.set(data.get("footer_image_path", ""))
        self.receipt_image_width_var.set(data.get("image_width", "220"))
        self.receipt_image_max_height_var.set(data.get("image_max_height", "96"))
        self.receipt_image_threshold_var.set(data.get("image_threshold", "auto"))
        self.receipt_image_dither_var.set(str(data.get("image_dither", "1")).strip().lower() not in ("0", "false", "off", "no", ""))

        self.receipt_qr_content_var.set(data.get("qr_content", ""))
        self.receipt_qr_size_var.set(data.get("qr_size", "180"))
        self.receipt_qr_border_var.set(data.get("qr_border", "2"))
        self.receipt_qr_error_correction_var.set(data.get("qr_error_correction", "M"))

        self.receipt_barcode_content_var.set(data.get("barcode_content", ""))
        self.receipt_barcode_width_var.set(data.get("barcode_width", "260"))
        self.receipt_barcode_height_var.set(data.get("barcode_height", "72"))

        self.receipt_items_text.delete("1.0", "end")
        self.receipt_items_text.insert("1.0", data.get("items_text", ""))
        self.receipt_items_text.edit_modified(False)

        self.receipt_footer_text.delete("1.0", "end")
        self.receipt_footer_text.insert("1.0", data.get("footer", ""))
        self.receipt_footer_text.edit_modified(False)

    def set_strategy_recommendation_info(self, *, mode_text: str, recommended_strategy: str, effective_strategy: str, summary: str, reasons: list[str], stats_text: str):
        self.recommend_mode_var.set(mode_text)
        self.recommend_system_var.set(recommended_strategy)
        self.recommend_effective_var.set(effective_strategy)
        self.recommend_summary_var.set(summary)
        self.recommend_stats_var.set(stats_text)

        content = "\n".join(f"- {item}" for item in reasons) if reasons else "-"
        self.recommend_reasons_text.configure(state="normal")
        self.recommend_reasons_text.delete("1.0", "end")
        self.recommend_reasons_text.insert("1.0", content)
        self.recommend_reasons_text.configure(state="disabled")

    def set_status(self, text: str):
        self.status_var.set(text)

    def set_uart1_connected(self, connected: bool):
        self.btn_connect1.config(text="断开 UART1" if connected else "连接 UART1")

    def set_uart2_connected(self, connected: bool):
        self.btn_connect2.config(text="断开 UART2" if connected else "连接 UART2")

    def set_image_path(self, path: str):
        self.image_path_var.set(path)

    def append_log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def append_uart2_raw(self, text: str):
        self.raw_uart2_text.configure(state="normal")
        self.raw_uart2_text.insert("end", text)
        self.raw_uart2_text.see("end")
        self.raw_uart2_text.configure(state="disabled")

    def clear_history_preview(self):
        self.history_canvas.delete("all")

    def get_uart1_port(self) -> str:
        return self.port1_var.get().strip()

    def get_uart2_port(self) -> str:
        return self.port2_var.get().strip()

    def get_uart1_baud(self) -> int:
        return int(self.baud1_var.get())

    def get_uart2_baud(self) -> int:
        return int(self.baud2_var.get())

    def get_send_text(self) -> str:
        return self.text_to_send.get()

    def get_append_crlf(self) -> bool:
        return bool(self.append_crlf_var.get())

    def get_send_hex(self) -> str:
        return self.hex_to_send.get().strip()

    def get_line_spacing(self) -> str:
        return self.line_spacing_var.get()

    def get_left_margin(self) -> str:
        return self.left_margin_var.get()

    def get_right_margin(self) -> str:
        return self.right_margin_var.get()

    def get_scale(self) -> str:
        return self.scale_var.get()

    def get_image_path(self) -> str:
        return self.image_path_var.get().strip()

    def get_image_width(self) -> str:
        return self.image_width_var.get().strip()

    def get_image_max_height(self) -> str:
        return self.image_max_height_var.get().strip()

    def get_image_dither(self) -> bool:
        return bool(self.image_dither_var.get())

    def get_image_threshold(self) -> str:
        return self.image_threshold_var.get().strip()

    def get_receipt_template(self) -> str:
        return self.receipt_template_var.get().strip()

    def get_send_strategy(self) -> str:
        return self.send_strategy_var.get().strip()

    def get_use_recommended_strategy(self) -> bool:
        return bool(self.use_recommended_strategy_var.get())

    def get_receipt_form_data(self) -> dict[str, str]:
        return {
            "title": self.receipt_title_var.get().strip(),
            "date": self.receipt_date_var.get().strip(),
            "receipt_no": self.receipt_no_var.get().strip(),
            "items_text": self.receipt_items_text.get("1.0", "end").strip(),
            "total": self.receipt_total_var.get().strip(),
            "cash": self.receipt_cash_var.get().strip(),
            "change": self.receipt_change_var.get().strip(),
            "footer": self.receipt_footer_text.get("1.0", "end").strip(),
            "logo_image_path": self.receipt_logo_image_path_var.get().strip(),
            "footer_image_path": self.receipt_footer_image_path_var.get().strip(),
            "image_width": self.receipt_image_width_var.get().strip(),
            "image_max_height": self.receipt_image_max_height_var.get().strip(),
            "image_threshold": self.receipt_image_threshold_var.get().strip(),
            "image_dither": "1" if self.receipt_image_dither_var.get() else "0",
            "qr_content": self.receipt_qr_content_var.get().strip(),
            "qr_size": self.receipt_qr_size_var.get().strip(),
            "qr_border": self.receipt_qr_border_var.get().strip(),
            "qr_error_correction": self.receipt_qr_error_correction_var.get().strip(),
            "barcode_content": self.receipt_barcode_content_var.get().strip(),
            "barcode_width": self.receipt_barcode_width_var.get().strip(),
            "barcode_height": self.receipt_barcode_height_var.get().strip(),
        }

    def get_zoom(self) -> int:
        return int(self.zoom_var.get())

    def get_auto_crop(self) -> bool:
        return bool(self.auto_crop_var.get())