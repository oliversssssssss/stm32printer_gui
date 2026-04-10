from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from PIL import Image, ImageOps
import qrcode
from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H


@dataclass(frozen=True)
class PreparedImage:
    width: int
    height: int
    row_bytes: int
    bitmap_bytes: bytes

    @property
    def total_bytes(self) -> int:
        return len(self.bitmap_bytes)

    def iter_chunks(self, chunk_size: int) -> Iterator[bytes]:
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须 > 0")

        data = self.bitmap_bytes
        for start in range(0, len(data), chunk_size):
            yield data[start:start + chunk_size]


class ImageProcessor:
    MAX_WIDTH = 384
    MAX_HEIGHT = 256
    MAX_QR_SIZE = 256


    QR_ERROR_CORRECTION_MAP = {
        "L": ERROR_CORRECT_L,
        "M": ERROR_CORRECT_M,
        "Q": ERROR_CORRECT_Q,
        "H": ERROR_CORRECT_H,
    }

    @staticmethod
    def _composite_to_white(img: Image.Image) -> Image.Image:
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(bg, rgba).convert("RGB")

    @staticmethod
    def _calc_otsu_threshold(gray: Image.Image) -> int:
        hist = gray.histogram()
        total = sum(hist)
        if total <= 0:
            return 128

        sum_total = 0
        for i, count in enumerate(hist):
            sum_total += i * count

        sum_bg = 0
        weight_bg = 0
        var_max = -1.0
        threshold = 128

        for i, count in enumerate(hist):
            weight_bg += count
            if weight_bg == 0:
                continue
            weight_fg = total - weight_bg
            if weight_fg == 0:
                break

            sum_bg += i * count
            mean_bg = sum_bg / weight_bg
            mean_fg = (sum_total - sum_bg) / weight_fg
            var_between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
            if var_between > var_max:
                var_max = var_between
                threshold = i

        return int(threshold)

    @classmethod
    def _prepare_from_pil(
        cls,
        img: Image.Image,
        *,
        target_width: int,
        threshold: Optional[int],
        max_height: int,
        dither: bool,
        canvas_width: Optional[int],
        align: str,
    ) -> PreparedImage:
        target_width = int(target_width)
        max_height = int(max_height)

        if target_width <= 0:
            raise ValueError("目标宽度必须 > 0")
        if target_width > cls.MAX_WIDTH:
            raise ValueError(f"目标宽度不能超过 {cls.MAX_WIDTH}")
        if max_height <= 0:
            raise ValueError("最大高度必须 > 0")
        if max_height > cls.MAX_HEIGHT:
            raise ValueError(f"最大高度不能超过 {cls.MAX_HEIGHT}")
        if threshold is not None and (threshold < 0 or threshold > 255):
            raise ValueError("二值化阈值必须在 0~255 之间")

        if canvas_width is None:
            canvas_width = target_width
        canvas_width = int(canvas_width)
        if canvas_width <= 0 or canvas_width > cls.MAX_WIDTH:
            raise ValueError(f"画布宽度必须在 1~{cls.MAX_WIDTH} 之间")
        if align not in ("left", "center", "right"):
            raise ValueError("align 必须是 left / center / right")

        src = cls._composite_to_white(img)
        gray = ImageOps.autocontrast(src.convert("L"))
        src_w, src_h = gray.size
        if src_w <= 0 or src_h <= 0:
            raise ValueError("图片尺寸非法")

        scale = min(target_width / src_w, max_height / src_h)
        if scale <= 0:
            raise ValueError("无法计算有效缩放比例")

        dst_w = max(1, min(target_width, int(round(src_w * scale))))
        dst_h = max(1, min(max_height, int(round(src_h * scale))))
        resized = gray.resize((dst_w, dst_h), Image.Resampling.LANCZOS)

        if dither:
            mono = resized.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
        else:
            if threshold is None:
                threshold = cls._calc_otsu_threshold(resized)
            mono = resized.point(lambda p: 255 if p >= threshold else 0, mode="1")

        if canvas_width < dst_w:
            raise ValueError("画布宽度不能小于处理后的图片宽度")

        row_bytes = (canvas_width + 7) // 8
        packed = bytearray(row_bytes * dst_h)

        if align == "center":
            x_offset = (canvas_width - dst_w) // 2
        elif align == "right":
            x_offset = canvas_width - dst_w
        else:
            x_offset = 0

        for y in range(dst_h):
            for x in range(dst_w):
                pixel = mono.getpixel((x, y))
                bit = 1 if pixel == 0 else 0
                if bit:
                    out_x = x + x_offset
                    byte_index = y * row_bytes + (out_x // 8)
                    bit_index = 7 - (out_x % 8)
                    packed[byte_index] |= (1 << bit_index)

        return PreparedImage(
            width=canvas_width,
            height=dst_h,
            row_bytes=row_bytes,
            bitmap_bytes=bytes(packed),
        )

    @classmethod
    def prepare_image(
        cls,
        image_path: str,
        *,
        target_width: int = 384,
        threshold: Optional[int] = None,
        max_height: int = 256,
        dither: bool = True,
        canvas_width: Optional[int] = None,
        align: str = "left",
    ) -> PreparedImage:
        if not image_path:
            raise ValueError("图片路径不能为空")

        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"图片不存在：{image_path}")

        with Image.open(path) as src:
            return cls._prepare_from_pil(
                src,
                target_width=target_width,
                threshold=threshold,
                max_height=max_height,
                dither=dither,
                canvas_width=canvas_width,
                align=align,
            )

    @classmethod
    def parse_qr_error_correction(cls, value: str | None) -> str:
        level = str(value or "M").strip().upper() or "M"
        return level if level in cls.QR_ERROR_CORRECTION_MAP else "M"

    @classmethod
    def prepare_qr_text(
        cls,
        qr_text: str,
        *,
        target_size: int = 180,
        qr_border: int = 2,
        error_correction: str = "M",
        canvas_width: Optional[int] = None,
        align: str = "center",
    ) -> PreparedImage:
        content = (qr_text or "").strip()
        if not content:
            raise ValueError("二维码内容不能为空")

        target_size = int(target_size)
        qr_border = int(qr_border)
        if target_size <= 0:
            raise ValueError("二维码尺寸必须 > 0")
        target_size = min(target_size, cls.MAX_QR_SIZE)
        qr_border = max(0, min(8, qr_border))

        qr_level = cls.parse_qr_error_correction(error_correction)

        qr = qrcode.QRCode(
            version=None,
            error_correction=cls.QR_ERROR_CORRECTION_MAP[qr_level],
            box_size=10,
            border=qr_border,
        )
        qr.add_data(content)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        return cls._prepare_from_pil(
            img,
            target_width=target_size,
            threshold=128,
            max_height=target_size,
            dither=False,
            canvas_width=canvas_width if canvas_width is not None else target_size,
            align=align,
        )
