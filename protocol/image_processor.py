
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from PIL import Image, ImageOps, ImageDraw
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
        sum_total = sum(i * c for i, c in enumerate(hist))
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
        if target_width <= 0 or target_width > cls.MAX_WIDTH:
            raise ValueError(f"目标宽度必须在 1~{cls.MAX_WIDTH} 之间")
        if max_height <= 0 or max_height > cls.MAX_HEIGHT:
            raise ValueError(f"最大高度必须在 1~{cls.MAX_HEIGHT} 之间")
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
        dst_w = max(1, min(target_width, int(round(src_w * scale))))
        dst_h = max(1, min(max_height, int(round(src_h * scale))))
        resized = gray.resize((dst_w, dst_h), Image.Resampling.LANCZOS)

        if dither:
            mono = resized.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
        else:
            if threshold is None:
                threshold = cls._calc_otsu_threshold(resized)
            mono = resized.point(lambda p: 255 if p >= threshold else 0, mode="1")

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

        return PreparedImage(width=canvas_width, height=dst_h, row_bytes=row_bytes, bitmap_bytes=bytes(packed))

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
        target_size = max(32, min(cls.MAX_QR_SIZE, int(target_size)))
        qr_border = max(0, min(8, int(qr_border)))
        ec_map = {
            "L": ERROR_CORRECT_L,
            "M": ERROR_CORRECT_M,
            "Q": ERROR_CORRECT_Q,
            "H": ERROR_CORRECT_H,
        }
        ec = ec_map.get(str(error_correction).strip().upper(), ERROR_CORRECT_M)

        qr = qrcode.QRCode(
            version=None,
            error_correction=ec,
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

    @classmethod
    def prepare_barcode_text(
        cls,
        barcode_text: str,
        *,
        target_width: int = 260,
        target_height: int = 72,
        canvas_width: Optional[int] = None,
        align: str = "center",
    ) -> PreparedImage:
        content = (barcode_text or "").strip()
        if not content:
            raise ValueError("条形码内容不能为空")
        for ch in content:
            code = ord(ch)
            if code < 32 or code > 126:
                raise ValueError("Code128-B 仅支持 ASCII 32~126")

        target_width = max(120, min(cls.MAX_WIDTH, int(target_width)))
        target_height = max(24, min(cls.MAX_HEIGHT, int(target_height)))

        # Code128-B patterns (module widths)
        patterns = [
            "212222","222122","222221","121223","121322","131222","122213","122312","132212","221213","221312",
            "231212","112232","122132","122231","113222","123122","123221","223211","221132","221231","213212",
            "223112","312131","311222","321122","321221","312212","322112","322211","212123","212321","232121",
            "111323","131123","131321","112313","132113","132311","211313","231113","231311","112133","112331",
            "132131","113123","113321","133121","313121","211331","231131","213113","213311","213131","311123",
            "311321","331121","312113","312311","332111","314111","221411","431111","111224","111422","121124",
            "121421","141122","141221","112214","112412","122114","122411","142112","142211","241211","221114",
            "413111","241112","134111","111242","121142","121241","114212","124112","124211","411212","421112",
            "421211","212141","214121","412121","111143","111341","131141","114113","114311","411113","411311",
            "113141","114131","311141","411131","211412","211214","211232","2331112"
        ]

        start_b = 104
        stop = 106

        values = [ord(ch) - 32 for ch in content]
        checksum = start_b
        for idx, val in enumerate(values, start=1):
            checksum += val * idx
        checksum %= 103

        code_sequence = [start_b] + values + [checksum, stop]

        modules = []
        for code in code_sequence:
            modules.append(patterns[code])

        quiet = 10
        total_modules = quiet + sum(sum(int(d) for d in p) for p in modules) + quiet
        module_px = max(1, target_width // total_modules)
        real_width = total_modules * module_px

        img = Image.new("RGB", (real_width, target_height), "white")
        draw = ImageDraw.Draw(img)

        x = quiet * module_px
        for pattern in modules:
            black = True
            for d in pattern:
                w = int(d) * module_px
                if black:
                    draw.rectangle([x, 0, x + w - 1, target_height - 1], fill="black")
                x += w
                black = not black

        return cls._prepare_from_pil(
            img,
            target_width=min(real_width, target_width),
            threshold=128,
            max_height=target_height,
            dither=False,
            canvas_width=canvas_width if canvas_width is not None else min(real_width, target_width),
            align=align,
        )
