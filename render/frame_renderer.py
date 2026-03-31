from __future__ import annotations

import tkinter as tk


class FrameRenderer:
    @staticmethod
    def auto_crop(rows: list[str], width: int, height: int, padding: int = 2):
        ones = [(x, y) for y, row in enumerate(rows) for x, bit in enumerate(row) if bit == "1"]
        if not ones:
            return rows, width, height

        xs = [x for x, _ in ones]
        ys = [y for _, y in ones]

        min_x = max(0, min(xs) - padding)
        max_x = min(width - 1, max(xs) + padding)
        min_y = max(0, min(ys) - padding)
        max_y = min(height - 1, max(ys) + padding)

        cropped = []
        for y in range(min_y, max_y + 1):
            cropped.append(rows[y][min_x:max_x + 1])

        return cropped, (max_x - min_x + 1), (max_y - min_y + 1)

    @classmethod
    def render_current_frame(cls, canvas: tk.Canvas, frame: dict, zoom: int, auto_crop: bool) -> tuple[int, int, int, int]:
        mode = frame["MODE"]
        rows = frame["ROWS"]
        width = frame["WIDTH"]
        height = frame["HEIGHT"]

        display_rows, display_width, display_height = rows, width, height
        if mode == "SETTINGS" and auto_crop:
            display_rows, display_width, display_height = cls.auto_crop(rows, width, height, padding=2)

        zoom = max(1, int(zoom))
        canvas.delete("all")
        canvas_w = max(1, display_width * zoom)
        canvas_h = max(1, display_height * zoom)
        canvas.config(scrollregion=(0, 0, canvas_w, canvas_h))

        for y, row_bits in enumerate(display_rows):
            for x, bit in enumerate(row_bits):
                if bit == "1":
                    x0 = x * zoom
                    y0 = y * zoom
                    x1 = x0 + zoom
                    y1 = y0 + zoom
                    canvas.create_rectangle(x0, y0, x1, y1, outline="", fill="black")

        return width, height, display_width, display_height

    @classmethod
    def render_history_frames(cls, canvas: tk.Canvas, frames: list[dict], zoom: int, auto_crop: bool) -> None:
        canvas.delete("all")
        zoom = max(1, int(zoom))

        y_cursor = 10
        paper_margin = 12
        section_gap = 6
        max_width = 0

        for frame in frames:
            rows = frame["ROWS"]
            width = frame["WIDTH"]
            height = frame["HEIGHT"]
            mode = frame["MODE"]

            display_rows, display_width, display_height = rows, width, height
            if mode == "SETTINGS" and auto_crop:
                display_rows, display_width, display_height = cls.auto_crop(rows, width, height, padding=2)

            for y, row_bits in enumerate(display_rows):
                for x, bit in enumerate(row_bits):
                    if bit == "1":
                        x0 = paper_margin + x * zoom
                        y0 = y_cursor + y * zoom
                        x1 = x0 + zoom
                        y1 = y0 + zoom
                        canvas.create_rectangle(x0, y0, x1, y1, outline="", fill="black")

            frame_right = paper_margin + display_width * zoom
            frame_bottom = y_cursor + display_height * zoom

            y_cursor = frame_bottom + section_gap
            max_width = max(max_width, frame_right + paper_margin)

        canvas.config(scrollregion=(0, 0, max(max_width, 600), max(y_cursor, 400)))
