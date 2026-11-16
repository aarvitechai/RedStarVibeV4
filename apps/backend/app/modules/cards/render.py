"""Card and share-image rendering with Pillow. Pure functions: spec + text (+ photo bytes) -> PNG bytes.

Fonts: Noto Sans + Noto Sans Devanagari (SIL OFL, installed in the image via fonts-noto-core).
"""

import io
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

_FONT_DIRS = (Path("/usr/share/fonts/truetype/noto"), Path("C:/Windows/Fonts"))
_FONT_FILES = {
    "bold": ("NotoSans-Bold.ttf", "NotoSansDevanagari-Bold.ttf", "arialbd.ttf"),
    "regular": ("NotoSans-Regular.ttf", "NotoSansDevanagari-Regular.ttf", "arial.ttf"),
}
WATERMARK = "Made with RedStarVibe"


def _has_devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in text)


@lru_cache(maxsize=64)
def _font(weight: str, size: int, devanagari: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = _FONT_FILES[weight]
    ordered = (names[1], names[0], names[2]) if devanagari else names
    for d in _FONT_DIRS:
        for n in ordered:
            p = d / n
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size=size)


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _gradient(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    w, h = size
    a, b = _hex(top), _hex(bottom)
    grad = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        grad.putpixel((0, y), (round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t), round(a[2] + (b[2] - a[2]) * t)))
    return grad.resize((w, h))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int, max_lines: int) -> list[str]:
    lines: list[str] = []
    for para in text.splitlines() or [""]:
        words, line = para.split(), ""
        for word in words:
            trial = f"{line} {word}".strip()
            if draw.textlength(trial, font=font) <= max_width:
                line = trial
            else:
                if line:
                    lines.append(line)
                line = word
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".") + "…"
    return lines


def _text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    center_x: int,
    y: int,
    size: int,
    weight: str,
    color: str,
    max_width: int,
    max_lines: int,
) -> int:
    font = _font(weight, size, _has_devanagari(text))
    for line in _wrap(draw, text, font, max_width, max_lines):
        w = draw.textlength(line, font=font)
        draw.text((center_x - w / 2, y), line, font=font, fill=_hex(color))
        y += int(size * 1.3)
    return y


def render_card(spec: dict[str, Any], fields: dict[str, str], photo: bytes | None, watermark: bool = True) -> bytes:
    w, h = int(spec.get("width", 1080)), int(spec.get("height", 1350))
    img = _gradient((w, h), spec["bg_top"], spec["bg_bottom"])
    draw = ImageDraw.Draw(img)
    accent = spec.get("accent", "#ffffff")
    # Decorative frame
    m = int(w * 0.04)
    draw.rounded_rectangle((m, m, w - m, h - m), radius=int(w * 0.04), outline=_hex(accent), width=max(4, w // 200))
    y = int(h * 0.1)
    if spec.get("emoji_line"):
        y = _text_block(
            draw,
            spec["emoji_line"],
            center_x=w // 2,
            y=y,
            size=int(w * 0.05),
            weight="bold",
            color=accent,
            max_width=w - 4 * m,
            max_lines=1,
        ) + int(h * 0.01)
    if photo:
        d = int(w * 0.42)
        with Image.open(io.BytesIO(photo)) as raw:
            pic = ImageOps.fit(ImageOps.exif_transpose(raw).convert("RGB"), (d, d))
        mask = Image.new("L", (d, d), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, d, d), fill=255)
        img.paste(pic, ((w - d) // 2, y), mask)
        draw.ellipse(((w - d) // 2 - 6, y - 6, (w + d) // 2 + 6, y + d + 6), outline=_hex(accent), width=8)
        y += d + int(h * 0.04)
    text_color = spec.get("text", "#ffffff")
    y = _text_block(
        draw,
        fields.get("title", spec.get("default_title", "")),
        center_x=w // 2,
        y=y,
        size=int(w * 0.085),
        weight="bold",
        color=text_color,
        max_width=w - 4 * m,
        max_lines=2,
    ) + int(h * 0.02)
    if fields.get("message"):
        y = _text_block(
            draw,
            fields["message"],
            center_x=w // 2,
            y=y,
            size=int(w * 0.045),
            weight="regular",
            color=text_color,
            max_width=w - 5 * m,
            max_lines=5,
        ) + int(h * 0.02)
    if fields.get("from"):
        _text_block(
            draw,
            f"— {fields['from']}",
            center_x=w // 2,
            y=y,
            size=int(w * 0.04),
            weight="bold",
            color=accent,
            max_width=w - 4 * m,
            max_lines=1,
        )
    if watermark:
        _text_block(
            draw,
            WATERMARK,
            center_x=w // 2,
            y=h - m - int(w * 0.06),
            size=int(w * 0.028),
            weight="regular",
            color=accent,
            max_width=w,
            max_lines=1,
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_share_image(title: str, subtitle: str, footer: str) -> bytes:
    """1200x630 Open Graph image for business pages (Blueprint 23.6)."""
    spec: dict[str, str] = {"bg_top": "#C8102E", "bg_bottom": "#9B0C23", "accent": "#FDF2F3", "text": "#FFFFFF"}
    img = _gradient((1200, 630), spec["bg_top"], spec["bg_bottom"])
    draw = ImageDraw.Draw(img)
    draw.text((60, 50), "★ RedStarVibe", font=_font("bold", 40, False), fill=_hex(spec["accent"]))
    y = _text_block(draw, title, center_x=600, y=190, size=76, weight="bold", color="#FFFFFF", max_width=1080, max_lines=2)
    _text_block(draw, subtitle, center_x=600, y=y + 20, size=38, weight="regular", color="#FDF2F3", max_width=1080, max_lines=2)
    _text_block(draw, footer, center_x=600, y=550, size=30, weight="regular", color="#FDF2F3", max_width=1100, max_lines=1)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
